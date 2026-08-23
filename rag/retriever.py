"""Semantic retrieval over the embedded public-doc corpus.

Reloads the persisted Chroma collection (no re-embedding) and returns the
top-k chunks with their similarity scores and citation metadata.

Scores: LlamaIndex converts Chroma cosine distance to similarity via
exp(-distance); thresholds for high/low/no_match live in config.py.
"""

from typing import Any

import chromadb
from llama_index.core import VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

import config

# Module-level singletons — the embedding model (~130MB) and index are
# expensive to build and identical for every request.
_embed_model: HuggingFaceEmbedding | None = None
_index: VectorStoreIndex | None = None


def _get_embed_model() -> HuggingFaceEmbedding:
    global _embed_model
    if _embed_model is None:
        _embed_model = HuggingFaceEmbedding(model_name=config.EMBEDDING_MODEL_NAME)
    return _embed_model


def get_index() -> VectorStoreIndex:
    """Load the persisted vector store as a queryable index."""
    global _index
    if _index is None:
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        try:
            collection = client.get_collection(config.COLLECTION_NAME)
        except Exception as exc:  # chroma raises bare ValueError subclasses
            raise RuntimeError(
                f"Collection '{config.COLLECTION_NAME}' not found in "
                f"{config.CHROMA_DIR}. Run `python -m ingestion.chunk_and_embed` first."
            ) from exc
        vector_store = ChromaVectorStore(chroma_collection=collection)
        _index = VectorStoreIndex.from_vector_store(
            vector_store, embed_model=_get_embed_model()
        )
    return _index


def retrieve(question: str, k: int | None = None) -> list[dict[str, Any]]:
    """Return top-k chunks: [{text, score, title, section, url_or_path}].

    Fetches extra candidates and keeps only the best-scoring chunk per
    source document, so a single page's many similar sections can't crowd
    other documents out of the context window.
    """
    top_k = k or config.RETRIEVAL_K
    nodes = get_index().as_retriever(
        similarity_top_k=top_k * config.CANDIDATE_MULTIPLIER
    ).retrieve(question)
    seen_docs: set[str] = set()
    results = []
    for scored in nodes:
        meta = scored.node.metadata
        url = str(meta.get("url_or_path", ""))
        if url in seen_docs:
            continue
        seen_docs.add(url)
        results.append({
            "text": scored.node.get_content(),
            "score": float(scored.score) if scored.score is not None else 0.0,
            "title": str(meta.get("title", "")),
            "section": str(meta.get("section", "")),
            "url_or_path": url,
            "source_type": str(meta.get("source_type", "")),
        })
        if len(results) >= top_k:
            break
    return results


def classify_confidence(scores: list[float]) -> str:
    """Map retrieved similarities to the API's confidence signal.

    Bands (thresholds in config.py, calibrated against measured
    distributions on the v4 index):
      >= HIGH  -> "high"     : generate an answer
      >= LOW   -> "low"      : deterministic refusal, nearest sources shown,
                              no LLM call — a mediocre match must never
                              become a confidently-wrong answer
      < LOW    -> "no_match" : nothing topically relevant at all

    The service refuses on BOTH low and no_match; only "high" reaches the
    generator.
    """
    if not scores:
        return "no_match"
    top = max(scores)
    if top >= config.CONFIDENCE_HIGH_MIN_SIMILARITY:
        return "high"
    if top >= config.CONFIDENCE_LOW_MIN_SIMILARITY:
        return "low"
    return "no_match"
