"""Runs untrusted commands inside a locked-down Docker container.

No network, non-root user, dropped capabilities, memory and pid limits,
read-only root filesystem, and a hard timeout. This is the only place in
the codebase that executes candidate C/C++ code.
"""

from __future__ import annotations

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


def run_in_sandbox(
    workdir: str,
    cmd: str,
    timeout_s: int = 30,
    mem: str = "512m",
    cpus: str = "1.0",
    cpuset: str | None = None,
    privileged_perf: bool = False,
) -> dict:
    """Run `cmd` inside the sandbox image with `workdir` mounted at /work."""
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
        tmpfs={"/tmp": "size=64m"},
        cap_drop=["ALL"],
        cap_add=(["PERFMON", "SYS_ADMIN"] if privileged_perf else []),
        security_opt=["no-new-privileges"],
        user="runner",
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
