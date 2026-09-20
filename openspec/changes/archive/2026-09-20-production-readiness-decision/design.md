# Design: production-readiness-decision

## Context

See `proposal.md` (Why). M6 closed at `64f9fd4` with no active pointer; the documented next milestone is M7 / HLD gate G7, a decision gate with no change artifact. The review method must work from existing sources only: `ROADMAP.md` M1–M7 gates, `ARCHITECTURE.md` R01–R20 + G1–G7 obligations, `EVALUATION.md` G1–G7 methods and R01–R20 proof index, `SECURITY.md` standing policy, `DECISIONS.md` provenance (2026-09-17 direction; U4-partial; boundary choices; M5/M6 findings), the 12 canonical `openspec/specs/`, and the M2–M6 archived evidence in `progress/CURRENT.md` / `progress/JOURNAL.md`. No threshold in these sources may be invented by the review; no U-decision may be resolved by it.

## Goals / Non-Goals

**Goals:** A repeatable, evidence-first review procedure that (1) inventories every G1–G7 proof obligation against recorded evidence using `EVALUATION.md` evidence discipline, (2) executes the quality evaluations the docs already specify (held-out sets, live NLU matrix, independent judging), (3) classifies every finding with the fixed gap taxonomy, (4) maintains the U1–U10 register below, and (5) yields three separate decision records.

**Non-Goals:** Resolving any U-decision; choosing numeric thresholds; fixing defects found; running state-mutating validations; granting release, production-write, or cloud-consent approvals.

## Decisions

- **D0 — Read-only evidence-first method.** Every gate section starts from recorded artifacts (`progress/`, archives, specs, code references) before any live execution. Rationale: prevents re-proving settled history and keeps the review inside its safety boundary. Alternative (re-run everything live) rejected: violates the no-mutation rule and duplicates M2–M6 verification.
- **D1 — Independent judging required.** Quality evaluation uses a judge independent of the generating model (`qwen2.5-coder:7b` self-judging is documented history, not M7 evidence), with per-question groundedness review against cited passages. Rationale: `EVALUATION.md` explicitly demands independent judging to resolve the faithfulness uncertainty. Alternative (reuse recorded means) rejected: valid-row drift makes the means non-comparable.
- **D2 — Fixed gap taxonomy as the single classification.** Each finding takes exactly one of: implementation defect / missing evidence / unresolved architecture decision / intentional deferred scope / governance-approval decision. Rationale: stops scope creep (deferred items cannot re-enter as "missing work") and routes each finding to its owner (build change vs review vs ADR vs user decision).
- **D3 — U1–U10 register (classification only, no resolutions).**
  - *Must be decided for M7 (at least for the named review scope):* **U1** (deployment model under review — readiness cannot be declared for an unknown topology); **U2** (index/ingestion ownership and publication contract behind G4 evidence); **U3** (executor placement/credentials/binding behind G5 confinement); **U4-remainder** (tool/result schemas and per-provider conformance for selected providers; shared-secret subset already accepted); **U5** (ratify the shipped coarse-tier model and its documented limits — a scope decision, not full ERPNext parity); **U6** (grant mechanism and revocation path, or an explicitly recorded local-only grant set); **U7** (proposal state machine, concurrency/idempotency, uncertain-outcome reconciliation, audit retention); **U8** (supported Frappe/Python/service/index matrix + release policy); **U9** (agree budgets, or explicitly record operation as unbudgeted — the agreement is the decision).
  - *U10 split:* Debug disclosure policy for the reviewed release is must-decide (G5 Debug tests need it); MCP direction and Workbench privileged-UX definition stay **deferred by accepted scope**.
  - *May remain explicitly undecided:* topology and tenancy choices for environments outside the named review scope; anything the gate criteria do not require, recorded as explicitly undecided rather than silently open.
  - *Deferred by accepted scope (never M7 work):* MCP (R15), Developer Workbench (R20), Qdrant/pgvector, alternate inverted indexes, dedicated search, reranking, shared multi-workspace routing — per the HLD deferred register and `EVALUATION.md` exclusions.
- **D4 — Thresholds become open questions, not findings.** Any criterion without an agreed numeric bar (latency, cost, recovery, quality) is recorded as "threshold requiring explicit agreement" and escalated to the user; the review never picks a passing value. Rationale: choosing bars would be an approval disguised as measurement.

## Risks / Trade-offs

- [Risk] Review re-discovers M2–M6 evidence already verified → Mitigation: D0 starts from archives and `progress/` records; re-execution only for held-out/independent-judge items the docs mark as still missing.
- [Risk] Live NLU matrix and provider-timeout paths need a running model/service, tempting mutation → Mitigation: safety-boundary rule — read-only probes only; anything stateful is flagged for separate authorization.
- [Risk] Pressure to resolve U-decisions "while here" → Mitigation: D3 register is classification-only by charter; resolutions require their own reviewed ADRs.
- [Risk] Self-judge reuse or mean-comparison shortcuts → Mitigation: D1 makes independent judging and per-question review mandatory for any quality claim.

## Migration Plan

Not applicable — a review change deploys nothing and migrates no data. Execution order is carried by `tasks.md`; rollback is trivially the pre-review tree (no runtime changes exist to revert).

## Open Questions

Genuinely requiring the user's explicit agreement during review execution (answering them does not change these artifacts, only fills the "threshold requiring explicit agreement" slots):
- O1: Which named environment(s) is M7 readiness being declared for (staging only, or a specific production target)?
- O2: Latency, cost, and recovery budgets for the reviewed scope (U9).
- O3: Quality bars for held-out groundedness/negatives and the live NLU matrix pass rate.
- O4: Audit retention/deletion windows and Debug disclosure policy for the reviewed release (U7/U10 portions).
- O5: Whether any cloud generation provider is in scope for review at all, and if so, the exact data-class grants and revocation path (U6) — default remains local-only.
