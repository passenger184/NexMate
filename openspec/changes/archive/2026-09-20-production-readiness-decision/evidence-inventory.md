# M7 Evidence Inventory (review working record — 2026-09-19)

Scope: staging only, local-only generation (tasks 1.1/1.2). Status values per
`EVALUATION.md`: implemented / tested(+scope) / live-tested / unverified /
planned / deferred. Historical dates are as-recorded, not re-verified here.

## G1 — Reviewed contracts and measurable criteria

| Item | State | Evidence / limitation |
|---|---|---|
| U4-partial (shared-secret service auth) | implemented + tested | `service-authentication` spec; DECISIONS.md 2026-09-17 U4 entry; offline auth-matrix tests |
| Boundary planning choices (roles, chat-only, key/site config) | implemented + tested | DECISIONS.md 2026-09-17 planning entry; gateway/dispatch negative tests; live Task 6.3 Desk checks 12/12 PASS 2026-09-18 |
| U1–U3, U5–U10 remainder | **unresolved architecture decision** | HLD U-register; no reviewed ADRs selecting mechanisms |
| U9 budgets, quality bars | **missing evidence** (threshold requiring explicit agreement) | No agreed latency/cost/recovery/quality numbers in any source |
| R01–R20 → observable scenarios | partially done | Canonical specs carry scenarios; provider conformance per-provider evidence missing |

## G2 — Authenticated Frappe boundary

| Item | State | Evidence / limitation |
|---|---|---|
| Gateway auth/site/binding + chat-only denial | tested + live-tested (bounded) | M2 change 20/21 tasks; live Task 6.3 12/12 PASS on `frontend` 2026-09-18 |
| Bounded integration/Desk evidence (M2 task 6.3) | **missing evidence** | Left unchecked in archived change: recorded unverified, not passed |
| Legacy/direct-tool entry coverage | tested (unit/mock scope) | `endpoint-access-control` spec; durable-approval requirement on every path |
| Full live NLU matrix (authoritative: model-present rerun) | **live-tested** | M7 task 3.2: 29/29 cases, 25 pass / 4 fail / 0 errors (staging, `qwen2.5-coder:7b` digest `dae161e27b0e`); mismatches `code-where`→rag, `followup-purchase`/`ambiguous-payments`/`contam-newtopic`→erpnext; 2/2 employee-denial probes + timeout probe pass; 0 uncaught exceptions |
| Full live NLU matrix (prior model-absent run, kept separate) | live-tested degraded-behavior evidence | 7/29 route-pass under `qwen2.5-coder:7b not found` host-side removal; safe mass-clarify + loud timeout characterized; its 3 escaped exceptions reclassified as outage artifacts, NOT application error — superseded by the 0-exception rerun |
| ERPNext populated-data retrieval | **missing evidence** | The ERPNext read branch was reached and live GET extraction executed, but the staging environment did not demonstrate successful retrieval against populated business data; therefore populated-data retrieval remains unverified |

## G3 — Owned state and authorized context

| Item | State | Evidence / limitation |
|---|---|---|
| Frappe-owned conversations/proposals, JSON store deleted | implemented + live-tested | M3 change 22/22 tasks; live migrate/start/ask/transcript/reset, cross-user refusal, concurrency serialization on `frontend` 2026-09-18 |
| Page-hint validation (SI-00042), minimal field reads | **missing evidence** | Target behavior, no implementation/test claim |
| Transcript restore / streaming / realtime in real Desk | **missing evidence** | Stub-DOM/preview only; target work per HLD |
| Restart/concurrency/ownership | tested (live, bounded) | M3 live restart-preservation + 3-way parallel serialization |

## G4 — Isolated retrieval, compatible providers, safe indexes

| Item | State | Evidence / limitation |
|---|---|---|
| Coarse ACL pre-filter, generations, deny-by-default egress | implemented + live-tested | M4 change 25/25 tasks; live backfill 7,410+325 chunks, `gen-1-m4`, cross-site/intra-site negatives, rollback/revocation cycle, 15/15 held-out non-empty |
| Full intra-site ACL parity | **intentional deferred scope** | Coarse tiers only; ERPNext permission parity explicitly deferred (`acl-aware-retrieval` spec) |
| Per-provider conformance (each selected provider) | **missing evidence** | One LiteLLM path exercised; no per-provider matrix |
| Frappe roles-cache revocation caveat | known limitation | Deleted-Role stale cache until `hdel`; recorded in M4 evidence |

## G5 — Durable tools, human approval, complete audit

| Item | State | Evidence / limitation |
|---|---|---|
| Durable proposals, audit ledger, filtered Debug, confined executor | implemented + tested + live-tested (bounded) | M5 20/20 + hardening; 35 M5 + 30 hardening tests; live `frontend` migrate, 0-row counts, mock execution succeeded + audit_pending/read-back |
| Live concurrency stress, second-actor, uncertain-outcome reconcile | **missing evidence** | Recorded M5 limits; offline-tested only |
| Production-write approval | **governance decision pending** | Explicitly separate; no approval in any source |

## G6 — Release, version/patch lifecycle, deployment parity

| Item | State | Evidence / limitation |
|---|---|---|
| Monorepo packaging, fresh-site install/migrate | implemented + live-tested | M6 13/13; `test-fresh-clone` migrate exit 0, 4 DocTypes/tables, 0 rows, root-independent imports; plain get-app proven undiscoverable (negative control) |
| Docker custom-image end-to-end build | **missing evidence** | Guardrail-blocked in M6; never run |
| Version matrix/policy, patches/upgrade, backup/restore, rollback | **missing evidence** | Dynamic 0.1.0 + Frappe >=15 unvalidated as v16 matrix |
| CI tests/lint | **missing evidence** | Lint/typecheck not configured (accepted as not-configured in M5/M6) |

## G7 inputs — quality evaluation

| Item | State | Evidence / limitation |
|---|---|---|
| Held-out grounded answers + negatives (independent judge) | **missing evidence** | No held-out set exists; the M7 re-score below used recorded baseline samples and does not satisfy this row |
| RAGAS baselines (recorded, self-judged) | tested with recorded limits | Faithfulness 0.734 (8/15), relevancy 0.939 (11/15), precision 0.564 (9/15); self-judge + valid-row drift prevent causal claims |
| RAGAS re-score, recorded samples, VL judge (M7 task 3.1, NOT held-out) | **tested with recorded limits** | 15/15 rows, 45/45 jobs, 29m22s, 0 timeouts; judge `huihui_ai/qwen2.5-vl-abliterated:3b` digest `67f505b2…`, local-only, `.env` untouched; 26/45 valid — faithfulness 13/15 valid 0.868, relevancy 12/15 valid 0.928, precision 1/15 valid 0.962 (**UNUSABLE as aggregate**); 19/45 `RagasOutputParserException`-after-retries; results `/tmp/m7-full-samples_234048.json`, repo untouched. Limits: recorded (not held-out) dataset; shared Qwen2.5 lineage (partial independence); means descriptive only; per-question review still required (idx2 0.286, idx14 0.0); parser failures are judge-output failures, not NexMate quality failures |
| Full live NLU matrix | **live-tested** (authoritative rerun) | See G2 rows: 25/29 pass + probes; 4 route mismatches recorded, not hidden |

## R01–R20 traceability (method → inventory row)

R01/R02/R03 → G4 rows (conformance missing). R04 → G2 rows + G6 rows.
R05/R06/R07 → G6 rows (matrix/policy/CI missing). R08 → G5 rows.
R09 → G2 entry coverage + G5 contracts. R10/R11/R12 → G3 rows (Desk delivery missing).
R13 → G2+G3+G4+G5 denial rows. R14 → G5 Debug rows. R15/R20 → deferred exclusions.
R16 → G4 rows (scaling evidence missing; alternates deferred). R17 → G5 rows + pending governance.
R18 → G4 rows (U1/U5 open). R19 → G4 egress rows (grants unapproved).

## M5/M6 as CLOSED inputs (by reference only — not reopened)

- M5 `2026-09-19-durable-tool-execution-audit` (archived; commit `c86fda5` lineage): durable lifecycle, ledger, Debug, executor.
- M6 `2026-09-19-m6-open-source-packaging` (archived; commit `64f9fd4`): Option A monorepo, `apps.json` directory workflow, fresh-site verification.
- No M5/M6 work item is recreated in this review.
