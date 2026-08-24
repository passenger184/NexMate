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

## [2026-08-23] Doc corpus sourced by crawling docs.frappe.io
**Decision:** Ingest public docs by crawling `https://docs.frappe.io/erpnext`
and `https://docs.frappe.io/framework` (sitemap.xml-driven), storing raw
markdown locally before chunking.
**Context:** The spec's preferred git-repo doc source no longer exists —
Frappe moved both doc sites into its wiki platform around 2021 (verified:
no docs dirs on `frappe/erpnext@version-15`, `frappe/frappe` branches;
`github.com/frappe/docs` 404s). The wiki serves each page as clean markdown
with YAML front-matter (`title`, `space`, `url`, `updated`) under
CC-BY-SA 3.0. Sitemap lists ~6.7k URLs total; current-version ERPNext manual
is ~2.7k pages, Framework ~650.
**Alternatives considered:** Legacy `frappe/erpnext_documentation` repo
(archived 2021, stale snapshot — rejected as outdated); scraping rendered
HTML from docs.erpnext.com (messier than the wiki's native markdown).
**Consequences:** Ingestion depends on the live site being reachable;
a polite rate-limited crawler with local caching of fetched pages is part
of the pipeline. Versioned subtrees (`/erpnext/v13|v14|v15/...`) exist and
can be added later for version-awareness.

## [2026-08-23] Hybrid chunking: MarkdownNodeParser + SentenceSplitter
**Decision:** Chunk in two stages — split markdown by heading structure
with LlamaIndex `MarkdownNodeParser`, then re-split any oversized section
with `SentenceSplitter(chunk_size≈400 tokens, chunk_overlap=50)` — and tag
every node with document title, section header-path, source URL, and
`source_type: public_doc`.
**Context:** Spec requires heading-based sections AND ~300–500 token chunks
with ~50-token overlap. `MarkdownNodeParser` alone enforces no size cap and
zero overlap (long Frappe tutorial pages would become single unusable
chunks); `SentenceSplitter` alone would ignore headings. Neither tool does
both. Also: parser splits correctly around code fences, which Frappe docs
are full of.
**Alternatives considered:** Pure `MarkdownNodeParser` (violates size
target); pure fixed-window splitting (violates heading requirement);
hand-rolled regex parser (reinvents tested library behavior).
**Consequences:** Overlap occurs within oversized sections rather than
across heading boundaries — accepted trade-off. Chroma metadata must stay
scalar (str/int/float/bool) or ingestion will raise.

## [2026-08-23] OLLAMA_BASE_URL mapped explicitly to litellm api_base
**Decision:** `.env` keeps `OLLAMA_BASE_URL` (as documented throughout this
repo); `rag/generator.py` reads it itself and passes it as litellm's explicit
`api_base=` argument at the single completion call site.
**Context:** litellm natively auto-reads an env var named
`OLLAMA_API_BASE`, not `OLLAMA_BASE_URL` — silently assuming our variable
name would make provider config appear broken when Ollama is remote
(the normal case here: Windows-hosted, reached over network).
**Alternatives considered:** Renaming the repo-wide variable to
`OLLAMA_API_BASE` for native pickup (would contradict DEVELOPMENT.md /
ARCHITECTURE.md / .env.example documentation).
**Consequences:** One explicit mapping line in `generator.py`; if that file
is ever refactored, the mapping must survive or remote Ollama breaks.

## [2026-08-24] Hybrid BM25+vector retrieval, recalibrated confidence gates
**Decision:** Fuse an in-house Okapi BM25 index (`rag/keyword_index.py`, built
lazily from the same Chroma collection) with cosine retrieval via Reciprocal
Rank Fusion (keyword weight 1.5 vs vector 1.0). A document may take a second
top-k slot only when another of its chunks has near-equal lexical evidence
(>=0.9 of the page's best BM25). Confidence gates now combine signals:
"high" = strong cosine OR solid cosine rescued by IDF-weighted query-term
coverage; "no_match" = coverage veto OR a query token absent from the whole
corpus (unless cosine clears the high bar). The generator gained a
deterministic check that every backticked identifier exists in the retrieved
context, with one corrective escalation.
**Context:** The 2026-08-24 verification run showed pure-vector retrieval (a)
burying exact-term pages (bench commands for Q12 sat outside top-8), (b) the
max-cosine gate refusing questions whose correct page was already in the
candidate pool (Q5/Q6/Q15 at 0.788-0.797 vs the 0.80 bar), and (c) the
0.72-0.80 cosine band unable to separate keyword-overlap negatives
(`frappe.auto_sync_with_jupiter` at 0.764) from hard positives (Q3 at 0.766).
**Alternatives considered:** `rank-bm25` package (rejected: adds a dependency
outside the locked stack for ~80 lines of fully specified math);
title/section-heading score boost (tried and REVERTED same day: pages titled
with generic query words swept the rankings and the target section sank
further); raising k (does nothing for intra-document section selection or
gating); purely prompt-side anti-fabrication rules (insufficient alone - a
7B model leaks identifiers without a deterministic net).
**Consequences:** Tokenizer suffix-folding (-s/-ing/-ed/final-e) applies
identically to queries and corpus, trading stemming precision for recall;
the BM25 index can never drift from the vector store since Chroma is its
source of truth; corpus is now 7,410 chunks (one stale /erpnext/v13/ page
purged, five collateral chunks repaired); `config.is_excluded_doc_path()`
replaces naive substring matching in BOTH crawler and loader (the old
substring also excluded legitimate /erpnext/v...aluation-style slugs).
