"""Static analysis of C/C++ source with tree-sitter.

Extracts functions and loops, and derives the static features the
Strategist and XGBoost predictor reason over. Deterministic, no LLM
involved.
"""

from __future__ import annotations

import re

import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser

_LANGS = {"c": Language(tsc.language()), "cpp": Language(tscpp.language())}
_LOOP_TYPES = {"for_statement", "while_statement", "do_statement"}
_ARRAY_SUBSCRIPT_RE = re.compile(r"(\w+)\s*\[")


def analyze(source: str, lang: str = "c") -> dict:
    parser = Parser(_LANGS[lang])
    tree = parser.parse(source.encode())

    loops: list[dict] = []
    functions: list[str] = []

    def walk(node: Node, depth: int, current_fn: str | None) -> None:
        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            if declarator is not None:
                name = declarator.text.decode().split("(")[0].strip().split()[-1]
                functions.append(name)
                current_fn = name

        if node.type in _LOOP_TYPES:
            depth += 1
            body = node.text.decode()
            loop_vars = _loop_vars(node)
            loops.append({
                "function": current_fn,
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "depth": depth,
                "iter_vars": loop_vars,
                "array_accesses": body.count("["),
                "has_call": bool(re.search(r"\w+\s*\(", body[body.find(")") + 1:])),
            })

        for child in node.children:
            walk(child, depth, current_fn)

    walk(tree.root_node, 0, None)

    return {
        "functions": functions,
        "loops": loops,
        "features": static_features(source, loops),
    }


def _loop_vars(node: Node) -> list[str]:
    if node.type != "for_statement":
        return []
    init = node.child_by_field_name("initializer")
    if init is None:
        return []
    return re.findall(r"\b([a-zA-Z_]\w*)\s*=", init.text.decode())


def static_features(source: str, loops: list[dict]) -> dict[str, float]:
    depths = [loop["depth"] for loop in loops]
    max_loop_depth = max(depths) if depths else 0
    n_nested_loops = sum(1 for d in depths if d > 1)

    return {
        "max_loop_depth": float(max_loop_depth),
        "n_loops": float(len(loops)),
        "n_nested_loops": float(n_nested_loops),
        "n_array_accesses": float(sum(loop["array_accesses"] for loop in loops)),
        "stride_mismatch": float(_stride_mismatch(source, loops)),
        "has_recursion": float(_has_recursion(source)),
        "n_mallocs_in_loop": float(source.count("malloc") + source.count("new ")),
        "uses_float": float("double" in source or "float" in source),
        "has_struct_array": float(bool(re.search(r"struct\s+\w+\s*\*?\s*\w+\s*\[", source))),
        "strlen_in_loop_cond": float("strlen(" in source),
        "loc": float(len(source.splitlines())),
    }


def _stride_mismatch(source: str, loops: list[dict]) -> bool:
    """True when the innermost loop variable indexes a non-trailing dimension.

    Heuristic: for subscripts like X[a*n+b], flag it when the innermost
    loop's iteration variable appears in the `a` position rather than `b`.
    """
    innermost = [loop for loop in loops if loop["depth"] == max((l["depth"] for l in loops), default=0)]
    for loop in innermost:
        for var in loop["iter_vars"]:
            for match in re.finditer(rf"\w+\[\s*(\w+)\s*\*\s*\w+\s*\+\s*(\w+)\s*\]", source):
                a, b = match.group(1), match.group(2)
                if a == var and b != var:
                    return True
    return False


def _has_recursion(source: str) -> bool:
    functions = re.findall(r"\b(\w+)\s*\([^;{]*\)\s*\{", source)
    for name in set(functions):
        body_calls = re.findall(rf"\b{re.escape(name)}\s*\(", source)
        if len(body_calls) > 1:
            return True
    return False
