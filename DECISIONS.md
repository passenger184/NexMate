# DECISIONS.md — Architecture Decision Log

Append new decisions here using the format below. Never rewrite history —
if a decision changes, add a new entry that supersedes the old one and note
that. This is the single canonical decision ledger; `ARCHITECTURE.md`
owns the HLD, `SECURITY.md` owns standing policy, and `progress/` records
dated evidence rather than approval.

Historical bodies retain their original wording and phase numbering. The
accepted sequence is 1 public RAG, 2 code tools, 3 company knowledge,
4 memory, 5 ERPNext reads, 6 orchestration, 7 employee mode, 8 ERPNext
writes (`ROADMAP.md`). Earlier references to Phase 7 writes are historical.
The 2026-09-17 direction entry below qualifies older single-store,
provider-switching and deployment assumptions for the production target;
it does not retroactively rewrite their decisions.

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

## Restored historical ADRs — provenance recorded 2026-09-17

The following four entries are restored verbatim from
`c2e500443ccc89823894fa015895092c7db4d64a:DECISIONS.md` (lines 81–164).
The removal was verified in
`a576c7b25684b478dec5cd46f9dd1cdf7bd9868a`'s `DECISIONS.md` diff.
Original dates and bodies below are historical records, not fresh approval,
current measurements or cloud-data consent. Later entries remain intact.

Restoration annotations (not part of the original bodies):
- Crawl source: historical discovery and page counts, not a new network or
  licensing verification. The original Phase 1 repo-source preference was
  superseded by this crawl decision; no new crawl is authorized here.
- Hybrid chunking: preserves the within-section overlap trade-off, not an
  assertion of overlap across every heading boundary.
- Ollama URL mapping: still explicit at `rag/generator.py:218`; the current
  Ollama model prefix is `ollama_chat` (`rag/generator.py:199`). Restoring
  provider configuration history grants no permission to export private data.
- Hybrid retrieval: the original “can never drift” consequence is not a
  current guarantee. `rag/keyword_index.py:209` caches a lazy process-local
  snapshot without automatic collection-change invalidation. The Phase 3
  ADR below subsequently extends corpus mixing and rare-term confidence
  rules; it supersedes the earlier gate description where they differ.
  Historical counts are dated, and identifier repair is not semantic proof.

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

## [2026-09-17] Accepted production direction: authenticated Frappe control plane with private inference

**Status:** Accepted architectural DIRECTION only; implementation decisions
remain unresolved, runtime migration is pending, production readiness is
not established.

**Provenance:** The user's 2026-09-17 request to reconcile architecture and
production HLD, captured in the archived change's `proposal.md` and
`design.md` under
`openspec/changes/archive/2026-09-17-reconcile-architecture-and-production-hld/`,
and the explicit docs-only apply instruction to record
that direction without accepting unresolved implementation, production
writes or cloud consent. Earlier architect consultation endorsed direction,
not a particular deployment or protocol. No journal observation substitutes
for an approval decision.

**Decision:** Browser requests go through authenticated Frappe only. Frappe
owns identity, permission checks before retrieval/execution, persistent
conversations, proposals, approvals and the audit lifecycle. Heavy AI work
stays in separate private inference, without authoritative user/workflow
state; bounded model/index caches are compatible with that direction.
ERPNext/Frappe remains business-record authority. Private knowledge/search
is site-isolated and additionally constrained by intra-site user permissions.
Company/live data stays local by default; every provider call is subject
to explicit data-egress policy. Production writes are proposal/draft-first,
human-approved and reauthorized at execution. Code/Git execution remains a
separate privileged boundary. One application source serves ordinary Bench
and Docker; deployment packaging is not a second application.

**Context:** The current single-project implementation has browser-facing
FastAPI, caller-supplied mode/session identifiers, service-owned history,
process-local proposals and partial local audit evidence. Those mechanisms
are not an authenticated production control plane. The canonical HLD keeps
current implementation, approved target direction, unresolved decisions and
deferred capabilities separate from test and deployment evidence.

**Alternatives considered:** Treating a transparent proxy as authorization
(rejected: forwarding does not establish identity, permissions or state
ownership); treating historical phase acceptance as production readiness
(rejected); selecting shared tenancy or physical per-site deployments now
(not decided); forbidding all inference caches (unnecessary for removing
authoritative workflow state).

**Unresolved:** Physical per-site versus shared inference/index topology,
site-to-repository binding, public-index sharing, ingestion/index ownership,
privileged executor placement, service authentication and identity
propagation, tool/result and provider adapter contracts, ACL representation,
streaming/realtime transport and version negotiation, cloud-policy grants
and revocation, proposal state machine/concurrency/idempotency and uncertain
outcomes, audit durability/redaction/retention, app versioning and exact
Frappe compatibility matrix, monorepo-to-Bench packaging, operational
budgets, quality thresholds and permitted Debug disclosures. These require
separately reviewed decisions before their future acceptance gates pass.

**Consequences and supersession:** This direction supersedes any reading
of the early single-project/single-store or provider-config ADRs as the
production authorization/locality design. Their current implementation and
historical rationale remain recorded; source-type tags are not ACLs, and
provider configuration is not cloud-data consent. Today's direct Chroma and
local embedding code is not certified portable: adapter and compatible
index migration contracts are future work. Qdrant, pgvector, alternate
search/reranking, MCP and the separate Developer Workbench remain deferred
options, not selected dependencies. Site isolation does not approve a shared
multi-workspace registry. R01–R20 remain in the canonical HLD, with ordered
future gates in `ROADMAP.md` and proof methods in `EVALUATION.md`.

No runtime, provider configuration, deployment, model download, release or
production-write authorization follows from this ADR. The 2026-08-24
staging-only write decision and all `SECURITY.md` code-edit, confirmation,
root-scoping, least-privilege and local-default safeguards remain in force.
Any production-write approval and any specific private-data cloud consent
must be separately explicit and recorded here; this entry grants neither.

## [2026-09-17] U4 (partial): shared-secret service authentication for the Frappe-to-inference boundary

**Status:** Accepted for the service-to-service authentication mechanism
only. This resolves the authentication-transport subset of U4 (service
authentication and identity propagation). The remaining U4 scope —
tool/result contracts, provider conformance, streaming/realtime transport,
version negotiation — stays unresolved. This decision does NOT by itself
satisfy migration gate G2/M2: user authorization, permission enforcement
before retrieval/execution, and owned state remain future work.

**Provenance:** User decision of 2026-09-17 while planning the
`authenticated-frappe-control-plane` OpenSpec change (planning artifacts in
`openspec/changes/authenticated-frappe-control-plane/`). Planning
authorization only; no implementation, deployment or test execution is
approved by this entry.

**Decision:**
- Shared secret service credential, transmitted as the `X-NexMate-Key`
  HTTP header on requests from the Frappe control plane to the private
  FastAPI inference service.
- Secret configured through environment configuration on the inference
  side (`.env`) and site configuration on the Frappe side
  (`site_config.json`); never hardcoded, never sent to the browser, never
  present in boot data or client storage.
- Production configuration fails closed: requests with a missing or
  invalid credential are rejected, and an unconfigured secret rejects all
  requests rather than permitting unauthenticated access.
- The existing standalone `/ui` local development workflow is preserved
  only through an explicit development-only configuration flag, default
  off; there is no implicit authentication bypass in production.
- No mTLS and no signed-request infrastructure in this change; the
  mechanism is the shared-secret header alone.

**Alternatives considered:** mTLS (rejected for this change: certificate
infrastructure disproportionate to the first boundary increment);
per-request cryptographic signatures (rejected: added complexity without
a current threat need); forwarding Frappe session cookies to inference
(rejected: couples the private service to Frappe session semantics and
does not establish a service identity).

**Consequences:** Constant-time credential comparison; rotation is a
documented configuration change. The secret authenticates the control
plane, not the end user: user identity and site travel with the request
and are recorded by inference, but authorization decisions remain Frappe
responsibilities delivered by later approved work. The related unresolved
choices — developer-mode privilege mapping, session/state behavior in the
authenticated increment, and which direct tool operations remain available
— are pending user decisions recorded in the change's design.md, not
silently defaulted here.

## [2026-09-17] Authenticated boundary: resolved planning choices and conditional implementation approval

**Status:** Accepted bounded decisions; subsequent implementation approved
once planning is internally consistent and strictly validated. This entry
records planning, not implementation, test completion or deployment.

**Provenance:** The user's explicit 2026-09-17 instruction to update planning
only for `authenticated-frappe-control-plane`, restricted to existing change
files, this ledger and ROADMAP.md. The user resolved the four pending points,
required backend natural-language tool denial and identity/site validation,
and approved implementation after plan consistency and strict validation.
The present pass does not execute that implementation authorization.

**Decision:**
- Use server-managed `nexmate_developer_roles`, default `[]`; no broad
  System Manager default or implicit Administrator elevation. The actual
  authenticated Frappe user's roles determine persona; browser mode does
  not. Persona grants neither tool permissions nor corpus/session ownership.
- Preserve optional legacy `session_id` forwarding strictly as temporary
  continuity, not authentication, authorization, ownership or site isolation.
  Leave JSON storage unchanged here. Immediately after this bounded boundary
  is verified, require separately approved `frappe-owned-conversation-state`
  covering Frappe records, user ownership, site association, persistence,
  removal of caller-controlled ownership, JSON replacement and a migration/
  compatibility strategy. Its implementation is not included or approved here.
- Keep the gateway chat-only. No read/search/explain/file/code/Git/business
  tools, proposals, approvals or reset through it. Enforce an immutable
  empty tool allowance in backend code before execution, including natural
  language routing, troubleshooting, follow-ups, fallbacks and incidental
  ERPNext version reads. Disabling slash commands or relying on the model
  does not satisfy this decision. Existing cited RAG is not live file search
  and does not become ACL retrieval; no new private-corpus grants are made.
- Desk makes no direct inference calls, including reset, stale approval/
  rejection handlers and failures. Start-fresh is local transcript clearing
  plus a fresh local identifier, not server deletion or ownership. Preserve
  legacy endpoints only behind credentials or explicit development access,
  with existing confirmation/write/locality safeguards unchanged.
- Exact `/health` is unauthenticated minimal liveness, even with key unset
  or invalid. It exposes no sensitive diagnostics, configuration, user/site
  or business data and does not establish protected-service readiness.
- Retain server-only `X-NexMate-Key`, inference environment
  `NEXMATE_SERVICE_KEY` and Frappe site `nexmate_service_key`. Require a
  strong random credential and constant-time comparison. Exclude keys and
  transport headers from logs, telemetry, prompts, boot/client storage,
  bundles and error responses; do not relay browser headers or follow
  credential-bearing redirects. Frappe missing-key errors never use bypass.
- Protected production requests fail closed on missing/invalid credentials
  or unset/invalid configuration. Development exemption is explicit,
  default off and configuration-only, never request/origin/Host/forwarded/
  localhost heuristics. Invalid supplied credentials remain rejected in dev.
- Validate complete gateway user/site/mode/scope before history, retrieval,
  routing or execution. Require valid service authentication even when dev
  exemption is enabled; partial envelopes cannot downgrade to legacy calls.
  Bind site to one trusted server-configured expected site. Only validated
  metadata receives attributed telemetry; recording is not validation or
  per-user authorization. This remains single-project with no tenant/root
  registry, site-isolated index or selected physical tenancy topology.

**Implementation-level planning choices:** `NEXMATE_ENV` defaults to
`production`; only exact `development` together with
`NEXMATE_DEV_UNAUTHENTICATED=1` permits missing-header development requests.
A valid or unset configured key is allowed in that explicit development
case; a malformed configured key or supplied invalid credential is not.
Unknown environments or invalid flag values never enable exemption. The
planned strong-key representation is 64 hexadecimal characters generated
from at least 32 random bytes. Proposed `NEXMATE_FRAPPE_SITE` is the fixed
expected site, not a routing key. Bounded nonempty user/site strings reject
Guest, control characters and edge whitespace; design.md defines the full
truth table and envelope. These configuration/validation choices implement
the approved constraints, not a new topology or broad U4 selection.

**Context and alternatives:** Earlier drafts simultaneously recorded the
four decisions and left contradictory pending questions, universal health
denial and UI-only tool restrictions. Stateless gateway/session stripping,
broad administrator role defaults, authenticated health and tool proxying
are not selected. A single dev flag or traffic-derived exception would not
satisfy the production-default constraint. Telemetry-only identity and
model-only tool denial do not establish the requested boundary.

**Consequences and supersession:** This entry supersedes only the preceding
U4 entry's planning-only approval status, pending four choices, and literal
"all requests" denial insofar as it contradicts minimal public health and
the explicit dual-opt-in development exception. Historical ADR text remains
unchanged. No mTLS or signing is introduced. Remaining U4 tool/result and
provider contracts, version negotiation and streaming/realtime remain
unresolved, as do other affected HLD gates. Legacy JSON and non-ACL retrieval
remain explicit limitations; this increment does not complete G2/M2 or
establish safe multi-user deployment. No release, production-write approval,
private-data cloud consent, live test/model call or successor implementation
is authorized by this planning entry. Stop and ask if an additional
substantive user choice is discovered before dependent implementation.

## [2026-09-18] frappe-owned-conversation-state: implementation findings
**Decision:** Frappe-owned `NexMate Conversation` records (owner+site, child turns) replace the deleted JSON session store; gateway `ask()` pre-appends the user turn with an explicit commit before the upstream call; inference validates envelope consistency only and persists nothing; legacy session paths fail explicitly.
**Context:** Live Bench verification exposed two facts the plan did not foresee: (1) Frappe rolls back errored requests, so the designed orphan-turn discipline required an explicit pre-append commit; (2) stock Frappe only syncs DocType JSONs from inside module directories and requires controller stubs plus an `app_description` hook, so the app carries a real Desk-module subpackage (container-only shims documented separately for the pre-existing layout gaps).
**Alternatives considered:** Accepting rollback (loses the documented orphan-turn guarantee); soft-close instead of delete-by-owner (deferred — no retention policy gives "closed" meaning); bulk-importing JSON sessions (rejected — fabricates ownership).
**Consequences:** Trust boundary from the review stands (Frappe authoritative; inference never authorizes ownership; privileged roles cannot bypass API owner checks; concurrent appends serialize under row locks with loud conflicts). `ARCHITECTURE.md` still describes the JSON store — left for a separate HLD reconciliation. No production readiness, ACL retrieval, streaming, or successor work is authorized by this entry.
