"""Retrieval quality check (Section 11.2): for a query clearly pointing at
one technique, is that technique's card in the top-4 results?

Ingests the corpus itself so the test is self-contained; upsert is
idempotent so running it repeatedly doesn't duplicate chunks.
"""

import pytest

from optiflow.core.schemas import ProfileReport, ProgramSummary
from optiflow.knowledge.ingest import ingest_corpus
from optiflow.knowledge.retriever import retrieve

pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")


def make_summary(**features) -> ProgramSummary:
    return ProgramSummary(program_id="x", language="c", source="", functions=[], loops=[], features=features)


def make_profile(text: str) -> ProfileReport:
    return ProfileReport(baseline_runtime_ms=1, runtime_std_ms=0, peak_mem_kb=0, bottleneck_text=text)

CASES = [
    (make_summary(max_loop_depth=3, stride_mismatch=1),
     make_profile("high L1 and LLC miss rate on a triple-nested loop over large 2D arrays"),
     "tiling"),
    (make_summary(max_loop_depth=3, stride_mismatch=1),
     make_profile("cache-hostile column access in a nested matrix loop, innermost index on the wrong dimension"),
     "interchange"),
    (make_summary(has_recursion=1),
     make_profile("exponential blowup from repeated recursive calls on overlapping subproblems"),
     "memoization"),
    (make_summary(has_struct_array=1),
     make_profile("array of structs where only 3 of 8 fields are touched per iteration"),
     "struct-of-arrays"),
    (make_summary(strlen_in_loop_cond=1),
     make_profile("strlen called every iteration inside the loop condition"),
     "hoisting"),
    (make_summary(max_loop_depth=1),
     make_profile("tight single loop over a contiguous array, no auto-vectorization detected"),
     "vectorization"),
]


@pytest.fixture(scope="module", autouse=True)
def _ingested():
    ingest_corpus()


@pytest.mark.parametrize("summary,profile,expected_technique", CASES)
def test_hit_at_4(summary, profile, expected_technique):
    docs = retrieve(summary, profile, k=4)
    headers = [d.splitlines()[0].lower() for d in docs]
    assert any(expected_technique in h for h in headers), (expected_technique, headers)
