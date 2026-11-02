"""Runs untrusted commands inside a locked-down Docker container.

No network, non-root user, dropped capabilities, memory and pid limits,
read-only root filesystem, and a hard timeout. This is the only place in
the codebase that executes candidate C/C++ code.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import time

import docker
from docker.errors import DockerException, NotFound

from optiflow.core.config import get_settings

_client = None

# docker.from_env() assumes the default Windows npipe, but Docker Desktop's
# "desktop-linux" context (the modern default) listens on a different one.
_WINDOWS_FALLBACK_ENDPOINTS = [
    "npipe:////./pipe/dockerDesktopLinuxEngine",
    "npipe:////./pipe/docker_engine",
]


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        _client = docker.from_env()
        _client.ping()
        return _client
    except DockerException:
        pass
    for endpoint in _WINDOWS_FALLBACK_ENDPOINTS:
        try:
            candidate = docker.DockerClient(base_url=endpoint)
            candidate.ping()
            _client = candidate
            return _client
        except DockerException:
            continue
    raise DockerException(
        "Could not connect to the Docker daemon. Is Docker Desktop running?"
    )


def sandbox_user() -> str:
    """The (always non-root) user candidate code runs as.

    Candidate directories are created by this process with mode 0700. On
    a Linux host -- e.g. the deployed app container driving the host's
    Docker daemon -- the sandbox must run as *this* uid to read them;
    making them world-writable instead would let one candidate tamper with
    another's files. On Windows/macOS (Docker Desktop file sharing ignores
    Unix permissions), or if this process is root, use the image's
    dedicated `runner` user.
    """
    getuid = getattr(os, "getuid", None)
    if getuid is None or getuid() == 0:
        return "runner"
    return f"{getuid()}:{os.getgid()}"


def backend() -> str:
    """"docker" (default): every command runs in a locked-down container.
    "local": commands run as an unprivileged subprocess of this process, for
    hosts that give the app no Docker daemon (e.g. Render). See _run_local."""
    return os.getenv("SANDBOX_BACKEND", "docker").strip().lower()


def sandbox_status() -> dict:
    """Cheap readiness probe for /api/health (no container is started)."""
    if backend() == "local":
        tools = {t: shutil.which(t) is not None for t in ("gcc", "g++", "hrtime", "prlimit", "timeout")}
        return {"backend": "local", "ready": all(tools.values()), "tools": tools,
                "isolation": "unprivileged process with resource limits (no network or filesystem namespace)"}
    ready = False
    try:
        client = _get_client()
        ready = bool(client.images.list(name=get_settings().sandbox_image))
    except Exception:  # noqa: BLE001
        pass
    return {"backend": "docker", "ready": ready, "isolation": "locked-down Docker container"}


def run_in_sandbox(
    workdir: str,
    cmd: str,
    timeout_s: int = 30,
    mem: str = "512m",
    cpus: str = "1.0",
    cpuset: str | None = None,
    privileged_perf: bool = False,
    env: dict[str, str] | None = None,
) -> dict:
    """Run `cmd` inside the sandbox image with `workdir` mounted at /work.

    `privileged_perf` adds CAP_PERFMON (and nothing else) so perf can read
    hardware counters; it's only ever set for the trusted baseline program.
    """
    if backend() == "local":
        return _run_local(workdir, cmd, timeout_s, mem, env)
    settings = get_settings()
    cpuset = cpuset or settings.sandbox_cpuset
    client = _get_client()

    full_cmd = f"timeout {timeout_s}s bash -c {_shquote(cmd)}"

    container = client.containers.run(
        settings.sandbox_image,
        full_cmd,
        detach=True,
        volumes={workdir: {"bind": "/work", "mode": "rw"}},
        network_disabled=True,
        mem_limit=mem,
        memswap_limit=mem,
        nano_cpus=int(float(cpus) * 1e9),
        cpuset_cpus=cpuset,
        pids_limit=64,
        read_only=True,
        # In-memory scratch. `exec` because the benchmark harness copies
        # binaries + input here: reading from the host bind mount (Docker
        # Desktop file sharing) made wall time erratic for input-heavy programs.
        tmpfs={"/tmp": "size=160m,exec"},
        cap_drop=["ALL"],
        cap_add=(["PERFMON"] if privileged_perf else []),
        environment=env or {},
        security_opt=["no-new-privileges"],
        user=sandbox_user(),
    )

    t0 = time.perf_counter()
    try:
        result = container.wait(timeout=timeout_s + 10)
        exit_code = result.get("StatusCode", 1)
        timed_out = exit_code == 124
    except Exception:
        exit_code = 137
        timed_out = True
    wall_ms = (time.perf_counter() - t0) * 1000

    try:
        stdout = container.logs(stdout=True, stderr=False).decode(errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode(errors="replace")
    except NotFound:
        stdout, stderr = "", ""

    try:
        container.remove(force=True)
    except NotFound:
        pass

    return {
        "exit": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "wall_ms": wall_ms,
        "timed_out": timed_out,
    }


def _shquote(cmd: str) -> str:
    """Wrap a command string in single quotes for `bash -c`, escaping embedded quotes."""
    return "'" + cmd.replace("'", "'\\''") + "'"


# ------------------------------------------------------------ local backend

LOCAL_UID = int(os.getenv("SANDBOX_LOCAL_UID", "10002"))
MAX_LOCAL_OUTPUT = 16 * 1024 * 1024
# Nothing from the app's environment (API keys, tokens) reaches user code.
_LOCAL_ENV_KEEP = ("PATH", "LANG", "LC_ALL")


def _mem_bytes(mem: str) -> int:
    units = {"k": 1024, "m": 1024**2, "g": 1024**3}
    return int(float(mem[:-1]) * units[mem[-1].lower()]) if mem[-1].lower() in units else int(mem)


def _run_local(workdir: str, cmd: str, timeout_s: int, mem: str, env: dict[str, str] | None) -> dict:
    """Runs `cmd` the way the container would, without one.

    Weaker than Docker, and deliberately only for hosts with no Docker
    daemon. What it does enforce: the command runs as an unprivileged uid
    (when the app is root, so it cannot read the app's /proc/<pid>/environ
    or other candidates' 0700 build dirs), with a scrubbed environment, a
    private scratch dir standing in for the container's /tmp, and CPU /
    memory / process / file-size limits. What it cannot: block the
    network, or hide world-readable files. Protect POST /api/runs with
    OPTIFLOW_API_TOKEN when exposing this publicly.
    """
    scratch = tempfile.mkdtemp(prefix="sbx_")
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    popen_extra: dict = {}
    if is_root:
        os.chmod(scratch, 0o700)
        os.chown(scratch, LOCAL_UID, LOCAL_UID)
        os.chown(workdir, LOCAL_UID, LOCAL_UID)
        popen_extra = {"user": LOCAL_UID, "group": LOCAL_UID, "extra_groups": []}

    child_env = {k: os.environ[k] for k in _LOCAL_ENV_KEEP if k in os.environ}
    child_env.update({"HOME": scratch, "TMPDIR": scratch, **(env or {})})
    # The commands are written for the container layout (/tmp scratch, /work).
    local_cmd = cmd.replace("/tmp", scratch).replace("/work", workdir)
    limit = _mem_bytes(mem)
    # prlimit (util-linux) rather than preexec_fn, which is unsafe in a multi-threaded process.
    limits = ["prlimit", f"--cpu={timeout_s + 5}", f"--fsize={256 * 1024 * 1024}", "--nproc=512", "--core=0"]
    if "ASAN_OPTIONS" in child_env:
        # AddressSanitizer maps ~16 TB of shadow memory, which any RLIMIT_DATA / RLIMIT_AS
        # rejects ("ReserveShadowMemoryRange failed"). Its own RSS cap stands in for it.
        child_env["ASAN_OPTIONS"] += f":hard_rss_limit_mb={limit // (1024 * 1024)}"
    else:
        limits.append(f"--data={limit}")
    limits.append("--")

    t0 = time.perf_counter()
    try:
        proc = subprocess.Popen(
            [*limits, "timeout", f"{timeout_s}s", "bash", "-c", local_cmd],
            cwd=workdir, env=child_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, **popen_extra,
        )
        try:
            out, err = proc.communicate(timeout=timeout_s + 10)
            exit_code = proc.returncode
            timed_out = exit_code == 124
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            out, err = proc.communicate()
            exit_code, timed_out = 137, True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if is_root:  # the app (root) must still be able to read and delete it
            os.chown(workdir, 0, 0)
    return {
        "exit": exit_code,
        "stdout": out[:MAX_LOCAL_OUTPUT].decode(errors="replace"),
        "stderr": err[:MAX_LOCAL_OUTPUT].decode(errors="replace"),
        "wall_ms": (time.perf_counter() - t0) * 1000,
        "timed_out": timed_out,
    }


def _kill_group(proc: subprocess.Popen) -> None:
    import signal

    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
