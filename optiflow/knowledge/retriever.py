"""Retrieves the top-k technique cards relevant to a program's profile."""

from __future__ import annotations

from optiflow.core.schemas import ProfileReport, ProgramSummary
from optiflow.knowledge.ingest import COLLECTION_NAME, get_client, get_embedding_fn


def build_query(summary: ProgramSummary, profile: ProfileReport) -> str:
    return (
        f"{profile.bottleneck_text}. max loop depth "
        f"{summary.features.get('max_loop_depth', 0):.0f}, "
        f"stride_mismatch={summary.features.get('stride_mismatch', 0):.0f}, "
        f"has_recursion={summary.features.get('has_recursion', 0):.0f}, "
        f"has_struct_array={summary.features.get('has_struct_array', 0):.0f}"
    )


def retrieve(summary: ProgramSummary, profile: ProfileReport, k: int = 4) -> list[str]:
    client = get_client()
    collection = client.get_or_create_collection(COLLECTION_NAME, embedding_function=get_embedding_fn())
    if collection.count() == 0:
        return []

    query = build_query(summary, profile)
    result = collection.query(query_texts=[query], n_results=min(k, collection.count()))
    return result["documents"][0] if result["documents"] else []


def retrieve_text(query: str, k: int = 4) -> list[str]:
    """Free-text search, used by the ReAct Strategist's knowledge_search tool."""
    client = get_client()
    collection = client.get_or_create_collection(COLLECTION_NAME, embedding_function=get_embedding_fn())
    if collection.count() == 0:
        return []
    result = collection.query(query_texts=[query], n_results=min(k, collection.count()))
    return result["documents"][0] if result["documents"] else []
