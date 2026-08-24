"""Hybrid retrieval over the embedded public-doc corpus.

Two signals, one corpus (DECISIONS.md [2026-08-24]):
  - Semantic: Chroma cosine similarity via the persisted LlamaIndex index.
  - Lexical: in-house Okapi BM25 (rag/keyword_index.py), built lazily from
    the same collection.

Candidate lists are fused with Reciprocal Rank Fusion before the existing
best-chunk-per-document dedupe, so exact-term pages (bench commands, hook
names, error strings) can surface even when their embeddings rank poorly,
and embedding-noise pages stop crowding out the right document.

Scores returned per chunk:
  score      - cosine similarity (exp(-distance)); gates confidence
  bm25_score - lexical evidence strength (0.0 for vector-only hits)

Confidence thresholds live in config.py and were recalibrated on measured
distributions after the fusion change.
"""

from typing import Any

import chromadb
import numpy as np
from llama_index.core import VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

import config
from rag.keyword_index import get_keyword_index

# Module-level singletons — the embedding model (~130MB) and indexes are
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


def _cosine(query_vec: list[float], text: str) -> float:
    """Exact cosine similarity between the query and an arbitrary chunk.

    Needed for keyword-only hits that never went through the vector
    retriever: without a real similarity number the confidence gate would
    be guessing.
    """
    q = np.asarray(query_vec, dtype=np.float32)
    d = np.asarray(_get_embed_model().get_text_embedding(text), dtype=np.float32)
    denom = float(np.linalg.norm(q) * np.linalg.norm(d))
    return float(np.dot(q, d) / denom) if denom else 0.0


def retrieve(question: str, k: int | None = None) -> list[dict[str, Any]]:
    """Return top-k chunks fused across both signals.

    Each result: {text, score, bm25_score, title, section, url_or_path,
    source_type}, best fused rank first, at most one chunk per source
    document so a single page's sections can't crowd the context window.
    """
    top_k = k or config.RETRIEVAL_K
    pool = top_k * config.CANDIDATE_MULTIPLIER

    scored_nodes = get_index().as_retriever(
        similarity_top_k=pool
    ).retrieve(question)
    query_vec = _get_embed_model().get_query_embedding(question)

    candidates: dict[str, dict[str, Any]] = {}
    vector_order: list[str] = []
    for ranked in scored_nodes:
        meta = ranked.node.metadata
        cid = ranked.node.id_
        vector_order.append(cid)
        candidates[cid] = {
            "text": ranked.node.get_content(),
            "score": float(ranked.score) if ranked.score is not None else 0.0,
            "bm25_score": 0.0,
            "title": str(meta.get("title", "")),
            "section": str(meta.get("section", "")),
            "url_or_path": str(meta.get("url_or_path", "")),
            "source_type": str(meta.get("source_type", "")),
        }

    keyword_hits = get_keyword_index().search(question, pool)
    keyword_order: list[str] = []
    for hit in keyword_hits:
        keyword_order.append(hit["id"])
        if hit["id"] in candidates:
            candidates[hit["id"]]["bm25_score"] = hit["bm25_score"]
        else:
            # Keyword-only hit: fetch its metadata from the BM25 side and
            # compute its true cosine so gating stays honest.
            candidates[hit["id"]] = {
                "text": "",
                "score": 0.0,
                "bm25_score": hit["bm25_score"],
                "title": hit["title"],
                "section": hit["section"],
                "url_or_path": hit["url_or_path"],
                "source_type": hit["source_type"],
                "_needs_text": True,
            }

    # Keyword-only hits carry no text yet (BM25 keeps only ids); pull the
    # chunk body back out of Chroma once per query rather than storing the
    # whole corpus' texts in RAM twice.
    missing_ids = [cid for cid, c in candidates.items() if c.pop("_needs_text", False)]
    if missing_ids:
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        rows = client.get_collection(config.COLLECTION_NAME).get(
            ids=missing_ids, include=["documents"]
        )
        bodies = dict(zip(rows["ids"], rows.get("documents") or []))
        for cid in missing_ids:
            text = bodies.get(cid, "")
            candidates[cid]["text"] = text
            candidates[cid]["score"] = _cosine(query_vec, text) if text else 0.0

    rrf: dict[str, float] = {}
    for rank, cid in enumerate(vector_order, start=1):
        rrf[cid] = rrf.get(cid, 0.0) + config.FUSION_VECTOR_WEIGHT / (
            config.RRF_K + rank
        )
    for rank, cid in enumerate(keyword_order, start=1):
        rrf[cid] = rrf.get(cid, 0.0) + config.FUSION_KEYWORD_WEIGHT / (
            config.RRF_K + rank
        )

    ordered_ids = sorted(rrf, key=lambda c: rrf[c], reverse=True)
    doc_counts: dict[str, int] = {}
    doc_best_bm25: dict[str, float] = {}
    results: list[dict[str, Any]] = []
    for cid in ordered_ids:
        cand = candidates[cid]
        url = cand["url_or_path"]
        best_bm25 = doc_best_bm25.get(url, 0.0)
        if url in doc_counts:
            # One chunk per document normally — but near-tied lexical
            # evidence from the same page is genuinely additional context
            # (e.g. two sections of hooks.md both matching "override").
            strong_second = (
                sum(1 for r in results if r["url_or_path"] == url) == 1
                and cand["bm25_score"] > 0.0
                and best_bm25 > 0.0
                and cand["bm25_score"]
                >= config.DOC_SECOND_CHUNK_MIN_RELATIVE_BM25 * best_bm25
            )
            if not strong_second:
                continue
        doc_counts[url] = doc_counts.get(url, 0) + 1
        doc_best_bm25[url] = max(best_bm25, cand["bm25_score"])
        results.append(cand)
        if len(results) >= top_k:
            break
    return results


def classify_confidence(chunks: list[dict[str, Any]], question: str) -> str:
    """Map hybrid retrieval results to the API's confidence signal.

    Bands (thresholds in config.py, calibrated against measured
    distributions on the v4 index + eval probes):

      no_match - the query's distinctive terms appear in none of the top
                 chunks (coverage veto: catches keyword-overlap negatives
                 whose generic words inflate cosine), OR top similarity is
                 below CONFIDENCE_LOW_MIN_SIMILARITY. Refuse, empty sources.
      low      - topically close but under the confident bar. Deterministic
                 refusal, nearest sources shown, no LLM call.
      high     - strong vector similarity, or solid similarity corroborated
                 by exact keyword evidence (coverage rescue).

    Only "high" reaches the generator.
    """
    if not chunks:
        return "no_match"
    keyword_index = get_keyword_index()
    unseen = keyword_index.unseen_query_terms(question)
    top = max(c["score"] for c in chunks)
    if unseen and top < config.CONFIDENCE_HIGH_MIN_SIMILARITY:
        # The question names something that appears nowhere in the corpus
        # (e.g. a fabricated feature). Only overwhelming semantic evidence
        # (cosine >= the high bar) can override one unknown token.
        return "no_match"
    coverage = max(
        keyword_index.term_coverage(question, c["text"]) for c in chunks[:3]
    )
    if coverage <= config.CONFIDENCE_NO_MATCH_MAX_COVERAGE:
        return "no_match"
    if top >= config.CONFIDENCE_HIGH_MIN_SIMILARITY:
        return "high"
    if (
        top >= config.CONFIDENCE_RESCUE_MIN_SIMILARITY
        and coverage >= config.CONFIDENCE_RESCUE_MIN_COVERAGE
    ):
        return "high"
    if top >= config.CONFIDENCE_LOW_MIN_SIMILARITY:
        return "low"
    return "no_match"
