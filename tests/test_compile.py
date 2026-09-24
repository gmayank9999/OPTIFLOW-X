from optiflow.tools.compile import ALLOWED_FLAGS, compile_and_register

VALID_C = """
#include <stdio.h>
int main(void) { printf("ok\\n"); return 0; }
"""

BROKEN_C = """
#include <stdio.h>
int main(void) { printf("missing paren"; return 0; }
"""


def test_compile_succeeds_on_valid_program():
    result = compile_and_register(VALID_C, lang="c", compiler="gcc", flags=["-O2"])
    assert result.ok
    assert result.candidate_id is not None
    assert result.binary_path is not None


def test_compile_fails_cleanly_on_syntax_error():
    result = compile_and_register(BROKEN_C, lang="c", compiler="gcc", flags=["-O2"])
    assert not result.ok
    assert result.candidate_id is None
    assert "error" in result.stderr.lower()


def test_disallowed_flags_are_stripped():
    result = compile_and_register(
        VALID_C, lang="c", compiler="gcc", flags=["-O2", "; rm -rf /"]
    )
    assert result.ok
    assert "; rm -rf /" not in ALLOWED_FLAGS
