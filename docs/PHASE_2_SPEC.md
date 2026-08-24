# docs/PHASE_2_SPEC.md — Live Code Read/Edit Agent (Single Project)

**Do not start this until Phase 1's confidence-gating bug is fixed and
`/test` confirms the DoD in `EVALUATION.md` is actually met — not just
self-reported.** Read `SECURITY.md`'s "Live code read/edit agent" section
in full before writing any code for this phase — the guardrails there are
non-negotiable, not suggestions to weigh against convenience.

## Scope

This project is single-project for now (see `ARCHITECTURE.md`'s "Scope:
single project for now") — no workspace registry, no `workspace_id`. The
project root is this same ERPNext/Frappe v16 project the RAG service
already runs against. Config it once (e.g. `PROJECT_ROOT` in `.env`), not
per-request.

## Goal

A tool the assistant can use, scoped to this project's root, to: read
files, search code, explain what's happening at a given location (e.g. why
an error occurs), and — only with explicit confirmation and a clean git
tree — apply edits.

## Two tool tiers (build and gate separately)

### Tier 1 — read/search/explain (always available, no confirmation)

- Read a file (respecting project-root scoping — reject any path resolving
  outside `PROJECT_ROOT`, including via `..` traversal or symlinks)
- Search code (grep-equivalent) within the project
- Given an error message or a description of unexpected behavior, locate
  the relevant code and explain the likely cause, grounded in what's
  actually read from the files — not a generic guess about ERPNext
  internals divorced from the actual project code
- This tier should feel immediate and unrestricted — no per-call
  confirmation, since it can't change anything

### Tier 2 — edit (confirmed, git-gated)

Before any edit:
1. Check the project's git status. If not clean, refuse and tell the user
   to commit or stash first — do not proceed, do not auto-stash on their
   behalf without asking.
2. Show the proposed change as a diff, not just a description.
3. Get explicit user confirmation for that specific change.
4. Apply it, then commit it as its own atomic commit with a clear message
   describing what changed and why.
5. Never queue up multiple file edits into one unreviewed batch — one
   proposed change, one confirmation, one commit, repeat.

Refuse edits to: files outside the project root, files outside version
control, git-ignored files. If the user's request implies one of these,
say so and ask how they want to handle it.

## Explicitly out of scope

- No writes to live ERPNext data via the API (documents, DocTypes as
  runtime data, etc.) — that's Phase 7, separately guarded, later.
- No multi-file automated refactors without a confirmation per file.
- No running arbitrary shell commands as part of "fixing" something unless
  that's the specific, confirmed action the user approved.
- No workspace/multi-project support — see `docs/FUTURE_MULTI_WORKSPACE.md`.

## Definition of Done

- [ ] Tier 1 (read/search/explain) verified working against this project
- [ ] A path-traversal attempt (e.g. `../../etc/passwd`-style) is verified
      to be rejected, not silently redirected
- [ ] Tier 2 correctly refuses to edit when the git tree isn't clean
- [ ] At least 3 real edits made end-to-end (diff shown → confirmed →
      applied → committed) and manually verified as correct and isolated
      to their own commits
- [ ] An edit targeting a git-ignored file is correctly refused with a
      clear explanation, not silently skipped or silently applied
- [ ] `progress/CURRENT.md` updated with what's now possible via this tool
