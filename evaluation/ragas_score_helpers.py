"""RAGAS scoring half of the baseline harness.

Kept separate from ragas_eval.py so the two phases can run under different
interpreters: this module only needs ragas/langchain/datasets, and runs in
`.venv-eval` (Python <= 3.13) because ragas 0.2.x breaks under Python 3.14's
asyncio (asyncio.wait_for/timeouts.timeout requires a Task context that
nest_asyncio-patched loops don't provide on 3.14).
"""

import asyncio
import sys


def _apply_py314_asyncio_shim() -> None:
    """On 3.14+, replace asyncio.wait_for with a plain await.

    ragas 0.2.x wraps each metric call in asyncio.wait_for(); 3.14's wait_for
    always enters asyncio.timeouts.timeout, raising "Timeout should be used
    inside a task" under nest_asyncio's loop. Per-call timeout enforcement is
    instead handled by ChatOllama's own request timeout.
    """
    if sys.version_info >= (3, 14):
        original = asyncio.wait_for

        async def _wait_for_direct(fut, timeout=None):  # noqa: ANN001, ANN201
            fut = asyncio.ensure_future(fut)
            try:
                return await fut
            except asyncio.CancelledError:
                if not fut.cancelled():
                    fut.cancel()
                raise

        asyncio.wait_for = _wait_for_direct  # noqa: A105
        _ = original  # kept for reference/debugging


_apply_py314_asyncio_shim()


def run_ragas(rows: list[dict]) -> dict:
    """Score rows {question, answer, contexts, ground_truth} with RAGAS."""
    import os

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

    dataset = Dataset.from_list(rows)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=judge_llm,
        embeddings=judge_embeds,
        raise_exceptions=False,
        # max_workers small: the local Ollama judge is the bottleneck and
        # parallel load degrades its latency severely.
        run_config=RunConfig(max_workers=2, timeout=None),
    )
    return result.to_pandas().to_dict(orient="list")
