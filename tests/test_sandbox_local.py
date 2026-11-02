"""The local sandbox backend (SANDBOX_BACKEND=local), used where the app has
no Docker daemon. Needs a POSIX host with gcc, prlimit and timeout; the
Render image has all three, so these run there (and on Linux dev machines)."""

import shutil
import sys

import pytest

from optiflow.tools import custom, registry, sandbox
from optiflow.tools.compile import compile_and_register, get_candidate_dir

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not all(shutil.which(t) for t in ("gcc", "prlimit", "timeout")),
    reason="needs a POSIX host with gcc, prlimit and timeout",
)


@pytest.fixture(autouse=True)
def local_backend(monkeypatch):
    monkeypatch.setenv("SANDBOX_BACKEND", "local")


def test_status_reports_the_local_backend():
    status = sandbox.sandbox_status()
    assert status["backend"] == "local" and "tools" in status


def test_compile_and_run_a_program(tmp_path):
    build = compile_and_register('#include <stdio.h>\nint main(void){puts("hi");return 0;}\n', "c", "gcc", ["-O2"])
    assert build.ok, build.stderr
    result = sandbox.run_in_sandbox(get_candidate_dir(build.candidate_id), "cp prog /tmp/prog && /tmp/prog", timeout_s=10)
    assert result["exit"] == 0 and result["stdout"] == "hi\n"


def test_secrets_in_the_app_environment_do_not_reach_user_code(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    result = sandbox.run_in_sandbox(str(tmp_path), "env", timeout_s=10)
    assert "super-secret-value" not in result["stdout"] and "GEMINI_API_KEY" not in result["stdout"]


def test_sandbox_environment_is_still_passed_through(tmp_path):
    result = sandbox.run_in_sandbox(str(tmp_path), "echo $FOO", timeout_s=10, env={"FOO": "x=1"})
    assert result["stdout"].strip() == "x=1"


def test_a_runaway_program_is_stopped(tmp_path):
    result = sandbox.run_in_sandbox(str(tmp_path), "while :; do :; done", timeout_s=2)
    assert result["timed_out"]


def test_the_scratch_dir_stands_in_for_tmp_and_is_removed(tmp_path):
    result = sandbox.run_in_sandbox(str(tmp_path), "echo data > /tmp/x && cat /tmp/x && pwd", timeout_s=10)
    assert result["stdout"].splitlines()[0] == "data"
    assert result["stdout"].splitlines()[1] == str(tmp_path)
    assert not list(__import__("pathlib").Path("/tmp").glob("sbx_*"))


def test_user_programs_are_verified_end_to_end_without_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CUSTOM_ROOT", tmp_path / "custom")
    source = '''#include <stdio.h>
int main(void){int n;if(scanf("%d",&n)!=1)return 1;printf("%d",n*2);putchar(10);return 0;}
'''
    pid = custom.new_program_id()
    custom.materialize(pid, source, "c", ["21\n"])
    assert (tmp_path / "custom" / pid / "expected" / "out1.txt").read_text().strip() == "42"
    with pytest.raises(custom.CustomProgramError, match="different output"):
        custom.materialize(custom.new_program_id(), '''#include <stdio.h>
#include <stdlib.h>
int main(void){printf("%p",malloc(8));putchar(10);return 0;}
''', "c", [])


SANITIZER_ENV = {"ASAN_OPTIONS": "detect_leaks=0:abort_on_error=0:exitcode=86",
                 "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1:exitcode=86"}


def _run_sanitized(source, mem="512m"):
    build = compile_and_register(source, "c", "gcc", sanitize=True)
    assert build.ok, build.stderr
    return sandbox.run_in_sandbox(get_candidate_dir(build.candidate_id), "cp prog /tmp/prog && /tmp/prog",
                                  timeout_s=20, mem=mem, env=SANITIZER_ENV)


def test_sanitizer_builds_can_run_under_the_local_sandbox():
    # Regression: a RLIMIT_DATA / RLIMIT_AS cap makes ASan fail with
    # "ReserveShadowMemoryRange failed", rejecting every candidate.
    result = _run_sanitized("#include <stdio.h>\nint main(void){puts(\"ok\");return 0;}\n")
    assert result["exit"] == 0 and "ReserveShadowMemoryRange" not in result["stderr"]
    assert result["stdout"] == "ok\n"


def test_sanitizer_still_catches_a_real_memory_error():
    result = _run_sanitized("#include <stdlib.h>\nint main(void){int *a=malloc(4*sizeof(int));a[10]=1;free(a);return 0;}\n")
    assert result["exit"] == 86 and ("AddressSanitizer" in result["stderr"] or "runtime error" in result["stderr"])


def test_a_memory_hog_is_stopped_under_the_sanitizer():
    # Grows 50 MB every 50 ms; ASan's RSS watchdog (set from `mem`) must stop it well before 2 GB.
    hog = """#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(void) {
    for (int i = 0; i < 40; i++) {
        size_t n = 50u << 20; char *p = malloc(n);
        if (!p) return 3;
        memset(p, 1, n); usleep(50000);
    }
    return 0;
}
"""
    result = _run_sanitized(hog, mem="256m")
    assert result["exit"] != 0
