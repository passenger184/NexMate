"""Retrieval diagnostics over the EVALUATION.md question set.

Prints per-question hybrid-retrieval numbers (top fused documents, cosine,
BM25, keyword term-coverage) plus the resulting confidence decision, so
gate thresholds in config.py can be calibrated against measured
distributions instead of guesses.

Usage:
    python -m evaluation.retrieval_probe            # positives + negatives
    python -m evaluation.retrieval_probe --k 5      # fewer results printed
"""

import argparse

from evaluation.reference_answers import REFERENCES
from rag import retriever

NEGATIVES = [
    "How do I bake sourdough bread?",                      # unrelated domain
    "How do I configure frappe.auto_sync_with_jupiter?",   # nonexistent feature
    "What about that thing where the settings don't stick?",  # ambiguous
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--k", type=int, default=3,
                        help="how many top documents to print per query")
    args = parser.parse_args()

    questions = list(REFERENCES) + NEGATIVES
    for qi, question in enumerate(questions, start=1):
        chunks = retriever.retrieve(question)
        confidence = retriever.classify_confidence(chunks, question)
        tag = "NEG" if qi > len(REFERENCES) else f"Q{qi}"
        top_cos = max((c["score"] for c in chunks), default=0.0)
        top_bm25 = max((c["bm25_score"] for c in chunks), default=0.0)
        cov = max(
            (retriever.get_keyword_index().term_coverage(question, c["text"])
             for c in chunks[:3]),
            default=0.0,
        )
        print(f"\n{tag} [{confidence}] cos={top_cos:.4f} "
              f"bm25={top_bm25:.2f} cov={cov:.3f}  {question!r}")
        for rank, c in enumerate(chunks[:args.k], start=1):
            print(f"   {rank}. ({c['score']:.4f} | {c['bm25_score']:7.2f}) "
                  f"{c['url_or_path']}")


if __name__ == "__main__":
    main()
