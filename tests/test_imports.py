"""Every module in the package must at least import.

Regression guard: a syntax error in an entry-point module nobody tests
directly (run_matrix.py) and a stray character in guardrails.py (a
NameError at import time) both slipped through a green test run, because
no test happened to import them.
"""

import importlib
import pkgutil

import pytest

import optiflow


def _modules() -> list[str]:
    return sorted(m.name for m in pkgutil.walk_packages(optiflow.__path__, prefix="optiflow."))


@pytest.mark.parametrize("name", _modules())
def test_module_imports(name):
    importlib.import_module(name)


def test_the_walk_found_the_whole_package():
    names = set(_modules())
    for expected in ("optiflow.security.guardrails", "optiflow.experiments.run_matrix",
                     "optiflow.interop.a2a_client", "optiflow.architectures.pipeline", "optiflow.api.main"):
        assert expected in names


def test_no_forbidden_agent_frameworks():
    """Rubric Item 7: CrewAI and Google ADK only; no other agentic framework."""
    import pathlib
    import re
    import sys

    # 1. Assert no forbidden framework imported in sys.modules
    forbidden = ("langchain", "autogen", "semantic_kernel", "metagpt", "transformers.agents")
    loaded_forbidden = [mod for mod in forbidden if any(m.startswith(mod) for m in sys.modules)]
    assert not loaded_forbidden, f"Forbidden agent frameworks loaded: {loaded_forbidden}"

    # 2. Assert no forbidden framework in requirement manifests
    for manifest in ("requirements.txt", "pyproject.toml"):
        p = pathlib.Path(manifest)
        if p.exists():
            text = p.read_text(encoding="utf-8")
            for f in forbidden:
                assert not re.search(rf"\b{f}\b", text, re.I), f"Forbidden framework '{f}' found in {manifest}"

