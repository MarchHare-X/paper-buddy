from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .chunker import Chunk
from .embeddings import DEFAULT_EMBEDDING_MODEL, embed_query, embed_texts


DEFAULT_CHROMA_DIR = Path(__file__).resolve().parents[1] / ".chroma"
DEFAULT_COLLECTION_NAME = "paper_chunks"
CURRENT_INDEX_VERSION = 7


@dataclass(frozen=True)
class VectorSearchResult:
    chunk: Chunk
    score: float
    source: str = "vector"


def get_collection(
    persist_directory: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
):
    import chromadb

    client = chromadb.PersistentClient(path=str(persist_directory))
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def chunk_id(paper_id: str, index: int) -> str:
    return f"{paper_id}::{index}"


def chunk_metadata(chunk: Chunk, paper_id: str, index: int) -> dict[str, str | int | float]:
    return {
        "paper_id": paper_id,
        "index_version": CURRENT_INDEX_VERSION,
        "chunk_index": index,
        "page": chunk.page,
        "chunk_type": chunk.chunk_type,
        "figure_id": chunk.figure_id or "",
        "section": chunk.section or "",
        "section_title": chunk.section_title or "",
        "paragraph_id": chunk.paragraph_id or 0,
        "source_block": chunk.source_block or 0,
        "quality_score": chunk.quality_score,
        "paper_title": chunk.paper_title or "",
    }


def paper_is_indexed(paper_id: str) -> bool:
    collection = get_collection()
    existing = collection.get(where={"paper_id": paper_id}, limit=1)
    metadatas = existing.get("metadatas") or []
    if not metadatas:
        return False
    return metadatas[0].get("index_version") == CURRENT_INDEX_VERSION


def delete_paper_index(paper_id: str) -> None:
    collection = get_collection()
    existing = collection.get(where={"paper_id": paper_id}, limit=1)
    if existing.get("ids"):
        collection.delete(where={"paper_id": paper_id})


def index_chunks(
    paper_id: str,
    chunks: list[Chunk],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> bool:
    """Index chunks for one paper. Return True when new records were written."""
    if paper_is_indexed(paper_id):
        return False

    if not chunks:
        return False

    delete_paper_index(paper_id)
    collection = get_collection()
    documents = [chunk.text for chunk in chunks]
    embeddings = embed_texts(documents, model_name=model_name)
    ids = [chunk_id(paper_id, index) for index in range(len(chunks))]
    metadatas = [
        chunk_metadata(chunk, paper_id=paper_id, index=index)
        for index, chunk in enumerate(chunks)
    ]

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return True


def distance_to_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    return 1.0 / (1.0 + max(distance, 0.0))


def search_similar_chunks(
    paper_id: str,
    query: str,
    top_k: int = 5,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> list[VectorSearchResult]:
    collection = get_collection()
    query_embedding = embed_query(query, model_name=model_name)
    raw_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"paper_id": paper_id},
        include=["documents", "metadatas", "distances"],
    )

    documents = raw_results.get("documents", [[]])[0]
    metadatas = raw_results.get("metadatas", [[]])[0]
    distances = raw_results.get("distances", [[]])[0]

    results: list[VectorSearchResult] = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        figure_id = metadata.get("figure_id") or None
        results.append(
            VectorSearchResult(
                chunk=Chunk(
                    text=document,
                    page=int(metadata["page"]),
                    chunk_type=str(metadata["chunk_type"]),
                    figure_id=str(figure_id) if figure_id else None,
                    section=str(metadata.get("section") or "") or None,
                    section_title=str(metadata.get("section_title") or "") or None,
                    paragraph_id=int(metadata.get("paragraph_id") or 0) or None,
                    source_block=int(metadata.get("source_block") or 0) or None,
                    quality_score=float(metadata.get("quality_score") or 0.0),
                    paper_title=str(metadata.get("paper_title") or "") or None,
                ),
                score=distance_to_score(distance),
            )
        )

    return results
