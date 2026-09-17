## Context

See `proposal.md` for motivation and scope. The 2026-09-17 read-only exploration found a single-project, browser-facing, stateful FastAPI application rather than the intended Frappe-controlled production system. Reuse that exploration, checking cited files against the working tree before changing documentation. No current environment connectivity, test result, or deployment health was established by this exploration.

Source anchors for the baseline:

| Concern | Observed implementation and starting references |
|---|---|
| Browser/Frappe boundary | Boot publishes an API URL; browser fetches FastAPI directly: `frappe_app/erpnext_ai_copilot/boot.py:10`, `frappe_app/public/js/copilot.bundle.js:337`, `service/main.py:289`. |
| Routing | Seven response routes at `service/main.py:224`; exact fast paths and NLU at `orchestrator.py:153`; task router at `orchestrator.py:468`; dispatch at `orchestrator.py:754`. Troubleshoot is an NLU kind mapping to code or clarify, not an eighth route. |
| Capability model | `capabilities.py:14` is a descriptive catalog, not authoritative tool authorization. Direct tool endpoints also exist outside orchestration. |
| Identity/state | Caller-provided mode/session at `service/main.py:198`; JSON history at `service/session_store.py:27`; browser identity persistence at `frappe_app/public/js/copilot.bundle.js:36`. No source-established incoming authenticated principal. |
| Retrieval | `rag/retriever.py:128` fuses public/company vector pools and BM25 with RRF; confidence at `rag/retriever.py:258`; local singleton BM25 at `rag/keyword_index.py:209`. |
| Ingestion/memory | Heading/resplitting at `ingestion/chunk_and_embed.py:120`; Python AST at `ingestion/ingest_project.py:76`; commit/diff/context resolutions at `tools/memory.py:67`. |
| Generation | LiteLLM at `rag/generator.py:199`; corrective grounding checks are not semantic guarantees. No enforced cloud-consent boundary in this call path. |
| Tools | Shared configured ERPNext principal at `tools/erpnext.py:44`; separate Git edit at `tools/edit.py:234` and create/update flow at `tools/erpnext_write.py:214`. Proposals are process-local; audit is local and post-write. |
| Version/telemetry | Live-version TTL cache at `orchestrator.py:391`; structured request logging at `service/main.py:601`, not complete audit. Version injection is not version-pinned retrieval. |
| Packaging | `frappe_app/pyproject.toml:9` uses dynamic versioning and `:16` declares Frappe >=15 despite the v16 product target. Hooks publish assets; package/install correctness is unverified. |
| Verification | `progress/CURRENT.md` and dated `progress/JOURNAL.md` entries record historical API tests, mock tests, incomplete live NLU acceptance and unverified real Desk integration. `evaluation/ragas_eval.py` evaluates retrieval/generation, not the complete production boundary. |

The initial working tree already includes changes to `progress/CURRENT.md` and `progress/JOURNAL.md` and unrelated untracked files. Preserve them. Planning may only write this change directory; apply may only make the documentation edits described here. Do not change `opencode.json`, runtime/package files, or other agent configuration to resolve documentation drift.

## Goals / Non-Goals

**Goals:**

- Establish an authoritative, reviewable current-versus-target HLD with traceable evidence, clear status, and no implied runtime delivery.
- Preserve the user's twenty long-term requirements and identify which future decisions block their implementation.
- Define documentation ownership, historical provenance, and independently verifiable future migration gates.

**Non-Goals:**

- No implementation of target contracts, DocTypes, authentication, provider adapters, tool registry, deployment, indexing changes, or UI behavior.
- No change to existing runtime exposure, privileges, production-write policy, compatibility identifiers, or provider configuration.
- No exhaustive new runtime specification baseline: `skip_specs: true` intentionally avoids promoting proposed behavior to maintained capability specs in a documentation-only change.

## Decisions

### 1. One canonical HLD, with explicit status dimensions

Rewrite `ARCHITECTURE.md` as the HLD, not a thin index pointing at a second HLD. This change's design explains the editing approach and is not the permanent HLD. Link focused existing specs and ADRs instead of copying whole documents.

Use four architectural statuses: **current implementation**, **approved target direction**, **unresolved implementation decision**, and **deferred capability**. Separately track evidence: **implemented**, **tested** (unit/mock/integration/browser with scope), **live-tested** (dated environment), **unverified**, **planned**, **deferred**. These are not a single completion ladder: a capability can be implemented and unverified in Bench. Historical user acceptance retains its exceptions and date.

Alternative rejected: one diagram mixing existing and desired components, which would conceal the trust-boundary migration. Alternative rejected: labeling all target choices accepted because the user approved the overall direction.

### 2. HLD structure and component/state ownership

The HLD will contain:

1. Product scope, v16 target, glossary, status legend, and document authority.
2. Current component and request-flow diagrams with source references.
3. Current orchestration, retrieval, source types, memory, versions, tools, state, frontend, and known limits.
4. Approved production component/deployment diagrams and responsibility table.
5. Trust boundaries, identity, authorization, site/private-data boundaries, data classes and egress policy.
6. Target Desk/context flow, explicit tool contracts, proposal/approval execution lifecycle, audit and Debug policy.
7. Provider interfaces, search lifecycle/scaling, version/provenance compatibility.
8. Bench/Docker parity, application release/version/migration lifecycle.
9. Evidence matrix, unresolved decisions, deferred capabilities.
10. Ordered migration direction and acceptance gates.

Document the following ownership shift without implementing it:

| Resource/responsibility | Current | Approved target / remaining choice |
|---|---|---|
| Browser API | Direct FastAPI calls, including tools/approvals | Authenticated Frappe methods only; browser page hints are untrusted input. |
| Identity/authorization | Client mode; upstream shared API account | Frappe identity/permissions authorize context, retrieval scope, tools and each execution. The LLM never grants access. |
| Conversation state | Service JSON files; localStorage ID | Persistent Frappe-owned records with ownership/access checks; inference receives bounded authorized history. |
| Heavy AI work | FastAPI router/RAG/generation plus privileged tools | Separate private inference service; no authoritative user/workflow state. Model/index caches may exist; persistent index ownership remains to be chosen. |
| Business data | ERPNext REST using configured credentials | ERPNext/Frappe remains the record authority; access and execution under Frappe-enforced permissions. Internal call/execution contract remains to be designed. |
| Knowledge | One Chroma collection plus BM25 snapshot | Site-isolated private search boundary, per-user permitted retrieval; physical topology and public-index sharing unresolved. |
| Proposals/audit | RAM proposals; Git/local JSONL evidence | Durable Frappe-controlled proposal/approval/audit lifecycle; exact schema, storage guarantees and retention unresolved. |
| Code/Git actions | FastAPI process mutates configured checkout | Explicit privileged execution boundary authorized by Frappe; executor placement and site-to-repository binding unresolved. |

Alternative rejected: a transparent proxy described as a control plane. Transport forwarding alone does not establish permission, state, or execution authority. Alternative rejected: treating statelessness as a ban on all caches or as justification for adding another service without need.

### 3. Preserve all twenty requirements with traceable status

The HLD coverage matrix will retain these identifiers so review can check that nothing was dropped. Status below describes direction, not implementation acceptance.

| ID | Requirement and architectural disposition | Documentation acceptance / future proof required |
|---|---|---|
| R01 | LLM abstraction: current LiteLLM generation; target supports Ollama, OpenAI, Anthropic, other compatible and future providers. | Distinguish supported configuration from provider-by-provider testing; document request/output, locality, timeout/error and policy boundaries. No automatic provider switching. |
| R02 | Embedding abstraction: local sentence-transformers now; clean future provider boundary is target. | Document interface, locality, dimensions/model identity and required rebuild on incompatible changes; no remote embeddings enabled. |
| R03 | Vector-store abstraction: Chroma now; portable adapter boundary is target; Qdrant is a future option, not a selection. | Document search/filter/upsert/delete and isolation contract, metadata/index migration; do not claim today's direct Chroma code is already portable. |
| R04 | Deployment: Frappe authenticated control plane plus separate private heavy-AI inference is approved target. | Browser/Frappe/inference/provider/store/executor trust-boundary diagrams; Docker is deployment, not another app implementation. |
| R05 | Professional lifecycle is target: Git repository -> NexMate Frappe app -> Bench/Docker -> test/lint/migrate -> release -> installation/update. | Document future CI/check, migration, release, rollback and restore gates; no release or working Docker claim. |
| R06 | Same application source across ordinary Bench and Docker is target invariant. | Document packaging/topology separation and future dual-environment install/update tests; no environment-specific application fork. |
| R07 | Deliberate app versioning, compatibility in pyproject.toml, normal Frappe patches/migrate are target. | Record current dynamic version and >=15 declaration versus v16 scope as a gap; exact supported version range and policy remain future decisions. Do not edit package metadata. |
| R08 | Complete auditable lifecycle is target; current telemetry/Git/JSONL is partial. | Include AI requests, tool calls, permitted retrieval provenance, proposals, approvals/rejections/expiry, executions, failures, security events, actor/site/correlation and retention/redaction decisions. |
| R09 | Explicit internal tools with authorization contracts are target; current routing is hard-coded with descriptive registry. | Document tool input/output, permission/context, side-effect class, approval, errors and audit boundaries; retain seven routes as routing outcomes, not seven agents/tools. |
| R10 | In-Desk sidebar/chat, history, streaming, Frappe realtime, Frappe-owned sessions are target; partial sidebar exists. | Distinguish current complete-JSON responses and missing transcript restoration from target; define future reconnect, cancellation, authorized realtime delivery and browser/Bench tests. |
| R11 | Authorized page context (route, DocType, document name) is target. | Trace browser hint -> Frappe validation/permission check -> minimal allowed document context; example Sales Invoice SI-00042 does not authorize access by itself. |
| R12 | Context-aware answers using authorized document data and conversation history are target; current history/live payload generation is partial. | Document minimization, ownership, bounded history, reauthorization on subsequent turns and permission changes. |
| R13 | Authorization before retrieval/execution is mandatory target. | Identity-derived permitted corpus/data/tool scope must precede retrieval and tool use; LLM classification and post-retrieval filtering are not authorization substitutes. Future negative tests must prove denied data never reaches model context. |
| R14 | Debug/transparency view is target, not current telemetry. | Specify role/policy-filtered retrieval info, documents/fields accessed, raw results and generated database queries only where such queries exist and disclosure is permitted. No SQL-generation feature implied. |
| R15 | MCP is deferred. | Preserve future adapter seam and unresolved server/client direction, trust and consumer requirements; no protocol/dependency introduced. |
| R16 | Search scaling is target extensibility; alternate inverted index, pgvector, dedicated search and reranking are deferred options. | Document current BM25/vector/RRF and freshness/rebuild risks; future choices require scale/quality evidence and site/ACL-preserving contracts, not parallel engines installed now. |
| R17 | Production writes are proposal/draft-first with human approval; current create/update safeguards are partial staging flows. | Future gates cover durable ownership, immutable approved payload, permission recheck, expiry/rejection, concurrency, retries/idempotency, uncertain outcomes and auditable failure; no production enablement. |
| R18 | Each Frappe site's private knowledge/search is isolated, approved target. | Explicitly resolve later per-site deployment versus shared service, repository binding and public-index sharing. Site isolation and intra-site user ACLs are separate requirements. |
| R19 | Company/live data local by default; cloud only by explicit policy, approved target not runtime-enforced today. | Data classification covers prompts, history, NLU/condensation, documents, code, resolutions, live results, embeddings, telemetry and debug; deny-by-default egress across all provider calls. Secrets excluded regardless of normal content approval. |
| R20 | Developer Workbench is deferred engineering surface, separate from employee Desk chat. | Preserve privileged code/tool boundary and future authorization/audit requirements without introducing a Workbench UI or conflating mode selection with authority. |

### 4. Explain current retrieval and routing accurately

Document source types actually indexed (`public_doc`, `company_doc`, `our_code`, `resolved_issue`) separately from reserved/future `core_code`. Show public/company vector pools, global lexical candidates, weighted RRF, deduplication and project-scope preference. Describe confidence as a calibrated heuristic separate from NLU confidence, not proof of accuracy.

Record observed limits rather than fixing them: public ingestion recreates the shared collection; BM25 can become stale; current-code reindex does not automatically follow edits; source-type tags are not ACLs; current similarity scales differ for vector versus keyword-only candidates; citation/identifier repair is not fail-closed semantic validation. Keep detailed bug remediation in future changes.

Show exact conversational fast paths, NLU kinds, task routing, distinct degraded/default behavior, deterministic capability/clarification responses, and direct tool endpoints. Do not describe multi-step autonomous agents, an executable permission registry, or universal version enforcement where source does not establish them.

### 5. Documentation ownership and bounded reconciliation

| Document | Canonical responsibility |
|---|---|
| ARCHITECTURE.md | HLD: current and target design, boundaries, state, constraints, open decisions and migration overview. |
| DECISIONS.md | Decision rationale, alternatives, status, provenance, consequences and supersession; single canonical decision ledger. |
| ROADMAP.md | Historical phase acceptance plus future milestone ordering/dependencies and acceptance gates. |
| SECURITY.md | Standing policy, authorization/locality/approval/audit requirements; distinguish policy from enforcement. |
| EVALUATION.md | Acceptance criteria, test types, evidence requirements and future production gates. |
| progress/ | Dated observed evidence and short current status/blockers, not design authority. |
| openspec/specs/ | Maintained behavioral requirements/scenarios introduced by future scoped behavior changes; not evidence of verification. |
| openspec/changes/ | Proposed deltas, local designs/tasks and verification; not competing permanent HLDs. |
| PROJECT.md | NexMate name, audiences and product invariants. |
| AGENTS.md | Document read/authority rules and approved post-roadmap work scope; security constraints remain in force. |
| DEVELOPMENT.md / README.md | Development/release runbook versus concise onboarding links; do not duplicate architecture. |

Use the roadmap's actual historic numbering: 1 public RAG, 2 live code, 3 company knowledge, 4 project memory, 5 ERPNext reads, 6 orchestration, 7 employee mode, 8 ERPNext writes. Label old phase specs historical instead of erasing their original requirements. Historical ADR bodies keep historical numbering, with explanatory annotations where needed.

Standardize current documentation-facing product name to NexMate. Preserve NexPilot in historical quotations with clarification. Do not rename technical package names, environment variables, storage keys or runtime UI files. State remaining runtime naming drift as a future cosmetic/compatibility decision.

Existing UI references need status/cross-reference reconciliation: `docs/UI_VISUAL_SPEC_updated.md` supersedes amber direction, while auto-loaded references still point to older material. Fix documentary authority and stable cross-references only; do not change styling or agent configuration.

Supporting documentation may include existing phase specs, UI specs, `docs/FUTURE_MULTI_WORKSPACE.md`, `docs/OPEN_SOURCE_LAUNCH_SPEC.md`, app README, changelog and progress. Reconcile relevant contradictions only, not unrelated content. Open-source packaging claims must not certify root-repository Bench installability without evidence.

### 6. ADR restoration and approval provenance

Exploration located four removed entries in `c2e5004:DECISIONS.md`, removed by `a576c7b`: documentation crawl source, hybrid chunking, explicit Ollama URL mapping, and hybrid retrieval/confidence gates. During apply, compare those exact historical versions, restore original text/date with a restoration note identifying both revisions, and preserve existing later entries. Do not attribute fresh approval or retroactively invent consent. If further history shows an entry was superseded, retain it with explicit supersession rather than deleting it.

Record the user-approved production direction with provenance to this 2026-09-17 request and distinguish acceptance of direction from runtime implementation/production authorization. Exact deployment isolation topology, executor placement, service authentication mechanism, retention, version matrix and adapters remain proposed/unresolved. Single-project current scope stays accurately described; do not equate independent single-site installations with an approved shared multi-workspace registry.

Alternative rejected: rewriting old ADRs as if the target had always been decided. Alternative rejected: using journal observations as proof of an explicit security approval.

### 7. Evidence and acceptance discipline

Place the architectural capability/evidence summary in the HLD, detailed dated evidence links in `progress/`, and verification methods in `EVALUATION.md`. Rows record capability, architectural status, source anchor, verification type, dated artifact/environment if available, limitation and next gate. Missing evidence is explicit, not guessed.

Preserve historical test totals only as dated results. Mocked NLU and stub-DOM tests are not live classifier or Bench evidence. One later live follow-up does not complete the full NLU matrix; a past outage is not proof the model remains unreachable. RAGAS valid-row counts and self-judge limitations accompany means; do not conclude a score drop is harmless judge noise. Retrieval/generation evaluation is not orchestration, permissions or UI evaluation. Docker remains planned; real Bench installation, assets and Desk behavior remain unverified absent specific evidence.

For this change, acceptance is documentary completeness and consistency, including R01-R20 coverage and preservation of runtime scope. It is not passing the future production gates. No live tests, lint installation, model calls or data mutation are needed to validate documentation artifacts.

## Risks / Trade-offs

- Target text mistaken for delivered behavior -> separate diagrams/status columns; forbid unqualified production-ready claims.
- Documentation silently approves costly/high-risk choices -> keep an unresolved register with decision prerequisites; accepted direction is not selected implementation.
- Restored ADRs conflict with current design -> preserve provenance and add supersession/interpretation notes rather than altering historical facts.
- Large cross-document scope produces unnecessary churn -> canonical ownership table, targeted reference fixes, and review of every changed file.
- Existing user modifications lost -> inspect diffs before apply edits; preserve additions; stop on conflicting intent.
- Provider portability overstated -> document interfaces and migration obligations, not zero-cost interchangeability.
- Audit/transparency becomes a private-data dump -> specify policy-filtered provenance, redaction, retention, least privilege and local default; complete auditability does not mean retaining every raw prompt/result.
- Specs skipped could hide future requirements -> R01-R20 coverage remains explicit in canonical HLD; future implementation proposals add capability specs and proof obligations before building.

## Migration Plan

### Applying this documentation change

1. Revalidate source/history anchors and existing user diffs; use the exploration as the baseline rather than a generic new audit.
2. Rewrite the HLD with current/target separation, R01-R20 coverage, ownership, evidence and open decisions.
3. Restore ADR provenance, reconcile the primary authority documents and targeted secondary references.
4. Update current evidence/blocker summaries without claiming new runtime verification.
5. Run documentation consistency/link checks and OpenSpec validation; independent reviewer checks coverage and factual claims before marking tasks complete.

No deployment or data migration occurs. Rollback, if requested, consists only of reverting the intended documentation edits while preserving pre-existing user work; no automatic commit or rollback is authorized.

### Future runtime migration direction to document, not execute

| Stage | Future acceptance gate |
|---|---|
| Resolve blocking contracts | User-reviewed decisions for site isolation topology, inference contract, tool execution ownership, identity propagation and data-egress policy; bounded OpenSpec proposals/specs. |
| Authenticated Frappe boundary | Browser uses Frappe only; private service verifies caller/site binding; identity-derived authorization covers all entry points including legacy/direct tools; no client mode privilege. |
| Frappe-owned state and authorized context | Owner-bound persistent conversations and proposals survive restart; history/page hints are authorized; realtime delivery is user-scoped; permission changes are respected. |
| Isolated knowledge and providers | Cross-site and intra-site denied content never enters retrieval/model context; cloud egress denied by default; index rebuild preserves unrelated corpora and refreshes lexical state; adapter compatibility tested. |
| Durable tools, approvals and audit | Proposal/draft-first writes; exact approved payload, permission recheck, TTL/rejection, concurrency and retry/uncertain-outcome tests; correlated successful/failed/denied action evidence. Separate code executor authority. |
| Release and deployment parity | Same source installs and updates in real Bench and Docker; assets, streaming/realtime, compatibility metadata, patches/migrate, tests/lint, backup/restore and rollback verified before release. |
| Production readiness decision | Independently reviewed security and quality evidence, held-out answers and negative cases, operational budgets, audit/locality validation, explicit production-write approval separate from release. |

Stages indicate dependencies, not authorization to build. Exact latency, quality, retention and recovery targets require future decisions before their gate can pass. Workbench, MCP, shared tenancy and alternative search engines remain deferred, reopened only through separately approved changes.

## Open Questions

These questions are intentionally deliverables of the HLD's unresolved register, not blockers to this documentation-only approach:

- Per-site inference/index deployments versus shared service isolation; site-to-repository mapping; permitted public-index sharing?
- Does inference access persistent indexes directly, and which component owns ingestion jobs, consistency and lifecycle?
- Where does privileged code execution run, and how are approved requests and repository credentials confined?
- Which service-auth protocol, tool/result contract, realtime/streaming transport and version-negotiation scheme?
- Which permission/ACL representation applies to company documents, code and resolved issues before retrieval?
- Which policy grants cloud access to which data classes, and how are revocation and provider locality verified?
- Which proposal state machine, concurrency/idempotency semantics, audit durability/retention and uncertain-outcome reconciliation?
- Which exact app/Frappe compatibility matrix, release versioning policy and validated monorepo-to-Bench packaging path?
- Which measured thresholds reopen reranking/search-store changes, MCP and Developer Workbench, and what Debug disclosures are permitted per role?

Document options and consequences; do not choose them merely to close this change.
