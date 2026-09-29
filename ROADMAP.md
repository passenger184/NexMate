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

## Historical pointer — M5 closure, 2026-09-19 (superseded)

> This section records the M5 → M6 decision as it was made. It is **history,
> not an active pointer**: M6, M7 and the post-M7 work below have all since
> closed. It is retained verbatim for provenance. The current position is the
> "Current position" section below.

M5 `durable-tool-execution-audit` is complete: implemented (20/20 tasks), hardened (fail-closed, owner-only, hash pre/site, Frappe ORM business-write, app-local code root), offline-verified (`330` Python tests `OK (1 skipped)`, `67` Node PASS, `7` specs + `1` change `strict PASS`), live-verified (Frappe M5 tables created via `bench --site frontend migrate` exit `0`, `tabNexMate Tool Proposal`/`Audit Entry` `0` rows, DocType authority with naive UTC, mock execution `succeeded` + `audit_pending`/`read-back`), archived, and committed as `ba220a8` (M5 offline) plus hardening (this commit) on `origin/main`. Per user direction the active pointer advanced to **M6 — Release and deployment parity** (packaging/installation direction: R04–R07, R10). That pointer authorized no implementation: M6 needed a separately approved OpenSpec change with its own requirements, design, and acceptance evidence. M4 delivered ACL/generations/egress; M5 delivered durable proposals, audit ledger, and filtered Debug. Remaining limitations: live cross-worker concurrency, live second-actor, live business-write, live uncertain/reconcile, and `frappe_app/` subdirectory packaging are documented as future verification/packaging work.

## M6 CLOSED — 2026-09-19

M6 `m6-open-source-packaging` is complete and formally closed: implemented (13/13 tasks), verified, and archived as `2026-09-19-m6-open-source-packaging`. Verified result only: **Option A preserved the monorepo** (no move, no shim); `apps.json` uses `directory: frappe_app` (plain root-level `bench get-app` does not discover the monorepo — proven by `FileNotFoundError: setup.py` on bench 5.31.0); fresh test-site installation/migration verified on site `test-fresh-clone` (bench 5.31.0, Frappe 16.31.0, app 0.1.0, `migrate` exit `0`); 4 NexMate DocTypes and 4 tables verified with initial counts `0`; imports verified without the repository root on `PYTHONPATH` (offline isolated subprocess + installed-path import); existing tests (`330` Python `OK (1 skipped)`, `67` Node PASS) and strict OpenSpec validation passed. The frontend/shared site was read only, never migrated; no production deployment was performed or claimed. No active implementation pointer remains: further work needs a separately approved OpenSpec change.

## M7 CLOSED — 2026-09-20

M7 `production-readiness-decision` is complete and formally closed: review executed (18/18 tasks), finalized, archived. Final decisions on collected evidence only: release NOT READY, production writes DENIED/PENDING (none authorized), private-data cloud/provider consent NO GRANT — recorded separately with no inheritance between them. Evidence: VL-judge re-score of recorded 2026-08-24 samples (26/45 valid; precision n=1 unusable; NOT held-out), authoritative live NLU matrix 25/29 with 4 named mismatches kept as findings, ERPNext populated-data retrieval unverified, U1–U10 unresolved where found unresolved, O1 staging-only, O5 local-only, O2/O3/O4 unagreed, MCP/Workbench/alternate-search deferred. Staging-continue posture unchanged; no production deployment, write approval, or cloud grant claimed or given. No active implementation pointer remains: further work needs a separately approved OpenSpec change.

## Post-M7 stabilization — CLOSED (evidence and documentation only, 2026-09-23 → 2026-09-26)

After M7 closed, four defects that M7 had recorded as live routing mismatches
were fixed and the resulting regressions contained, via two archived
documentation-scoped changes. These are **stabilization and evidence** work; no
milestone was opened, no architecture or governance decision changed, and no
new gate was passed.

| Change | Implementation commit | Archive commit | Result |
|---|---|---|---|
| `fix-routing-precision-after-m7` | `9f274ed` | `ba51b47` → `openspec/changes/archive/2026-09-25-fix-routing-precision-after-m7/` | Live 26/29; surfaced three regressions |
| `fix-post-live-routing-regressions` | `ee8b0de` | `4ec4463` → `openspec/changes/archive/2026-09-23-fix-post-live-routing-regressions/` | **Live 28/29** |

**Final live routing evaluation (`ee8b0de` closure, 2026-09-23):** 29 total,
**28 passed, 1 failed, 0 harness errors**; model
`qwen2.5-coder:7b` digest `dae161e27b0e`; `evaluation/routing_cases.json`
deliberately unmodified to preserve the M7 baseline. Staging ERPNext was
unreachable during this run, so the ERPNext read branch returned lookup-failure;
the archived evidence records that as a read-branch/lookup-availability
condition, not a routing failure, and the routing verdicts stand.

Resolved by these two changes: code-location question → `code`; ambiguous
"payments" → `clarify`; unrelated new topic → `rag`; a knowledge question no
longer becoming `clarify`; follow-up purchase → `rag`; dead-port degraded path →
safe degraded `clarify` without entering generation.

**Not fixed:** the sole remaining non-pass, `bye` ("see you later"), is repeated
unparseable small-model NLU output. It is recorded as **model-output variance,
not a demonstrated routing regression, and deliberately not relabeled fixed**.

**Do not confuse the two figures.** M7's authoritative live matrix was
**25/29** and remains the historical M7 record. The later 28/29 is post-M7
stabilization evidence. Both changes state verbatim that they carry no
production-readiness, write, cloud, U/O or threshold implication, and that
**M7 remains authoritative**. M7's three decisions — release **NOT READY**,
production writes **DENIED/PENDING**, private-data cloud/provider consent
**NO GRANT** — are unchanged.

## Post-M7 ERPNext evidence — recorded 2026-09-26 (no milestone)

Populated ERPNext business-data retrieval was demonstrated through the real
orchestrated path: `orchestrator.handle_question(mode="developer")` as a normal
integration user → NLU `task` 0.8 → route `erpnext` → `GET /api/resource/Customer/Test`
HTTP 200 (`customer_name = Test`) → payload-grounded local `qwen2.5-coder:7b`
answer with a `[1]` citation. One GET, no writes, no code changes, no cloud.
This closes one M7 evidence gap and is recorded in `progress/CURRENT.md`.

It is **not** a Developer Mode delivery: the run exercised the inference-side
developer path, while the Desk gateway
carried `"execution_scope": "chat-only"`. Desk-facing Developer Mode,
permission parity with the incoming Desk identity (**U5**) and the normal
integration user's `Customer` schema access (403) all remain unproven.

## U5 frappe-native-authorized-erpnext-reads — CLOSED (2026-09-27), independent of M7

Authenticated user ERPNext business-data reads (`document`, `list`) are now
authorized inside the Frappe request process against `frappe.session.user`,
with strict request validation, field-level enforcement before serialization,
minimized results, one metadata-only audit event per read, fail-closed audit,
and externally indistinguishable not-found/permission-denied. Inference no
longer queries ERPNext for those reads and no longer needs the shared
credential for them.

**Scope honesty.** This resolves U5 for **ERPNext business-record reads only**.
Knowledge-corpus retrieval ACL coarse tiers, multi-site tenancy (U1), DocType
schema/metadata authorization, and the shared credential retained for the
version lookup and legacy writes all remain open. `schema` reads stay on the
retained legacy client under the existing per-mode policy.

## Retire `chat-only`, Developer capability, configurable metadata policy — DELIVERED 2026-09-29

The fixed `chat-only` scope is replaced by a generic authenticated scope that
grants nothing; capability is derived live from Frappe roles and carried in the
existing `mode` field. DocType metadata is served in-process by Frappe under
capability plus the administrator-controlled `NexMate Settings` policy
(`all | allowlist`, fail-closed, uncached), with a five-field projection, a
dedicated `doctype_schema` audit action, and a metadata-specific collapse. The
three legacy `/tools/erpnext/*` routes are removed; no-envelope requests cannot
assert `authorized_context`, `scope`, or `conversation`. The `code` route stays
denied pre-entry. Three additive DocType synchronizations, no data migration;
`audit.py` unchanged; `erpnext_read.py` changed only in three operational
bound constants, aligned to the approved service ceilings. Migration ran
2026-09-29 on
`frontend` with a verified backup; live evidence is in the change's
`verification-notes.md`. The metadata field bound is a configurable
administrator value: default 300 fields, immutable service ceiling 500,
immutable byte ceiling 131072. At the default every DocType observed live
on the test site is served, the widest being Sales Invoice at 233 fields.

**Evidence.** Implemented and verified: 457 Python tests OK (1 skipped)
and the Node harness passing, including a dedicated adapter suite and a
boundary suite. Live verification was subsequently performed on 2026-09-27
on test Bench site `frontend` (Frappe 16.31.0 / ERPNext 16.33.0) with explicit
project-owner approval for the migration, the fixtures and the live runs:
`bench --site frontend migrate` exited 0 with all four NexMate DocTypes
persisting and no orphan deletion; role authorization, User Permission,
`if_owner` and DocShare were proven with differing row sets per user; field
minimization returned only the requested fields; exactly three metadata-only
`erpnext_read` audit events were written for three reads (`success`,
`permission_denied`, `not_found`, all `site=frontend`); not-found and
permission-denied produced byte-identical caller output; and an authorized
read with the ERPNEXT credential absent still returned correct user-scoped
rows. Source: the archived change's `verification-notes.md`, "Live evidence"
section. This is recorded evidence, not certification. **Still not
obtained:** adapter-level field-level `permlevel` enforcement (L-7), and
forged-`site` and oversized-list rejection, which are offline-verified only.
Non-strict User Permission on the test site also means NexMate can narrow
but does not always strictly narrow, so the guarantee is "cannot widen".

**This change does not reopen M7.** Release **NOT READY**, production writes
**DENIED/PENDING** and private-data cloud/provider consent **NO GRANT** remain
the authoritative M7 decisions, unchanged. No M8 was created.

## Current position — 2026-09-27

- **M2, M3, M4, M5, M6 and M7 are all CLOSED.** No milestone is active.
- **No active OpenSpec change exists.** `openspec/changes/` contains only
  `archive/`.
- **No M8 exists and none is implied.** No new implementation milestone has been
  approved or authorized.
- Work since M7 has been **evidence and documentation stabilization**, plus one
  separately approved implementation change: U5 `frappe-native-authorized-erpnext-reads`,
  implemented, live-verified, archived and committed. U5 is **not** a new
  milestone and **does not reopen M7**; release **NOT READY**, production writes
  **DENIED/PENDING** and cloud/private-data consent **NO GRANT** are unchanged.
- Any future implementation work requires a **separately approved OpenSpec
  change** with its own requirements, design, tasks and acceptance evidence.
- Blocking the next gate are the unresolved register items **U1–U10** — with
  U5 advanced only for ERPNext business-record reads — and the unagreed
  thresholds **O2–O4**, all recorded in `ARCHITECTURE.md` and
  `progress/BLOCKERS.md`. No U-item and no O-threshold is fully resolved; U1,
  U3, U8, U9 and U10 remain untouched.

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
is authenticated transport with deterministic backend operation denial,
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
