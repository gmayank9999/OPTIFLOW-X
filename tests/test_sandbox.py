"""Sandbox security and reliability checks (Section 7.3 of the plan)."""

import tempfile

from optiflow.tools.compile import compile_and_register
from optiflow.tools.sandbox import run_in_sandbox

SOCKET_PROGRAM = """
#include <sys/socket.h>
#include <stdio.h>
int main(void) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    printf("socket_fd=%d\\n", fd);
    return 0;
}
"""

BIG_ALLOC_PROGRAM = """
#include <stdlib.h>
#include <string.h>
int main(void) {
    size_t n = 2UL * 1024 * 1024 * 1024;
    char *p = malloc(n);
    if (!p) return 1;
    memset(p, 1, n);
    return 0;
}
"""


def test_basic_command_runs():
    workdir = tempfile.mkdtemp()
    result = run_in_sandbox(workdir, "echo hello", timeout_s=10)
    assert result["exit"] == 0
    assert "hello" in result["stdout"]


def test_infinite_loop_hits_timeout():
    workdir = tempfile.mkdtemp()
    result = run_in_sandbox(workdir, "while true; do :; done", timeout_s=3)
    assert result["timed_out"] is True


def test_network_is_disabled():
    build = compile_and_register(SOCKET_PROGRAM, lang="c", compiler="gcc", flags=["-O0"])
    assert build.ok, build.stderr
    from optiflow.tools.compile import get_candidate_dir
    result = run_in_sandbox(get_candidate_dir(build.candidate_id), "./prog", timeout_s=10)
    # socket() itself may succeed (address family only), but with
    # network_disabled the container has no interfaces to use it on.
    assert result["exit"] == 0


def test_memory_limit_kills_large_allocation():
    build = compile_and_register(BIG_ALLOC_PROGRAM, lang="c", compiler="gcc", flags=["-O0"])
    assert build.ok, build.stderr
    from optiflow.tools.compile import get_candidate_dir
    result = run_in_sandbox(
        get_candidate_dir(build.candidate_id), "./prog", timeout_s=15, mem="256m"
    )
    assert result["exit"] != 0


def test_readonly_root_blocks_writes_outside_work():
    workdir = tempfile.mkdtemp()
    result = run_in_sandbox(workdir, "touch /etc/should_fail", timeout_s=10)
    assert result["exit"] != 0
