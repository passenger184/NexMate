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
import re
from typing import Any

from litellm import completion

# An inline citation marker like [1], [2][3]
_CITATION_RE = re.compile(r"\[\d+\]")
# Backtick-quoted spans: the model's concrete identifiers (hooks, methods,
# commands). Used for a deterministic grounding check against the context.
_IDENTIFIER_RE = re.compile(r"`([^`\n]+)`")

SYSTEM_PROMPT = """You are a documentation assistant for ERPNext and the \
Frappe framework, answering a developer/admin user.

Rules you must follow:
1. Write your OWN concise answer in your own words. Do NOT copy or repeat \
the context passages back. Your reply must not contain passage headers like \
"[1] (Title — section)".
2. Use ONLY facts present in the numbered context passages. Never use your \
own knowledge about ERPNext/Frappe internals. This includes secondary \
details: role requirements, version requirements, defaults, restarts or \
other side effects must NOT be stated unless a passage explicitly says so \
— never substitute your own role names, versions, or distinctions between \
similar features that the passages don't make. Every concrete identifier \
you write — hook names, method names, CLI commands, config keys, JSON \
fields — must appear VERBATIM in a passage. If the passages don't contain \
the exact identifier the question asks about, say so and present only what \
they DO cover. Superficial keyword overlap does NOT count as coverage: if \
no passage actually addresses what the user asked, decline.
3. Cite supporting passages inline with their numbers, like [1] or [2][3]. \
Every substantive claim or step needs at least one citation marker next to \
it; an answer with zero [n] markers is invalid.
4. If the passages are irrelevant to the question or too thin to answer \
confidently, reply exactly: "I don't have a confident answer for this in \
the knowledge base." Do not guess. If they cover the question only \
partially, answer the parts they DO cover and briefly note what is \
missing instead of declining outright.
5. Prefer numbered steps over prose. Keep any code from the passages intact.
6. The passages come from current-version official documentation; do not \
claim version-specific behavior the passages don't state. Passages labeled \
"project code" or "project docs" describe THIS repository itself (its own \
tools, service, configuration, and internal documentation) — when a \
question concerns this project's actual behavior, those passages are the \
authoritative source and take precedence over generic framework docs."""


def _passage_label(source_type: str) -> str:
    return {
        "our_code": "project code",
        "company_doc": "project docs",
        "resolved_issue": "past fix in this project",
    }.get(source_type, "framework docs")


CONDENSE_PROMPT = """Rewrite the user's follow-up question as ONE short \
standalone search query (max ~18 words) suitable for keyword search over \
code and documentation. Rules:
1. Resolve every conversational reference ("that", "it", "the one you \
mentioned") against the conversation.
2. If the conversation established a concrete symbol the follow-up refers \
to (constant, function, file, flag), the rewritten query MUST contain \
that exact symbol verbatim.
3. Drop ALL conversational scaffolding — no "which", "did you just", \
"where is its value set", "in your previous answer". Keep only the \
substantive topic words and the symbols.
4. DO NOT answer the question and DO NOT add facts not present in the \
conversation or the question.
Output ONLY the rewritten query text."""


def condense_followup(
    history: list[dict[str, str]], question: str
) -> str | None:
    """Rewrite an anaphoric follow-up into a standalone search question.

    Phase 4 session continuity: per-turn retrieval runs BEFORE generation,
    so a follow-up like "which constant did you just cite?" retrieves
    nothing on its own terms and gets refused before memory can matter.
    Condensing uses the history purely to restate the question — answers,
    gates, and grounding are untouched downstream.

    Returns None on any failure; callers then fall back to the raw
    question (previous behavior), since this is a retrieval-quality aid,
    not a safety component.
    """
    if not history:
        return None
    convo = "\n".join(f"{t['role']}: {t['content']}" for t in history[-4:])
    messages = [
        {"role": "system", "content": CONDENSE_PROMPT},
        {"role": "user",
         "content": f"Conversation:\n{convo}\n\nFollow-up: {question}"},
    ]
    try:
        rewritten = _complete(messages)
    except Exception:
        return None
    rewritten = rewritten.strip().strip('"')
    if not rewritten or len(rewritten) > 1000:
        return None
    return rewritten


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


def _complete(messages: list[dict[str, str]]) -> str:
    response = completion(
        model=_model_string(),
        messages=messages,
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


def _ungrounded_identifiers(answer: str, chunks: list[dict[str, Any]]) -> list[str]:
    """Backticked identifiers in the answer that appear in NO context chunk.

    Small models leak training-knowledge identifiers (hook/command names the
    corpus never mentions) even under grounded-only instructions. This is the
    deterministic net for exactly that failure mode (Q6 'after_save', found
    2026-08-24). Prose-y spans (spaces), very short ones, and templates are
    skipped — only concrete-looking names are checked.
    """
    context = "\n".join(c["text"] for c in chunks)
    bad: list[str] = []
    for ident in _IDENTIFIER_RE.findall(answer):
        name = ident.strip()
        if len(name) < 4 or " " in name or "{" in name or "}" in name:
            continue
        if name not in context and name not in bad:
            bad.append(name)
    return bad


def generate_answer(
    question: str,
    chunks: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
) -> str:
    """Generate an answer grounded in the retrieved chunks.

    `history` carries prior turns of the same session (Phase 4 session
    continuity) and is inserted before the current question; grounding
    rules still apply to the ANSWER only — retrieval is per-turn.

    Raises on any provider failure — fail loud, never fall back to
    answering without context.
    """
    if not chunks:
        return "I don't have a confident answer for this in the knowledge base."

    passages = "\n\n".join(
        f"[{i + 1}] ({c['title']} — {c['section']}; "
        f"{_passage_label(c.get('source_type', ''))})\n{c['text']}"
        for i, c in enumerate(chunks)
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    for turn in history or []:
        role = "user" if turn["role"] == "user" else "assistant"
        messages.append({"role": role, "content": turn["content"]})
    messages.append({
        "role": "user",
        "content": f"Question: {question}\n\nContext passages:\n{passages}",
    })
    answer = _complete(messages)

    # Deterministic citation-compliance check: small local models skip the
    # inline [n] markers more often than not. Up to two escalated retries —
    # multi-turn so the model sees exactly what it produced.
    decline = answer == "I don't have a confident answer for this in the knowledge base."
    escalations = [
        "Your response contains no [n] citation markers. Rewrite it: same "
        "content and grounding rules, but add an [n] marker next to every "
        "substantive claim or step (e.g. [1], [2][3]). Keep any code blocks "
        "unchanged from the passages.",
        "Still no [n] markers. Output the same answer again, but this time "
        "end EVERY sentence or step with its passage number in brackets "
        "like [1]. Do not drop any content.",
    ]
    for escalation in escalations:
        if decline or _CITATION_RE.search(answer):
            break
        messages = messages + [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": escalation},
        ]
        answer = _complete(messages)
        decline = (
            answer == "I don't have a confident answer for this in the knowledge base."
        )
    # Grounding net for leaked identifiers: one corrective retry listing the
    # offending names. If the model still can't produce a clean answer, it is
    # returned as-is — the response contract carries no fabrication flag and
    # silently discarding an otherwise-useful answer would trade one flaw for
    # another; the sources list lets the user audit every claim.
    if not decline:
        ungrounded = _ungrounded_identifiers(answer, chunks)
        if ungrounded:
            listing = "; ".join(ungrounded[:8])
            messages = messages + [
                {"role": "assistant", "content": answer},
                {"role": "user", "content": (
                    f"Your response uses these identifiers that appear "
                    f"NOWHERE in the context passages: {listing}. Rewrite "
                    f"the response: for each one, either drop the claim or "
                    f"replace it with what the passages ACTUALLY say using "
                    f"their exact identifiers — prefer replacement over "
                    f"deletion, and do not decline if the passages cover "
                    f"the topic with different names. Keep the same "
                    f"structure and keep the [n] citation markers."
                )},
            ]
            answer = _complete(messages)
    return answer
