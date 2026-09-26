# progress/BLOCKERS.md — Open Blockers

List anything that stopped forward progress and needs a human decision.
Remove an entry once resolved, and note the resolution in
`progress/JOURNAL.md`.

**Last updated:** 2026-09-26 — brought forward under the documentation-only
OpenSpec change `reconcile-post-m7-project-state`, using only verified current
evidence from the M2–M7 archives, the two post-M7 routing changes and
`progress/CURRENT.md`. This pass ran no runtime test, model call, network check
or live configuration inspection. **M7's governance decisions are reproduced
below unchanged.**

## Governance blockers — UNCHANGED

These are not documentation gaps. They are standing governance decisions and
explicitly unagreed thresholds, carried forward verbatim in substance from the
M7 `production-readiness-decision` review (archived
`2026-09-20-production-readiness-decision/`).

- **Release readiness: NOT READY.** M7 CLOSED and authoritative.
- **Production-write authorization: DENIED/PENDING** — no production writes
  authorized, no named production environment proposed. Staging-only posture
  unchanged per `SECURITY.md`.
- **Private-data cloud/provider consent: NO GRANT** — scope is local-only; all
  cloud paths remain deny-by-default with zero data-class grants recorded.
- **Review posture:** staging-only, local-only generation.
- **Direction is not choice or consent.** Authenticated Frappe control/state
  ownership with separate private inference is approved direction, not a
  selected per-site/shared topology, executor/protocol or implementation.
  Provider configuration is not private-data cloud consent. No present
  environment settings are certified here.
- **Production contracts unresolved (U1–U10).** `ARCHITECTURE.md` owns the
  decision register: physical tenancy/repository binding (U1), index/ingestion
  ownership (U2), executor confinement (U3), identity/service/tool/provider/
  streaming contracts (U4), intra-site ACLs (U5), all-call egress
  grants/revocation (U6), durable state/audit (U7), version/packaging policy
  (U8), operational budgets (U9), Debug/MCP/Workbench disclosure (U10). Per the
  M7 rule, M2–M5 delivering *mechanisms* changed evidence states, not decision
  states; **no U-item is resolved**.
- **Thresholds requiring explicit agreement (O2–O4).** O2 latency/cost/recovery
  budgets; O3 held-out/NLU quality bars; O4 audit retention/deletion windows and
  Debug disclosure policy. O1 staging-only and O5 local-only were confirmed by
  M7. No numeric threshold has been invented here.
- **Deferred, not missing delivery.** MCP (R15), Developer Workbench (R20),
  alternate search/reranking engines, Qdrant/pgvector, shared multi-workspace
  routing and ERPNext delete remain explicitly postponed. Reopening any requires
  separate approved scope.

## Closed evidence gaps

Verified closed since the previous version of this file. Recorded as evidence,
not as new approvals, and each entry is **bounded** by the still-open items
listed further below.

- **M2 authenticated Frappe control plane — DEMONSTRATED (bounded), 2026-09-18.**
  Live Desk/Frappe acceptance 12/12 PASS on site `frontend`: Desk reachable
  (HTTP 200), app loaded and hooks confirmed, authenticated `ask()` via
  session cookie + Frappe CSRF, **no direct browser→inference traffic**,
  server-derived user/site/persona, forged `user`/`execution_scope` fields
  refused, 401 fail-closed, minimal `/health`, chat-only preserved, no
  code/ERPNext/write dispatch, and clean leak scans. *Bounded:* archived M2
  task 6.3 was left unchecked as unverified; page-hint validation and Desk
  streaming/realtime/transcript restore remain open.
- **M2 packaged Desk assets — DEMONSTRATED 2026-09-18.** The built
  `copilot.bundle.7NJBDU3K.js` and its stylesheet were served with HTTP 200 and
  the bundle hash appeared in the Desk HTML, i.e. `app_include_js`/css build and
  injection plus boot delivery worked in a real Bench.
- **M3 Frappe-owned conversation state — DEMONSTRATED 2026-09-18.** Live
  `frontend` migrate created the tables; start → ask → transcript → reset
  verified; a non-privileged actor was refused on an Administrator-owned
  thread and served its own; 3-way parallel appends serialized (1 winner + 2
  loud `Conversation is busy`); restart preserved threads; the legacy JSON
  session store was deleted and `session_id`/reset paths fail explicitly
  (422/404). *Bounded:* cited-RAG-with-history and real-browser transcript
  restore remain open.
- **M4 ACL, index generations and egress — DEMONSTRATED 2026-09-18.** Coarse
  retrieval ACL stamped at ingestion and enforced pre-retrieval on vector pools
  and BM25 candidates; live metadata backfill of 7,410 public + 325 project
  chunks with vectors untouched and a metadata backup kept; `gen-1-m4` published
  at a verified 384-dim fingerprint; cross-site, intra-site and unstamped
  negatives proven absent from all candidates; role grant/revoke effective
  without restart; full deletion → rollback → revocation-refusal cycle; 15/15
  held-out questions non-empty with zero legacy leaks; deny-by-default egress
  choke point wired into generation, retries, NLU, condensation, embeddings and
  judges. *Bounded:* full intra-site ACL parity was **intentionally deferred**
  (coarse tiers only), per-provider conformance is still missing, revocation
  immediacy inherits a Frappe roles-cache caveat, and no cloud grant mechanism
  exists (**U6**).
- **M5 durable proposals, audit ledger and filtered Debug — DEMONSTRATED
  (bounded), 2026-09-19.** Durable actor/site-bound proposals with SHA256
  immutable payload, expiry, preconditions, advisory locking and an idempotency
  key; a correlated redacted audit ledger; a policy-filtered Debug view; a
  confined code/Git executor. Live `frontend` migrate created the DocTypes and
  tables at `0` rows, and a mock execution returned `succeeded` with
  `audit_pending` and read-back. *Bounded:* live concurrency stress, a live
  second actor, live business-write execution and live uncertain-outcome
  reconciliation were **not** performed; audit retention/redaction/access and
  restore objectives remain unselected (**U7**); executor placement, credentials
  and locking remain undecided (**U3**).
- **M6 monorepo packaging and fresh-site install — DEMONSTRATED 2026-09-19.**
  Option A preserved the monorepo (no move, no root shim); `apps.json` uses
  `directory: frappe_app`, with plain root-level `bench get-app` proven *not* to
  discover the monorepo (negative control). Fresh-clone install and
  `bench --site test-fresh-clone migrate` exited `0`; 4 NexMate DocTypes and 4
  tables at initial counts `0`; imports verified without the repository root on
  `PYTHONPATH`. *Bounded:* the Docker custom-image build was guardrail-blocked
  and never run; the version matrix/policy, patches/upgrade, backup/restore and
  rollback are unevidenced (**U8**); CI tests/lint are **not configured**; the
  shared frontend site was read only, never migrated.
- **Live conversational/NLU routing defects — CLOSED.** M7 recorded four live
  route mismatches (`code-where`→rag; `followup-purchase`,
  `ambiguous-payments`, `contam-newtopic`→erpnext). All four were fixed by
  `fix-routing-precision-after-m7` (`9f274ed`), which surfaced three regressions
  (a knowledge question flipping RAG→clarify, a follow-up purchase moving to
  clarify instead of RAG, and an uncaught provider exception escaping through
  RAG generation in the dead-port probe). Those three were contained by
  `fix-post-live-routing-regressions` (`ee8b0de`). Final live result
  **28/29 passed, 1 failed, 0 harness errors** (model
  `qwen2.5-coder:7b` digest `dae161e27b0e`, `evaluation/routing_cases.json`
  unmodified). Staging ERPNext was unreachable during that run, so the ERPNext
  read branch returned lookup-failure; the archived evidence records this as a
  read-branch/lookup-availability condition, **not** a routing failure, and the
  routing verdicts stand. M7's 25/29 remains the authoritative M7 figure; the
  later 28/29 is post-M7 stabilization evidence with no production-readiness,
  write, cloud, U/O or threshold implication.
- **ERPNext populated business-data retrieval — DEMONSTRATED 2026-09-26.** A
  normal (non-administrator) integration user question routed through
  `orchestrator.handle_question` reached `GET /api/resource/Customer/Test`
  (HTTP 200, `customer_name = Test`) and produced a payload-grounded local
  answer with a `[1]` citation. One GET, no writes, no code changes, no cloud.
  This closes the M7 gap *"ERPNext populated-data retrieval unverified"* for
  that capability and path only. *Bounded:* the run exercised the
  **inference-side** developer path with `chat_only` at its default `False`,
  bypassing the Desk gateway's hard-coded `"execution_scope": "chat-only"`; the
  Desk-facing Developer Mode experience is therefore **not** demonstrated, and
  the normal integration user's `Customer` schema access remains 403.
- **Documentation reconciliation — CLOSED 2026-09-17.** Independent read-only
  architecture and security reviews found no blocking documentation findings;
  strict OpenSpec validation and `git diff --check` passed. Archived at
  `openspec/changes/archive/2026-09-17-reconcile-architecture-and-production-hld/`.
  (Reconciled forward for project state on 2026-09-26 under
  `reconcile-post-m7-project-state`.)

## Still-open evidence

Not blockers to documentation; they block the dependent production gates. Each
needs its own separately approved OpenSpec change and a controlled environment.

- **Held-out grounded/negative evaluation — MISSING.** No held-out set exists.
  The M7 VL-judge re-score used *recorded* baseline samples and does not satisfy
  this row (26/45 valid; precision n=1 unusable as an aggregate; shared Qwen2.5
  lineage, so only partial judge independence).
- **Independent judging and per-question groundedness review — OUTSTANDING.**
  The recorded RAGAS means remain self-judged by the generating model
  (faithfulness 0.734 / 8/15 valid, relevancy 0.939 / 11/15, precision 0.564 /
  9/15). Valid-row drift prevents causal comparison. Neither harmless judge
  noise nor an application regression follows from those means; idx2 (0.286),
  idx14 (0.0) and the precision-failure mode still require review.
- **Page-hint validation and minimal authorized field reads — MISSING.** The
  SI-00042-style untrusted-hint validation contract is target behavior with no
  implementation or test claim.
- **Transcript restore, streaming and realtime in real Desk — MISSING.**
  Stub-DOM and standalone-preview evidence only.
- **Provider conformance matrix — MISSING.** One LiteLLM path exercised; no
  per-provider request/output/error/timeout/locality evidence.
- **M5 live concurrency stress, second actor and uncertain-outcome
  reconciliation — MISSING.** Offline-tested only; live business-write
  execution was not performed.
- **Docker custom-image build — MISSING.** Guardrail-blocked in M6; never run.
  Same-source Bench/Docker install-and-update parity is therefore unevidenced.
- **Version matrix/policy, patches/upgrade, backup/restore, rollback —
  MISSING.** Dynamic `0.1.0` and the Frappe `>=15` declaration remain
  unvalidated against a v16 product scope (U8).
- **CI tests/lint — NOT CONFIGURED.** Recorded as not-configured, not as passed.
- **Full intra-site ACL parity — DEFERRED BY DESIGN (U5).** M4 shipped coarse
  retrieval tiers, so ERPNext permission parity is not delivered.
- **Normal integration-user `Customer` schema access — NOT DEMONSTRATED.** The
  `GET /api/resource/DocType/Customer` 403 is an upstream Frappe permission
  outcome for that test user, recorded as still-not-demonstrated. No permission
  change is proposed; the administrator-only 87-field schema check was a
  separate temporary test.
- **`bye` routing case — NOT FIXED.** "see you later" produced repeated
  unparseable small-model NLU output across three runs. Recorded as model-output
  variance, not a demonstrated routing regression, and deliberately not
  relabeled fixed.
- **Index/quality maintenance gaps — NEED SEPARATELY APPROVED WORK.** Public
  rebuilds can still remove unrelated corpora; BM25 snapshots and current-code
  chunks can go stale. Version exclusions do not prove exact v16 compatibility.
  Historical corpus counts and installed versions are dated, not current
  inventory. No rebuild, migration or model call is authorized to resolve these
  here.
- **Frappe roles-cache revocation caveat.** A deleted Role left a stale entry in
  Frappe's own `roles` cache until an explicit `hdel`; revocation immediacy
  inherits Frappe's cache invalidation behavior.

No future production gate is passed by this documentation update. Any future
runtime work requires a separately approved OpenSpec change.

## Resolved

## [2026-08-23] ERPNext/Frappe doc source no longer exists in git
**Finding:** `PHASE_1_SPEC.md`'s preferred option — doc source in the
`frappe/erpnext` / `frappe/docs` repos — is dead. Both docs sites migrated
off GitHub into Frappe's wiki platform (~2021): canonical sources are now
`https://docs.frappe.io/erpnext` and `https://docs.frappe.io/framework`
(docs.erpnext.com links there directly). Verified absent from git:
`frappe/erpnext@version-15` has no docs dir; `frappe/frappe@version-15`
and `develop` have no `frappe/docs/`; `github.com/frappe/docs` is 404.
**Resolution:** Ingest via sitemap crawl of docs.frappe.io (clean markdown
with YAML front-matter per page, CC-BY-SA 3.0). This is the spec's own
named fallback ("scraping the live site") and the site docs.erpnext.com
itself points to — not a workaround guess. Logged as ADR in
`DECISIONS.md`; flagged to user for veto.

