"""In-memory BM25 keyword index over the embedded public-doc corpus.

Hybrid retrieval half (DECISIONS.md [2026-08-24]): semantic embeddings miss
exact-term pages (bench commands, hook names, error strings) that lexical
matching finds trivially. This module builds an Okapi BM25 index over the
SAME Chroma collection the vector side serves, so the two candidate lists
always describe an identical corpus.

No third-party BM25 dependency: Okapi BM25 is a small, fully specified
formula, and keeping it in-house avoids adding a package outside the locked
stack (SECURITY.md dependency hygiene) for ~80 lines of standard math.

Also exposes IDF-weighted query-term coverage, used by the confidence gate
to distinguish "keyword-overlap noise" (negative probes whose distinctive
terms appear nowhere in a chunk) from real topical matches.
"""

from __future__ import annotations

import math
import re
from typing import Any

import chromadb

import config

# --- Tokenization ----------------------------------------------------------
# Lowercase, split camelCase and snake_case, keep alphanumeric runs, drop
# stopwords and single characters. A conservative plural stripper ('s' suffix
# on words >3 chars) normalizes hook/hooks, scheduler/schedulers on BOTH the
# query and corpus side; consistency matters more than linguistic perfection.
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset("""
a about after again all also am an and any are as at be because been before
being between both but by can could did do does doing down during each else
few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself
no nor not now of off on once only or other our ours ourselves out over own
same she should so some such than that the their theirs them themselves
then there these they this those through to too under until up very was we
were what when where which while who whom why will with you your yours
yourself yourselves
""".split())


def _normalize(tok: str) -> str:
    """Light suffix folding so inflections match ('overriding'~'override').

    Deliberately NOT a real stemmer: strips plural -s, progressive -ing,
    past -ed, and a trailing silent -e. Applied identically to queries and
    corpus, so consistency matters more than linguistic correctness.
    """
    if len(tok) > 3 and tok.endswith("s") and tok[:-1] not in STOPWORDS:
        tok = tok[:-1]
    if len(tok) > 4 and tok.endswith("ing"):
        tok = tok[:-3]
    elif len(tok) > 4 and tok.endswith("ed"):
        tok = tok[:-2]
    if len(tok) > 4 and tok.endswith("e") and not tok.endswith("ee"):
        tok = tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    """Lowercased, stopword-filtered, suffix-normalized word tokens."""
    prepared = _TOKEN_RE.findall(_CAMEL_SPLIT_RE.sub(" ", text.lower()).replace("_", " "))
    tokens: list[str] = []
    for raw in prepared:
        if raw in STOPWORDS or len(raw) < 2:
            continue
        tok = _normalize(raw)
        if tok in STOPWORDS or len(tok) < 2:
            continue
        tokens.append(tok)
    return tokens


class KeywordIndex:
    """Okapi BM25 over pre-loaded chunk texts.

    Build cost for the full corpus (~7.4k chunks) is well under a second,
    so the index is rebuilt lazily per process rather than persisted —
    no stale-index failure mode, and it can never drift from Chroma
    because Chroma itself is the source of truth.
    """

    def __init__(self, ids: list[str], texts: list[str], metadatas: list[dict]):
        if len(ids) != len(texts) or len(ids) != len(metadatas):
            raise RuntimeError(
                f"KeywordIndex input mismatch: {len(ids)} ids, "
                f"{len(texts)} texts, {len(metadatas)} metadatas"
            )
        self.ids = ids
        self.metadatas = metadatas
        self.doc_tokens: list[list[str]] = [tokenize(t) for t in texts]
        self.doc_len = [len(toks) for toks in self.doc_tokens]
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        if not self.avgdl:
            raise RuntimeError("Cannot build keyword index over an empty corpus")

        self.term_freqs: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for toks in self.doc_tokens:
            tf: dict[str, int] = {}
            for tok in toks:
                tf[tok] = tf.get(tok, 0) + 1
            self.term_freqs.append(tf)
            for tok in tf:
                df[tok] = df.get(tok, 0) + 1

        n_docs = len(self.ids)
        # BM25+ style floor at 0 keeps every observed term positive.
        self.idf = {
            term: math.log(1.0 + (n_docs - dfr + 0.5) / (dfr + 0.5))
            for term, dfr in df.items()
        }

    def _bm25_score(self, doc_idx: int, query_terms: list[str]) -> float:
        tf_map = self.term_freqs[doc_idx]
        norm = config.BM25_K1 * (
            1.0 - config.BM25_B + config.BM25_B * self.doc_len[doc_idx] / self.avgdl
        )
        score = 0.0
        for term in query_terms:
            tf = tf_map.get(term)
            if not tf:
                continue
            score += (
                self.idf[term] * tf * (config.BM25_K1 + 1.0) / (tf + norm)
            )
        return score

    def search(self, question: str, top_n: int) -> list[dict[str, Any]]:
        """Top-n chunks with positive BM25 score, best first."""
        query_terms = tokenize(question)
        if not query_terms:
            return []
        scored = [
            (i, self._bm25_score(i, query_terms))
            for i in range(len(self.ids))
        ]
        hits = [
            {
                "id": self.ids[i],
                "bm25_score": round(score, 4),
                **{k: str(self.metadatas[i].get(k, ""))
                   for k in ("title", "section", "url_or_path", "source_type")},
            }
            for i, score in scored
            if score > 0.0
        ]
        hits.sort(key=lambda h: h["bm25_score"], reverse=True)
        return hits[:top_n]

    def term_coverage(self, question: str, chunk_text: str) -> float:
        """IDF-weighted fraction of informative query terms found in a chunk.

        Common words contribute little; a distinctive term with no match
        anywhere in the chunk drags coverage toward 0. Query terms that
        appear NOWHERE in the corpus are weighted at max IDF in the
        denominator — otherwise a fabricated-feature name like
        'auto_sync_with_jupiter' would cost nothing to miss and coverage
        would stay high on keyword-overlap negatives (found 2026-08-24).
        """
        query_terms = set(tokenize(question))
        if not query_terms:
            return 0.0
        chunk_terms = set(tokenize(chunk_text))
        unseen_weight = max(self.idf.values(), default=0.0)

        def weight(term: str) -> float:
            return self.idf.get(term, unseen_weight)

        total_weight = sum(weight(t) for t in query_terms)
        if total_weight <= 0.0:
            return 0.0
        matched_weight = sum(
            weight(t) for t in query_terms if t in chunk_terms
        )
        return matched_weight / total_weight

    def unseen_query_terms(self, question: str) -> list[str]:
        """Informative query terms that appear NOWHERE in the corpus.

        A fabricated-feature name ('jupiter' in frappe.auto_sync_with_jupiter)
        has zero corpus occurrences, while legitimate-but-infrequent jargon
        ('orm' df~10, 'migrate' df~4) does occur — so absence-from-corpus,
        not rarity, is the reliable fabrication signal.
        """
        return sorted(t for t in set(tokenize(question)) if t not in self.idf)


_keyword_index: KeywordIndex | None = None


def get_keyword_index() -> KeywordIndex:
    """Lazily build the BM25 index from the persisted Chroma collection."""
    global _keyword_index
    if _keyword_index is None:
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        try:
            collection = client.get_collection(config.COLLECTION_NAME)
        except Exception as exc:  # chroma raises bare ValueError subclasses
            raise RuntimeError(
                f"Collection '{config.COLLECTION_NAME}' not found in "
                f"{config.CHROMA_DIR}. Run `python -m ingestion.chunk_and_embed` first."
            ) from exc
        dumped = collection.get(include=["documents", "metadatas"])
        docs = dumped.get("documents") or []
        metas = dumped.get("metadatas") or []
        if not docs:
            raise RuntimeError(
                f"Collection '{config.COLLECTION_NAME}' is empty; "
                "cannot build keyword index"
            )
        _keyword_index = KeywordIndex(dumped["ids"], docs, metas)
    return _keyword_index
