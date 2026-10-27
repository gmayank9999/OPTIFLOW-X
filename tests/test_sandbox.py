"""Sandbox security and reliability checks (Section 7.3 of the plan)."""

import tempfile

from optiflow.tools.compile import compile_and_register, get_candidate_dir
from optiflow.tools.sandbox import run_in_sandbox

SOCKET_PROGRAM = r"""
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <sys/socket.h>
int main(void) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(53);
    inet_pton(AF_INET, "1.1.1.1", &addr.sin_addr);
    int rc = fd < 0 ? -1 : connect(fd, (struct sockaddr *)&addr, sizeof addr);
    printf(rc == 0 ? "connected\n" : "connect_failed\n");
    return 0;
}
"""

BIG_ALLOC_PROGRAM = r"""
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
    result = run_in_sandbox(tempfile.mkdtemp(), "echo hello", timeout_s=10)
    assert result["exit"] == 0 and "hello" in result["stdout"]


def test_infinite_loop_hits_timeout():
    result = run_in_sandbox(tempfile.mkdtemp(), "while true; do :; done", timeout_s=3)
    assert result["timed_out"] is True


def test_outbound_network_connections_fail():
    build = compile_and_register(SOCKET_PROGRAM, lang="c", compiler="gcc", flags=["-O0"])
    assert build.ok, build.stderr
    result = run_in_sandbox(get_candidate_dir(build.candidate_id), "./prog", timeout_s=15)
    # socket() may succeed, but with network_disabled the container only
    # has loopback: an outbound connect must fail.
    assert "connect_failed" in result["stdout"], result


def test_memory_limit_kills_large_allocation():
    build = compile_and_register(BIG_ALLOC_PROGRAM, lang="c", compiler="gcc", flags=["-O0"])
    assert build.ok, build.stderr
    result = run_in_sandbox(get_candidate_dir(build.candidate_id), "./prog", timeout_s=15, mem="256m")
    assert result["exit"] != 0


def test_readonly_root_blocks_writes_outside_work():
    result = run_in_sandbox(tempfile.mkdtemp(), "touch /etc/should_fail", timeout_s=10)
    assert result["exit"] != 0


def test_runs_as_non_root_without_capabilities():
    result = run_in_sandbox(tempfile.mkdtemp(), "id -u; grep CapEff /proc/self/status", timeout_s=10)
    uid, cap = result["stdout"].split("\n")[:2]
    assert uid.strip() != "0"
    assert cap.split()[-1] == "0000000000000000"


def test_sandbox_user_is_never_root(monkeypatch):
    import optiflow.tools.sandbox as sb

    monkeypatch.setattr(sb.os, "getuid", lambda: 10001, raising=False)
    monkeypatch.setattr(sb.os, "getgid", lambda: 10001, raising=False)
    assert sb.sandbox_user() == "10001:10001"   # same uid as the 0700 candidate dirs
    monkeypatch.setattr(sb.os, "getuid", lambda: 0, raising=False)
    assert sb.sandbox_user() == "runner"        # never run candidates as root
