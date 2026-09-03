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
- Sessions reuse service.session_store; the RAG branch mirrors
  service/main.ask's gating exactly (only "high" generates).
"""

import json
import re
import time
from typing import Any

import config
from rag import generator, retriever
from tools import erpnext, explain
from tools import search as code_search

NO_ANSWER = "I don't have a confident answer for this in the knowledge base."

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


def decide_route(question: str) -> tuple[str, str]:
    """Returns (route, how) where how ∈ {'heuristic','classifier','default'}."""
    lowered = question.lower()
    erp_score = sum(1 for h in _ERPNEXT_HINTS if h in lowered)
    code_score = sum(1 for h in _CODE_HINTS if h in lowered)
    if erp_score >= 2 and erp_score > code_score:
        return "erpnext", "heuristic"
    if code_score >= 1 and code_score > erp_score:
        return "code", "heuristic"
    if erp_score >= 1 and code_score == 0 and any(
            h in lowered for h in ("how many", "count of", "schema of")):
        return "erpnext", "heuristic"
    return _classify_with_llm(question)


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


def _classify_with_llm(question: str) -> tuple[str, str]:
    messages = [
        {"role": "system", "content": _CLASSIFIER_PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        raw = generator._complete(messages)
        route = json.loads(raw.strip()).get("route")
    except Exception:
        return "rag", "default"
    if route not in _ROUTES:
        return "rag", "default"
    return route, "classifier"


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
    session_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    mode: str = "developer",
) -> dict[str, Any]:
    """Route + execute + generate. Mirrors /ask's safety semantics.

    mode="employee" (Phase 7) restricts the SAME orchestrator: no code
    agent, no schema introspection, public-docs-only retrieval with the
    plain-language desk-user persona (least privilege per SECURITY.md).
    """
    route, how = decide_route(question)
    if mode not in ("developer", "employee"):
        return {"answer": f"Unknown mode {mode!r}.", "sources": [],
                "confidence": "low", "route": route, "route_how": how}

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
                "answer": (
                    f"Could not complete the live-instance lookup: {exc}"
                ),
                "sources": [], "confidence": "low",
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
        extra_system=version_preamble(), persona=mode)
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
