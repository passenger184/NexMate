## Why

M6 (`m6-open-source-packaging`) is formally CLOSED at commit `64f9fd4`; the read-only roadmap assessment confirms M7 — Production Readiness Decision (HLD gate G7) is the documented next milestone. No active implementation pointer remains, and the M7 gate has no change artifact yet. A scoped, evidence-first review is needed to decide — independently of any build agent self-report — whether the current implementation and its recorded evidence satisfy the accepted production-readiness criteria, and to keep release readiness, production-write authorization, and private-data cloud consent as three strictly separate decisions.

## What Changes

- **A scoped M7 Production Readiness Review is defined (review only, no implementation):** inventory of G1–G7 and M2–M6 delivered evidence; held-out grounded-question and negative sets; full live NLU matrix; RAG/evaluation evidence with its known self-judge/valid-row limits; security/control-plane, locality/egress, audit/proposal/write, and Bench/Docker evidence; operational budgets; upgrade/backup/rollback evidence where existing criteria require it.
- **An open-decision register for U1–U10 is produced**, classifying each as must-decide-for-M7, may-remain-explicitly-undecided, or deferred-by-accepted-scope — without resolving any of them here.
- **Acceptance criteria are derived only from existing sources** (`ROADMAP.md`, `ARCHITECTURE.md` R01–R20/G1–G7, `EVALUATION.md` methods, `SECURITY.md` policy, `DECISIONS.md` provenance, canonical `openspec/specs/`). Where no threshold exists, the review records "threshold requiring explicit agreement" instead of inventing one.
- **Three separate decision outputs are produced** (release readiness; production-write authorization for a named environment; private-data cloud/provider consent), with no implication that one grants the others.
- **Findings use a fixed gap taxonomy** (implementation defect vs missing evidence vs unresolved architecture decision vs intentional deferred scope vs governance/approval decision).
- **No runtime, configuration, migration, model, data, deployment, or approval action is authorized by this change.** The review must not mutate production or test environments to obtain evidence; any mutation-requiring validation is flagged for separate authorization.

## Capabilities

### New Capabilities
- `production-readiness-review`: requirements governing the M7 review itself — evidence inventory, requirement traceability, open-U-decision register, evaluation execution and reporting, findings taxonomy, separate decision records, blocker lists, and the review safety boundary. This capability describes review obligations and deliverables, not runtime behavior.

### Modified Capabilities
(none — no existing spec's runtime requirements change; M5 and M6 remain CLOSED and are referenced as historical evidence only.)

## Impact
- **Docs/review only:** new planning artifacts under this change; no application code (`service/`, `rag/`, `tools/`, `config.py`, `orchestrator.py`, `frappe_app/`) is modified.
- **Existing specs untouched:** canonical `openspec/specs/` gain no edits; the new `production-readiness-review` capability is additive.
- **Explicitly excluded:** implementation work, MCP (R15), Developer Workbench (R20), alternate search engines / Qdrant / pgvector, reranking, shared tenancy, new AI providers, RAG redesign, production deployment, production writes, and any production-readiness decision itself (the review *prepares* the decision; the user makes it).
