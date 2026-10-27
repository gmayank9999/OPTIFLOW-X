from optiflow.tools.compile import ALLOWED_FLAGS, compile_and_register, sanitize_flags

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
    assert result.ok and result.candidate_id is not None and result.binary_path is not None


def test_compile_fails_cleanly_on_syntax_error():
    result = compile_and_register(BROKEN_C, lang="c", compiler="gcc", flags=["-O2"])
    assert not result.ok and result.candidate_id is None and "error" in result.stderr.lower()


def test_disallowed_flags_are_stripped_and_reported():
    result = compile_and_register(VALID_C, lang="c", compiler="gcc", flags=["-O2", "; rm -rf /"])
    assert result.ok
    assert "; rm -rf /" not in ALLOWED_FLAGS and "; rm -rf /" in result.dropped_flags


def test_fast_math_dropped_for_exact_compare_kept_for_tolerance():
    kept, dropped = sanitize_flags(["-Ofast", "-ffast-math", "-march=native"], allow_unsafe_math=False)
    assert kept == ["-O2", "-march=native"]  # -O2 inserted because -Ofast was dropped
    assert dropped == ["-Ofast", "-ffast-math"]
    kept, dropped = sanitize_flags(["-Ofast", "-ffast-math"], allow_unsafe_math=True)
    assert kept == ["-Ofast", "-ffast-math"] and dropped == []


def test_flags_are_deduplicated_and_an_opt_level_is_guaranteed():
    kept, _ = sanitize_flags(["-march=native", "-march=native", "-lm"])
    assert kept == ["-O2", "-march=native"]


def test_clang_builds_too():
    result = compile_and_register(VALID_C, lang="c", compiler="clang", flags=["-O3"])
    assert result.ok
