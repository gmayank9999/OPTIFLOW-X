from optiflow.agents.safety import check

CLEAN_SOURCE = """
#include <stdio.h>
int main(void) { printf("hi\\n"); return 0; }
"""


def test_clean_source_passes():
    ok, reason = check(CLEAN_SOURCE)
    assert ok
    assert reason is None


def test_rejects_system_call():
    ok, reason = check('#include <stdlib.h>\nint main(){ system("rm -rf /"); return 0; }')
    assert not ok
    assert "system" in reason


def test_rejects_socket():
    ok, reason = check("#include <sys/socket.h>\nint f(){ return socket(2,1,0); }")
    assert not ok
    assert "socket" in reason


def test_rejects_fork():
    ok, reason = check("#include <unistd.h>\nint f(){ return fork(); }")
    assert not ok


def test_rejects_inline_asm():
    ok, reason = check('int f(){ asm("nop"); return 0; }')
    assert not ok


def test_rejects_fopen_outside_workdir():
    ok, reason = check('#include <stdio.h>\nint f(){ FILE *f = fopen("/etc/passwd", "r"); return 0; }')
    assert not ok


def test_allows_fopen_relative_path():
    ok, reason = check('#include <stdio.h>\nint f(){ FILE *f = fopen("scratch.tmp", "w"); return 0; }')
    assert ok
