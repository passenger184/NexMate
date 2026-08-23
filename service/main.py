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

    confidence = retriever.classify_confidence([c["score"] for c in chunks])
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
