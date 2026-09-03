"""Tier-1 explain: locate code relevant to a reported problem, explain it.

Pipeline (docs/PHASE_2_SPEC.md "explain"): derive search terms from the
user's description of an error/unexpected behavior -> run project searches
-> read the located files (project-root scoped, size-capped) -> build
numbered excerpts -> ONE grounded-only LLM call that must cite real
locations and may honestly say the excerpts don't cover it. Never generic
ERPNext folklore divorced from this project's actual code.

Since 2026-08-24 the entry point also serves GENERAL questions about the
project (anything routed `code` that isn't an error report). A
deterministic classifier picks the prompt: the error template must never
fire on a non-error input, because the model will otherwise invent an
"error" section, a diagnosis, and quoted statements to satisfy the
template (fabrication class of Q3/Q9).

LLM access goes through rag.generator._complete — intentionally THE single
litellm call site (ARCHITECTURE.md "Generation provider config"); no
provider logic lives here. The backtick-identifier grounding net is also
reused from the generator so explanations obey the same verbatim rule as
answers.
"""

import re
from typing import Any

import config
from rag.generator import _complete, _ungrounded_identifiers
from tools import search
from tools.files import read_project_file

# Identifiers worth searching: quoted strings first-class, then words long
# enough to be meaningful. Stopwords cover generic error vocabulary that
# matches half the codebase and would drown the signal.
_NOISE_WORDS = frozenset("""
the a an and or but if then else for of to in on at by with from is are was
were be been being this that these those it its as not no yes when what
which who how why all any some none error errors exception exceptions fail
failed failing fails failure problem issue bug wrong unexpected behavior
message messages line lines file files code function functions method
methods class classes return returns returning call calls called value
values key keys missing invalid incorrect good check checks checked
unexpectedly weird strange broken brokenly crash crashes crashing
""".split())

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_QUOTED_RE = re.compile(r"[\"'`]([^\"'`]{3,80})[\"'`]")

EXPLAIN_SYSTEM_PROMPT = """You are a code-explanation assistant for THIS \
project. You are given numbered excerpts of actual project source code and \
a developer's description of an error or unexpected behavior.

Rules you must follow:
1. Base every claim on the excerpts. Never invent project internals, file \
names, functions, or behavior that the excerpts don't show.
2. Every concrete identifier you write — function names, variables, paths — \
must appear VERBATIM in an excerpt. Reference locations as `path/to/file.py` \
followed by plain line numbers OUTSIDE the backticks, e.g. `tools/files.py` \
line 42.
3. Only diagnose the failure the user actually reported. If the description \
reports no specific failure, do NOT invent one: no "cause of error",
"unexpected behavior", "recommendations", or "steps to fix/diagnose" \
sections.
4. Never present a sentence as a quotation from the project — a comment, \
error message, log line, or reported developer statement — unless it \
appears VERBATIM in one of the excerpts.
5. Explain the likely cause in plain prose, walking through the relevant \
excerpt logic. If the excerpts genuinely do not contain enough information, \
say exactly that and describe what WOULD be needed — a wrong guess is worse \
than an honest gap.
6. Keep code references exact; quote only short snippets you can see."""

CODE_QA_SYSTEM_PROMPT = """You are a code assistant for THIS project. You \
are given numbered excerpts of actual project source and documentation, \
and a developer's question about the project. The user did NOT report an \
error.

Rules you must follow:
1. Answer ONLY the question asked, using ONLY the excerpts. Never invent \
project internals, file names, functions, or behavior that the excerpts \
don't show.
2. Every concrete identifier you write — function names, variables, paths — \
must appear VERBATIM in an excerpt. Reference locations as `path/to/file.py` \
followed by plain line numbers OUTSIDE the backticks, e.g. `tools/files.py` \
line 42.
3. Never frame the answer as error diagnosis: do NOT add "Error", \
"Unexpected Behavior", "Likely Cause", "Recommendations", "Steps to \
Fix/Diagnose", or similar sections, and do NOT describe any bug or \
misbehavior.
4. Never present a sentence as a quotation from the project — a comment, \
error message, log line, or reported developer statement — unless it \
appears VERBATIM in one of the excerpts.
5. Some excerpts are labeled "planning doc": they state INTENT and roadmaps \
(ARCHITECTURE.md, ROADMAP.md, future-work notes), NOT current reality. When \
asked what exists or how something currently works, prefer source code and \
records of completed work, and explicitly mark anything drawn from planning \
docs as planned, proposed, or future — never as already built.
6. If the excerpts genuinely do not contain enough information, say exactly \
that — a wrong guess is worse than an honest gap."""

# Planning/vision documents: intent and roadmaps, not current state.
# Excerpts from these get an explicit label so answers can't present
# target architecture as already-built reality.
_VISION_DOCS = frozenset({
    "ARCHITECTURE.md",
    "ROADMAP.md",
    "docs/FUTURE_MULTI_WORKSPACE.md",
})

# Whole-word signals that the user is reporting a failure, not asking a
# general question. Kept intentionally narrow: over-triggering merely
# selects the error template (which now refuses to invent unreported
# errors), under-triggering still gets grounded non-error answers.
_ERROR_SIGNALS = (
    "traceback", "stack trace", "raise", "raised", "raises", "raising",
    "fail", "fails", "failed", "failing", "failure", "broken", "crash",
    "crashes", "crashed", "crashing", "bug", "wrong", "unexpected",
    "instead of", "not working", "doesn't work", "does not work",
    "regression", "misbehav",
)


def looks_like_error(description: str) -> bool:
    """True if the text reports a failure (vs. asking about the project).

    Matches exception-class names (CamelCase*Error/Exception/Warning),
    HTTP 4xx/5xx codes, and whole-word failure vocabulary.
    """
    text = description.lower()
    if re.search(r"\b[A-Za-z_][A-Za-z0-9_]*(Error|Exception|Warning)\b",
                 description):
        return True
    if re.search(r"\b[45]\d\d\b", text):
        return True
    return any(re.search(r"\b" + re.escape(sig) + r"\b", text)
               for sig in _ERROR_SIGNALS)


def _vision_suffix(rel_path: str) -> str:
    if rel_path in _VISION_DOCS:
        return " (planning doc — describes intent, not current state)"
    return ""


def extract_search_terms(description: str) -> list[str]:
    """Pick the most searchable tokens from a problem description.

    Quoted phrases rank first (they're usually exact identifiers or error
    text), then identifiers by length (longer == rarer == more locating).
    Generic vocabulary is dropped entirely.
    """
    terms: list[str] = []

    for quoted in _QUOTED_RE.findall(description):
        cleaned = quoted.strip()
        if len(cleaned) >= 3 and cleaned.lower() not in _NOISE_WORDS:
            terms.append(cleaned)

    seen = set(terms)
    identifiers = [
        m.group(0)
        for m in _IDENTIFIER_RE.finditer(description)
        if m.group(0).lower() not in _NOISE_WORDS
        and m.group(0).lower() not in seen
    ]
    identifiers.sort(key=len, reverse=True)
    for ident in identifiers:
        if len(terms) >= config.EXPLAIN_MAX_SEARCH_TERMS:
            break
        if ident not in seen:
            terms.append(ident)
            seen.add(ident)
    return terms


def _locate_files(terms: list[str]) -> tuple[dict[str, dict[str, Any]], int]:
    """Search each term; score files by weighted, capped match counts.

    Weight = term position x specificity: identifier-style terms
    (snake_case / CamelCase) are far more locating than common lowercase
    words, which can appear dozens of times in unrelated files. Per-term
    contributions cap at 5 matches so one chatty file can't drown the
    signal. Returns ({rel_path: {"score","hit_lines"}}, total_hits).
    """
    def term_weight(position: int, term: str) -> float:
        positional = len(terms) - position
        specific = 3.0 if ("_" in term or any(c.isupper() for c in term)) else 1.0
        return positional * specific

    scores: dict[str, dict[str, Any]] = {}
    total_hits = 0
    for position, term in enumerate(terms):
        weight = term_weight(position, term)
        result = search.search_project(term)
        total_hits += result["total_matches"]
        per_file_counts: dict[str, list[int]] = {}
        for match in result["matches"]:
            per_file_counts.setdefault(match["path"], []).append(
                match["line_number"]
            )
        for path, lines in per_file_counts.items():
            entry = scores.setdefault(path, {"score": 0.0, "hit_lines": []})
            entry["score"] += weight * min(len(lines), 5)
            entry["hit_lines"].extend(lines[:5])
    return scores, total_hits


def _excerpt(text_lines: list[str], hit_lines: list[int]) -> tuple[str, int, int]:
    """Window around the first hit; returns (snippet, start_line, end_line)."""
    max_chars = config.EXPLAIN_MAX_EXCERPT_CHARS
    window = config.EXPLAIN_WINDOW_LINES
    if len("\n".join(text_lines)) <= max_chars:
        return "\n".join(text_lines), 1, len(text_lines)

    center = max((h for h in hit_lines if 1 <= h <= len(text_lines)), default=1)
    start = max(1, center - window)
    end = min(len(text_lines), center + window)
    snippet = "\n".join(text_lines[start - 1:end])
    clipped = ""
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars]
        clipped = "…"
    return f"[lines {start}-{end}]\n{snippet}{clipped}", start, end


def locate_and_explain(description: str) -> dict[str, Any]:
    """Find the code behind a reported problem and explain the cause.

    Also serves general questions about the project routed here: when the
    input reports no failure, the general code-Q&A prompt is used instead
    of the error template (which would otherwise fabricate error sections
    for bugs that were never reported). Returns "kind": "error"|"general".
    """
    is_error = looks_like_error(description)
    terms = extract_search_terms(description)
    if not terms:
        return {
            "located": False,
            "explanation": (
                "Couldn't derive any searchable terms from that "
                "description — try including the exact error message or "
                "an identifier you suspect."
            ),
            "sources": [],
            "search_terms": [],
            "total_hits": 0,
        }

    scores, total_hits = _locate_files(terms)
    if not scores:
        return {
            "located": False,
            "explanation": (
                "No matching code found in the project for any derived "
                f"search term ({', '.join(terms)}). The described behavior "
                "may live outside this repository, or needs different "
                "wording."
            ),
            "sources": [],
            "search_terms": terms,
            "total_hits": 0,
        }

    ranked = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)
    sources: list[dict[str, Any]] = []
    passages: list[str] = []
    for rel_path, info in ranked[:config.EXPLAIN_MAX_FILES]:
        try:
            file_info = read_project_file(rel_path)
        except Exception:  # unreadable since listing — skip, others remain
            continue
        text_lines = file_info["content"].splitlines()
        excerpt, start_line, end_line = _excerpt(
            text_lines, info["hit_lines"]
        )
        passages.append(
            f"[{len(passages) + 1}] (`{rel_path}` lines "
            f"{start_line}-{end_line}{_vision_suffix(rel_path)})\n{excerpt}"
        )
        sources.append({
            "path": rel_path,
            "line_start": start_line,
            "line_end": end_line,
        })

    system_prompt = EXPLAIN_SYSTEM_PROMPT if is_error else CODE_QA_SYSTEM_PROMPT
    user_content = (
        (f"Problem description: {description}"
         if is_error else f"Question: {description}")
        + "\n\nCode excerpts:\n"
        + "\n\n".join(passages)
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    answer = _complete(messages)

    ungrounded = _ungrounded_identifiers(answer, [
        {"text": p} for p in passages
    ])
    if ungrounded:
        listing = "; ".join(ungrounded[:8])
        messages = messages + [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": (
                f"Your response uses these identifiers that appear NOWHERE "
                f"in the code excerpts: {listing}. Rewrite it using only "
                f"identifiers visible in the excerpts, keeping the same "
                f"structure and `path` + line-number citations."
            )},
        ]
        answer = _complete(messages)

    return {
        "located": True,
        "explanation": answer,
        "sources": sources,
        "search_terms": terms,
        "total_hits": total_hits,
        "kind": "error" if is_error else "general",
    }
