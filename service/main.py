"""FastAPI service exposing the Phase 1 RAG pipeline.

Contract (docs/PHASE_1_SPEC.md):

    POST /ask  {"question": "..."}
    -> {"answer": "...", "sources": [{"title", "section", "url_or_path"}],
        "confidence": "high" | "low" | "no_match"}

A "no_match" response carries the honest no-answer message and NO sources —
the UI renders it as visibly distinct from a real answer. Run locally bound
to localhost only (SECURITY.md).
"""

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
import logging

logger = logging.getLogger("nexmate")
# Uvicorn's default logging setup leaves non-uvicorn loggers without a
# handler at WARNING level, which silently swallowed this service's
# structured telemetry. Attach our own stderr handler so decision logs
# always emit regardless of the ASGI server's logging config.
if not logger.handlers:
    _telemetry_handler = logging.StreamHandler()
    _telemetry_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_telemetry_handler)
logger.setLevel(logging.INFO)

import config
from rag import generator, retriever
from service import session_store
from service.auth import ServiceAuthMiddleware, validate_gateway_envelope
from tools import edit as edit_tool
from tools import erpnext as erpnext_tool
from tools import erpnext_write as erpnext_write_tool
from tools import explain as explain_tool
from tools import files
from tools import search as search_tool
from tools.pathsafe import PathOutsideRootError

import orchestrator

NO_ANSWER = "I don't have a confident answer for this in the knowledge base."


class AskRequest(BaseModel):
    # Transport validity only: non-blank, bounded size. Short messages
    # ("hi", "ok") are conversationally valid — length must never decide
    # that. Blank-only input is not a message and is still rejected.
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(
        None, pattern=r"[A-Za-z0-9_-]{1,64}",
        description="optional thread id; enables server-side continuity",
    )

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v


class Source(BaseModel):
    title: str
    section: str
    url_or_path: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    confidence: Literal["high", "low", "no_match"]
    session_id: str | None = None
    turn_count: int | None = None
    condensed_question: str | None = None


class SessionResetRequest(BaseModel):
    session_id: str = Field(pattern=r"[A-Za-z0-9_-]{1,64}")


class SessionResetResponse(BaseModel):
    cleared: bool


class ReadFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class ReadFileResponse(BaseModel):
    path: str
    absolute_path: str
    content: str
    size_bytes: int
    line_count: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    ignore_case: bool = False


class SearchMatch(BaseModel):
    path: str
    line_number: int
    line: str


class SearchResponse(BaseModel):
    query: str
    regex_source: str
    literal_fallback: bool
    ignore_case: bool
    matches: list[SearchMatch]
    total_matches: int
    truncated: bool
    files_searched: int
    skipped_binary: int
    skipped_large: int


class ExplainRequest(BaseModel):
    description: str = Field(min_length=8, max_length=4000)


class ExplainSource(BaseModel):
    path: str
    line_start: int
    line_end: int


class ExplainResponse(BaseModel):
    located: bool
    explanation: str
    sources: list[ExplainSource]
    search_terms: list[str]
    total_hits: int


class ProposeEditRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    find: str = Field(min_length=1)
    replace: str = ""
    message: str = Field(min_length=10, max_length=500)
    context: str = Field(
        "", max_length=2000,
        description="question/explanation that motivated this edit; "
                    "indexed as resolved-issue memory on apply",
    )


class EditProposalResponse(BaseModel):
    proposal_id: str
    path: str
    diff: str
    message: str
    expires_minutes: int


class ApplyEditRequest(BaseModel):
    proposal_id: str = Field(min_length=4, max_length=64)
    confirmed: bool


class EditApplyResponse(BaseModel):
    applied: bool
    path: str
    commit_hash: str
    message: str
    diff: str
    memory: dict = {}


class ErpnextSchemaRequest(BaseModel):
    doctype: str = Field(min_length=1, max_length=140)


class ErpnextDocumentRequest(BaseModel):
    doctype: str = Field(min_length=1, max_length=140)
    name: str = Field(min_length=1, max_length=140)


class ErpnextListRequest(BaseModel):
    doctype: str = Field(min_length=1, max_length=140)
    filters: dict | None = None
    fields: list[str] | None = None
    limit: int = Field(config.ERPNEXT_DEFAULT_LIST_LIMIT, ge=1, le=100)
    order_by: str | None = Field(None, max_length=140)


class OrchestrateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: Any = None
    site: Any = None
    execution_scope: Any = None

    # Same transport-validity contract as AskRequest: non-blank and
    # bounded. Conversational validity is the router's job, not the
    # schema's.
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(
        None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    mode: Literal["developer", "employee"] = "developer"

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v


class OrchestrateSource(BaseModel):
    title: str
    section: str
    url_or_path: str
    source_type: str | None = None
    line_start: int | None = None
    line_end: int | None = None


class OrchestrateResponse(BaseModel):
    answer: str
    sources: list[OrchestrateSource]
    confidence: Literal["high", "low", "no_match"]
    route: Literal["erpnext", "code", "rag", "smalltalk",
                   "capability", "clarify", "out_of_scope"]
    route_how: str
    mode: Literal["developer", "employee"]
    version_info: dict
    session_id: str | None = None
    turn_count: int | None = None
    condensed_question: str | None = None


class ErpnextWriteProposeRequest(BaseModel):
    action: Literal["create", "update"]
    doctype: str = Field(min_length=1, max_length=140)
    payload: dict
    reason: str = Field(min_length=10, max_length=1000)
    name: str | None = Field(None, max_length=140)


class ErpnextWriteProposalResponse(BaseModel):
    proposal_id: str
    action: str
    doctype: str
    name: str
    preview: dict
    reason: str
    expires_minutes: int
    env_label: str


class ErpnextWriteApplyRequest(BaseModel):
    proposal_id: str = Field(min_length=4, max_length=64)
    confirmed: bool


class ErpnextWriteApplyResponse(BaseModel):
    applied: bool
    action: str
    doctype: str
    name: str
    result: dict
    audited: bool


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Fail loud at startup if the vector store is missing/unreadable,
    # rather than serving errors on every request.
    retriever.get_index()
    yield


app = FastAPI(title="NexMate — Your ERPNext AI Companion", lifespan=_lifespan)

# Standalone UI preview: serves the same bundle a Frappe bench injects,
# so the sidebar can be exercised without a bench (docs/UI_SPEC.md).
_ui_dir = config.ROOT_DIR / "frappe_app" / "public"
if _ui_dir.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/ui", StaticFiles(directory=str(_ui_dir), html=True),
              name="ui")

# The Frappe desk page calls this service from a different origin (the
# ERPNext site), so browsers need CORS headers. Origins are configurable
# for production; the permissive default is acceptable only because the
# service holds no secrets and binds to localhost (SECURITY.md).
_cors_origins = os.environ.get("COPILOT_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)
app.add_middleware(ServiceAuthMiddleware)


@app.exception_handler(RequestValidationError)
async def safe_orchestrate_validation(request: Request, exc: RequestValidationError):
    if request.url.path == "/orchestrate":
        return JSONResponse({"detail": "invalid_orchestrate_request"}, status_code=422)
    return await request_validation_exception_handler(request, exc)


def _dedupe_sources(chunks: list[dict[str, Any]]) -> list[Source]:
    """One citation per distinct (document, section), in retrieval order."""
    seen: set[tuple[str, str]] = set()
    sources: list[Source] = []
    for c in chunks:
        key = (c["url_or_path"], c["section"])
        if key not in seen:
            seen.add(key)
            sources.append(Source(
                title=c["title"], section=c["section"],
                url_or_path=c["url_or_path"],
            ))
    return sources


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    history: list[dict[str, str]] = []
    if req.session_id:
        try:
            history = session_store.load_history(req.session_id)
        except session_store.InvalidSessionId as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Phase 4: anaphoric follow-ups ("which constant did you cite?") don't
    # retrieve on their own terms — condense against the conversation
    # BEFORE retrieval. Best-effort: on failure we fall back to the raw
    # question (stateless semantics). Gates downstream stay absolute.
    search_question = req.question
    condensed: str | None = None
    if orchestrator.should_condense_followup(history, req.question):
        candidate = generator.condense_followup(history, req.question)
        if candidate:
            condensed = candidate
            search_question = candidate

    try:
        chunks = retriever.retrieve(search_question)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    confidence = retriever.classify_confidence(chunks, search_question)
    answer = (
        NO_ANSWER if confidence in ("no_match", "low")
        else generator.generate_answer(req.question, chunks, history)
    )

    turn_count: int | None = None
    if req.session_id:
        try:
            # Persist BOTH sides of the exchange so the next call sees it.
            n1 = session_store.append_turn(
                req.session_id, "user", req.question)
            n2 = session_store.append_turn(
                req.session_id, "assistant", answer)
            turn_count = min(n1, n2)
        except (session_store.InvalidSessionId, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if confidence == "no_match":
        return AskResponse(answer=answer, sources=[],
                           confidence="no_match",
                           session_id=req.session_id,
                           turn_count=turn_count,
                           condensed_question=condensed)
    if confidence == "low":
        return AskResponse(answer=answer,
                           sources=_dedupe_sources(chunks),
                           confidence="low",
                           session_id=req.session_id,
                           turn_count=turn_count,
                           condensed_question=condensed)

    return AskResponse(
        answer=answer, sources=_dedupe_sources(chunks), confidence=confidence,
        session_id=req.session_id, turn_count=turn_count,
        condensed_question=condensed,
    )


@app.post("/tools/session/reset", response_model=SessionResetResponse)
def tools_session_reset(req: SessionResetRequest) -> SessionResetResponse:
    """"Start fresh": clears the visible thread. Resolved-issue knowledge
    indexed in Chroma is permanent and deliberately untouched."""
    try:
        cleared = session_store.delete_session(req.session_id)
    except session_store.InvalidSessionId as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SessionResetResponse(cleared=cleared)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/read_file", response_model=ReadFileResponse)
def tools_read_file(req: ReadFileRequest) -> ReadFileResponse:
    """Tier-1 read_file (docs/PHASE_2_SPEC.md): always-on, no confirmation.

    Rejections are loud and explained, never silent redirects:
      400 - path resolves outside PROJECT_ROOT (traversal, symlink escape)
      404 - file does not exist / 400 non-file or unreadable content
      413 - file exceeds MAX_READ_FILE_BYTES
    """
    try:
        info = files.read_project_file(req.path)
    except PathOutsideRootError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (files.NotAFileError, files.BinaryFileError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except files.FileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except OSError as exc:  # permissions, I/O errors — fail loud
        raise HTTPException(status_code=500, detail=f"Read failed: {exc}") from exc

    return ReadFileResponse(**info)


@app.post("/tools/search", response_model=SearchResponse)
def tools_search(req: SearchRequest) -> SearchResponse:
    """Tier-1 code search (grep-equivalent, gitignore-aware). Always-on."""
    try:
        result = search_tool.search_project(req.query, req.ignore_case)
    except search_tool.SearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SearchResponse(**result)


@app.post("/tools/explain", response_model=ExplainResponse)
def tools_explain(req: ExplainRequest) -> ExplainResponse:
    """Tier-1 explain: locate relevant code and explain the cause,
    grounded in what the files actually contain. Always-on."""
    try:
        result = explain_tool.locate_and_explain(req.description)
    except RuntimeError as exc:  # generation/provider failures — fail loud
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # unexpected tool failure — surface, not hide
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ExplainResponse(**result)


_REFUSAL_STATUS = {
    "dirty_tree": 409,
    "outside_root": 400,
    "not_found": 404,
    "untracked_file": 400,
    "ignored_file": 400,
    "ambiguous_match": 400,
    "no_op": 400,
    "bad_request": 400,
    "bad_message": 400,
    "binary_file": 400,
    "confirmation_required": 400,
    "unknown_proposal": 404,
    "expired_proposal": 410,
    "stale_proposal": 409,
}


def _refuse_as_http(exc: "edit_tool.EditRefusal") -> HTTPException:
    return HTTPException(
        status_code=_REFUSAL_STATUS.get(exc.category, 400),
        detail=f"[{exc.category}] {exc.detail}",
    )


@app.post("/tools/propose_edit", response_model=EditProposalResponse)
def tools_propose_edit(req: ProposeEditRequest) -> EditProposalResponse:
    """Tier-2 step 1: validate the edit and return it as a unified diff.

    Applies NOTHING. Every SECURITY.md gate runs here (clean tree, root
    scoping, tracked-not-ignored, unique match) so problems surface before
    the user reviews a diff.
    """
    try:
        proposal = edit_tool.propose_edit(
            req.path, req.find, req.replace, req.message, req.context
        )
    except edit_tool.EditRefusal as exc:
        raise _refuse_as_http(exc) from exc
    return EditProposalResponse(**proposal)


@app.post("/tools/apply_edit", response_model=EditApplyResponse)
def tools_apply_edit(req: ApplyEditRequest) -> EditApplyResponse:
    """Tier-2 step 2: apply a proposal after explicit confirmation.

    Re-checks every gate at apply time (tree still clean, file unchanged
    since proposal), then writes + stages + commits that ONE file.
    """
    try:
        result = edit_tool.apply_edit(req.proposal_id, req.confirmed)
    except edit_tool.EditRefusal as exc:
        raise _refuse_as_http(exc) from exc
    return EditApplyResponse(**result)


def _erpnext_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, erpnext_tool.ErpnextUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, erpnext_tool.ErpnextApiError) and exc.status != 413:
        return HTTPException(status_code=exc.status,
                             detail=f"ERPNext: {exc}")
    if isinstance(exc, erpnext_tool.ErpnextApiError):
        return HTTPException(status_code=413, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.post("/tools/erpnext/schema")
def tools_erpnext_schema(req: ErpnextSchemaRequest) -> dict:
    """Phase 5 read-only tool: live DocType schema (fields, perms, naming)."""
    try:
        return erpnext_tool.get_doctype_schema(req.doctype)
    except (erpnext_tool.ErpnextUnavailable,
            erpnext_tool.ErpnextApiError) as exc:
        raise _erpnext_http_error(exc) from exc


@app.post("/tools/erpnext/document")
def tools_erpnext_document(req: ErpnextDocumentRequest) -> dict:
    """Phase 5 read-only tool: one live document by exact name."""
    try:
        return erpnext_tool.get_document(req.doctype, req.name)
    except (erpnext_tool.ErpnextUnavailable,
            erpnext_tool.ErpnextApiError) as exc:
        raise _erpnext_http_error(exc) from exc


@app.post("/tools/erpnext/list")
def tools_erpnext_list(req: ErpnextListRequest) -> dict:
    """Phase 5 read-only tool: filtered document list (light fields)."""
    try:
        return erpnext_tool.list_documents(
            req.doctype, filters=req.filters, fields=req.fields,
            limit=req.limit, order_by=req.order_by,
        )
    except (erpnext_tool.ErpnextUnavailable,
            erpnext_tool.ErpnextApiError) as exc:
        raise _erpnext_http_error(exc) from exc


@app.post("/orchestrate", response_model=OrchestrateResponse)
def orchestrate(req: OrchestrateRequest, request: Request) -> OrchestrateResponse:
    """Phase 6: single entry point routing between RAG, code agent, and
    the live ERPNext tool; injects live instance versions into prompts.

    Sessions behave like /ask (condense-then-retrieve on follow-ups);
    routing happens on the CONDENSED question when a session is active.
    """
    chat_only = validate_gateway_envelope(req.model_dump(), req.model_fields_set, request)
    import json as _json
    request_id = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    history: list[dict[str, str]] = []
    if req.session_id:
        try:
            history = session_store.load_history(req.session_id)
        except session_store.InvalidSessionId as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    search_question = req.question
    condensed: str | None = None
    if orchestrator.should_condense_followup(history, req.question):
        candidate = generator.condense_followup(history, req.question)
        if candidate:
            condensed = candidate
            search_question = candidate

    result = orchestrator.handle_question(
        search_question, req.session_id, history, mode=req.mode, chat_only=chat_only)

    turn_count: int | None = None
    if req.session_id:
        try:
            n1 = session_store.append_turn(req.session_id, "user",
                                           req.question)
            n2 = session_store.append_turn(req.session_id, "assistant",
                                           result["answer"])
            turn_count = min(n1, n2)
        except (session_store.InvalidSessionId, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    sources = []
    for s in result.get("sources", []):
        s = dict(s)
        if "source_type" not in s and "url_or_path" in s:
            # RAG chunks carry source_type at top level of the chunk dict
            pass
        sources.append(OrchestrateSource(**{
            "title": s.get("title", ""),
            "section": str(s.get("section", "")),
            "url_or_path": s.get("url_or_path", ""),
            "source_type": s.get("source_type"),
            "line_start": s.get("line_start"),
            "line_end": s.get("line_end"),
        }))

    route = result["route"]
    tools_used: list[str] = []
    if route == "erpnext" and result.get("confidence") == "high":
        op = (result.get("route_meta") or {}).get("op", "unknown")
        tools_used = [f"erpnext.{op}"]
    elif route == "code" and result.get("confidence") == "high":
        tools_used = (["code.listing"] if "+listing" in
                      str(result.get("route_how", "")) else ["code.explain"])
    # Structured request telemetry: decision metadata only, never message
    # text (questions may contain company data). HTTP errors propagate
    # without a telemetry line; uvicorn access logs cover those.
    logger.info(_json.dumps({
        "request_id": request_id,
        "conversation_id": req.session_id or "-",
        "route": route,
        "route_how": result.get("route_how"),
        "detected_intent": result.get("nlu_kind"),
        "intent_confidence": result.get("nlu_confidence"),
        "intent_topic": result.get("nlu_topic"),
        "refined_question": result.get("refined_question"),
        "confidence": result.get("confidence"),
        "mode": req.mode,
        "context_used": bool(history) and condensed is not None,
        "retrieval_used": route == "rag",
        "tools_used": tools_used,
        "fallback": result.get("fallback"),
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "error_type": None,
    }))
    return OrchestrateResponse(
        answer=result["answer"],
        sources=sources,
        confidence=result["confidence"],
        route=result["route"],
        route_how=result["route_how"],
        mode=req.mode,
        version_info=(orchestrator.unavailable_versions() if chat_only
                      else orchestrator.get_instance_versions()),
        session_id=req.session_id,
        turn_count=turn_count,
        condensed_question=condensed,
    )


_WRITE_REFUSAL_STATUS = {
    "writes_disabled": 403,
    "unsupported_action": 400,
    "bad_request": 400,
    "bad_reason": 400,
    "payload_too_large": 413,
    "unknown_fields": 400,
    "doctype_missing": 404,
    "confirmation_required": 400,
    "unknown_proposal": 404,
    "expired_proposal": 410,
}


def _write_refusal_as_http(exc) -> HTTPException:
    return HTTPException(
        status_code=_WRITE_REFUSAL_STATUS.get(exc.category, 400),
        detail=f"[{exc.category}] {exc.detail}",
    )


@app.post("/tools/erpnext_write/propose",
          response_model=ErpnextWriteProposalResponse)
def tools_erpnext_write_propose(
        req: ErpnextWriteProposeRequest) -> ErpnextWriteProposalResponse:
    """Phase 8: validate a live-data write and return an exact preview.

    Applies NOTHING. Gates: global write flag, allowed actions
    (create/update only — delete does not exist), reason required,
    payload caps, pre-flight schema validation of every fieldname.
    """
    try:
        proposal = erpnext_write_tool.propose_write(
            req.action, req.doctype, req.payload, req.reason, req.name)
    except erpnext_write_tool.WriteRefusal as exc:
        raise _write_refusal_as_http(exc) from exc
    except (erpnext_tool.ErpnextUnavailable,
            erpnext_tool.ErpnextApiError) as exc:
        raise _erpnext_http_error(exc) from exc
    return ErpnextWriteProposalResponse(**proposal)


@app.post("/tools/erpnext_write/apply",
          response_model=ErpnextWriteApplyResponse)
def tools_erpnext_write_apply(
        req: ErpnextWriteApplyRequest) -> ErpnextWriteApplyResponse:
    """Phase 8: execute a confirmed proposal against the live instance.

    The write flag is re-checked here. Every applied write is appended to
    the audit log (data/erpnext_writes.jsonl).
    """
    try:
        result = erpnext_write_tool.apply_write(
            req.proposal_id, req.confirmed)
    except erpnext_write_tool.WriteRefusal as exc:
        raise _write_refusal_as_http(exc) from exc
    except erpnext_write_tool.WriteTransportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ErpnextWriteApplyResponse(**result)
