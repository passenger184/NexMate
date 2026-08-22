# DECISIONS.md — Architecture Decision Log

Append new decisions here using the format below. Never rewrite history —
if a decision changes, add a new entry that supersedes the old one and note
that.

## Format

```
## [YYYY-MM-DD] Short decision title
**Decision:** what was decided
**Context:** why this came up
**Alternatives considered:** what else was on the table
**Consequences:** what this locks in or rules out
```

## Existing decisions (established before build start)

## Chroma as the vector store
**Decision:** Use Chroma (local, persistent client) for vector storage.
**Context:** Needed a free, local, zero-hosting-cost vector DB for solo
development.
**Alternatives considered:** FAISS (lighter but less LlamaIndex ergonomics),
hosted options (Pinecone/Weaviate/Qdrant — introduces cost and an account).
**Consequences:** Migration to a hosted DB later is a re-index, not a
rewrite, if this is outgrown.

## Local embeddings via sentence-transformers
**Decision:** Use `BAAI/bge-small-en-v1.5` (fallback `all-MiniLM-L6-v2`) run
locally, not a paid embeddings API.
**Context:** Anthropic has no embeddings API; wanted zero cost and no extra
vendor account during validation.
**Alternatives considered:** OpenAI `text-embedding-3-small` (cheap, higher
quality, but a paid dependency).
**Consequences:** Slightly lower embedding quality than a hosted model;
acceptable for docs retrieval, revisit if quality proves insufficient.

## [SUPERSEDED] Ollama-only for local LLM generation (Phase 1)
**Decision:** Use Ollama running `llama3.1:8b` for answer generation during
Phase 1, not the Claude API.
**Status:** Superseded by the entry below — user wants provider choice, not
a fixed default.

## Provider-agnostic generation via litellm
**Decision:** Generation calls go through `litellm`, configured by
`GENERATION_PROVIDER`/`GENERATION_MODEL` env vars. Default is local Ollama
(`ollama/llama3.1:8b`, already installed on the user's Windows host), but
switching to Anthropic, OpenAI, or a different local model is a `.env` edit,
never a code change.
**Context:** User wants to choose cloud vs. local generation and switch
models freely without redoing the integration each time. User already has
Ollama running on Windows, not WSL — WSL reaches it over the network rather
than running a second local instance.
**Alternatives considered:** Hardcoding one provider (simpler, but exactly
what the user asked to avoid); writing a custom provider-abstraction layer
instead of using `litellm` (more control, but reinventing a well-maintained
open-source library for no real benefit here).
**Consequences:** One extra dependency (`litellm`); `rag/generator.py`
should have exactly one call site that reads the provider config — no
provider-specific logic anywhere else in the codebase.

## Embedded-in-ERPNext UI, not standalone
**Decision:** Build the assistant as a Frappe app with a sidebar/desk panel
inside ERPNext, not a separate standalone application.
**Context:** The assistant should feel present in the tool the user already
works in daily.
**Alternatives considered:** Standalone app queried alongside ERPNext.
**Consequences:** UI work depends on Frappe's own frontend framework and
app conventions rather than a general web stack.

## Single vector store with metadata tags, not parallel knowledge bases
**Decision:** Public docs, company docs, and code all live in one Chroma
store, distinguished by a `source_type` metadata field, filtered at query
time.
**Context:** The original design sketch showed separate "public" and
"company" knowledge systems.
**Alternatives considered:** Two fully separate vector stores/pipelines.
**Consequences:** Simpler to build and keep in sync; mode-based filtering
(developer vs. employee, later) becomes a metadata filter, not a system
swap.
