# Tasks — reconcile-post-m7-project-state

Documentation-only. No runtime behavior, no spec change, no approval, no M8.
Each task states its verification inline.

## 1. Baseline and scope verification (read-only, before any edit)

- [x] 1.1 Verify Git baseline: HEAD, branch, `origin/main`, full commit hashes
  for `9f274ed`, `ba51b47`, `ee8b0de`, `4ec4463`, `4243af2`, `e119eb8`; confirm
  `openspec/changes/` holds no active change and that working tree carries only
  the four known untracked entries.
- [x] 1.2 Verify the stated post-M7 facts against the repository rather than
  assuming them: the 28/29 / 1-fail / 0-harness-error closure result and the
  `bye`/"see you later" variance in the archived `fix-post-live-routing-regressions`
  tasks; the resolved-defect list; and the M7 25/29 historical figure in
  `m7-review-report.md:18`.
- [x] 1.3 Confirm the OpenSpec convention for documentation-only work by
  inspecting the archived `reconcile-architecture-and-production-hld` change and
  the two routing changes: each uses `.openspec.yaml` with `skip_specs: true`
  and proposal/design/tasks with no `specs/` directory. Confirm no
  `progress/DECISIONS.md` exists and that the ADR ledger is repo-root
  `DECISIONS.md`.
- [x] 1.4 Verify every source anchor the reconciliation will cite, and record
  that `service/session_store.py` is deleted while `ARCHITECTURE.md:582` still
  cites it; confirm `conversations.py:122`, `api.py:236`, `rag/acl.py:38`,
  `rag/generations.py`, `rag/egress.py`, `tools/contracts.py`,
  `orchestrator.py:830`, `orchestrator.py:1090`, `apps.json` and the four NexMate
  DocType directories exist as described.
- [x] 1.5 Confirm the out-of-scope set is untouched and stays untouched: runtime
  code, tests, `.env`, ERPNext/Docker/provider configuration,
  `evaluation/routing_cases.json`, routing logic, `openspec/specs/`,
  `DECISIONS.md`, and every archived change directory including M7.

## 2. ARCHITECTURE.md — current-state reconciliation (D1)

- [x] 2.1 Update the authority header to record the 2026-09-26 forward
  reconciliation as documentation-only with no runtime executed, keeping the
  2026-09-17 reconciliation and the approved target design intact.
- [x] 2.2 Add one sentence to the status legend making architectural status and
  evidence state independent axes and naming implemented / demonstrated /
  partially demonstrated / unresolved / deferred. Introduce no new
  architectural label.
- [x] 2.3 Correct the broken `service/session_store.py:39` anchor: re-anchor to
  the M3 Frappe-owned conversation module, record owned state as implemented and
  live-verified, retain M3's recorded limits, and preserve the 2026-08-24
  JSON-store content as history.
- [x] 2.4 Add the post-M7 routing stabilization row adjacent to the existing
  routing row: M7 25/29 historical → `9f274ed` 26/29 → `ee8b0de` 28/29 passed,
  1 failed, 0 harness errors; name the resolved defects; record
  `bye`/"see you later" as unfixed model-output variance; state that it carries
  no production-readiness, write, cloud, U/O or threshold implication and does
  not alter M7.
- [x] 2.5 Extend the ERPNext reads row with the 2026-09-26 orchestrated
  populated-data demonstration (normal integration user, `Customer/Test`, HTTP
  200, grounded local generation, `[1]` citation, no writes) while retaining the
  2026-08-24 evidence, and record that normal-user `Customer` schema access
  remains not demonstrated (403).
- [x] 2.6 Add the explicit **Developer Mode distinction** row: inference-side
  developer capability demonstrated; Desk-facing Developer Mode experience not
  demonstrated because `api.py:236` fixes Desk to `chat-only`; permission parity
  with the incoming Desk identity unresolved (U5 open, M4 coarse tiers by
  intent); Developer Workbench deferred (R20, no milestone). Verify the document
  nowhere states Developer Mode is fully demonstrated.
- [x] 2.7 Replace the single `:591` "Planned; no target-boundary
  implementation/verification claimed" row with four milestone-accurate rows
  (M2 authenticated control, M3 owned state, M4 ACL/generations/egress, M5
  durable audit/Debug), each with its own anchor, evidence class and its own
  retained missing-evidence list. Verify the document no longer claims these are
  unimplemented while still recording what remains unevidenced.
- [x] 2.8 Add the M6 packaging row (`apps.json` directory workflow, fresh-site
  install/migrate exit 0, 4 DocTypes/tables) and record Docker parity, version
  matrix and CI/lint as still missing.
- [x] 2.9 Annotate the U1–U10 register with a status paragraph and per-item
  notes where M2–M5 actually bear, applying the DR-3 rule: implementation and
  evidence never resolve a U-item. Verify no U-item is deleted, reworded in
  substance, reordered or marked resolved, and that U4 is recorded as only
  partially settled by M2.
- [x] 2.10 Append a 2026-09-26 closing note recording that no gate was passed, no
  U/O item resolved, no approval granted and M7 unchanged, alongside the
  preserved 2026-09-17 note.

## 3. ROADMAP.md — pointer reconciliation (D2, D3)

- [x] 3.1 Retitle the `:19-21` **"Active pointer — 2026-09-19"** heading as a
  historical M5 closure record, preserving the body text verbatim, so the
  document no longer implies M5 → M6 is the current milestone.
- [x] 3.2 Add a "Post-M7 stabilization — CLOSED" section recording both routing
  changes, all four commit hashes, the 28/29 result, the resolved defect list,
  `bye` unfixed, and an explicit statement that M7's 25/29 and its three
  decisions remain authoritative.
- [x] 3.3 Add a consolidated current-position block: M2–M7 closed; no active
  implementation milestone; no M8 created or implied; post-M7 work is
  evidence/documentation stabilization; future implementation requires a
  separately approved OpenSpec change. Verify no M8, M9 or successor milestone
  name appears anywhere in the file.

## 4. progress/CURRENT.md — evidence state (D2, D5)

- [x] 4.1 Extend the header's "Current task" to name the post-M7 stabilization
  state and the absence of an active implementation milestone, without altering
  the M7 CLOSED decisions line.
- [x] 4.2 Add a dated post-M7 routing stabilization section with commit-level
  detail, mirroring the ROADMAP entry.
- [x] 4.3 Extend the 2026-09-26 boundary paragraph with the four-way Developer
  Mode distinction, so the ERPNext demonstration cannot be misread as Developer
  Mode delivery, while preserving the existing boundary wording verbatim.
- [x] 4.4 Verify the pre-existing M7, M6, M5, M4, M3 and Task 6.3 sections are
  unchanged and no historical record was rewritten.

## 5. progress/BLOCKERS.md — bring forward (D4)

- [x] 5.1 Re-date the file and restructure into **Closed evidence gaps**,
  **Still-open evidence** and **Governance blockers — unchanged**, using only
  verified current evidence.
- [x] 5.2 Record closed evidence: the four M7 routing defects and three
  post-fix regressions, populated ERPNext business-data retrieval, and the
  preserved 2026-09-17 resolved-documentation entry.
- [x] 5.3 Record still-open evidence: held-out grounded/negative set (none
  exists), independent judging and per-question groundedness review,
  page-hint/minimal authorized field reads, transcript restore/streaming/realtime
  in real Desk, provider conformance matrix, M5 live concurrency/second actor/
  uncertain outcome, Docker custom image and version matrix,
  patch/upgrade/backup/restore/rollback, CI/lint, full intra-site ACL parity,
  normal integration-user `Customer` schema access, and the `bye` routing case.
- [x] 5.4 Reproduce the governance blockers unchanged — M7 release NOT READY,
  production writes DENIED/PENDING, cloud consent NO GRANT, staging-only,
  local-only, U1–U10, O2–O4 — each explicitly framed as unchanged.
- [x] 5.5 Preserve the resolved ERPNext/Frappe doc-source entry at the file tail.

## 6. progress/JOURNAL.md

- [x] 6.1 Append one dated entry (newest at bottom, per the file's convention)
  recording the documentation unit: what was reconciled, which anchors were
  verified, the broken `service/session_store.py` citation that was corrected,
  and what was deliberately left untouched.

## 7. Documentation-only validation

- [x] 7.1 Run `git diff --check` and confirm it is clean.
- [x] 7.2 Run
  `openspec validate reconcile-post-m7-project-state --type change --strict --no-interactive`
  and record the exact result.
- [x] 7.3 Audit scope with `git status --short` and `git diff --stat`: confirm
  changes are confined to `ARCHITECTURE.md`, `ROADMAP.md`,
  `progress/CURRENT.md`, `progress/BLOCKERS.md`, `progress/JOURNAL.md` and this
  change record; confirm zero changes under `openspec/specs/`, `evaluation/`,
  `tests/`, `frappe_app/`, `service/`, `rag/`, `tools/`, `ingestion/`,
  `orchestrator.py`, `config.py`, `.env`, `.env.example`, `apps.json`, or any
  `archive/` directory.
- [x] 7.4 Run a credential/secret scan over the diff and confirm no secret,
  token, key or personal path was introduced.
- [x] 7.5 Verify M7's decisions, the M7 25/29 figure, the RAGAS and VL-judge
  caveats, the U1–U10 register state and the O2–O4 thresholds are all unchanged
  in substance by re-reading the edited regions.
- [x] 7.6 Confirm no runtime, test, migration, service, model, network, Docker or
  ERPNext action occurred, and that no out-of-scope repository was accessed.
- [x] 7.7 Record no commit, push or archive without explicit user instruction.

## 8. Not yet performed — required before archival

Per `EVALUATION.md`'s documentation-only acceptance method ("obtain independent
read-only review") and the precedent of the archived
`reconcile-architecture-and-production-hld` change, the following remain open.
This change is **not** ready to archive until they are done.

- [x] 8.1 Independent read-only review of documentation fidelity: confirm every
  `C`-descriptor and evidence row matches a verifiable artifact, that the
  deleted `service/session_store.py` anchor is correctly replaced, that no
  partial implementation was promoted to an architectural guarantee, and that
  the Developer Mode four-way distinction is stated without overclaiming.
- [x] 8.2 Independent security-policy review: confirm M7's three decisions, the
  staging-only and local-only postures, the U1–U10 and O2–O4 states, and the
  unchanged production-write and cloud-consent positions are all still intact,
  and that no permission, policy or approval was weakened.
- [x] 8.3 Confirm the routing evidence is recorded as stabilization only and
  that M7's 25/29 plus its decisions remain authoritative; confirm the `bye`
  case is recorded as **not fixed**.
- [ ] 8.4 Archive this change only after 8.1–8.3. Commit and push nothing until
  the user explicitly asks.

## 9. Correction pass — post-review findings (2026-09-26)

An independent pre-archive review (read-only) returned **Review 1 FAIL** and
**Review 2 PASS**, with one HIGH, three MEDIUM and four LOW documentation
findings. All are corrected below. No governance decision, U-item, spec,
runtime, test or evaluation artifact was touched.

- [x] 9.1 **HIGH — stale `Current runtime and request flows — C`.** The section
  still described the pre-M2/M3/M5 architecture and contradicted the file's own
  evidence matrix at four points: `direct fetch -> FastAPI (no incoming
  authenticated principal)`, `localStorage: session ID + caller-selected mode`,
  `JSON sessions on disk`, and `proposals in process memory`. Rewritten as two
  labelled paths — **A supported Desk/Frappe path** (same-origin
  `/api/method/…` with CSRF; Frappe derives user/site/persona; server-side
  `chat-only`; Frappe-owned conversations and durable proposals) and
  **B standalone `/ui` preview (preview/legacy, not the production
  architecture)**. Verified the orchestrator's own code/ERPNext/write branches
  still exist and are gated rather than removed, and kept them visible with the
  gate cited. The adjacent `POST /tools/session/reset` row was corrected to
  "retired by M3" (the route no longer exists; legacy `session_id` refused).
- [x] 9.2 **MEDIUM — U6 self-contradiction.** The U-register annotation listed
  U6 as "untouched by all post-2026-09-17 work" in the same paragraph that states
  M4 exercised a U6-shaped choke point. Corrected to `U1, U3, U5, U8, U9 and
  U10`, matching `design.md`. The U1–U10 register table itself is untouched and
  U6 remains unresolved.
- [x] 9.3 **MEDIUM — `BLOCKERS.md` did not close base evidence.** Expanded
  **Closed evidence gaps** with the already-demonstrated M2 (Desk acceptance
  12/12 + packaged assets), M3 (Frappe-owned conversations), M4 (ACL,
  generations, egress), M5 (durable proposals/audit, bounded) and M6
  (monorepo packaging + fresh-site install) evidence, each carrying an explicit
  `*Bounded:*` clause. No still-open item was removed or weakened.
- [x] 9.4 **MEDIUM — release-lifecycle overstatement.** "Real root-repository
  Bench installation, package asset inclusion, `app_include_js/css`
  build/injection, boot behavior, migrations and update parity remain
  unverified" was too broad. Narrowed to what genuinely remains unverified:
  root-repository installation, root-repository update parity, and Bench↔Docker
  parity. The demonstrated sub-questions (Desk 200, built bundle/CSS, boot
  delivery, `ask()` via session+CSRF, fresh-site `migrate` exit 0) are now
  stated. The `/ui`, Docker and package-metadata caveats are preserved.
- [x] 9.5 **LOW — inaccurate auth anchors.** `service/auth.py:30` (a
  conversation-ID regex) and `api.py:116` (JSON parsing) did not point at
  authentication logic. Replaced with verified `service/auth.py:119`
  (`ServiceAuthMiddleware`) and `frappe_app/erpnext_ai_copilot/api.py:67`
  (`_mode_for_user`).
- [x] 9.6 **LOW — Developer Mode anchor.** `orchestrator.py:892` is the
  `chat_only` parameter; the enforcement point is
  `orchestrator.py:1038` (`if chat_only and route in ("code", "erpnext")`).
  Repointed, keeping `api.py:236` and `orchestrator.py:1090`.
- [x] 9.7 **LOW — unsourced `0 blocked` metric.** The repository defines no
  such metric (`routing_cases.json` case keys are `expect`, `extraction`,
  `history`, `id`, `message`, `mode`, `nlu`, `task_route`; the archived closure
  evidence says "28/29, 0 harness errors"). Removed `0 blocked` from all
  documentation and this change's artifacts; the authoritative phrasing is now
  **28/29 passed, 1 failed, 0 harness errors**.
- [x] 9.8 **LOW — missing 28/29 run caveat.** Recorded that staging ERPNext was
  unreachable during the 2026-09-23 routing run, so the ERPNext read branch
  returned lookup-failure; the archived evidence classifies this as a
  read-branch/lookup-availability condition, not a routing failure, and the
  routing verdicts stand. Added to `ARCHITECTURE.md`, `ROADMAP.md`,
  `progress/CURRENT.md` and `progress/BLOCKERS.md`.
- [x] 9.9 **Additional anchor drift found and disclosed (not silently
  retained).** Several `service/main.py` line anchors in the pre-existing
  "Legacy and direct endpoints" table have drifted since the 2026-09-17 pass.
  Re-anchoring all of them was outside this correction pass, so an explicit
  anchor caveat was added to that table rather than leaving stale positions to
  look authoritative. The endpoint names themselves were re-verified against
  current source.
- [x] 9.10 Re-run the full documentation-only validation set after the
  corrections: `git diff --check`, strict OpenSpec validation, `openspec/specs/`
  unchanged, no runtime/test/evaluation/config change, U-register rows
  unchanged, M7 governance language unchanged, 25/29 vs 28/29 still distinct,
  the six routing fixes and the `bye` not-fixed status intact, ERPNext evidence
  still evidence-only, and the forbidden repository never accessed.
