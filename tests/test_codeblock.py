from optiflow.agents.codeblock import extract_code, unified_diff

RESPONSE = """\
Here is the optimized version:

```c
#include <stdio.h>
int main(void) { printf("hi\\n"); return 0; }
```
"""


def test_extract_code_pulls_fenced_block():
    code = extract_code(RESPONSE)
    assert code.startswith("#include <stdio.h>")
    assert "```" not in code


def test_extract_code_falls_back_to_raw_text_without_fence():
    raw = "int main(void) { return 0; }"
    assert extract_code(raw).strip() == raw


def test_unified_diff_shows_changes():
    original = "int main(void) {\n    return 0;\n}\n"
    updated = "int main(void) {\n    return 1;\n}\n"
    diff = unified_diff(original, updated)
    assert "-    return 0;" in diff
    assert "+    return 1;" in diff
