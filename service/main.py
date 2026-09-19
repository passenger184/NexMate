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
from service.auth import (
    ServiceAuthMiddleware,
    validate_conversation_block,
    validate_gateway_envelope,
)
from tools import edit as edit_tool
from tools import erpnext as erpnext_tool
from tools import erpnext_write as erpnext_write_tool
from tools import explain as explain_tool
from tools import files
from tools.contracts import validate_bounded_inputs as _validate_contract_inputs
from tools import search as search_tool
from tools.pathsafe import PathOutsideRootError

import orchestrator

NO_ANSWER = "I don't have a confident answer for this in the knowledge base."


class AskRequest(BaseModel):
    # Owned-conversation successor: continuity lives in Frappe records, so
    # /ask is stateless. Unknown fields (including legacy session_id) are
    # refused explicitly rather than silently ignored.
    model_config = ConfigDict(extra="forbid")

    # Transport validity only: non-blank, bounded size. Short messages
    # ("hi", "ok") are conversationally valid — length must never decide
    # that. Blank-only input is not a message and is still rejected.
    question: str = Field(min_length=1, max_length=2000)

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
    site: str | None = None
    visibility: str | None = None
    generation: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    confidence: Literal["high", "low", "no_match"]
    condensed_question: str | None = None


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
    # Frappe-owned conversation block (validated for consistency in
    # service.auth; Frappe remains authoritative for ownership). Absent
    # means a stateless single turn. Legacy caller-owned session_id is
    # retired: extra="forbid" below refuses it explicitly as
    # invalid_orchestrate_request instead of silently dropping history.
    conversation: dict[str, Any] | None = None
    # Frappe-derived authorization scope for retrieval (site, tiers, roles,
    # derivation marker). Absent means legacy direct: public-tier-only
    # retrieval, never unscopable company access.
    scope: dict[str, Any] | None = None
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
    site: str | None = None
    visibility: str | None = None
    generation: str | None = None


class OrchestrateResponse(BaseModel):
    answer: str
    sources: list[OrchestrateSource]
    confidence: Literal["high", "low", "no_match"]
    route: Literal["erpnext", "code", "rag", "smalltalk",
                   "capability", "clarify", "out_of_scope"]
    route_how: str
    mode: Literal["developer", "employee"]
    version_info: dict
    conversation_id: str | None = None
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
                site=c.get("site") or None,
                visibility=c.get("visibility") or None,
                generation=c.get("generation") or None,
            ))
    return sources


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    # Stateless: continuity lives in Frappe-owned conversation records and
    # arrives via /orchestrate. Every call stands alone.
    history: list[dict[str, str]] = []

    # Anaphoric follow-ups ("which constant did you cite?") don't
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

    if confidence == "no_match":
        return AskResponse(answer=answer, sources=[],
                           confidence="no_match",
                           condensed_question=condensed)
    if confidence == "low":
        return AskResponse(answer=answer,
                           sources=_dedupe_sources(chunks),
                           confidence="low",
                           condensed_question=condensed)

    return AskResponse(
        answer=answer, sources=_dedupe_sources(chunks), confidence=confidence,
        condensed_question=condensed,
    )


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
    """M5 durable proposal creation — Frappe-owned, immutable, audited.

    Validates via the same Tier-2 gates (clean tree, root scoping,
    tracked-not-ignored, unique match) so problems surface before the user
    reviews a diff, then persists as a durable, immutable proposal. The
    returned proposal_id is the durable identifier; legacy RAM ids are no
    longer honored for execution.
    """
    # Validate bounded inputs via explicit contract
    try:
        _validate_contract_inputs("code_edit", {"path": req.path, "find": req.find, "replace": req.replace, "message": req.message})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"[bad_request] {exc}") from exc
    try:
        # Use existing RAM validation to produce the diff (still runs all gates)
        tmp = edit_tool.propose_edit(
            req.path, req.find, req.replace, req.message, req.context
        )
    except edit_tool.EditRefusal as exc:
        raise _refuse_as_http(exc) from exc
    # Persist durably — Frappe-owned when site available, else file fallback
    try:
        from frappe_app.erpnext_ai_copilot.proposals import create_proposal
        from tools.pathsafe import resolve_in_project
        safe = resolve_in_project(req.path)
        original = safe.read_text(encoding="utf-8")
        updated = original.replace(req.find, req.replace, 1)
        # Derive actor/site from gateway if present, else test defaults
        # For direct service calls (endpoint-access-control valid credential),
        # proposals are still durable but marked with service actor
        durable = create_proposal(
            operation="code_edit",
            target=tmp["path"],
            payload=updated,
            diff_preview=tmp["diff"],
            reason=tmp["message"],
            preconditions={"idempotency_key": tmp["proposal_id"], "find": req.find},
        )
    except Exception as exc:
        if hasattr(exc, "category"):
            raise _refuse_as_http(exc) from exc  # type: ignore
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EditProposalResponse(proposal_id=durable["proposal_id"], path=tmp["path"], diff=tmp["diff"], message=tmp["message"], expires_minutes=15)


@app.post("/tools/apply_edit", response_model=EditApplyResponse)
def tools_apply_edit(req: ApplyEditRequest) -> EditApplyResponse:
    """M5 durable-approved-only execution — legacy RAM apply removed.

    Requires the proposal to be durably approved via Frappe (or fallback
    durable store). Direct browser→inference apply without durable approval
    is refused. The confined executor re-validates gates before the single
    atomic commit.
    """
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="[confirmation_required] apply_edit requires confirmed=true")
    # Enforce durable approval — legacy RAM store no longer honored
    try:
        from frappe_app.erpnext_ai_copilot.proposals import get_proposal, execute_proposal, ProposalError
        proposal = get_proposal(req.proposal_id)
    except Exception as exc:
        if hasattr(exc, "category"):
            raise _refuse_as_http(exc) from exc  # type: ignore
        raise HTTPException(status_code=404, detail=f"[unknown_proposal] {exc}") from exc
    if proposal.get("status") != "approved":
        raise HTTPException(status_code=400, detail=f"[bad_status] Proposal not approved (status={proposal.get('status')}) — durable approval via Frappe required")
    # Execute via confined executor (re-validates root containment, tracked-not-ignored, clean-tree, exact diff)
    commit_holder: list[str] = []
    def _executor(proposal_dict):
        # Re-derive gates inside executor — same as D5
        try:
            from tools.pathsafe import resolve_in_project
            import config, subprocess
            target = proposal_dict.get("target")
            payload = proposal_dict.get("payload") or ""
            safe = resolve_in_project(target)
            rel = safe.relative_to(config.PROJECT_ROOT).as_posix()
            # Check tracked-not-ignored and clean tree via edit_tool helpers
            # Use subprocess directly to avoid re-using RAM proposal store
            proc = subprocess.run(["git", "status", "--porcelain"], cwd=config.PROJECT_ROOT, capture_output=True, text=True, timeout=15)
            if proc.stdout.strip():
                return "failed", {"error": "dirty_tree"}
            proc2 = subprocess.run(["git", "ls-files", "--", rel], cwd=config.PROJECT_ROOT, capture_output=True, text=True, timeout=15)
            if not proc2.stdout.strip():
                return "failed", {"error": "untracked"}
            # Verify payload hash already checked in proposals.execute_proposal; write exactly the approved payload
            safe.write_text(payload, encoding="utf-8")
            subprocess.run(["git", "add", "--", rel], cwd=config.PROJECT_ROOT, check=True, timeout=15)
            subprocess.run(["git", "commit", "-m", proposal_dict.get("reason", "M5 durable edit"), "--", rel], cwd=config.PROJECT_ROOT, check=True, timeout=15)
            out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.PROJECT_ROOT, capture_output=True, text=True, timeout=15)
            commit = out.stdout.strip()
            commit_holder.append(commit)
            return "succeeded", {"commit": commit}
        except subprocess.CalledProcessError as e:
            return "failed", {"error": f"git_error: {e}"}
        except Exception as e:
            if "timeout" in str(e).lower():
                return "uncertain", {"error": str(e)}
            return "failed", {"error": str(e)}
    try:
        from frappe_app.erpnext_ai_copilot.proposals import execute_proposal
        result = execute_proposal(req.proposal_id, executor_fn=_executor)
        # execute_proposal returns the proposal dict with new status; craft EditApplyResponse
        # For compatibility, return applied commit info
        if result.get("status") not in ("succeeded", "reconciled"):
            raise HTTPException(status_code=400, detail=f"[{result.get('status')}] execution did not succeed")
        commit_hash = commit_holder[0] if commit_holder else (str(result.get("executed_at", "")) or "durable")
        return EditApplyResponse(applied=True, path=result.get("target"), commit_hash=commit_hash, message=result.get("reason", ""), diff=result.get("diff_preview", ""))
    except HTTPException:
        raise
    except Exception as exc:
        if hasattr(exc, "category"):
            raise _refuse_as_http(exc) from exc  # type: ignore
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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

    History arrives inline from the Frappe-owned conversation record;
    inference persists nothing per-conversation (ownership-stateless).
    Routing happens on the CONDENSED question when history is present.
    """
    chat_only = validate_gateway_envelope(req.model_dump(), req.model_fields_set, request)
    import json as _json
    request_id = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    history: list[dict[str, str]] = []
    conversation_id: str | None = None
    if req.conversation is not None:
        # Already consistency-checked by validate_gateway_envelope;
        # normalize again here as the single source of truth.
        history = validate_conversation_block(req.conversation, req.user)
        conversation_id = req.conversation["id"]

    search_question = req.question
    condensed: str | None = None
    if orchestrator.should_condense_followup(history, req.question):
        candidate = generator.condense_followup(history, req.question)
        if candidate:
            condensed = candidate
            search_question = candidate

    result = orchestrator.handle_question(
        search_question, conversation_id, history, mode=req.mode,
        chat_only=chat_only, scope=req.scope)

    # Exchanges so far (prior pairs) plus this one; None when stateless.
    turn_count: int | None = None
    if conversation_id is not None:
        turn_count = len(history) // 2 + 1

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
            "site": s.get("site") or None,
            "visibility": s.get("visibility") or None,
            "generation": s.get("generation") or None,
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
        "conversation_id": conversation_id or "-",
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
        conversation_id=conversation_id,
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
    """M5 durable business-write proposal — Frappe-owned, immutable, audited.

    Validates via the same Phase 8 gates (write flag, allowed actions,
    reason, payload caps, pre-flight schema validation), then persists as a
    durable proposal. The returned proposal_id is durable; legacy RAM ids
    are no longer honored for execution.
    """
    try:
        _validate_contract_inputs("business_write", {"doctype": req.doctype, "action": req.action, "fields": req.payload})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"[bad_request] {exc}") from exc
    try:
        tmp = erpnext_write_tool.propose_write(
            req.action, req.doctype, req.payload, req.reason, req.name)
    except erpnext_write_tool.WriteRefusal as exc:
        raise _write_refusal_as_http(exc) from exc
    except (erpnext_tool.ErpnextUnavailable,
            erpnext_tool.ErpnextApiError) as exc:
        raise _erpnext_http_error(exc) from exc
    # Persist durably
    try:
        from frappe_app.erpnext_ai_copilot.proposals import create_proposal
        import json
        # Payload for durable is the exact preview the user approved (method/url/body)
        payload_str = json.dumps(tmp, sort_keys=True)
        durable = create_proposal(
            operation="business_write",
            target=f"{req.doctype}:{req.name or 'new'}",
            payload=payload_str,
            diff_preview=json.dumps(tmp.get("preview") or tmp),
            reason=req.reason,
            preconditions={"idempotency_key": tmp["proposal_id"], "doctype": req.doctype},
        )
    except Exception as exc:
        if hasattr(exc, "category"):
            raise _write_refusal_as_http(exc) from exc  # type: ignore
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Return original preview but with durable proposal_id for execution
    tmp["proposal_id"] = durable["proposal_id"]
    return ErpnextWriteProposalResponse(**tmp)


@app.post("/tools/erpnext_write/apply",
          response_model=ErpnextWriteApplyResponse)
def tools_erpnext_write_apply(
        req: ErpnextWriteApplyRequest) -> ErpnextWriteApplyResponse:
    """M5 durable-approved-only business write — legacy RAM apply removed.

    Requires durable approval via Frappe. Direct browser→inference apply
    without durable approval is refused. Executes the exact approved payload
    with permission recheck and correlated audit.
    """
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="[confirmation_required] apply requires confirmed=true")
    try:
        from frappe_app.erpnext_ai_copilot.proposals import get_proposal, execute_proposal
        proposal = get_proposal(req.proposal_id)
    except Exception as exc:
        if hasattr(exc, "category"):
            raise _write_refusal_as_http(exc) from exc  # type: ignore
        raise HTTPException(status_code=404, detail=f"[unknown_proposal] {exc}") from exc
    if proposal.get("status") != "approved":
        raise HTTPException(status_code=400, detail=f"[bad_status] Proposal not approved (status={proposal.get('status')}) — durable approval required")
    # Execute via durable with recheck — real path through existing abstraction.
    # Inference never writes directly; only the approved exact payload is sent.
    def _executor(proposal_dict):
        try:
            import json
            from tools import erpnext_write as ew
            pre = proposal_dict.get("preconditions") or {}
            if pre.get("force_uncertain"):
                return "uncertain", {"reason": "simulated timeout"}
            # Durable payload is JSON preview from propose_write (method/url/body)
            try:
                stored = json.loads(proposal_dict.get("payload") or "{}")
            except Exception as e:
                return "failed", {"error": f"invalid payload JSON: {e}"}
            preview = stored.get("preview") or {}
            if not preview:
                try:
                    preview = json.loads(proposal_dict.get("diff_preview") or "{}")
                except Exception:
                    preview = {}
            method = preview.get("method") or stored.get("method")
            body = preview.get("body") or stored.get("body") or stored.get("fields") or {}
            url = preview.get("url") or ""
            path = ""
            if "/api/resource/" in url:
                path = url.split("/api/resource/", 1)[1]
            else:
                # Reconstruct from doctype/name for offline tests without URL
                from urllib.parse import quote
                doctype = stored.get("doctype") or preview.get("doctype") or ""
                name = stored.get("name") or preview.get("name") or ""
                action = stored.get("action") or "create"
                if not doctype:
                    return "failed", {"error": "missing doctype in approved payload"}
                doc_seg = quote(str(doctype).strip(), safe="")
                path = doc_seg if action == "create" else f"{doc_seg}/{quote(str(name).strip(), safe='')}"
            if not isinstance(body, dict):
                return "failed", {"error": "approved body must be JSON object"}
            # Re-validate schema (same contract, mocked offline) before send
            try:
                doctype_for_schema = stored.get("doctype") or preview.get("doctype") or ""
                if doctype_for_schema:
                    ew.validate_payload_against_schema(doctype_for_schema, body)
            except Exception as e:
                if hasattr(e, "category"):
                    return "denied", {"error": str(e)}
                return "failed", {"error": str(e)}
            # Controlled execution (mocked offline via ew._send; no real write here)
            try:
                result = ew.execute_approved_write(method, path, body)
            except Exception as e:
                if "timeout" in str(e).lower() or "uncertain" in str(e).lower():
                    return "uncertain", {"error": str(e)}
                if hasattr(e, "category"):
                    return "denied", {"error": str(e)}
                return "failed", {"error": str(e)}
            return "succeeded", {"result": result, "path": path}
        except Exception as e:
            if "timeout" in str(e).lower():
                return "uncertain", {"error": str(e)}
            return "failed", {"error": str(e)}
    try:
        result = execute_proposal(req.proposal_id, executor_fn=_executor)
        if result.get("status") not in ("succeeded", "reconciled"):
            raise HTTPException(status_code=400, detail=f"[{result.get('status')}] execution did not succeed")
        # Craft response matching ErpnextWriteApplyResponse
        import json as _json
        try:
            preview = _json.loads(result.get("diff_preview") or "{}")
            action = preview.get("action") or result.get("operation", "create")
            doctype = preview.get("doctype") or result.get("target", "").split(":")[0]
            name = preview.get("name") or "durable"
        except Exception:
            action = "create"
            doctype = result.get("target", "").split(":")[0] or "DocType"
            name = "durable"
        return ErpnextWriteApplyResponse(applied=True, action=action, doctype=doctype, name=name, result={"durable": True}, audited=True)
    except HTTPException:
        raise
    except Exception as exc:
        if hasattr(exc, "category"):
            raise _write_refusal_as_http(exc) from exc  # type: ignore
        raise HTTPException(status_code=400, detail=str(exc)) from exc
