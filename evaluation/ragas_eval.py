"""RAGAS baseline over the EVALUATION.md developer-question set.

Two-phase (they may run under different interpreters):

  1. GENERATE — runs the real pipeline (rag.retriever + rag.generator, the
     same code path the service uses minus HTTP) per question and writes
     question/answer/contexts/ground_truth rows to
     data/ragas_samples_<stamp>.json. Needs the main project venv.
  2. SCORE — feeds those rows to RAGAS metrics (faithfulness,
     answer_relevancy, context_precision) and writes results JSON.

Scoring needs its own Python <=3.13 environment (`.venv-eval`, see README):
ragas 0.2.x is incompatible with this repo's dev Python 3.14 asyncio.

The judge LLM/embedding are the local Ollama generation model and local
bge-small embeddings — self-judging is a known approximation; treat scores
as comparative baselines (EVALUATION.md), recorded in progress/CURRENT.md.

Usage (from repo root):
    python -m evaluation.ragas_eval generate            # phase 1
    python -m evaluation.ragas_eval score <samples.json>  # phase 2 (.venv-eval)
"""

import argparse
import json
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

QUESTIONS = [
    "How do I create a custom DocType?",
    "How does frappe.whitelist work?",
    "How do I override a controller in ERPNext?",
    "How do I create a server script?",
    "How do I create a custom app?",
    "What hook should I use to run code after a document is saved?",
    "How do I safely migrate a customization to a new ERPNext version?",
    "How do I add a custom field to an existing DocType?",
    "What's the difference between a Server Script and a Client Script?",
    "How do I create a REST API endpoint for a custom DocType?",
    "How do child tables work in Frappe?",
    "How do I set up a scheduled/background job in Frappe?",
    "How do permissions work for a custom DocType?",
    "What's the correct way to query the database in a Frappe app "
    "(ORM vs raw SQL)?",
    "How do I debug a validation error on document submit?",
]

NO_MATCH = "I don't have a confident answer for this in the knowledge base."


def build_samples() -> tuple[list[dict], list[dict]]:
    """Run retrieval+generation per question; return (ragas_rows, audit_rows).

    ragas_rows feed the metrics; audit_rows record confidence/sources for
    the manual-verification trail.
    """
    from evaluation.reference_answers import REFERENCES
    from rag import generator, retriever

    rows: list[dict] = []
    audit: list[dict] = []
    for i, q in enumerate(QUESTIONS):
        chunks = retriever.retrieve(q)
        confidence = retriever.classify_confidence(chunks, q)
        # Mirror service/main.py gating: only "high" reaches the generator;
        # low/no_match are deterministic refusals.
        answer = (
            NO_MATCH if confidence != "high"
            else generator.generate_answer(q, chunks)
        )
        rows.append({
            "question": q,
            "answer": answer,
            "contexts": [c["text"] for c in chunks],
            "ground_truth": REFERENCES[q],
        })
        audit.append({
            "question": q,
            "confidence": confidence,
            "top_score": round(max(c["score"] for c in chunks), 3),
            "sources": [c["url_or_path"] for c in chunks],
        })
        print(f"[{i + 1}/{len(QUESTIONS)}] {confidence} {q[:60]}")
    return rows, audit


def run_ragas(rows: list[dict]) -> dict:
    """Score with local Ollama as judge and local bge embeddings."""
    from datasets import Dataset
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_ollama import ChatOllama
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, context_precision, faithfulness
    from ragas.run_config import RunConfig

    judge_llm = LangchainLLMWrapper(ChatOllama(
        model=os.environ["GENERATION_MODEL"],
        base_url=os.environ.get("OLLAMA_BASE_URL"),
        temperature=0.0,
        num_predict=1024,
        timeout=300,
    ))
    judge_embeds = LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
    ))

    # NOTE: timeout must stay None on Python 3.14 — ragas 0.2.x wraps each
    # metric call in asyncio.wait_for(timeouts.timeout), which raises
    # "Timeout should be used inside a task" under 3.14's stricter asyncio.
    # With timeout=None that code path is skipped entirely.
    dataset = Dataset.from_list(rows)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=judge_llm,
        embeddings=judge_embeds,
        raise_exceptions=False,
        run_config=RunConfig(max_workers=2, timeout=None),
    )
    return result.to_pandas().to_dict(orient="list")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="phase", required=True)
    sub.add_parser("generate", help="run the pipeline, write samples JSON")
    score_p = sub.add_parser("score", help="score a samples JSON with RAGAS")
    score_p.add_argument("samples", help="path to data/ragas_samples_*.json")
    args = parser.parse_args()

    if args.phase == "generate":
        rows, audit = build_samples()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out_path = f"data/ragas_samples_{stamp}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": stamp, "rows": rows, "audit": audit},
                      f, indent=2)
        print(f"Samples written to {out_path}")
        return

    # --- score phase ---
    from evaluation.ragas_score_helpers import run_ragas

    with open(args.samples, encoding="utf-8") as f:
        payload = json.load(f)
    print(f"Scoring {len(payload['rows'])} samples "
          f"(generated {payload['timestamp']})...")
    scored = run_ragas(payload["rows"])

    def _mean_valid(vals: list) -> float:
        # ragas marks failed metric calls as NaN; exclude them explicitly
        valid = [v for v in vals if v is not None and v == v]
        return round(sum(map(float, valid)) / len(valid), 3)

    means = {
        k: _mean_valid(scored[k])
        for k in ("faithfulness", "answer_relevancy", "context_precision")
        if any(v is not None and v == v for v in scored[k])
    }
    out_path = args.samples.replace("_samples_", "_baseline_").replace(
        ".json", "") + f"_{datetime.now(timezone.utc).strftime('%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": payload["timestamp"],
                   "means": means, "rows": scored}, f, indent=2, default=str)
    print("\n=== RAGAS baseline ===")
    for k, v in means.items():
        print(f"{k}: {v}")
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
