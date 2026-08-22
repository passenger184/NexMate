# ROADMAP.md — Phase Sequence

**Current phase: Phase 1.** See `docs/PHASE_1_SPEC.md` for the detailed,
actionable spec. Do not start a later phase until the current one meets its
Definition of Done and `progress/CURRENT.md` is updated to reflect it.

| Phase | Name | Delivers | Status |
|---|---|---|---|
| 1 | Pure RAG, Developer mode | Working RAG over public ERPNext/Frappe docs, embedded sidebar UI, source citations | **In progress** |
| 2 | Custom app source code | Company's custom Frappe app indexed alongside docs | Not started |
| 3 | Company knowledge | Internal configs/workflows/procedures as a third tagged corpus | Not started |
| 4 | Read-only ERPNext API tool | Live-instance lookups (schemas, field values, doc status) | Not started |
| 5 | Orchestrator/router | Routes between RAG and ERPNext API tool; enforces version-awareness | Not started |
| 6 | Employee/User mode | Restricted persona/prompt on the same orchestrator and knowledge base | Not started |
| 7 | Developer Agent | Guarded, multi-step write actions, staging-only until proven safe | Not started |

## Sequencing rules

- Each phase must produce something genuinely usable on its own before the
  next begins — no half-built skeletons across multiple phases at once.
- A phase is not "done" until `EVALUATION.md`'s Definition of Done for that
  phase is verified, not just "runs without errors."
- Do not introduce a phase's tooling (see `ARCHITECTURE.md`'s "Explicitly
  deferred" list) before its phase starts.
