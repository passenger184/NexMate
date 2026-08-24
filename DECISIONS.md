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

## [SUPERSEDED] One shared, workspace-aware service instead of one service per project
**Status:** Superseded by the entry below — user chose to defer
multi-workspace support entirely until the single-project system is mature.
Original reasoning kept in `docs/FUTURE_MULTI_WORKSPACE.md` for when this
is revisited.

## Single-project scope, multi-workspace support deferred
**Decision:** Build and operate this as a single-project system — one
project root, one Chroma store, one service instance, no workspace
registry or `workspace_id` concept anywhere in the current codebase.
**Context:** User runs multiple local projects and eventually wants
multi-project support, but chose to defer it until the single-project
system (RAG, live code editing, company knowledge) is mature and proven,
rather than adding workspace-routing complexity now.
**Alternatives considered:** Building workspace-awareness now (see the
superseded decision above) so it wouldn't need retrofitting later.
**Consequences:** Simpler current codebase. When multi-workspace support
is eventually built, `docs/FUTURE_MULTI_WORKSPACE.md` has the design
already worked out — this is a deferred addition, not an unconsidered one.

## Live code read/edit agent brought forward to Phase 2, gated by git
**Decision:** Build a live code read/search/explain/edit tool earlier than
originally planned (was bundled into the last, most-guarded phase), scoped
to this project's root, with edits gated behind a clean git tree and
per-edit confirmation.
**Context:** User wants full read+edit capability now, not deferred behind
company-knowledge and orchestrator phases.
**Alternatives considered:** Keep it as the last phase per the original
plan (safer sequencing, but doesn't meet what the user actually wants);
build it with no git/confirmation gating (faster, but no undo path if the
agent makes a bad edit).
**Consequences:** This tool is explicitly scoped to source code only — it
never writes to live ERPNext data. That capability (Phase 7) stays later
and separately guarded, since a bad code edit is a `git revert` and a bad
live data write generally is not.

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

## [2026-08-24] Phase 3: project corpus mixing + code chunking
**Decision:** Ingest this repo's own source (.py via stdlib-ast
function/class-boundary splitting) and markdown (heading-split) into the ONE
existing Chroma collection tagged `our_code`/`company_doc`; at query time,
vector retrieval runs as TWO pools (public vs project) fused with RRF under
a modest company boost (`FUSION_COMPANY_BOOST=1.25`); generator passages
carry explicit labels ("project code"/"project docs"/"framework docs").
**Context:** PHASE_3_SPEC requires company answers to win when both corpora
cover a question, without letting 325 project chunks get swamped by (or
swamp) 7,410 public chunks. Spec explicitly prefers simple boundary
chunking before any tree-sitter adoption.
**Alternatives considered:** single undifferentiated pool (scoring would be
dominated by whichever corpus is larger); separate collections (violates
the one-store ADR); tree-sitter (deferred until simple chunking proves
inadequate per spec).
**Consequences:** idempotent re-ingest deletes+reinserts only project
chunks (public index untouched); module preambles merge into the first
symbol chunk after standalone-docstring chunks lost per-document dedupe to
real code (found live, P1); indexing our own journals means past negative
probes exist in-corpus, so an ultra-rare-term guard
(`CONFIDENCE_RARE_TERM_DF_MAX=4`) now blocks the coverage RESCUE — such
questions decline honestly instead of answering high.

## [2026-08-24] Phase 8: writes enabled for the staging instance only
**Decision:** ERPNEXT_WRITE_ENABLED=true with ERPNEXT_ENV_LABEL=staging,
scoped to http://localhost:8081 — a development instance with no real
company data. Production writes remain OFF; pointing ERPNEXT_BASE_URL at
a production system requires an explicit approval decision recorded here
before that configuration stays on.
**Context:** Phase 8 needs live verification of guarded writes
(create/update) per ROADMAP; SECURITY.md forbids production writes until
explicitly approved.
**Consequences:** every applied write is audit-logged to
data/erpnext_writes.jsonl with env label + reason; delete is not
implemented anywhere in the toolchain; two clearly-labeled test Customers
exist on the staging instance as a result (deletable via its UI).
