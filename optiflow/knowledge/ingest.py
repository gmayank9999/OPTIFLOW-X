"""Chunks the technique-card corpus and loads it into a persistent Chroma
collection. Run once (or whenever corpus/ changes); retriever.py queries
what this writes.
"""

from __future__ import annotations

import pathlib

import chromadb
from chromadb.utils import embedding_functions

CORPUS_DIR = pathlib.Path(__file__).parent / "corpus"
STORE_DIR = pathlib.Path("kb_store")
COLLECTION_NAME = "optiflow"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


def get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(STORE_DIR))


def split(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        start += size - overlap
    return chunks


def ingest_corpus() -> int:
    client = get_client()
    collection = client.get_or_create_collection(COLLECTION_NAME, embedding_function=_embedding_fn)

    ids, documents, metadatas = [], [], []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        technique = path.stem
        for i, chunk in enumerate(split(text)):
            ids.append(f"{technique}_{i}")
            documents.append(chunk)
            metadatas.append({"technique": technique, "source": path.name})

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(ids)


if __name__ == "__main__":
    n = ingest_corpus()
    print(f"ingested {n} chunks from {CORPUS_DIR}")
