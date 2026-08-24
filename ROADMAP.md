# ROADMAP.md — Phase Sequence

**Current phase: Phase 8 — complete.** The roadmap is exhausted: all
eight phases are functionally complete and verified. Standing rules stay
in force (`SECURITY.md`): writes remain gated on ERPNEXT_WRITE_ENABLED,
production use requires an explicit approval decision, and every write is
confirm-gated and audit-logged.

**Scope note:** this is a single-project system for now. Multi-project/
workspace support is a deferred future direction — see
`docs/FUTURE_MULTI_WORKSPACE.md` — not on this roadmap until the user
explicitly reopens it.

| Phase | Name | Delivers | Status |
|---|---|---|---|
| 1 | Pure RAG, Developer mode | Working RAG over public ERPNext/Frappe v16 docs, embedded sidebar UI, source citations | **Functionally complete (user-accepted 2026-08-24).** All eval questions pass with citations; negatives decline. Consciously deferred: real-bench sidebar install, RAGAS re-score post-hybrid-retrieval. |
| 2 | Live code read/edit agent | Read/search/explain (always-on) + confirmed, git-checkpointed file edits, scoped to this project's root | **Functionally complete (user-accepted 2026-08-24).** All six DoD items verified; bench-dependent sidebar diff/approve UI deferred |
| 3 | Company knowledge | This project's custom app source + internal docs/procedures added to the index as a tagged corpus | **Functionally complete (user-accepted 2026-08-24).** P1–P6 + dual-source preference verified; index 7,410 public + 321 project chunks |
| 4 | Project memory | Session continuity + resolved-issue corpus fed by Phase 2's commits | **Functionally complete (2026-08-24).** Continuity proven incl. second-order follow-up; 4 resolutions indexed (3 backfilled + 1 auto) |
| 5 | Read-only ERPNext API tool | Live-instance lookups (schemas, field values, doc status) | **Functionally complete (2026-08-24).** Schema/list(+filters)/document verified live at http://localhost:8081; GET-only client, clean 403/404 mapping |
| 6 | Orchestrator/router | Routes between RAG, code agent, and ERPNext API tool; enforces version-awareness | **Functionally complete (user-accepted 2026-08-24).** All routes + misroute guards verified live; versions injected from the real instance |
| 7 | Employee/User mode | Restricted persona/prompt on the same orchestrator and knowledge base | **Functionally complete (2026-08-24).** Code agent + schema denied for employees, public-docs-only persona, developer mode unchanged (live control) |
| 8 | Write-capable ERPNext Agent | Guarded, multi-step actions against live ERPNext data — staging-only until proven safe | **Functionally complete (2026-08-24).** Flag-gated writes, Tier-2 confirm flow, schema preflight, audit log; create+update verified live on staging (localhost:8081); delete deliberately unimplemented |

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
