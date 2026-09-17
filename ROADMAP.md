# ROADMAP.md — Historical Phases and Future Migration Gates

The original eight phases were **functionally complete with recorded
exceptions on 2026-08-24**. This is historical acceptance, not a current
phase pointer, universal verification or production readiness. NexMate
post-roadmap work requires a user-approved OpenSpec change; this
reconciliation authorizes documentation only.

`ARCHITECTURE.md` is the sole canonical HLD. `DECISIONS.md` records the
2026-09-17 accepted production direction, not chosen implementation or
production-write/cloud-data approval. `SECURITY.md` remains standing policy:
ERPNext writes are staging-only, flag-gated and individually confirmed;
complete production authorization and audit enforcement remain future gates.

Current scope is one project. Shared multi-workspace routing, MCP and the
separate Developer Workbench remain deferred. Site-isolated private
knowledge is an approved target, not a selected shared-tenancy mechanism.

## Historical Phase 1–8 acceptance

Evidence is dated in `progress/CURRENT.md` and `progress/JOURNAL.md`.
Counts and environments below describe those runs, not today's health or
corpus inventory. Original requirements remain in the historical phase specs.

| Phase | Name | Historical delivery and acceptance | Exceptions / limits |
|---|---|---|---|
| 1 | Public RAG, Developer mode | User-accepted 2026-08-24: 15 developer questions and 3 negatives verified with citations/refusal behavior; local public-doc retrieval and sidebar code. | Real Bench sidebar installation deferred and still unverified. Post-hybrid RAGAS re-score deferred at acceptance, then recovered 2026-09-09 from the completed 2026-09-08 run; valid-row/self-judge caveats apply (`EVALUATION.md`). |
| 2 | Live code read/edit tool | User-accepted 2026-08-24: read/search/explain and confirmed tracked-file, root-scoped, clean-tree atomic Git edits; six tool DoD items recorded verified. | Bench-dependent diff/approve UI unverified; tool verification is not Desk deployment proof. |
| 3 | Company knowledge | User-accepted 2026-08-24: P1–P6 and dual-source preference verified; 7,410 public + 321 project chunks recorded. | Source-type tags distinguish provenance, not authenticated ACLs; ingestion is not cloud consent. |
| 4 | Project memory | Accepted 2026-08-24: session continuity including second-order follow-up; 4 resolutions indexed (3 backfilled, 1 automatic). | Service JSON/localStorage identity is not authenticated user ownership; browser transcript restoration remains unverified/target work. |
| 5 | Read-only ERPNext API tool | Accepted 2026-08-24: schema/list/filter/document live tests at http://localhost:8081; GET-only client and 403/404 mapping. | Shared upstream account does not establish incoming-user authorization; API tests are not Bench installation proof. |
| 6 | Orchestrator/router | User-accepted 2026-08-24: three task routes, misroute guards and live version injection verified. | Does not accept the later seven-route conversational/NLU redesign; full live NLU matrix remains incomplete. Version injection is not version-pinned retrieval. |
| 7 | Employee/User mode | Accepted 2026-08-24: code/schema denied, orchestrated public-doc persona and developer control verified live. | Caller-selected mode is not an authenticated role; direct tools/legacy paths do not inherit orchestration guards. Wider rollout is not accepted. |
| 8 | Guarded ERPNext writes | Accepted 2026-08-24: flag-gated proposal/confirm create+update, schema preflight and local audit tested on staging at localhost:8081. | Delete deliberately unimplemented. RAM proposals and post-write audit are partial safeguards, not durable production approval/audit. Production writes remain unapproved. |

## Sequencing and standing boundaries

- Historical order was public RAG, live code, company knowledge, memory,
  ERPNext reads, orchestration, employee mode, then ERPNext writes. Old
  “Phase 7 writes” wording in original specs/ADRs is historical numbering,
  not today's sequence. Earlier phase prohibitions do not prohibit
  maintenance of later implemented features or authorize new work.
- Retain the incremental principle: each approved change needs a usable,
  independently reviewed outcome and the applicable `EVALUATION.md` proof,
  not merely “runs without errors” or a build agent's self-report. Historical
  acceptance retains its explicit exceptions; no new phase is closed here.
- Phase 2 code edits remain separate from Phase 8 business writes. Product
  root scoping, tracked-not-ignored files, clean tree, per-edit confirmation
  and atomic commits remain mandatory (`SECURITY.md`). They do not require
  commits for this docs-only workflow.
- `docs/UI_SPEC.md` owns standing interactions and
  `docs/UI_VISUAL_SPEC_updated.md` the canonical blue visual direction.
  UI references are not evidence of Bench delivery. Resolution memory is
  a corpus distinct from conversation state (`docs/PHASE_4_SPEC.md`).

## Immediate bounded sequence — 2026-09-17 planning update

The user approved implementing `authenticated-frappe-control-plane` after
its plans are internally consistent and strictly validated; this update is
planning only, not implementation or complete M2/G2 acceptance. Its scope
is authenticated chat-only transport with deterministic backend tool denial,
not owned sessions, ACL retrieval or production readiness. DECISIONS.md's
appended clarification records the four resolved choices and approval.

Immediately after that bounded boundary is verified, the next milestone is
the separately approved `frappe-owned-conversation-state` change: persistent
Frappe-owned records, authenticated user ownership, site association,
replacement of caller-controlled ownership and the JSON store, and a
migration/compatibility strategy. Legacy `session_id` forwarding is only a
temporary continuity bridge until then, never auth, ownership or isolation.
This sequence neither implements nor approves the successor, passes M2/M3,
nor changes the wider gates below.

## Ordered future migration milestones — not authorized implementation

The stages below express dependencies, not a new active numbered phase or
permission to build. Each needs a separately approved OpenSpec change with
maintained requirements/scenarios before implementation. Acceptance methods
are in `EVALUATION.md`; the HLD owns design and its R01–R20 status matrix.
No gate is passed by this documentation change.

| Stage | Dependencies and future acceptance gate | Requirement coverage |
|---|---|---|
| M1 Resolve blocking contracts | User-reviewed decisions for site/index isolation, inference and tool contracts, identity propagation, executor/repository ownership, ACLs and egress policy. Resolve state/audit guarantees, transport, version/packaging policy and measurable budgets before dependent gates can pass. | R01–R09, R13, R16–R19 |
| M2 Authenticated Frappe boundary | After M1: browser uses Frappe only; private inference validates caller/site binding; identity-derived authorization covers orchestration and legacy/direct tools. No client-selected privilege or transparent-proxy substitute. | R04, R09, R13, R18 |
| M3 Frappe-owned state and authorized context | After M2: owner/site-bound conversations and proposals persist across restart; page hints and bounded history are authorized again on later turns/permission changes. Define streaming/realtime reconnect, cancellation and user-scoped delivery. | R10–R13, R17–R18 |
| M4 Isolated knowledge and providers | After M2 and relevant M3 context contracts: cross-site and intra-site denied content never enters candidates/model context; all-call egress is deny-by-default. Safe rebuilds preserve unrelated corpora and refresh lexical state; provider/index compatibility and source/version provenance are tested. | R01–R03, R13, R16, R18–R19 |
| M5 Durable tools, approvals and audit | After M2–M4: explicit authorized tool contracts and separate code executor; exact immutable human-approved payload, recheck, expiry/rejection, restart/concurrency/idempotency and uncertain-outcome behavior. Correlated successful/failed/denied audit evidence and policy-filtered Debug; no SQL feature implied. | R08–R09, R14, R17–R19 |
| M6 Release and deployment parity | After preceding security/state gates: same application source installs/updates in real Bench and Docker; assets, Desk behavior, streaming/realtime, compatibility metadata, versioning, patches/migrate, tests/lint, backup/restore and rollback verified. Git -> packaged Frappe app -> tested installation/update -> explicitly approved release. | R04–R07, R10 |
| M7 Production readiness decision | After M1–M6: independent security/quality review, full and held-out question/negative sets, operational latency/cost/recovery budgets and audit/locality evidence. Release approval and production-write approval are separate; the latter requires a specific environment decision in `DECISIONS.md`. | All applicable R01–R20; deferred rows remain explicit exclusions |

R15 MCP and R20 Developer Workbench have **no implementation milestone** in
this change. Reopening them requires separate trust/consumer and privileged
surface requirements and authorization/audit review. Workbench stays
separate from employee Desk chat. R16 alternate search/reranking engines,
Qdrant/pgvector and shared tenancy remain options requiring measured need
and separately approved contracts, not installations implied by these gates.
