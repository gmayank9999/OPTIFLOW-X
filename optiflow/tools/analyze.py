"""Static analysis of C/C++ source with tree-sitter.

Extracts functions and loops, and derives the static features the
Strategist and XGBoost predictor reason over. Every feature is computed
from the syntax tree, scoped to where it actually matters (a malloc only
counts if it sits inside a loop, strlen only if it sits in a loop
condition), so a feature means exactly what its name says. Deterministic,
no LLM involved.
"""

from __future__ import annotations

import re

import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser

_LANGS = {"c": Language(tsc.language()), "cpp": Language(tscpp.language())}
_LOOP_TYPES = {"for_statement", "while_statement", "do_statement", "for_range_loop"}
_ALLOC_FUNCS = {"malloc", "calloc", "realloc"}
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


def analyze(source: str, lang: str = "c") -> dict:
    parser = Parser(_LANGS[lang])
    tree = parser.parse(source.encode())
    root = tree.root_node

    loops: list[dict] = []
    functions: list[dict] = []

    def walk(node: Node, depth: int, current_fn: str | None) -> None:
        if node.type == "function_definition":
            name = _function_name(node)
            if name:
                functions.append({
                    "name": name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                })
                current_fn = name

        if node.type in _LOOP_TYPES:
            depth += 1
            body = node.child_by_field_name("body")
            loops.append({
                "function": current_fn,
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "depth": depth,
                "iter_vars": _loop_vars(node),
                "array_accesses": _count(body, "subscript_expression") if body else 0,
                "has_call": bool(body and _first(body, "call_expression")),
                "innermost": body is not None and not _contains(body, _LOOP_TYPES),
                "_node": node,
            })

        for child in node.children:
            walk(child, depth, current_fn)

    walk(root, 0, None)

    features = static_features(source, root, loops, functions)
    for loop in loops:
        loop.pop("_node")

    return {
        "functions": [f["name"] for f in functions],
        "function_spans": functions,
        "loops": loops,
        "features": features,
    }


def static_features(source: str, root: Node, loops: list[dict], functions: list[dict]) -> dict[str, float]:
    depths = [loop["depth"] for loop in loops]
    return {
        "max_loop_depth": float(max(depths, default=0)),
        "n_loops": float(len(loops)),
        "n_nested_loops": float(sum(1 for d in depths if d > 1)),
        "n_array_accesses": float(sum(loop["array_accesses"] for loop in loops)),
        "stride_mismatch": float(_stride_mismatch(loops)),
        "has_recursion": float(_has_recursion(root)),
        "n_mallocs_in_loop": float(_mallocs_in_loops(root)),
        "uses_float": float(_uses_float(root)),
        "has_struct_array": float(_struct_array_in_loop(loops)),
        "strlen_in_loop_cond": float(_strlen_in_loop_condition(loops)),
        "pointer_chasing": float(_pointer_chasing(loops)),
        "loc": float(len(source.splitlines())),
    }


# --- tree helpers -----------------------------------------------------------

def _iter(node: Node):
    yield node
    for child in node.children:
        yield from _iter(child)


def _count(node: Node, node_type: str) -> int:
    return sum(1 for n in _iter(node) if n.type == node_type)


def _first(node: Node, *node_types: str) -> Node | None:
    for n in _iter(node):
        if n is not node and n.type in node_types:
            return n
    return None


def _contains(node: Node, node_types: set[str]) -> bool:
    """Whether `node` itself or any descendant has one of `node_types`.
    (An unbraced `for (...) for (...)` body *is* the inner loop node.)"""
    return any(n.type in node_types for n in _iter(node))


def _text(node: Node | None) -> str:
    return node.text.decode(errors="replace") if node is not None else ""


def _function_name(fn: Node) -> str | None:
    declarator = fn.child_by_field_name("declarator")
    while declarator is not None and declarator.type != "function_declarator":
        declarator = declarator.child_by_field_name("declarator")
    if declarator is None:
        return None
    name_node = declarator.child_by_field_name("declarator")
    return _text(name_node).split("::")[-1] or None


def _call_name(call: Node) -> str:
    return _text(call.child_by_field_name("function")).split("::")[-1]


def _loop_vars(node: Node) -> list[str]:
    if node.type == "for_statement":
        init = node.child_by_field_name("initializer")
        if init is not None:
            names = re.findall(r"\b([a-zA-Z_]\w*)\s*=(?!=)", _text(init))
            if names:
                return names
        # `for (; i < n; i++)`: fall back to whatever the update step mutates.
        update = node.child_by_field_name("update")
        return re.findall(r"\b([a-zA-Z_]\w*)\s*(?:\+\+|--|\+=|-=)", _text(update))
    if node.type in {"while_statement", "do_statement"}:
        cond = node.child_by_field_name("condition")
        body = node.child_by_field_name("body")
        cond_vars = set(_IDENT_RE.findall(_text(cond)))
        mutated = set(re.findall(r"\b([a-zA-Z_]\w*)\s*(?:\+\+|--|\+=|-=|=(?!=))", _text(body)))
        return sorted(cond_vars & mutated)
    return []


# --- individual features ----------------------------------------------------

def _stride_mismatch(loops: list[dict]) -> bool:
    """True when an innermost loop's iteration variable indexes a
    non-trailing dimension of some array it touches.

    Handles both `X[a][b]` (v appears in `a`, not in `b`) and flattened
    `X[a*n + b]` (v appears only in a multiplied term).
    """
    for loop in loops:
        # Only nested innermost loops: a 1-D init loop touching one column
        # is strided too, but it's never where the time goes.
        if not loop["innermost"] or loop["depth"] < 2 or not loop["iter_vars"]:
            continue
        body = loop["_node"].child_by_field_name("body")
        if body is None:
            continue
        for var in loop["iter_vars"]:
            for sub in _iter(body):
                if sub.type != "subscript_expression":
                    continue
                if sub.parent is not None and sub.parent.type == "subscript_expression" \
                        and sub.parent.child_by_field_name("argument") == sub:
                    continue  # handled when we visit the outermost subscript
                if _subscript_mismatch(sub, var):
                    return True
    return False


def _subscript_indices(sub: Node) -> list[str]:
    """Indices of a (possibly multi-dimensional) subscript, outermost dim first."""
    indices = []
    node = sub
    while node is not None and node.type == "subscript_expression":
        idx = node.child_by_field_name("index") or node.child_by_field_name("indices")
        indices.append(_text(idx).strip("[] "))
        node = node.child_by_field_name("argument")
    return list(reversed(indices))


def _uses(expr: str, var: str) -> bool:
    return var in _IDENT_RE.findall(expr)


def _subscript_mismatch(sub: Node, var: str) -> bool:
    indices = _subscript_indices(sub)
    if len(indices) >= 2:
        return any(_uses(i, var) for i in indices[:-1]) and not _uses(indices[-1], var)
    if len(indices) == 1:
        terms = _top_level_terms(indices[0])
        if len(terms) < 2:
            return False
        scaled = [t for t in terms if "*" in t and _uses(t, var)]
        unit = [t for t in terms if "*" not in t and _uses(t, var)]
        return bool(scaled) and not unit
    return False


def _top_level_terms(expr: str) -> list[str]:
    terms, depth, current = [], 0, ""
    for ch in expr:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch in "+-" and depth == 0 and current.strip():
            terms.append(current)
            current = ""
            continue
        current += ch
    if current.strip():
        terms.append(current)
    return [t.strip() for t in terms]


def _has_recursion(root: Node) -> bool:
    for fn in _iter(root):
        if fn.type != "function_definition":
            continue
        name = _function_name(fn)
        body = fn.child_by_field_name("body")
        if not name or body is None:
            continue
        if any(n.type == "call_expression" and _call_name(n) == name for n in _iter(body)):
            return True
    return False


def _inside_loop(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type in _LOOP_TYPES:
            return True
        if parent.type == "function_definition":
            return False
        parent = parent.parent
    return False


def _mallocs_in_loops(root: Node) -> int:
    count = 0
    for n in _iter(root):
        is_alloc = (n.type == "call_expression" and _call_name(n) in _ALLOC_FUNCS) or n.type == "new_expression"
        if is_alloc and _inside_loop(n):
            count += 1
    return count


def _uses_float(root: Node) -> bool:
    return any(n.type == "primitive_type" and _text(n) in {"float", "double"} for n in _iter(root))


def _struct_array_in_loop(loops: list[dict]) -> bool:
    """`arr[i].field` inside a loop: an array of structs read field-by-field."""
    for loop in loops:
        body = loop["_node"].child_by_field_name("body")
        if body is None:
            continue
        for n in _iter(body):
            if n.type == "field_expression":
                arg = n.child_by_field_name("argument")
                if arg is not None and arg.type == "subscript_expression":
                    return True
    return False


def _strlen_in_loop_condition(loops: list[dict]) -> bool:
    for loop in loops:
        cond = loop["_node"].child_by_field_name("condition")
        if cond is not None and any(
            n.type == "call_expression" and _call_name(n) == "strlen" for n in _iter(cond)
        ):
            return True
    return False


def _pointer_chasing(loops: list[dict]) -> bool:
    """`p = p->next`-style traversal inside a loop: a linked structure walk."""
    pattern = re.compile(r"\b(\w+)\s*=\s*\1\s*->\s*\w+")
    return any(pattern.search(_text(loop["_node"])) for loop in loops)
