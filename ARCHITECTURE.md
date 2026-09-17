# ARCHITECTURE.md — NexMate Canonical HLD

## Authority, scope and status

Reconciled **2026-09-17** against repository source, read-only. This is the
single canonical high-level design (HLD), not a production-readiness
certificate. The OpenSpec change `reconcile-architecture-and-production-hld`
is documentation-only; its detailed design guides this reconciliation and
is not a second permanent HLD. No runtime migration, provider consent,
release or production write is authorized here.

**NexMate — Your ERPNext AI Companion** targets **Frappe v16 / ERPNext
v16**, serving developers/admins and employees through different permitted
experiences. Source citations, version-appropriate answers and honest
uncertainty remain product invariants. Existing persona selection is not
an authenticated role. Historical “NexPilot” names refer to the
conversational redesign, not another product; technical package names,
storage keys and environment variables remain unchanged. For example,
`frappe_app/erpnext_ai_copilot/hooks.py:1` retains the older app title while
`frappe_app/public/js/copilot.bundle.js:610` displays NexMate.

### Scope: single project for now

The current configuration has one project root, one configured ERPNext
connection and one local Chroma collection (`config.py:17`, `config.py:28`,
`config.py:147`, `tools/erpnext.py:44`). There is no approved shared
multi-workspace registry, browser-selected root or `workspace_id` feature.
Independent installations are not such a registry. Future private
knowledge must be isolated by Frappe site, but physical per-site deployment
versus a shared service remains undecided; see the unresolved register.

### Status legend and approval provenance

| Architectural status | Meaning |
|---|---|
| **C — Current implementation** | Present source behavior; not necessarily verified in a real deployment. |
| **T — Approved target direction** | Agreed requirement/direction, not delivered functionality or selection of every mechanism. |
| **U — Unresolved implementation decision** | Requires an explicit decision before the affected implementation proceeds. |
| **D — Deferred capability** | Preserved future possibility, outside current implementation scope. |

Evidence is a separate dimension: **implemented** (source exists),
**tested** (identify unit/mock/integration/browser scope), **live-tested**
(dated environment), **unverified**, **planned**, or **deferred**. These
are not a completion ladder: implemented UI can remain unverified in Desk.
The evidence matrix below retains historical acceptance and its exceptions.

Prior architect consultation, reaffirmed by the 2026-09-17 reconciliation
request, endorsed an **authenticated Frappe control plane with separate
private inference**. It did not accept a physical per-site deployment,
privileged executor placement, service authentication protocol or provider
interface protocol. A per-site deployment recommendation remains an
option, not an accepted decision. The same distinction applies to cloud
content permission and production-write authorization.

### Glossary and document ownership

- **Control plane:** authenticated Frappe ownership of identity, policy,
  conversations, proposals and execution authority; not a forwarding proxy.
- **Inference:** bounded routing/retrieval/generation work, without
  authoritative user/workflow state. Model and index caches are compatible
  with this definition; persistent index ownership is still unresolved.
- **Route:** response classification, distinct from an NLU kind, executable
  tool, persona or autonomous agent.
- **Site isolation:** separation of each Frappe site's private data and
  search; **intra-site ACLs** additionally restrict individual users.
- **RAG / BM25 / RRF:** retrieval-augmented generation / lexical ranking /
  reciprocal rank fusion. Retrieval confidence is a heuristic, not proof
  of correctness or permission.

| Document | Canonical responsibility |
|---|---|
| `ARCHITECTURE.md` | Current/target HLD, boundaries, ownership, requirements, decisions still needed and migration direction. |
| `DECISIONS.md` | Single ADR ledger: rationale, alternatives, approval provenance, status and supersession. |
| `PROJECT.md` | Product name, audiences and invariants. |
| `ROADMAP.md` | Historical phase acceptance and future milestone ordering. |
| `SECURITY.md` | Standing policy; policy must not be confused with current enforcement. |
| `EVALUATION.md` | Acceptance methods and required evidence. |
| `AGENTS.md` | Read/authority rules and approved work scope. |
| `progress/` | Dated observations, current evidence and blockers; not design authority. |
| `DEVELOPMENT.md` / `README.md` | Development/release runbook / concise onboarding. |
| `docs/UI_SPEC.md` | Interaction structure; `docs/UI_VISUAL_SPEC_updated.md` is the canonical blue visual reference, superseding historical amber `docs/UI_VISUAL_SPEC.md`. |
| `docs/PHASE_*_SPEC.md` | Historical phase requirements, not competing current-phase pointers. |
| `openspec/specs/` / `openspec/changes/` | Future maintained behavioral requirements / scoped proposals, designs and tasks; neither establishes verification. |

Historic sequence: 1 public RAG, 2 live code, 3 company knowledge,
4 project memory, 5 ERPNext reads, 6 orchestration, 7 employee mode,
8 ERPNext writes. Phase 1–8 functional acceptance does not pass the future
production gates below. Post-roadmap work needs a separately approved,
bounded change; this HLD alone is not an implementation instruction.

## Current runtime and request flows — C

```text
Frappe Desk server
  hooks: app_include_js/css + extend_bootinfo
    -> browser receives sidebar assets + FastAPI address

Browser sidebar (or standalone /ui preview)
  localStorage: session ID + caller-selected mode
  direct fetch -> FastAPI (no incoming authenticated principal established)
                    |
                    +-- orchestrator -> code reads/search/explain -> checkout
                    |                -> ERPNext GET client -> shared API account
                    |                -> hybrid RAG -> local Chroma + BM25
                    +-- legacy /ask -> RAG
                    +-- direct read/search/explain and ERPNext read endpoints
                    +-- Git propose/apply -> configured checkout + Git
                    +-- ERPNext propose/apply -> separate POST/PUT client
                    |
                    +-- generation/condensation/NLU -> LiteLLM -> configured LLM
                    +-- JSON sessions on disk; proposals in process memory
                    +-- request telemetry; Git commits; post-write JSONL log

Offline ingestion -> same local Chroma collection
  public markdown / project Python + markdown / resolved commit cases
```

Wiring: `frappe_app/erpnext_ai_copilot/hooks.py:6`,
`frappe_app/erpnext_ai_copilot/boot.py:10`,
`frappe_app/public/js/copilot.bundle.js:26`,
`frappe_app/public/js/copilot.bundle.js:337`, `service/main.py:271`.
The startup lifespan loads the index; `/health` returns a simple status,
not a comprehensive provider/ERPNext health assessment (`service/main.py:393`).
Preview assets are served at `/ui` (`service/main.py:281`). Hooks and preview
source do not prove Bench packaging, asset injection or real Desk behavior.

### Conversational and task routing

```text
POST /orchestrate {question, session_id?, mode}
  -> load server JSON history using caller-supplied ID
  -> optional anaphoric follow-up condensation (failure keeps raw question)
  -> Layer 1: exact normalized conversational match, no routing model
       greeting / thanks / goodbye / acknowledgement -> smalltalk
       help -> capability
  -> otherwise Layer 2 NLU over message + bounded recent history
       conversational -> smalltalk
       capability     -> capability
       clarify        -> clarify
       out_of_scope   -> out_of_scope
       troubleshoot   -> code if error-like; otherwise targeted clarify
       task           -> NLU-confidence check; optional contextual rewrite
                         -> three-way task router -> erpnext | code | rag
  -> append user/assistant turns; log request metadata; complete JSON response
```

Exactly **seven response routes** exist: `erpnext`, `code`, `rag`,
`smalltalk`, `capability`, `clarify`, `out_of_scope`
(`service/main.py:224`). **`troubleshoot` is one of six NLU kinds, not an
eighth response route, separate tool or autonomous agent**
(`orchestrator.py:174`, `orchestrator.py:795`). No autonomous write loop is
part of this dispatch.

Layer 1 normalizes case and trailing punctuation; its small exact map
includes `hi`, `hey`, `hello`, `bye`, `goodbye`, `thanks`, `thank you`, `ok`,
`okay`, `got it`, `help` (`orchestrator.py:160`, `orchestrator.py:210`).
Layer 2 uses a per-attempt NLU timeout and one corrective parse retry
(`orchestrator.py:214`, `config.py:74`). A failed NLU decision uses only
strong task heuristics, otherwise clarification (`orchestrator.py:769`).
By contrast, the three-way task router tries heuristics, then a classifier
with corrective retry, and defaults to RAG if that classifier fails
(`orchestrator.py:468`, `orchestrator.py:498`). These distinct degradation
paths replace the obsolete “any classifier failure defaults to RAG” summary.

Capability/clarification/scope replies are deterministic; non-exact
conversational replies may use generation with a deterministic fallback
(`orchestrator.py:304`, `orchestrator.py:338`). The three-entry catalog
renders mode-filtered capability help but neither dispatches nor authorizes
tools (`capabilities.py:14`, `capabilities.py:60`). Its “authoritative
registry” comment describes help content, not an executable security registry.

Employee orchestration denies code/schema and restricts RAG to public docs;
developer project-scope hints admit company retrieval
(`orchestrator.py:822`, `orchestrator.py:862`, `orchestrator.py:892`).
Mode is caller-provided (`service/main.py:198`), so these are partial
behavioral guards, not identity-derived authorization. NLU confidence is
separate from retrieval confidence. `high` on a conversational or code
response is not a measured universal answer-quality score.

### Legacy and direct endpoints

| Entry point | Current path and source |
|---|---|
| `POST /ask` | Legacy RAG, optional history/condensation, no employee-mode check or orchestrated version preamble (`service/main.py:317`). |
| `POST /tools/read_file`, `/tools/search`, `/tools/explain` | Direct code read/search/explanation (`service/main.py:398`, `service/main.py:423`, `service/main.py:433`). |
| `POST /tools/propose_edit`, `/tools/apply_edit` | Separate confirmed Git edit flow (`service/main.py:471`, `service/main.py:488`). |
| `POST /tools/erpnext/schema`, `/document`, `/list` | Direct shared-account ERPNext reads (`service/main.py:513`, `service/main.py:523`, `service/main.py:533`). |
| `POST /tools/erpnext_write/propose`, `/apply` | Separate create/update confirmation flow (`service/main.py:665`, `service/main.py:686`). |
| `POST /tools/session/reset` | Delete JSON session, not indexed resolutions (`service/main.py:382`). |

Direct tool endpoints do not inherit orchestrator mode checks. CORS defaults
to `*` (`service/main.py:293`); neither CORS nor a development localhost bind
is authentication. The nearby “service holds no secrets” comment is stale:
ERPNext client code reads configured credentials (`tools/erpnext.py:44`).
This review read source only, not credentials or actual environment settings.

## Current retrieval, generation and index lifecycle — C

### Knowledge base layering and ingestion

One collection is used, with source-type tags rather than separate stores
(`config.py:147`, `rag/retriever.py:50`). Tags identify provenance, **not
site or user ACLs**.

| Source type | Current ingestion and meaning |
|---|---|
| `public_doc` | Cached framework/ERPNext markdown, canonical URL/title/section/updated metadata; heading parsing, oversized-section resplitting, base64-image scrub and stub removal (`ingestion/chunk_and_embed.py:61`, `ingestion/chunk_and_embed.py:120`). |
| `company_doc` | Project markdown parsed by headings and resplit (`ingestion/ingest_project.py:167`). |
| `our_code` | Project Python parsed with stdlib AST at function/class boundaries; large classes split at methods; oversized content resplit (`ingestion/ingest_project.py:76`, `ingestion/ingest_project.py:198`). This is not tree-sitter. |
| `resolved_issue` | Commit message, motivating context and bounded diff; citation path includes commit hash (`tools/memory.py:67`). Indexed after a successful code-edit commit or explicit backfill (`tools/edit.py:295`, `tools/memory.py:103`). |
| `core_code` | Reserved/future source type; no current core-code ingestion established by these pipelines. |

Project discovery handles `.py` and `.md`, with directory exclusions, not
all source languages (`ingestion/ingest_project.py:44`). It is not an ACL
or secret-classification pipeline. Resolved issues are ordinary retrievable
knowledge alongside company docs/code, not a separate memory database or
user-fact summarization system (`rag/retriever.py:40`). Indexing failure after
an edit is returned in the memory result; it does not undo the commit
(`tools/edit.py:295`).

### Hybrid retrieval and confidence

```text
question -> local query embedding
         -> public_doc vector candidates
         -> optional company vector candidates (our_code/company_doc/resolved_issue)
         -> global BM25 candidates (public-only mode filters this candidate list)
         -> weighted RRF -> per-document deduplication -> top-k passages
         -> confidence heuristic -> refusal or cited generation
```

`rag/retriever.py:128` uses two metadata-filtered vector pools plus global
BM25, weighted RRF and document deduplication. Public-only retrieval filters
lexical hits **after** global candidate selection (`rag/retriever.py:173`),
not through an ACL-aware lexical index. Company ranking is boosted only for
project-scoped questions (`rag/retriever.py:214`). Current defaults are k=8,
candidate multiplier 2, RRF dampener 60, vector weight 1.0, lexical weight
1.5, company boost 1.25 and a second-document-chunk lexical ratio of 0.9
(`config.py:155`, `config.py:165`, `config.py:193`).

Confidence uses maximum retrieved similarity, IDF-weighted coverage in the
first three chunks, unseen terms and rare-term protection
(`rag/retriever.py:258`, `config.py:210`):

- No chunks, insufficient coverage (<=0.05), or an unseen term below the
  high similarity bar yield `no_match`.
- After the vetoes, similarity >=0.80 yields `high`; >=0.74 with coverage
  >=0.45 can rescue to `high` unless query terms have corpus df 1–4.
- Remaining similarity >=0.72 yields `low`; below it yields `no_match`.
- RAG `low` refuses with sources; `no_match` refuses without sources;
  only `high` proceeds to answer generation (`service/main.py:343`,
  `orchestrator.py:899`). This does not mean no earlier NLU/condensation call.

These are calibrated heuristics, not semantic validation. Vector hits use
`exp(-cosine_distance)` (`rag/retriever.py:105`), while keyword-only hits use
raw cosine (`rag/retriever.py:115`, `rag/retriever.py:207`). The scales are
not identical despite older “cosine score” descriptions. RRF orders
candidates; it is not the confidence value.

### Generation provider config and grounding

Generation uses LiteLLM, taking `GENERATION_PROVIDER` and `GENERATION_MODEL`
from environment configuration. Ollama is mapped to `ollama_chat/<model>`;
`OLLAMA_BASE_URL` is passed as `api_base` (`rag/generator.py:199`,
`rag/generator.py:213`). There is no automatic provider switching or
provider-by-provider acceptance implied by this configurable call site.
Ollama, OpenAI, Anthropic and other compatible providers are supported
configuration directions; actual credentials, reachability and compatibility
must be established for the chosen setup. No actual `.env` was inspected.

Local embeddings use `HuggingFaceEmbedding` and configured
`BAAI/bge-small-en-v1.5` (`rag/retriever.py:43`, `config.py:134`). The
~130MB embedding-model download exemption and generation-model confirmation
rules remain in `AGENTS.md`; local Windows-hosted Ollama access is covered
by `DEVELOPMENT.md`. No model download or call is part of this change.
LlamaIndex supplies loading/chunking/vector glue; Chroma `PersistentClient`
is used directly. These are current integrations, not portable adapters.

Generation includes numbered passages, source-type labels and bounded
history; missing citations and selected ungrounded backticked identifiers
trigger corrective requests (`rag/generator.py:250`, `rag/generator.py:290`).
A still-defective answer can be returned after retries. Citation presence
and identifier matching are **not fail-closed semantic grounding**, nor a
check that each cited claim follows from its source. Live-payload generation
has a similar corrective identifier check (`orchestrator.py:666`). The
application call path has no enforced per-data-class cloud-consent gate
(`rag/generator.py:213`). Evaluation also has its own judge integration
(`evaluation/ragas_eval.py:91`), not a universal all-provider policy boundary.

### Known index lifecycle gaps, not remediated here

1. **Destructive shared rebuild:** public ingestion deletes and recreates
   the configured collection (`ingestion/chunk_and_embed.py:155`), so a
   public rebuild can remove company and resolved-issue content too.
2. **Stale lexical snapshot:** BM25 lazily snapshots the collection once
   per process (`rag/keyword_index.py:209`). There is no automatic freshness
   coupling after ingestion or resolution insertion. “Cannot drift” is not
   an accurate guarantee; global corpus statistics also influence gates.
3. **Current-code drift:** code edits index a resolution, not refreshed
   `our_code` chunks (`tools/edit.py:295`). Explicit project sync replaces
   only `our_code`/`company_doc` (`ingestion/ingest_project.py:252`); deletion
   followed by insertion is not an atomic published index generation.
4. **Compatibility/provenance gaps:** no enforced embedding-model/index
   fingerprint or version-pinned retrieval contract is established by
   collection loading (`rag/retriever.py:50`). Metadata records sources,
   but does not establish authenticated ACLs, exact installed-version
   compatibility or safe cross-site sharing.

Future fixes need scoped changes and migration evidence, not re-ingestion
as a side effect of documentation edits.

## Current state, tools, versions and frontend — C

| Resource | Source-established behavior | Boundary/limitation |
|---|---|---|
| Conversations | Caller-selected session ID; JSON files; regex validation, bounded reads and process-local lock; temporary-file replacement on writes (`service/session_store.py:19`, `service/session_store.py:39`, `service/session_store.py:64`). | Filename safety is not ownership. No authenticated user/site binding; no established cross-process transaction or exchange-level concurrency guarantee. |
| Browser state/history | localStorage ID and mode (`frappe_app/public/js/copilot.bundle.js:44`); in-memory message DOM starts empty (`frappe_app/public/js/copilot.bundle.js:602`). | Backend continuity can survive refresh, but the UI does not restore the transcript from the server. Start-fresh requests deletion and clears locally even if deletion fails (`frappe_app/public/js/copilot.bundle.js:649`). |
| Code read/search/explain | Resolve-and-contain paths; capped UTF-8 reads; Git-discovered search; source excerpts for explanation (`tools/pathsafe.py:19`, `tools/files.py:26`, `tools/search.py:28`, `tools/explain.py:226`). | Project-root scope is not a sensitive-file authorization policy. Direct file read does not itself enforce Git-ignore exclusion; search discovery does. |
| Git proposals/execution | In-memory proposals; diff preview; clean-tree/tracked/unique-match gates; explicit confirmation, TTL and content recheck; one-file write/stage/commit (`tools/edit.py:114`, `tools/edit.py:130`, `tools/edit.py:234`). | No durable actor-bound approval workflow or transaction spanning file write, Git, memory and audit. A one-file commit is not a proven concurrency-safe or failure-atomic execution protocol. |
| ERPNext reads | GET-only operations through one configured API account; capped responses, bounded list limits and upstream errors (`tools/erpnext.py:44`, `tools/erpnext.py:56`, `tools/erpnext.py:119`). | Upstream account permissions do not identify or authorize the browser user. Returned list `count` is the fetched page length, not necessarily a total count. |
| ERPNext writes | Separate create/update module; flag checked at propose/apply; schema field-name preflight; exact API preview; explicit confirmation and TTL (`tools/erpnext_write.py:49`, `tools/erpnext_write.py:141`, `tools/erpnext_write.py:214`). Delete is absent. | Proposals are process-local, unbound to actor/site; no durable rejection, idempotency, concurrency or uncertain-outcome reconciliation. Environment label/flag do not prove staging or a production approval. |
| Write audit | Local JSONL after upstream success, recording environment, action, target, reason and payload keys (`tools/erpnext_write.py:134`, `tools/erpnext_write.py:238`). | Upstream write can succeed before audit fails. No complete request/approval/rejection/denial/failure lifecycle or authenticated actor/correlation chain. |
| Versions | Read-only version lookup cached for 600 seconds, including unavailable result; preamble on orchestrated RAG/live-data generation; response version metadata (`orchestrator.py:391`, `orchestrator.py:419`, `orchestrator.py:674`, `orchestrator.py:913`, `service/main.py:637`, `config.py:67`). | Not injected into every model call or legacy/direct path; not version-pinned retrieval. Versioned doc-subtree exclusion (`config.py:113`) does not certify current cached pages as exact v16 documentation. |
| Telemetry | Request ID, conversation, route, intent, mode, tools and latency on successful orchestrated return (`service/main.py:601`). | HTTP-error paths may lack this event; no complete audit. `intent_topic` and `refined_question` can contain content despite the “decision metadata only” comment. |

The current sidebar has a floating toggle, resizable panel, mode selector,
citations and inline approval cards. Calls await complete JSON, not streamed
tokens (`frappe_app/public/js/copilot.bundle.js:337`,
`frappe_app/public/js/copilot.bundle.js:442`,
`frappe_app/public/js/copilot.bundle.js:602`). Reject currently updates the
DOM only, without server invalidation (`frappe_app/public/js/copilot.bundle.js:463`).
The ERPNext API proposal contains method/URL/body, but its card displays the
body and reason, not the entire transport preview
(`frappe_app/public/js/copilot.bundle.js:497`). Real navbar integration,
Frappe realtime, authorized page context and transcript restoration are
**target work**, not delivered by the preview or historical UI specification.

## Approved production design — T, with U boundaries

### Logical component and trust-boundary diagram

```text
Untrusted browser: Desk chat + page hints
       | authenticated Frappe requests only
       v
Frappe control plane / site authority
  authenticated actor + site; permissions before retrieval/execution
  conversations; proposals; approval decisions; audit ownership
       |---- authorized business reads/writes ----> ERPNext/Frappe records
       |
       | bounded authorized history/context + permitted operation/scope
       | authenticated private service boundary (protocol U)
       v
Private FastAPI inference
  NLU/routing + retrieval + generation; no user/workflow authority
       |---- authorized search boundary ----> knowledge/index stores
       |                                      private data isolated by site
       |                                      and filtered by user permission
       |---- egress policy boundary --------> local model/embedding providers
       |                                      cloud only by explicit policy
       |
       +---- tool requests/results through Frappe authorization contracts

Frappe-approved privileged code action
       | separate execution authority (placement/transport U)
       v
Confined code/Git executor ----> explicitly bound repository
```

Arrows express responsibilities, **not a settled network protocol**. The
LLM may request a tool but cannot grant access, choose an authoritative
site/root, approve its own output or execute an unapproved action.
Inference cannot receive denied content first and rely on output filtering.
A transparent browser-to-service proxy would not satisfy this design.

### Deployment invariants, not a selected tenancy topology

```text
One NexMate application source
       +--> ordinary Bench: Frappe app + Desk assets + lifecycle hooks
       +--> Docker packaging: the same application, not a fork
                         |
                 private inference boundary
                         |
          stores/providers and confined executor boundaries
          physical service/index/executor placement: unresolved
```

Per-site inference/index instances could simplify isolation at operational
cost; a shared private service could reduce duplication but requires
stronger tenant binding, resource and cache isolation. Neither is accepted.
Whether public indexes can be shared is separately undecided; private
knowledge and intra-site permissions must remain isolated in either model.
Docker packaging does not decide tenancy or transfer authority from Frappe.

### Target ownership

| Responsibility | Approved target | Remaining implementation choice |
|---|---|---|
| Identity, authorization, API entry | Frappe authenticates user/site and derives allowed data/tools; browser speaks to Frappe only. | Private-service authentication, identity propagation and revocation protocol. |
| Conversation/session state | Persistent Frappe-owned owner-bound records; authorized bounded history supplied to inference. | Record schema, retention, concurrent-turn and reset semantics. |
| Business records | ERPNext/Frappe remains record authority; every read and execution obeys actual Frappe permissions. | Internal tool/result transport and execution integration. |
| Heavy AI work | Separate private inference, with model/index caches but no authoritative workflow state. | Worker placement, quotas, cancellation and service-version negotiation. |
| Private knowledge/search | Site isolation plus intra-site user permission before retrieval. | Physical topology, ACL representation, public sharing, ingestion and persistent-index ownership. |
| Proposals, approval and audit | Durable Frappe-controlled lifecycle and correlation. | State machine, storage guarantees, retention and outcome reconciliation. |
| Privileged code/Git work | Separate confined execution boundary under Frappe authorization. | Executor location, credentials, site-to-repository binding and locking. |

### Authorized Desk context and explicit tools

Target flow: browser route/DocType/document-name hint -> Frappe validates
structure and actual read permission -> minimal allowed fields/context ->
authorized retrieval/tool scope plus bounded owner-bound conversation ->
inference -> cited response -> authorized persistence and delivery.
For example, a hint naming **Sales Invoice SI-00042** is not permission to
read that invoice. History, follow-ups and cached context must be
reauthorized when permissions change; previous disclosure is not enduring
access authority. Documents and model outputs are untrusted content, not
instructions that can change security scope.

Target tool contracts specify operation/version, validated inputs, bounded
outputs and provenance, authenticated actor/site binding, required
permission and context, side-effect class, approval requirement, typed
errors, timeout/cancellation behavior and audit events. Read-only ERPNext,
retrieval, code search, code edits and business-data writes retain distinct
contracts. Route labels and the current descriptive catalog are not those
contracts. No general SQL-generation tool is introduced by this design.

Desk chat should provide persistent history restoration, streaming and
Frappe realtime delivery scoped to the authorized user/conversation.
Reconnect, partial responses, cancellation, duplicate events and permission
revocation need explicit behavior and real-browser tests. The exact
stream/realtime transport is unresolved. Developer/admin capabilities must
come from permissions, not a mode selector; the future Developer Workbench
is a separate engineering surface, not employee chat with a privileged toggle.

A target **Debug/transparency** view may disclose permitted retrieval
provenance, documents/fields accessed, raw results and generated database
queries **only where such queries exist and disclosure is authorized**.
This is neither current telemetry nor permission to dump prompts/results.
It must be role/policy-filtered, minimized, redacted and audited, without
revealing denied source existence or sensitive fields through diagnostics.

### Authorization, locality and durable approval/audit

Authorization must precede retrieval and execution on every entry point,
including replacements for legacy/direct endpoints. Frappe-derived site,
actor and permitted corpus/data/tool scope constrain vector and lexical
search, caches, citations and model context. Source-type tags and
post-retrieval filtering are not substitutes for ACL enforcement. Site
isolation does not by itself establish intra-site user access control.

**Local-default data classes:** company documents/code, resolved issues,
live ERPNext results, document/page context, prompts and conversation
history, NLU/classification/condensation input/output, embeddings, telemetry
and Debug data. Public docs can have different policy, but a mixed request
inherits restrictions of its sensitive contents. Cloud transmission needs
explicit approved policy for the exact data classes, provider and purpose;
revocation must apply to subsequent calls. Deny-by-default policy covers
all generation, corrective retries, routing, condensation, embeddings and
evaluation/judge paths, not just final-answer generation. Secrets are
excluded regardless of ordinary content approval. Provider configuration
alone is not cloud consent. Current call paths do not enforce this target.

Production business writes remain **proposal/draft-first and human-approved**;
code edits retain a separate approval/execution boundary. Target lifecycle:

1. Validate identity, site, permission and side-effect class; create a
   durable owner-bound proposal/draft with exact immutable intended payload,
   target, reason, expiry and concurrency preconditions.
2. Persist explicit approval or rejection by an authorized actor; changes
   to payload/target require a new approval. Expiry/revocation must be
   enforced server-side, not only represented by a UI card.
3. Recheck permission, target state, approval validity and policy immediately
   before execution; serialize conflicting operations or reject stale ones.
4. Correlate attempts and outcomes with idempotency/retry semantics. A timeout
   with unknown upstream outcome must be reconciled, not blindly replayed.
5. Record success, denial, failure and uncertain outcome durably; surface
   audit failure and recovery status. Do not claim a distributed atomic
   transaction before the chosen implementation proves its guarantees.

Audit must cover AI requests, permitted retrieval provenance, tool calls,
proposal creation, approvals/rejections/expiry, execution attempts/results,
failures and security events, linked by actor/site/correlation identifiers.
Complete lifecycle coverage does not mean retention of every raw prompt or
result. Redaction, access control, tamper resistance, retention/deletion and
recovery guarantees require decisions and tests. Existing Git/JSONL/logging
is partial evidence, not this lifecycle.

Standing safeguards are unchanged: root-scoped code operations,
clean-tree/explicit-per-edit confirmation, separate business-data writes,
`ERPNEXT_WRITE_ENABLED` gating, staging before production, and explicit
production approval recorded in `DECISIONS.md`. Release approval does not
authorize production writes; no live settings are certified by this HLD.

## Provider and search interfaces — T, not existing portability

| Boundary | Current | Target contract and compatibility obligation |
|---|---|---|
| Generation (R01) | LiteLLM environment-selected call (`rag/generator.py:199`). | Provider-neutral bounded messages/context and output/error contract; capability/model identity, locality, timeouts, cancellation/streaming and policy checks. Ollama, OpenAI, Anthropic, compatible and future providers need individual conformance evidence. No silent fallback/provider switching. |
| Embeddings (R02) | Local HuggingFace/sentence-transformers integration (`rag/retriever.py:43`). | Batch/query embedding interface with model/revision, dimensions, normalization/metric, locality and errors. An incompatible model or dimension change requires a controlled rebuild, not mixing vectors; remote embeddings are not enabled. |
| Vector store (R03) | Direct Chroma queries and ingestion APIs (`rag/retriever.py:89`, `ingestion/ingest_project.py:252`). | Search/filter/upsert/delete and lifecycle interface that preserves site/ACL scope, IDs, metadata/provenance and compatible scoring semantics. Qdrant is an option, not a selection or delivered adapter. |
| Search/ranking (R16) | Global in-process BM25 plus vector/RRF (`rag/keyword_index.py:212`, `rag/retriever.py:209`). | Measured latency, memory, freshness and quality drive scaling. Alternative inverted indexes, pgvector, dedicated search and reranking are deferred options, not parallel engines to install now. |

Target index generations need explicit source/version/model/ACL provenance,
ingestion ownership, incremental update/delete semantics, lexical/vector
freshness coupling and safe rebuild publication. Migration must preserve
unrelated corpora/resolutions and site boundaries, verify counts and
retrieval quality, support rollback and invalidate incompatible caches.
Reembedding/search changes also require confidence recalibration and
held-out evaluation. Provider portability is not zero-cost interchangeability;
wire contracts, ownership and operational budgets remain unresolved.

## Application release and Bench/Docker lifecycle — T

Target lifecycle: **Git source -> packaged NexMate Frappe app -> test/lint
and compatibility checks -> Bench/Docker install/update with normal Frappe
patches/migrate -> backup/restore and rollback verification -> approved
versioned release -> repeatable installation/update**. Use the same app
source in ordinary Bench and Docker; deployment packaging/topology may
differ, application logic must not fork by environment.

Current metadata uses Flit and dynamic versioning
(`frappe_app/pyproject.toml:9`), with `0.1.0` at
`frappe_app/erpnext_ai_copilot/__init__.py:1`; Python is declared `>=3.10`
and Frappe `>=15` (`frappe_app/pyproject.toml:7`,
`frappe_app/pyproject.toml:16`). These declarations do not establish a tested
support matrix and differ from the concrete v16 product scope. Exact app
versioning policy, supported Frappe/Python ranges, service/index schema
compatibility and monorepo-to-Bench packaging path remain unresolved.
No package metadata is changed or certified here.

Real root-repository Bench installation, package asset inclusion,
`app_include_js/css` build/injection, boot behavior, migrations and update
parity remain unverified. Standalone `/ui` serves a filesystem directory;
it does not prove that an installed Frappe package contains or loads the
same assets. Docker deployment is planned, not delivered/certified by this
reconciliation. Future CI/release evidence must cover clean install,
upgrade, patches/migrate, real Desk assets/context/streaming, both deployment
forms, backup/restore, index compatibility and rollback behavior before
publishing. The existing `docs/OPEN_SOURCE_LAUNCH_SPEC.md` is a launch
checklist/reference, not evidence those gates passed.

## R01–R20 requirement traceability

Every requirement remains explicit. C/T/U/D use the architectural legend;
proof obligations below are **future**, not newly passed checks.

| ID | Requirement and disposition | HLD coverage / future proof obligation |
|---|---|---|
| R01 | LLM abstraction — C LiteLLM; T provider-neutral support for Ollama/OpenAI/Anthropic/compatible/future providers; U exact interface. | Provider interfaces: conformance, request/output/error/timeout/locality and policy tests per provider; no automatic switching. |
| R02 | Embedding abstraction — C local embeddings; T clean provider boundary; U contract; D remote provider enablement. | Provider interfaces: model/dimension identity and rebuild compatibility, local-default egress enforcement. |
| R03 | Vector-store abstraction — C direct Chroma; T portable search/filter/upsert/delete boundary; U adapter/migration contract; D Qdrant option. | Provider/search interfaces: site-safe metadata/index migration, rollback and adapter conformance; no existing-portability claim. |
| R04 | Deployment — C browser-facing FastAPI; T authenticated Frappe control plus separate private inference; U tenancy/service/executor topology. | Target diagrams/ownership: browser-to-Frappe-only and private-service identity/site validation; proxy alone fails. |
| R05 | Professional lifecycle — C Git source; T Git-to-app-to-test/lint/migrate-to-release/install/update; U release gates/policy details. | Release lifecycle: reproducible CI, compatibility, migration, backup/restore and rollback proof, not a release claim. |
| R06 | Bench/Docker parity — T same application source; C partial Frappe packaging; U validated packaging/topology. | Release lifecycle: clean install and update in both real environments with identical application behavior; no fork. |
| R07 | Versioning/compatibility/patches — C dynamic 0.1.0 and Frappe >=15 declaration; T deliberate versions, v16 support and normal patches/migrate; U supported matrix/policy. | Metadata gap above: test chosen matrix and upgrade paths before changing compatibility claims. |
| R08 | Complete auditability — C partial telemetry/Git/JSONL; T correlated durable lifecycle; U storage/retention/redaction guarantees. | Approval/audit section: AI/retrieval/tools/proposals/decisions/execution/failure/security events with actor/site and minimized content; failure/recovery evidence. |
| R09 | Explicit tools — C hard-coded dispatch/descriptive registry; T authorized tool contracts; U schema and transport. | Tool section: validate inputs/outputs, scope, permissions, side effects, approval, errors and audit; seven response routes are not seven agents. |
| R10 | In-Desk chat/history/streaming/realtime — C partial sidebar, complete JSON, service sessions; T Frappe-owned history and streaming/realtime; U transport. | Desk section: real Bench/browser history restore, reconnect/cancellation and user-scoped delivery; preview/stub DOM is insufficient. |
| R11 | Page-aware context — T authorized route/DocType/document hints; not current request behavior; U context contract. | Desk context flow: SI-00042 hint validated before reading minimal permitted fields; denial tests before model input. |
| R12 | Document/history-aware answers — C service continuity and live-payload answers; T owner-bound authorized document/history context; U schemas/budgets. | Target ownership/context: minimization, bounded history, later-turn permission recheck and revocation tests. |
| R13 | Authorization before retrieval/execution — C partial mode/shared-account guards; T mandatory identity-derived scope; U ACL/identity mechanism. | Security boundary: cross-site/intra-site negatives prove denied content never reaches search results/model context; LLM and post-filtering cannot grant access. |
| R14 | Debug/transparency — C telemetry only, not Debug; T policy-filtered provenance/results/field/query visibility; U disclosure policy. | Debug section: role-filtered disclosure and redaction tests; query visibility only where queries exist, no new SQL-generation feature. |
| R15 | MCP — D future adapter seam; U server/client direction, consumers, trust and protocol. | Deferred register: separately approved integration with tool authorization/audit, no current MCP dependency or runtime feature. |
| R16 | Search scaling — C vector/BM25/RRF; T extensible fresh search; U scale thresholds; D alternative inverted index/pgvector/dedicated search/reranking. | Index lifecycle/provider sections: scale/quality measurements, freshness/rebuild preservation, site/ACL-safe migration before selecting options. |
| R17 | Human-approved production writes — C partial staging create/update and Git flows; T durable proposal/draft-first approval; U state/concurrency/retry guarantees. | Approval lifecycle: immutable approved payload, owner binding, expiry/rejection, permission recheck, stale/concurrent/retry/uncertain-outcome tests; explicit production approval still required. |
| R18 | Site-isolated private knowledge/search — C single configured project; T site isolation plus intra-site ACLs; U physical tenancy, repository binding and public sharing. | Target topology/security: isolation of retrieval, stores and caches; per-site deployment is not an accepted decision or shared-workspace feature. |
| R19 | Local-default company/live data — C local embedding/store, configurable generation without enforced consent boundary; T explicit all-call egress policy; U grants/revocation mechanism. | Locality section: classify prompts/history/NLU/docs/code/resolutions/live results/embeddings/telemetry/Debug, deny cloud by default, always exclude secrets, test every provider path. |
| R20 | Developer Workbench — D separate future engineering surface; U privileged interaction design. | Deferred register/tool boundary: permissioned code execution and audit, distinct from employee Desk chat; caller-selected mode is not authority. |

## HLD evidence matrix

Source references above were revalidated **2026-09-17**, without executing
runtime code. Historical results below are reported evidence from
`progress/CURRENT.md` and `progress/JOURNAL.md`, not reruns or current
connectivity measurements. Missing dates/environments are not inferred.

| Capability / architectural status | Source anchor | Evidence type and recorded artifact/environment | Limitation and next gate |
|---|---|---|---|
| Public RAG / C | `rag/retriever.py:128`, `rag/generator.py:250` | Implemented; reported live API sweep 2026-08-24: 15 positives and 3 negatives, `data/sweep_2026-08-24_hybrid_v2.json`, described in `progress/CURRENT.md` “Verification state”. | Historical `/ask` acceptance, not held-out production quality; revalidate grounding/version behavior and future ACL boundaries. |
| Company corpus and resolutions / C | `ingestion/ingest_project.py:252`, `tools/memory.py:103` | Implemented; 2026-08-24 company P1–P6/preference probes and four resolutions reported in CURRENT Phase 3/4 verification; historical count 7,410 public + 321 project, before resolution additions. | Counts are not a present inventory. Prove safe rebuilds, edit freshness and ACL-isolated search. |
| Session continuity / C; owned state / T | `service/session_store.py:39`, `service/main.py:546` | Implemented; reported 2026-08-24 live second-order follow-up/reset, CURRENT Phase 4 verification; unit tests in `tests/test_memory.py`. | No owner-bound Frappe state or transcript restoration; future restart/concurrency/ownership tests. |
| Code tools and Git edits / C | `tools/pathsafe.py:19`, `tools/edit.py:234` | Implemented; historical unittest/temporary-Git integration and three live one-file commits on 2026-08-24, CURRENT Phase 2 verification. | Does not prove production executor isolation, cross-process atomicity or durable approvals. |
| ERPNext reads / C | `tools/erpnext.py:56` | Implemented; 2026-08-24 live REST reads/error mapping at staging `localhost:8081`, CURRENT Phase 5 verification; mocked client tests in `tests/test_erpnext.py`. | Shared upstream account, not browser-user permission proof or Desk installation evidence. |
| Orchestration/personas/versions / C | `orchestrator.py:754`, `orchestrator.py:862`, `orchestrator.py:391` | Earlier three-route/persona live checks 2026-08-24, CURRENT Phase 6/7; reported v16.31.0/v16.32.3 environment. | Predates full conversational redesign; versions are historical, not current connection facts. |
| Seven-route conversational redesign / C | `service/main.py:224`, `orchestrator.py:769` | Implemented; 29-case mocked-NLU routing result reported in CURRENT; JOURNAL sessions 18/19 record unit/mock Python and Node checks, latest aggregate 145 Python + 26 Node. | Unit/mock routing and stub-DOM checks are not live NLU or real browser/Bench acceptance. Full live NLU matrix remains incomplete. |
| Degraded path and later follow-up / C | `orchestrator.py:214`, `rag/generator.py:180` | JOURNAL session 18: live service on :8001 with provider down; session 19: later successful Sales/Purchase Invoice follow-up. These entries lack explicit calendar dates; CURRENT's 2026-09-09 header records the aggregate. | Historical outage does not prove current unreachability; one later live success does not complete the NLU matrix. |
| Guarded ERPNext writes / C | `tools/erpnext_write.py:214` | Implemented; 2026-08-24 staging create/update/read-back and refusal tests reported in CURRENT Phase 8; `tests/test_erpnext_write.py` mocks transport. | Not production approval, durable audit or owner-bound approval proof; test recovery/uncertain outcomes before production decision. |
| Sidebar / C; Bench/Docker / T | `frappe_app/public/js/copilot.bundle.js:602`, `frappe_app/erpnext_ai_copilot/hooks.py:6` | Implemented bundle and preview; historical Node/stub-DOM coverage and session 13 preview report. Real Bench/Desk installation/assets unverified; Docker planned. | Verify packaged source, real Desk assets, context/history/realtime and dual-environment install/update. API live tests do not pass this gate. |
| RAGAS / C evaluation harness | `evaluation/ragas_eval.py:55`, `evaluation/ragas_eval.py:91` | Reported scoring 2026-09-08, recovered/logged 2026-09-09, on 2026-08-24 samples; CURRENT “RAGAS baseline” names sample/result artifacts. | Self-judge and missing rows limit interpretation; not an orchestration/auth/UI evaluation. See means below. |
| Authenticated control, isolated knowledge, egress and complete audit / T | Current gaps: `service/main.py:198`, `rag/generator.py:213`, `tools/erpnext_write.py:238` | Planned; no target-boundary implementation/verification claimed. | Resolve contracts, then demonstrate negative permissions/egress and durable failure/recovery evidence. |
| MCP, Workbench, alternative search / D | R15/R16/R20 and unresolved register | Deferred, no delivery/test claim. | Separate approved scope and measured justification before implementation. |

Recorded post-hybrid RAGAS means: **faithfulness 0.734 (8/15 valid), answer
relevancy 0.939 (11/15), context precision 0.564 (9/15)**. Judge was the
same local `qwen2.5-coder:7b` used for generation, with bge-small embeddings.
Pre-hybrid 2026-08-23 means were 0.992 (12/15), 0.941 (15/15), 0.562
(15/15), respectively. Reported NaNs include judge parse failures; changing
valid-row coverage and self-judging prevent a clean causal comparison.
The faithfulness drop cannot be dismissed as harmless judge noise, nor does
it alone establish a regression. Stronger independent judging, per-question
review and held-out cases remain future evidence requirements. No result
file was regenerated or model evaluated by this documentation change.

## Unresolved decisions and deferred capabilities

These are deliverables of the HLD, not blockers to documenting the target.
They block their respective implementation gates; do not select an option
merely to close a documentation task.

| Decision | Options/consequences and required decision input |
|---|---|
| U1 — Physical tenancy and repository binding | Per-site inference/index instances versus shared service isolation; decide operational cost, identity/cache isolation, site-to-repository mapping and whether public indexes may be shared. No accepted per-site deployment or shared-workspace registry. |
| U2 — Index/ingestion ownership | Inference direct persistent-store access versus mediated access; choose job owner, consistency/publication, deletion, model/version/ACL provenance and recovery guarantees. |
| U3 — Code executor | Choose location, sandbox/privilege boundary, repository credentials, approval binding, locking and failure recovery; ordinary inference must not acquire ambient write authority. |
| U4 — Service/tool/provider contracts | Decide authenticated caller/site propagation, result schemas, compatibility/version negotiation, provider conformance and streaming/realtime transport; logical diagrams do not choose a wire protocol. |
| U5 — Intra-site ACLs | Define document/code/resolution permissions, identity-derived pre-retrieval filters and revocation/cache invalidation; site separation alone is insufficient. |
| U6 — Egress policy | Decide who grants cloud access to which data classes/providers/purposes, how locality and revocation are verified, and how all application/evaluation paths obey policy. |
| U7 — Durable workflow/audit | Choose proposal state machine, concurrency and idempotency guarantees, uncertain-outcome reconciliation, audit durability/redaction/access/retention and restore objectives. |
| U8 — Versions and packaging | Choose app release policy, supported Frappe/Python/service/index matrix and proven monorepo-to-Bench packaging path; validate normal patches/migrate and Docker parity. |
| U9 — Operational/quality budgets | Establish latency, quality, scale, recovery and retention targets; these determine search/reranking changes and production acceptance. |
| U10 — Transparency and future surfaces | Define authorized Debug disclosures; MCP consumer/server/client/trust requirements and Workbench audience/privileged UX before separately reopening them. |

**Deferred:** MCP (R15) preserves a potential adapter seam around explicit
authorized tools, without selecting server/client direction or introducing
a protocol/dependency. Developer Workbench (R20) preserves a separate
engineering surface with privileged authorization/audit, not an employee
chat mode. Qdrant, pgvector, alternate inverted indexes, dedicated search,
reranking and shared multi-workspace routing remain options requiring
separate approval and evidence; none is selected to satisfy extensibility.
`docs/FUTURE_MULTI_WORKSPACE.md` is reference only, not current scope.

## Ordered future migration gates — not executed

Each stage requires a bounded approved OpenSpec behavior change and
independent review. Stages express dependencies, not authorization to build.
Exact operational/quality/recovery targets must be decided before declaring
a gate passed; detailed acceptance methods belong in `EVALUATION.md`.

| Stage | Required future acceptance evidence |
|---|---|
| G1 — Resolve blocking contracts | User-reviewed ADRs for U1–U8 as needed: topology, identity/service binding, tool/provider contracts, executor authority, ACLs, locality and durable state. No recommendation silently becomes an accepted deployment decision. |
| G2 — Authenticated Frappe boundary | Integration/negative tests across every entry point, including legacy/direct tools: browser uses Frappe only; private service verifies caller/site; denied/client-selected mode cannot establish privilege. |
| G3 — Owned state and authorized context | Real Frappe ownership checks and restart/concurrency tests for conversations/proposals; page hints validated, fields/history minimized and reauthorized; permission changes respected; user-scoped realtime and reconnect/cancellation verified. |
| G4 — Isolated knowledge and providers | Cross-site and intra-site negatives demonstrate denied content never reaches retrieved/model context or caches; all-call cloud egress denied by default; safe rebuild preserves unrelated corpora, publishes fresh lexical/vector state and verifies adapter/model/index compatibility and rollback. |
| G5 — Durable tools, approvals and audit | Proposal/draft-first exact payload approval, permission recheck, expiry/rejection/revocation, stale/concurrent attempts, retries/idempotency, uncertain-outcome and audit-failure recovery tested; correlated success/failure/denial evidence; separate code executor confinement demonstrated. |
| G6 — Release and deployment parity | Same source installs/updates in real Bench and Docker; package assets/boot/Desk verified in browsers; compatibility metadata, versioned patches/migrate, CI tests/lint, backup/restore, index migration and rollback proven before release. |
| G7 — Production readiness decision | Independent security/quality/operational review: held-out grounded answers and negatives, full live NLU matrix, provider/locality/audit checks and agreed latency/quality/recovery budgets. Explicit production-write approval remains separate from release and historical phase acceptance. |

The 2026-09-17 reconciliation verifies documentary coverage and source
fidelity only. It does not pass G1–G7, enable production writes, execute
migrations/tests/model calls or remove historical acceptance exceptions.
