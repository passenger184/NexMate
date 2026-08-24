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
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from rag import generator, retriever
from tools import edit as edit_tool
from tools import explain as explain_tool
from tools import files
from tools import search as search_tool
from tools.pathsafe import PathOutsideRootError

NO_ANSWER = "I don't have a confident answer for this in the knowledge base."


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class Source(BaseModel):
    title: str
    section: str
    url_or_path: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    confidence: Literal["high", "low", "no_match"]


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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Fail loud at startup if the vector store is missing/unreadable,
    # rather than serving errors on every request.
    retriever.get_index()
    yield


app = FastAPI(title="ERPNext AI Copilot — Phase 1", lifespan=_lifespan)

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
    try:
        chunks = retriever.retrieve(req.question)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    confidence = retriever.classify_confidence(chunks, req.question)
    if confidence == "no_match":
        # Nothing even topically close: refuse, show nothing.
        return AskResponse(answer=NO_ANSWER, sources=[], confidence="no_match")
    if confidence == "low":
        # Retrieval was mediocre (top score below CONFIDENCE_HIGH_MIN):
        # refuse deterministically — no LLM call, no chance of a
        # confidently-wrong answer — but surface the nearest documents so
        # the user can judge for themselves.
        return AskResponse(
            answer=NO_ANSWER,
            sources=_dedupe_sources(chunks),
            confidence="low",
        )

    answer = generator.generate_answer(req.question, chunks)
    return AskResponse(
        answer=answer, sources=_dedupe_sources(chunks), confidence=confidence,
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
    """Tier-2 step 1: validate the edit and return it as a unified diff.

    Applies NOTHING. Every SECURITY.md gate runs here (clean tree, root
    scoping, tracked-not-ignored, unique match) so problems surface before
    the user reviews a diff.
    """
    try:
        proposal = edit_tool.propose_edit(
            req.path, req.find, req.replace, req.message
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
