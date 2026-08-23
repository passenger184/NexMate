"""Answer generation via litellm — the ONLY provider-aware module.

Reads GENERATION_PROVIDER / GENERATION_MODEL (+ OLLAMA_BASE_URL or provider
API keys) from the environment. Switching providers is a `.env` edit and a
service restart, never a code change (see ARCHITECTURE.md "Generation
provider config").

The prompt hard-gates answers to retrieved context: grounded-only output is
a Phase 1 non-negotiable (PROJECT.md), so the model is instructed to say it
doesn't know rather than fill gaps from its own training knowledge.
"""

import os
from typing import Any

from litellm import completion

SYSTEM_PROMPT = """You are a documentation assistant for ERPNext and the \
Frappe framework, answering a developer/admin user.

Rules you must follow:
1. Write your OWN concise answer in your own words. Do NOT copy or repeat \
the context passages back. Your reply must not contain passage headers like \
"[1] (Title — section)".
2. Use ONLY facts present in the numbered context passages. Never use your \
own knowledge about ERPNext/Frappe internals — if the passages don't cover \
it, say you don't know. Superficial keyword overlap does NOT count as \
coverage: if no passage actually addresses what the user asked, decline.
3. Cite supporting passages inline with their numbers, like [1] or [2][3].
4. If the passages are irrelevant to the question or too thin to answer \
confidently, reply exactly: "I don't have a confident answer for this in \
the knowledge base." Do not guess. If they cover the question only \
partially, answer the parts they DO cover and briefly note what is \
missing instead of declining outright.
5. Prefer numbered steps over prose. Keep any code from the passages intact.
6. The passages come from current-version official documentation; do not \
claim version-specific behavior the passages don't state."""


def _model_string() -> str:
    """litellm model string from env config.

    `ollama/<model>` hits Ollama's legacy /api/generate; `ollama_chat/<model>`
    hits /api/chat, which is what chat-style messages want. This mapping is
    deliberately confined to this one call site (DECISIONS.md).
    """
    provider = os.environ["GENERATION_PROVIDER"]
    model = os.environ["GENERATION_MODEL"]
    if provider == "ollama":
        return f"ollama_chat/{model}"
    return f"{provider}/{model}"


def generate_answer(question: str, chunks: list[dict[str, Any]]) -> str:
    """Generate an answer grounded in the retrieved chunks.

    Raises on any provider failure — fail loud, never fall back to
    answering without context.
    """
    if not chunks:
        return "I don't have a confident answer for this in the knowledge base."

    passages = "\n\n".join(
        f"[{i + 1}] ({c['title']} — {c['section']})\n{c['text']}"
        for i, c in enumerate(chunks)
    )
    response = completion(
        model=_model_string(),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nContext passages:\n{passages}"},
        ],
        api_base=os.environ.get("OLLAMA_BASE_URL") or None,
        temperature=0.2,
        timeout=120,
        num_retries=1,
    )
    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise RuntimeError(f"Generation returned empty content "
                           f"({_model_string()}); not fabricating an answer")
    return answer.strip()
