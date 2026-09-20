# M7 Review Report — FINAL (review conclusions finalized 2026-09-20 on collected evidence only; governance approvals remain separate user acts, none granted here)

Scope: staging only, local-only generation (user-confirmed 2026-09-19).
Status: evidence collection complete for tasks 3.1 (full recorded-sample re-score) and 3.2 (authoritative model-present live matrix); held-out evaluation was never available and remains missing.
This draft prepares user decisions; it approves nothing.

## Evidence base

- `evidence-inventory.md` (this change): G1–G7 rows with evidence states, R01–R20 traceability, M5/M6 closed references.
- Prior records: `progress/CURRENT.md`, `progress/JOURNAL.md`, M2–M6 archives, 12 canonical specs.
- Live model work this review, all under explicit user checkpoints: (a) VL-judge full re-score — judge `huihui_ai/qwen2.5-vl-abliterated:3b` digest `67f505b2…` at `http://172.30.224.1:11434` (re-pinned pre-run), 15 recorded 2026-08-24 rows via hash-verified `/tmp` copy, 45/45 jobs in 29m22s, results `/tmp/m7-full-samples_234048.json`; (b) live NLU matrix model-present rerun — 29 cases + 2 employee probes + timeout probe with `qwen2.5-coder:7b` digest `dae161e27b0e` (re-pinned pre-run), throwaway `/tmp` runner, no mocks; plus an earlier model-absent run kept as separate degraded-behavior evidence. No other model calls. No environment mutation of any kind (no session files, writes, installs, restarts, config changes).

## Quality findings (with RAGAS limits carried)

- Recorded self-judged RAGAS means stand with their caveats: faithfulness 0.734 (8/15), relevancy 0.939 (11/15), precision 0.564 (9/15); judge was the generating model; valid-row drift blocks causal comparison. No mean-based conclusion is drawn.
- M7 VL-judge re-score (recorded samples, NOT held-out): 26/45 valid — faithfulness 13/15 valid 0.868, relevancy 12/15 valid 0.928, precision 1/15 valid 0.962 (**unusable as an aggregate; do not cite**); 19/45 judge parser failures after retries; 0 timeouts. Judge shares Qwen2.5 lineage with the generator (partial independence only). Per-question review still required (idx2 0.286, idx14 0.0 reproduced). Parser failures are judge-output failures, not NexMate quality failures.
- Held-out grounded/negative sets with independent judge: still MISSING EVIDENCE — no held-out set exists.
- Full live NLU matrix: LIVE-TESTED (authoritative model-present rerun, task 3.2): 25/29 route-pass, 4 genuine mismatches (`code-where`→rag; `followup-purchase`, `ambiguous-payments`, `contam-newtopic`→erpnext — 3/4 over-route into ERPNext on invoice/payment inputs), 0 errors, 2/2 employee-denial probes + timeout probe pass. Prior model-absent run (7/29, `not found` outage) kept separate; its 3 escaped exceptions reclassified as outage artifacts after the 0-exception rerun.

## Boundary findings (taxonomy-classified)

- G2/G3: implemented + bounded live evidence (M2 20/21, M3 22/22, Task 6.3 12/12) plus the live 25/29 NLU matrix with downstream reach (NLU, RAG, code-explain, ERPNext read branch, tool gating, follow-ups, mode restrictions, out-of-scope, degraded + timeout paths). Missing evidence: M2 task 6.3 integration/Desk tail, page-hint validation, Desk streaming/realtime/transcript restore. ERPNext limitation: read branch entered but returned lookup-failure fallbacks — populated-data retrieval NOT demonstrated and not claimed.
- G4: implemented + live evidence (M4 25/25, negatives, rollback/revocation). Intentional deferred scope: full ERPNext permission parity. Missing evidence: per-provider conformance. Known limitation: Frappe roles-cache revocation caveat.
- G5: implemented + tested/bounded-live (M5 20/20 + hardening, denial/failure legs). Missing evidence: live concurrency stress, second-actor, uncertain-outcome reconcile.
- G6: implemented + live install/migrate (M6 13/13). Missing evidence: Docker custom-image build, version matrix/policy, patches/upgrade, backup/restore, CI/lint.
- G1: U4-partial + boundary choices done; U1–U3/U5–U10 remainder open (see register).

## U1–U10 register status

Per design.md D3: U1/U2/U3/U4-remainder/U5-scope/U6/U7/U8/U9 must-decide (for the named scope); U10 split (Debug policy must-decide, MCP/Workbench deferred); out-of-scope topology may remain explicitly undecided; R15/R20/alternate-search/reranking/shared-tenancy deferred exclusions. Reconciled against evidence only in this pass: no U-item is resolved — live testing success changes evidence states, never decision states. Tenancy/binding, index ownership, executor placement, tool/provider/streaming contracts, full ACL representation, egress governance, workflow/audit guarantees, version matrix, budgets, and Debug/MCP/Workbench remain exactly as classified. No resolution written here.

## Thresholds requiring explicit agreement (escalated, O2–O4)

O2 latency/cost/recovery budgets; O3 held-out/NLU quality bars; O4 audit retention/deletion windows and Debug disclosure policy. No numeric threshold invented in this review.

## Draft decision records (recommendations, not approvals)

Finalized 2026-09-20 on the evidence above; no new evidence taken for finalization. Unresolved architecture/governance items are recorded as such, not converted into work.

1. **Release readiness — FINAL: NOT READY.** Live evidence advanced (25/29 NLU matrix, VL re-score with stated limits, 0-exception rerun), but blockers remain: no held-out evaluation, 4 live route mismatches unreviewed/unfixed, per-question groundedness review outstanding, U1–U9 decisions open, Docker/version-matrix/CI evidence missing, budgets unagreed. Staging-continue is supported by M2–M6 evidence; release is not.
2. **Production-write authorization (named environment) — FINAL: DENIED/PENDING (no production writes authorized).** No named production environment proposed; staging-only write posture unchanged per `SECURITY.md`; M5 staging evidence does not transfer.
3. **Private-data cloud/provider consent — FINAL: NO GRANT.** Scope is local-only by user confirmation; all cloud paths remain denied-by-default with zero data-class grants recorded.

No record implies inheritance between the three; each stands on its own evidence linkage above.

## Blocker lists

- 3.1/3.2 evidence complete as recorded above; remaining quality work: per-question groundedness review (idx2, idx14, precision-failure mode), a genuinely held-out set with a lineage-independent judge if quality acceptance is ever sought.
- To satisfy G1/G7 fully: reviewed ADRs for must-decide U-items + agreed O2–O4 thresholds.
- To satisfy G4/G6 fully: per-provider conformance matrix; Docker custom-image build; version matrix/policy, patches/upgrade, backup/restore, CI/lint evidence.
- Explicit exclusions (not blockers): MCP, Workbench, alternate search/reranking/shared tenancy, new providers, RAG redesign, production deployment.

## Safety compliance

Zero environment mutations; zero business writes; model calls only under explicit user checkpoints (VL-judge full run, live NLU matrix rerun, one earlier smoke test, one terminated phi4-mini attempt with no output persisted); results outside the repo (`/tmp`) except where this review's own planning files record them; `.env`, app code, evaluation code, and test definitions untouched; M5/M6 never reopened.
