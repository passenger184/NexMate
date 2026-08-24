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
from rag.keyword_index import get_keyword_index, tokenize as tokenize_for_gate

# Module-level singletons — the embedding model (~130MB) and indexes are
# expensive to build and identical for every request.
_embed_model: HuggingFaceEmbedding | None = None
_index: VectorStoreIndex | None = None
_chroma_collection = None

# resolved_issue chunks (Phase 4) ride in the boosted company pool so past
# fixes surface alongside current code and docs.
COMPANY_SOURCE_TYPES = ("our_code", "company_doc", "resolved_issue")


def _get_embed_model() -> HuggingFaceEmbedding:
    global _embed_model
    if _embed_model is None:
        _embed_model = HuggingFaceEmbedding(model_name=config.EMBEDDING_MODEL_NAME)
    return _embed_model


def get_chroma_collection():
    """The persisted collection, shared by vector pools and keyword index."""
    global _chroma_collection
    if _chroma_collection is None:
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        try:
            _chroma_collection = client.get_collection(config.COLLECTION_NAME)
        except Exception as exc:  # chroma raises bare ValueError subclasses
            raise RuntimeError(
                f"Collection '{config.COLLECTION_NAME}' not found in "
                f"{config.CHROMA_DIR}. Run `python -m ingestion.chunk_and_embed` first."
            ) from exc
    return _chroma_collection


def get_index() -> VectorStoreIndex:
    """Load the persisted vector store as a queryable index."""
    global _index
    if _index is None:
        vector_store = ChromaVectorStore(
            chroma_collection=get_chroma_collection()
        )
        _index = VectorStoreIndex.from_vector_store(
            vector_store, embed_model=_get_embed_model()
        )
    return _index


def _vector_pool(question_embedding: list[float], where: dict,
                 pool: int) -> list[dict[str, Any]]:
    """One similarity-search pool against a metadata-filtered slice.

    Direct Chroma query (rather than the LlamaIndex retriever) so public
    docs and project material are retrieved as SEPARATE ranked lists and
    fused with explicit weights. Similarity conversion matches config's
    documented semantics: exp(-cosine_distance).
    """
    import math

    res = get_chroma_collection().query(
        query_embeddings=[question_embedding],
        n_results=pool,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    out: list[dict[str, Any]] = []
    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for cid, text, meta, dist in zip(ids, docs, metas, dists):
        meta = meta or {}
        out.append({
            "id": cid,
            "text": text or "",
            "score": math.exp(-(dist or 0.0)),
            "bm25_score": 0.0,
            "title": str(meta.get("title", "")),
            "section": str(meta.get("section", "")),
            "url_or_path": str(meta.get("url_or_path", "")),
            "source_type": str(meta.get("source_type", "")),
        })
    return out


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


def retrieve(question: str, k: int | None = None,
             include_company: bool = True) -> list[dict[str, Any]]:
    """Return top-k chunks fused across three signals.

    Vector similarity is retrieved as TWO pools — public docs and project
    material (our_code/company_doc/resolved_issue) — so the company pool
    can be boosted explicitly instead of hoping 321 project chunks out-rank
    7,410 doc chunks on raw cosine. The third signal is global BM25. All
    three fuse via Reciprocal Rank Fusion before best-chunk-per-document
    dedupe.

    include_company=False restricts everything (both vector pools AND the
    BM25 list) to public framework docs — used by the orchestrator for
    generic how-to questions, where this repo's own meta-docs (which QUOTE
    eval questions verbatim) would otherwise out-rank the real answer
    pages through pure keyword coincidence.

    Each result: {text, score, bm25_score, title, section, url_or_path,
    source_type}, best fused rank first.
    """
    top_k = k or config.RETRIEVAL_K
    pool = top_k * config.CANDIDATE_MULTIPLIER

    query_vec = _get_embed_model().get_query_embedding(question)
    public_pool = _vector_pool(
        query_vec, {"source_type": "public_doc"}, pool
    )
    company_pool = _vector_pool(
        query_vec, {"source_type": {"$in": list(COMPANY_SOURCE_TYPES)}}, pool
    ) if include_company else []

    candidates: dict[str, dict[str, Any]] = {}
    vector_orders: dict[str, list[str]] = {
        "public": [],
        "company": [],
    }
    for pool_name, pool_rows in (("public", public_pool),
                                 ("company", company_pool)):
        for row in pool_rows:
            cid = row.pop("id")
            vector_orders[pool_name].append(cid)
            if cid in candidates:
                continue
            candidates[cid] = row

    keyword_hits = get_keyword_index().search(question, pool)
    keyword_order: list[str] = []
    for hit in keyword_hits:
        if not include_company and hit.get("source_type") != "public_doc":
            continue
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
        rows = get_chroma_collection().get(
            ids=missing_ids, include=["documents"]
        )
        bodies = dict(zip(rows["ids"], rows.get("documents") or []))
        for cid in missing_ids:
            text = bodies.get(cid, "")
            candidates[cid]["text"] = text
            candidates[cid]["score"] = _cosine(query_vec, text) if text else 0.0

    rrf: dict[str, float] = {}

    def add_rank(cid: str, rank: int, weight: float) -> None:
        rrf[cid] = rrf.get(cid, 0.0) + weight / (config.RRF_K + rank)

    # Company boost applies ONLY to project-scoped questions; generic
    # how-tos must rank public docs on merit (found live 2026-08-24).
    lowered = question.lower()
    scoped = any(h in lowered for h in config.PROJECT_SCOPE_HINTS)
    company_weight = config.FUSION_VECTOR_WEIGHT * (
        config.FUSION_COMPANY_BOOST if scoped else 1.0
    )

    for rank, cid in enumerate(vector_orders["public"], start=1):
        add_rank(cid, rank, config.FUSION_VECTOR_WEIGHT)
    for rank, cid in enumerate(vector_orders["company"], start=1):
        add_rank(cid, rank, company_weight)
    for rank, cid in enumerate(keyword_order, start=1):
        add_rank(cid, rank, config.FUSION_KEYWORD_WEIGHT)

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
    rare_terms = [
        t for t in set(tokenize_for_gate(question))
        if 0 < keyword_index.corpus_df(t) <= config.CONFIDENCE_RARE_TERM_DF_MAX
    ]
    if (
        top >= config.CONFIDENCE_RESCUE_MIN_SIMILARITY
        and coverage >= config.CONFIDENCE_RESCUE_MIN_COVERAGE
        and not rare_terms
    ):
        return "high"
    if top >= config.CONFIDENCE_LOW_MIN_SIMILARITY:
        return "low"
    return "no_match"
