"""Phase 6 orchestrator/router: one brain, three hands.

Routes a developer question to the right capability (docs/ROADMAP.md
Phase 6; ARCHITECTURE.md "AI Orchestrator"):

  erpnext - questions about the LIVE instance: schemas, field values,
            document status, counts ("what fields does Customer have?")
  code    - questions about THIS repository's code / error location
            ("why does resolve_in_project raise on symlinks?")
  rag     - general ERPNext/Frappe developer knowledge (default)

Design rules:
- Deterministic overrides first (cheap, predictable); an LLM classifier
  only breaks ties; ANY classifier failure defaults to rag. Routing may
  be wrong, never fatal.
- Version-awareness (PROJECT.md non-negotiable): the connected
  instance's Frappe/ERPNext versions are fetched read-only, cached with
  a TTL, and injected into every generation prompt — answers must fit
  the ACTUAL installed version, not the latest docs.
- The single litellm call site stays rag.generator._complete.
- History arrives inline from Frappe-owned conversation records; the RAG
  branch mirrors service/main.ask's gating exactly (only "high" generates).
"""

import json
import re
import time
from typing import Any

import config
from rag import generator, retriever
from tools import erpnext, explain
from tools import search as code_search

import capabilities

NO_ANSWER = "I don't have a confident answer for this in the knowledge base."

CHAT_ONLY_CAPABILITIES = (
    "I can discuss ERPNext/Frappe and answer questions from the indexed "
    "knowledge base with citations when available. Live data lookups, file "
    "tools, edits, approvals and server session reset are unavailable in Desk chat."
)

CHAT_ONLY_UNAVAILABLE = (
    "That operation is unavailable in Desk chat. I can answer questions "
    "from indexed ERPNext/Frappe documentation, but cannot access live "
    "records, search files, make edits or execute approvals."
)

EMPLOYEE_OUT_OF_SCOPE = (
    "That question needs developer access to this project's source code, "
    "which isn't available in employee mode. Please ask your "
    "administrator or developer team."
)


def _looks_like_listing(question: str) -> bool:
    """True for "what files are in the project"-style directory questions.

    Three independent signals (interrogative + file-target + project
    scope) keep precision high: "show me files that mention X" has no
    scope word, "where is Y implemented" has no listing verb, so neither
    misfires into a directory dump.
    """
    t = question.lower()
    has_what = bool(re.search(
        r"\b(what|which|list|show|enumerate)\b", t))
    has_target = bool(re.search(
        r"\b(files?|directories|folders?|structure|tree|layout)\b", t))
    has_scope = bool(re.search(
        r"\b(project|repo|repository|root|codebase|workspace)\b", t))
    return has_what and has_target and has_scope


def _answer_listing(how: str) -> dict[str, Any]:
    """Deterministic project-tree answer from the live git index."""
    tree = code_search.list_project_files()
    return {
        "answer": (
            "Files currently in the project (live listing of the "
            f"repository file index, {tree['total']} files — not a "
            "description from documentation):\n\n" + tree["tree"]
        ),
        "sources": [{
            "title": "project file tree",
            "section": "live listing",
            "url_or_path": ".",
        }],
        "confidence": "high",
        "route": "code",
        "route_how": how + "+listing",
    }

_ROUTES = ("erpnext", "code", "rag")

# --- conversation hygiene --------------------------------------------------------
# Greetings and topic changes must never inherit prior-turn context
# (Phase 4 condensation carried a whole previous topic onto "hello").

_GREETING_RE = re.compile(
    r"^(hi|hey|hello|yo|sup|howdy|hiya|greetings|good\s?(morning|afternoon|"
    r"evening|day)|thanks?|thank\s?you|thx|bye|goodbye|see\s?you"
    r"|welcome|cheers)[\s!.,?]*$"
)

# Tokens showing the message refers back to earlier turns. Includes
# conversational past-tense verbs ("did you just cite") alongside classic
# pronouns — erring toward over-triggering is safe here because the
# condense prompt forbids adding facts, while under-triggering loses
# legitimate follow-ups entirely.
_ANAPHORA_RE = re.compile(
    r"\b(it|its|they|them|their|theirs|that|those|this|these|such|same|"
    r"above|previous|earlier|mentioned|said|discussed|instead|rather|"
    r"else|just|cite|cited)\b"
)


def is_greeting(text: str) -> bool:
    """True for standalone casual messages ("hey", "thanks!").

    Full-string match only: "hey, how do I create a customer?" is a real
    question with a greeting attached, not a greeting.
    """
    return bool(_GREETING_RE.match(text.strip().lower()))


def has_anaphora_reference(text: str) -> bool:
    """True if the message plausibly refers back to earlier turns."""
    return bool(_ANAPHORA_RE.search(text.lower()))


def should_condense_followup(history: list[dict[str, str]],
                             question: str) -> bool:
    """Gate for Phase 4 condensation: rewrite only anaphoric follow-ups.

    Greetings and self-contained topic changes retrieve on their own
    terms; otherwise a new message inherits the previous turn's topic
    ("hello" answered with last question's Sales Invoice content).
    """
    return (bool(history)
            and not is_greeting(question)
            and has_anaphora_reference(question))


_SMALLTALK_REPLY = (
    "Hey, I'm NexMate! I can look up ERPNext/Frappe docs, search this "
    "project's code, or check live data on your connected ERPNext "
    "instance. What do you need?"
)


def _answer_smalltalk(how: str) -> dict[str, Any]:
    """Deterministic greeting reply: no retrieval, no tools, no LLM."""
    return {
        "answer": _SMALLTALK_REPLY,
        "sources": [],
        "confidence": "high",
        "route": "smalltalk",
        "route_how": how,
        "fallback": None,
    }


# --- conversational understanding (Layer 1 fast-path + Layer 2 NLU) --------
# The fast path is a latency optimization for canonical strings ONLY.
# Spelling variants, slang, and colloquial phrasings ("hiii", "heyyy",
# "what can u do") are deliberately NOT listed here — the NLU layer
# below generalizes to them. Never grow this map into a phrase
# dictionary.

_EXACT_CONVERSATIONAL = {
    "hi": "greeting",
    "hey": "greeting",
    "hello": "greeting",
    "bye": "goodbye",
    "goodbye": "goodbye",
    "thanks": "thanks",
    "thank you": "thanks",
    "ok": "ack",
    "okay": "ack",
    "got it": "ack",
    "help": "capability",
}

_NLU_KINDS = ("conversational", "capability", "troubleshoot", "clarify",
              "out_of_scope", "task")
_NLU_SUBTYPES = ("greeting", "thanks", "goodbye", "ack", None)

_NLU_PROMPT = """You route messages for NexMate, an ERPNext/Frappe \
assistant. Classify the user's LATEST message into EXACTLY ONE kind, \
using the conversation history only to resolve references (pronouns, \
"that", ellipses, "what about X?" continuing a prior topic).

Kinds:
- "conversational": greetings, thanks, goodbyes, acknowledgements, pure \
chit-chat with no request. subtype: greeting|thanks|goodbye|ack.
- "capability": the user asks what the assistant itself can do or asks \
for help in general. subtype: null.
- "troubleshoot": something is broken, failing, or behaving unexpectedly \
and needs diagnosis. subtype: null.
- "clarify": too vague to act on — a bare topic word ("invoices"), a \
fragment, or a request missing the details needed to proceed. subtype: \
null.
- "out_of_scope": clearly not about ERPNext/Frappe, this project's code, \
or using the assistant (weather, jokes, sports, general trivia). \
subtype: null.
- "task": a concrete actionable request — how-to, live-data lookup, code \
question, error report, or a follow-up continuing the prior topic. \
subtype: null.

Also judge context_dependency ("none" or "follows_topic": the message \
only makes sense with prior turns) and your confidence 0..1 in this \
classification. "topic": a 1-4 word noun phrase naming the subject, or \
null when there isn't one.

Respond with ONLY a JSON object: {"kind": ..., "subtype": ...|null, \
"topic": ...|null, "context_dependency": "none"|"follows_topic", \
"confidence": 0..1}"""


def _normalize_conversational(question: str) -> str:
    return question.strip().lower().rstrip("!.,? ").strip()


def _understand_with_llm(
    question: str,
    history: list[dict[str, str]] | None,
) -> dict[str, Any] | None:
    """Classify the message; None when the output is unusable.

    One corrective retry on malformed JSON (same pattern as the ERPNext
    extractor). Callers must treat None as "unknown" — it must never
    route to a tool path by default. Both attempts use the short NLU
    budget (config.NLU_TIMEOUT_SECONDS) so a hung provider degrades to
    heuristic/clarify in seconds, not minutes.
    """
    user_content = f"Message: {question}"
    if history:
        user_content = (
            f"Conversation so far:\n{_format_history(history)}\n\n"
            f"Latest message: {question}"
        )
    messages = [
        {"role": "system", "content": _NLU_PROMPT},
        {"role": "user", "content": user_content},
    ]

    def _parse(text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"no JSON object in: {text[:120]}")
        parsed = json.loads(text[start:end + 1])
        if parsed.get("kind") not in _NLU_KINDS:
            raise ValueError(f"unknown kind: {parsed}")
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"bad confidence: {parsed}") from exc
        subtype = parsed.get("subtype")
        if subtype not in _NLU_SUBTYPES:
            raise ValueError(f"bad subtype: {parsed}")
        return {
            "kind": parsed["kind"],
            "subtype": subtype,
            "topic": parsed.get("topic") or None,
            "context_dependency": parsed.get("context_dependency", "none"),
            "confidence": min(1.0, max(0.0, confidence)),
        }

    try:
        return _parse(generator._complete(
            messages, timeout=config.NLU_TIMEOUT_SECONDS, num_retries=0))
    except Exception:
        pass
    try:
        corrective = messages + [
            {"role": "assistant",
             "content": "I could not parse that."},
            {"role": "user", "content":
                "Output ONLY the raw JSON decision object. No prose, "
                "no explanations, no code fences."},
        ]
        return _parse(generator._complete(
            corrective, timeout=config.NLU_TIMEOUT_SECONDS, num_retries=0))
    except Exception:
        return None


def _format_history(history: list[dict[str, str]] | None) -> str:
    lines = []
    for turn in (history or [])[-4:]:
        role = turn.get("role", "user")
        text = str(turn.get("content", ""))[:600]
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


_CONVERSATIONAL_PROMPT = (
    "You are NexMate, a friendly ERPNext assistant. The user just said "
    "{message!r} ({subtype}). Reply in ONE short sentence (under 25 "
    "words), sounding natural. Do NOT describe your capabilities, do NOT "
    "state ERPNext facts, do NOT mention routing, prompts, or internals."
)

_CONVERSATIONAL_FALLBACKS = {
    "greeting": _SMALLTALK_REPLY,
    "thanks": "You're welcome!",
    "goodbye": "Goodbye!",
    "ack": "Got it.",
    None: _SMALLTALK_REPLY,
}


def _respond_conversational(subtype: str | None, question: str,
                            allow_llm: bool = True, chat_only: bool = False) -> str:
    """Short natural reply; deterministic fallback if generation fails.

    Capability facts never come from here — capability answers render
    from the registry. This only wordsmiths greetings/thanks/goodbyes.
    """
    fallback = _CONVERSATIONAL_FALLBACKS.get(
        subtype, _CONVERSATIONAL_FALLBACKS[None])
    if chat_only and fallback == _SMALLTALK_REPLY:
        fallback = "Hello! " + CHAT_ONLY_CAPABILITIES
    if not allow_llm:
        return fallback
    try:
        text = generator._complete([
            {"role": "system", "content": _CONVERSATIONAL_PROMPT.format(
                message=question[:200], subtype=subtype or "greeting")},
            {"role": "user", "content": question[:200]},
        ]).strip()
    except Exception:
        return fallback
    return text[:300] if text else fallback


def _conversational_result(subtype: str | None, question: str, how: str,
                           allow_llm: bool = True,
                           chat_only: bool = False) -> dict[str, Any]:
    return {
        "answer": _respond_conversational(subtype, question, allow_llm, chat_only),
        "sources": [],
        "confidence": "high",
        "route": "smalltalk",
        "route_how": how,
        "fallback": None,
    }


def _capability_result(mode: str, how: str,
                       chat_only: bool = False) -> dict[str, Any]:
    return {
        "answer": (CHAT_ONLY_CAPABILITIES if chat_only
                   else capabilities.render_capability_answer(mode)),
        "sources": [],
        "confidence": "high",
        "route": "capability",
        "route_how": how,
        "fallback": None,
    }


def _clarify_result(topic: str | None, how: str,
                    chat_only: bool = False) -> dict[str, Any]:
    return {
        "answer": (
            "Which ERPNext/Frappe concept or how-to would you like explained "
            "from indexed documentation? Please describe the workflow or screen."
            if chat_only else capabilities.render_clarification(topic)
        ),
        "sources": [],
        "confidence": "low",
        "route": "clarify",
        "route_how": how,
        "fallback": "clarify",
    }


def _scope_result(how: str, chat_only: bool = False) -> dict[str, Any]:
    return {
        "answer": (
            "That's outside Desk chat's scope. I can answer ERPNext/Frappe "
            "how-to and concept questions from indexed documentation. "
            "Try asking how to create a Sales Invoice."
            if chat_only else capabilities.render_out_of_scope()
        ),
        "sources": [],
        "confidence": "low",
        "route": "out_of_scope",
        "route_how": how,
        "fallback": "scope",
    }


_TROUBLESHOOT_CLARIFY = (
    "To diagnose this I need a bit more detail: what's the exact error "
    "message or traceback (if any), what were you trying to do, and "
    "which DocType or screen was involved? Paste the error text if you "
    "have it."
)


def _troubleshoot_clarify_result(how: str,
                                 chat_only: bool = False) -> dict[str, Any]:
    return {
        "answer": (
            "Which ERPNext/Frappe workflow or screen is giving you trouble, "
            "and what did you expect to happen? I can explain relevant "
            "guidance from indexed documentation."
            if chat_only else _TROUBLESHOOT_CLARIFY
        ),
        "sources": [],
        "confidence": "low",
        "route": "clarify",
        "route_how": how,
        "fallback": "clarify",
    }

# --- version awareness ---------------------------------------------------------

_versions_cache: dict[str, Any] = {"fetched_at": 0.0, "data": None}

def get_instance_versions(force: bool = False) -> dict[str, str]:
    """{'frappe': '16.31.0', 'erpnext': '16.32.3', 'status': 'live'|'unknown'}"""
    ttl = config.ORCHESTRATOR_VERSION_TTL_SECONDS
    if not force and _versions_cache["data"] is not None \
            and time.time() - _versions_cache["fetched_at"] < ttl:
        return _versions_cache["data"]
    try:
        envelope = erpnext.call_method("frappe.utils.change_log.get_versions")
        message = envelope.get("message", {}) if isinstance(envelope, dict) else {}
        data = {
            "frappe": str(message.get("frappe", {}).get("version", "unknown")),
            "erpnext": str(message.get("erpnext", {}).get("version", "unknown")),
            "status": "live",
        }
        if data["frappe"] == "unknown" and data["erpnext"] == "unknown":
            raise erpnext.ErpnextApiError(502, "no versions in payload")
    except Exception:
        # Instance down or method missing: degrade HONESTLY — answers still
        # work, they just carry no live-version authority.
        data = {"frappe": "unknown", "erpnext": "unknown",
                "status": "unavailable"}
    _versions_cache["fetched_at"] = time.time()
    _versions_cache["data"] = data
    return data


def unavailable_versions() -> dict[str, str]:
    return {"frappe": "unknown", "erpnext": "unknown", "status": "unavailable"}


def version_preamble() -> str:
    v = get_instance_versions()
    if v["status"] != "live":
        return ""
    return (
        f"\n\nThe connected ERPNext instance runs Frappe {v['frappe']} and "
        f"ERPNext {v['erpnext']}. Answers MUST be valid for those exact "
        f"versions; if a passage describes different behavior, say so "
        f"explicitly instead of blending versions."
    )


# --- routing -------------------------------------------------------------------

_ERPNEXT_HINTS = (
    "how many", "count of", "in our erpnext", "in the erpnext", "in our "
    "instance", "in the instance", "on our site", "live instance",
    "what fields does", "which fields does", "schema of", "docstatus",
    "is submitted", "are submitted", "submitted ", "draft ", "list all ",
    "show me the ", "current value", "what is the status of",
)
_CODE_HINTS = (
    "in this repo", "in this project", "this codebase", "our code",
    "our repo", "why does it fail", "why do we", "traceback",
    "stack trace", "raises when", "where is it implemented",
    "which function implements", "in tools/", "in rag/", "in service/",
)


def _heuristic_route(question: str) -> str | None:
    """Deterministic task signals only; None when nothing fires.

    Shared by decide_route (which falls through to the LLM classifier)
    and by the degraded path when NLU classification itself fails — that
    path may only proceed on a strong heuristic hit, never by default.
    """
    lowered = question.lower()
    erp_score = sum(1 for h in _ERPNEXT_HINTS if h in lowered)
    code_score = sum(1 for h in _CODE_HINTS if h in lowered)
    if erp_score >= 2 and erp_score > code_score:
        return "erpnext"
    if code_score >= 1 and code_score > erp_score:
        return "code"
    if erp_score >= 1 and code_score == 0 and any(
            h in lowered for h in ("how many", "count of", "schema of")):
        return "erpnext"
    return None


def decide_route(question: str,
                 history: list[dict[str, str]] | None = None
                 ) -> tuple[str, str]:
    """Returns (route, how) where how ∈ {'heuristic','classifier','default'}.

    History is history-free for the heuristic (deterministic signals only)
    but threads into the LLM tiebreaker so elliptical follow-ups ("what
    about Purchase Invoices?") resolve against the prior topic instead of
    being classified as a bare live-data/code probe.
    """
    heuristic = _heuristic_route(question)
    if heuristic is not None:
        return heuristic, "heuristic"
    return _classify_with_llm(question, history)


_CLASSIFIER_PROMPT = """Classify the developer question into EXACTLY ONE \
route:
- "erpnext": needs data from the LIVE ERPNext instance right now — doc \
schemas, field lists, document values/status, counts of records. Clues: \
"how many", "what fields does X have", "status of", naming a concrete \
DocType's current data.
- "code": about THIS project repository's own source code or behavior — \
its files, functions, why its code raises errors.
- "rag": general ERPNext/Frappe development knowledge answerable from \
official documentation (how-to, concepts, hooks, API usage).

Answer with ONLY a JSON object: {"route": "erpnext"|"code"|"rag"}"""


def _classify_with_llm(question: str,
                       history: list[dict[str, str]] | None = None
                       ) -> tuple[str, str]:
    # History rides in the user message (same shape as the NLU layer),
    # never as prompt surgery: the system instruction stays byte-identical
    # so the small model's JSON discipline doesn't degrade when context
    # is present. One corrective retry on malformed output, same pattern
    # as the NLU verdict and the ERPNext extractor.
    user_content = question
    if history:
        # Same context the NLU layer used: the tiebreaker must see what
        # "what about X?" refers to. History never overrides an explicit
        # signal — the heuristic already ran and declined.
        user_content = (
            f"Conversation so far:\n{_format_history(history)}\n\n"
            f"Question: {question}"
        )
    messages = [
        {"role": "system", "content": _CLASSIFIER_PROMPT},
        {"role": "user", "content": user_content},
    ]

    def _parse(text: str) -> str:
        route = json.loads(text.strip()).get("route")
        if route not in _ROUTES:
            raise ValueError(f"unusable route: {text[:120]}")
        return route

    try:
        return _parse(generator._complete(messages)), "classifier"
    except Exception:
        pass
    try:
        corrective = messages + [
            {"role": "assistant",
             "content": "I could not parse that."},
            {"role": "user", "content":
                'Output ONLY the raw JSON object, e.g. {"route": "rag"}. '
                "No prose, no explanations, no code fences."},
        ]
        return _parse(generator._complete(corrective)), "classifier"
    except Exception:
        return "rag", "default"


# Frappe's body for an unknown DocType, e.g.
# '..."message":"DocType Invoices not found",...'. A 404 carrying this
# shape means the EXTRACTED name is wrong (often a pluralized guess like
# "Invoices"), not that the instance is down or the records are missing.
_UNKNOWN_DOCTYPE_RE = re.compile(r"DocType (.+?) not found")


def _unknown_doctype_name(exc: Exception) -> str | None:
    """The bad DocType name when exc is Frappe's unknown-DocType 404."""
    if isinstance(exc, erpnext.ErpnextApiError) and exc.status == 404:
        match = _UNKNOWN_DOCTYPE_RE.search(str(exc))
        if match:
            return match.group(1)
    return None


def _lookup_failure_answer(exc: Exception) -> str:
    unknown = _unknown_doctype_name(exc)
    if unknown is None:
        return f"Could not complete the live-instance lookup: {exc}"
    return (
        f"I couldn't complete that lookup: there is no DocType called "
        f"'{unknown}' on the connected ERPNext instance, so that name "
        f"was likely misheard. DocType names are singular — for example "
        f"'Sales Invoice' or 'Purchase Invoice'. Tell me which one you "
        f"meant and I'll look it up."
    )


# --- erpnext branch --------------------------------------------------------------

_EXTRACT_PROMPT = """Extract what the question needs from the LIVE \
ERPNext instance as JSON ONLY:
{"op": "schema"|"document"|"list",
 "doctype": "<DocType name>",
 "name": "<exact document name, only for op=document>",
 "fields": ["fieldnames"], "filters": {"field": value},
 "limit": <int, only for op=list>}
Rules: op=schema asks what a DocType contains; op=document needs one \
specific record by name; op=list asks for records/counts/status. Use \
standard Frappe DocType names (Customer, Sales Order, User...). Omit keys \
that don't apply. Output ONLY the raw JSON object - no prose, no code \
fences."""


def _extract_erpnext_request(question: str) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": _EXTRACT_PROMPT},
        {"role": "user", "content": question},
    ]

    def _parse(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        # tolerate ```json fences and leading/trailing prose
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"no JSON object in: {text[:120]}")
        return json.loads(cleaned[start:end + 1])

    def _validate(parsed: dict[str, Any]) -> dict[str, Any]:
        op = parsed.get("op")
        doctype = (parsed.get("doctype") or "").strip()
        if op not in ("schema", "document", "list") or not doctype:
            raise ValueError(f"unusable extraction: {parsed}")
        if op == "document" and not (parsed.get("name") or "").strip():
            # A document lookup without a name is not executable — refuse
            # here instead of invoking the tool with a missing argument.
            raise ValueError(f"document op needs a name: {parsed}")
        return parsed

    try:
        return _validate(_parse(generator._complete(messages)))
    except (ValueError, json.JSONDecodeError):
        pass
    # ONE corrective escalation — small models sometimes narrate first.
    messages = messages + [
        {"role": "assistant",
         "content": "I could not parse that."},
        {"role": "user", "content":
            "Output ONLY the raw JSON object matching the schema. No "
            "prose, no explanations, no code fences."},
    ]
    return _validate(_parse(generator._complete(messages)))


def run_erpnext_branch(question: str,
                       preextracted: dict[str, Any] | None = None
                       ) -> dict[str, Any]:
    request = preextracted or _extract_erpnext_request(question)
    op = request["op"]
    doctype = request["doctype"]
    if op == "schema":
        payload = erpnext.get_doctype_schema(doctype)["data"]
        summary = {
            "doctype": payload.get("doctype"),
            "module": payload.get("module"),
            "naming_rule": payload.get("naming_rule"),
            "is_submittable": payload.get("is_submittable"),
            "field_count": len(payload.get("fields", [])),
            "fields": [
                {k: f.get(k) for k in ("fieldname", "fieldtype", "label")}
                for f in payload.get("fields", [])
            ],
        }
    elif op == "document":
        payload = erpnext.get_document(
            doctype, request.get("name", ""))["data"]
        summary = {"doctype": doctype, "document": payload}
    else:
        listed = erpnext.list_documents(
            doctype,
            filters=request.get("filters"),
            fields=request.get("fields"),
            limit=request.get("limit", config.ERPNEXT_DEFAULT_LIST_LIMIT),
        )
        summary = listed

    passages = json.dumps(summary, indent=2, default=str)
    messages = [
        {"role": "system", "content":
            "You answer questions about the user's LIVE ERPNext instance "
            "using ONLY the numbered JSON payloads provided. They are real "
            "instance responses — treat them as ground truth. Cite the "
            "payload number like [1] next to every claim. If the payload "
            "does not contain what was asked, say so plainly."
            + version_preamble()},
        {"role": "user",
         "content": f"Question: {question}\n\nPayload:\n[1] {passages}"},
    ]
    answer = generator._complete(messages)
    ungrounded = generator._ungrounded_identifiers(answer, [
        {"text": passages}])
    if ungrounded:
        listing = "; ".join(ungrounded[:8])
        messages = messages + [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": (
                f"These identifiers appear NOWHERE in the payload: "
                f"{listing}. Rewrite using only identifiers visible in the "
                f"payload, keeping [1]-style citations.")},
        ]
        answer = generator._complete(messages)

    sources = [{
        "title": f"live ERPNext: {doctype}",
        "section": op,
        "url_or_path": f"{erpnext.__name__}://{doctype}"
                        + (f"/{request['name']}" if op == "document" else ""),
    }]
    return {
        "answer": answer,
        "sources": sources,
        "confidence": "high",
        "route_meta": {"op": op, "doctype": doctype},
    }


# --- entry point -------------------------------------------------------------

def handle_question(
    question: str,
    conversation_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    mode: str = "developer",
    *,
    chat_only: bool = False,
) -> dict[str, Any]:
    """Route + execute + generate. Mirrors /ask's safety semantics.

    Layered routing: Layer 1 exact fast-path (canonical strings only,
    zero model calls) → Layer 2 NLU understanding → task pipeline
    (existing heuristic + classifier router). NLU failure degrades to
    heuristic-only task routing, else safe clarification — conversational
    input is never blind-fallbacked into RAG.

    mode="employee" (Phase 7) restricts the SAME orchestrator: no code
    agent, no schema introspection, public-docs-only retrieval with the
    plain-language desk-user persona (least privilege per SECURITY.md).

    The result always carries the internal NLU verdict (nlu_kind,
    nlu_confidence, nlu_topic) for structured telemetry. These keys are
    observability only — service/main.py logs them, never sends them to
    the user.
    """
    tag: dict[str, Any] = {}
    out = _handle_question_inner(question, conversation_id, history, mode, tag, chat_only)
    out = dict(out)
    out.setdefault("nlu_kind", tag.get("nlu_kind"))
    out.setdefault("nlu_confidence", tag.get("nlu_confidence"))
    out.setdefault("nlu_topic", tag.get("nlu_topic"))
    out.setdefault("refined_question", tag.get("refined_question"))
    return out


def _handle_question_inner(
    question: str,
    conversation_id: str | None,
    history: list[dict[str, str]] | None,
    mode: str,
    tag: dict[str, Any],
    chat_only: bool = False,
) -> dict[str, Any]:
    """Body of handle_question; records its NLU verdict into tag.

    Every return path leaves tag holding the classification behind the
    routing decision (or the exact/degraded marker when no model verdict
    exists), so the wrapper can attach it for telemetry.
    """
    # Layer 1 — tiny exact fast-path for canonical strings.
    exact = _EXACT_CONVERSATIONAL.get(_normalize_conversational(question))
    tag.update(nlu_kind=None, nlu_confidence=None, nlu_topic=None)
    if exact is not None:
        tag.update(nlu_kind=f"exact:{exact}", nlu_confidence=1.0,
                   nlu_topic=None)
    if exact == "capability":
        return _capability_result(mode, "heuristic", chat_only)
    if exact is not None:
        return _conversational_result(exact, question, "heuristic",
                                      allow_llm=False, chat_only=chat_only)
    if mode not in ("developer", "employee"):
        return {"answer": f"Unknown mode {mode!r}.", "sources": [],
                "confidence": "low", "route": "smalltalk",
                "route_how": "default", "fallback": None}
    # Layer 2 — NLU understanding over the message + recent history.
    nlu = _understand_with_llm(question, history)
    if nlu is None:
        tag.update(nlu_kind="degraded", nlu_confidence=None,
                   nlu_topic=None)
        # Degraded: classification itself failed. Only a strong heuristic
        # signal may proceed to the task pipeline; otherwise clarify
        # safely instead of executing a possibly-wrong tool path.
        degraded = _heuristic_route(question)
        if degraded is None:
            return _clarify_result(None, "degraded", chat_only)
        route, how = degraded, "degraded"
    else:
        tag.update(nlu_kind=nlu["kind"],
                   nlu_confidence=nlu.get("confidence"),
                   nlu_topic=nlu.get("topic"))
        kind = nlu["kind"]
        if kind == "conversational":
            return _conversational_result(
                nlu.get("subtype"), question, "classifier", chat_only=chat_only)
        if kind == "capability":
            return _capability_result(mode, "classifier", chat_only)
        if kind == "clarify":
            return _clarify_result(nlu.get("topic"), "classifier", chat_only)
        if kind == "out_of_scope":
            return _scope_result("classifier", chat_only)
        if kind == "troubleshoot":
            # Troubleshooting reuses existing capabilities only: error
            # text goes down the code-explain path, anything vaguer gets
            # a targeted clarification. No fan-out, no new agents.
            if explain.looks_like_error(question):
                route, how = "code", "classifier"
            else:
                return _troubleshoot_clarify_result("classifier", chat_only)
        else:  # task
            if nlu.get("confidence", 0.0) < config.NLU_MIN_CONFIDENCE:
                return _clarify_result(nlu.get("topic"), "classifier", chat_only)
            if (history and nlu.get("context_dependency") == "follows_topic"
                    and nlu.get("topic")):
                # Elliptical continuation ("what about Purchase
                # Invoices?") retrieves nothing on its own terms — the
                # anchored rewrite ("How do I create a Purchase Invoice?")
                # does. Reuses the Phase 4 condenser; None keeps the raw
                # question, so this is retrieval-quality aid, not safety.
                # Greetings/capability/new topics never reach here (they
                # return before the task branch), so old context cannot
                # contaminate unrelated messages.
                condensed = generator.condense_followup(history, question)
                if condensed:
                    question = condensed
                    tag["refined_question"] = condensed
            route, how = decide_route(question, history)

    if chat_only and route in ("code", "erpnext"):
        return {
            "answer": CHAT_ONLY_UNAVAILABLE,
            "sources": [],
            "confidence": "low",
            "route": route,
            "route_how": how + "+chat-only-denied",
        }

    if route == "code":
        if mode == "employee":
            # Least privilege: the code agent is developer-only.
            return {
                "answer": EMPLOYEE_OUT_OF_SCOPE,
                "sources": [],
                "confidence": "low",
                "route": route,
                "route_how": how + "+denied",
            }
        if _looks_like_listing(question):
            # Deterministic answer from the live git index — never let
            # vision/planning docs stand in for a directory listing.
            return _answer_listing(how)
        result = explain.locate_and_explain(question)
        if result.get("located"):
            # explain sources are {path,line_start,line_end}; map to the
            # unified citation shape so the UI renders them consistently
            sources = [{
                "title": s["path"],
                "section": f"lines {s['line_start']}-{s['line_end']}",
                "url_or_path": s["path"],
                "line_start": s.get("line_start"),
                "line_end": s.get("line_end"),
            } for s in result["sources"]]
            return {
                "answer": result["explanation"],
                "sources": sources,
                "confidence": "high",
                "route": route,
                "route_how": how,
            }
        return {
            "answer": NO_ANSWER,
            "sources": [],
            "confidence": "low",
            "route": route,
            "route_how": how,
        }

    if route == "erpnext":
        try:
            request = _extract_erpnext_request(question)
            if mode == "employee" and request.get("op") == "schema":
                # Schema introspection is developer territory; employees
                # get document/list lookups only.
                out = {
                    "answer": (
                        "DocType schemas are a developer/administrator "
                        "view and aren't available in employee mode. If "
                        "you need a document or a list (for example your "
                        "open orders), just ask for that instead."
                    ),
                    "sources": [], "confidence": "low",
                    "route_meta": {"op": request.get("op"),
                                   "doctype": request.get("doctype")},
                }
            else:
                out = run_erpnext_branch(
                    question, preextracted=request)
        except (erpnext.ErpnextUnavailable, erpnext.ErpnextApiError,
                ValueError, json.JSONDecodeError) as exc:
            out = {
                "answer": _lookup_failure_answer(exc),
                "sources": [], "confidence": "low",
                "fallback": "lookup-failure",
            }
        out.update({"route": route, "route_how": how})
        return out

    # RAG branch — same gates as /ask (only "high" generates). Company
    # material joins retrieval ONLY for project-scoped questions in
    # DEVELOPER mode; employees always get public docs only, answered
    # with the plain-language persona.
    lowered = question.lower()
    scoped = (mode == "developer") and any(
        h in lowered for h in config.PROJECT_SCOPE_HINTS)
    chunks = retriever.retrieve(question, include_company=scoped)
    confidence = retriever.classify_confidence(chunks, question)
    if confidence != "high":
        sources = [] if confidence == "no_match" else [
            {"title": c["title"], "section": c["section"],
             "url_or_path": c["url_or_path"]} for c in chunks]
        return {
            "answer": NO_ANSWER,
            "sources": sources,
            "confidence": confidence,
            "route": route,
            "route_how": how,
        }
    history = history or []
    answer = generator.generate_answer(
        question, chunks, history,
        extra_system="" if chat_only else version_preamble(), persona=mode)
    return {
        "answer": answer,
        "sources": [
            {"title": c["title"], "section": c["section"],
             "url_or_path": c["url_or_path"],
             "source_type": c.get("source_type", "")}
            for c in chunks
        ],
        "confidence": confidence,
        "route": route,
        "route_how": how,
    }
