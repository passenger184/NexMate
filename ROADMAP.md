# ROADMAP.md — Phase Sequence

**Current phase: Phase 1.** See `docs/PHASE_1_SPEC.md` for the detailed,
actionable spec. Do not start a later phase until the current one meets its
Definition of Done and `progress/CURRENT.md` is updated to reflect it.

**Scope note:** this is a single-project system for now. Multi-project/
workspace support is a deferred future direction — see
`docs/FUTURE_MULTI_WORKSPACE.md` — not on this roadmap until the user
explicitly reopens it.

| Phase | Name | Delivers | Status |
|---|---|---|---|
| 1 | Pure RAG, Developer mode | Working RAG over public ERPNext/Frappe v16 docs, embedded sidebar UI, source citations | **Reported done by build agent — unverified.** Known open issue: confidence-gating bug (low-confidence answers still generate instead of declining). RAGAS + sidebar unverified. Fix before proceeding. |
| 2 | Live code read/edit agent | Read/search/explain (always-on) + confirmed, git-checkpointed file edits, scoped to this project's root | Not started — **next** |
| 3 | Company knowledge | This project's custom app source + internal docs/procedures added to the index as a tagged corpus | Not started |
| 4 | Project memory | Session continuity + resolved-issue corpus fed by Phase 2's commits | Not started |
| 5 | Read-only ERPNext API tool | Live-instance lookups (schemas, field values, doc status) | Not started |
| 6 | Orchestrator/router | Routes between RAG, code agent, and ERPNext API tool; enforces version-awareness | Not started |
| 7 | Employee/User mode | Restricted persona/prompt on the same orchestrator and knowledge base | Not started |
| 8 | Write-capable ERPNext Agent | Guarded, multi-step actions against live ERPNext data — staging-only until proven safe | Not started |

## Sequencing rules

- Each phase must produce something genuinely usable on its own before the
  next begins — no half-built skeletons across multiple phases at once.
- A phase is not "done" until `EVALUATION.md`'s Definition of Done for that
  phase is verified, not just "runs without errors" or a self-report from
  the build agent — confirm with `/test` and `/review`.
- Do not introduce a phase's tooling (see `ARCHITECTURE.md`'s "Explicitly
  deferred" list) before its phase starts.
- Phase 2 (live code editing) is intentionally ahead of company knowledge
  and the orchestrator — the user wants this capability early. It is
  gated by hard guardrails (git-clean requirement, per-edit confirmation,
  project-root scoping) regardless of how early it lands — see
  `SECURITY.md`. This is editing source code with git as a safety net, NOT
  writing to live ERPNext data — that stays Phase 7, deliberately later,
  since it has no equivalent undo button.
- Multi-workspace support is explicitly NOT on this roadmap — see
  `docs/FUTURE_MULTI_WORKSPACE.md`.
- UI work follows `docs/UI_SPEC.md` throughout — it's a standing reference,
  not a numbered phase. Memory (Phase 4) is RAG-native per
  `docs/PHASE_4_SPEC.md` — no separate memory subsystem.
