# Design — reconcile-post-m7-project-state

Documentation-only. No runtime behavior, no spec change, no approval.

## 1. Problem statement

`AGENTS.md` names `ARCHITECTURE.md` the **sole canonical HLD**. That document was
reconciled 2026-09-17 and archived as
`openspec/changes/archive/2026-09-17-reconcile-architecture-and-production-hld/`
— i.e. **before** M2 through M7 landed. Nine archived changes and four post-M7
commits have since made it stale. Its own companion records flagged this three
times and deferred it each time:

- `DECISIONS.md` 2026-09-18: *"`ARCHITECTURE.md` still describes the JSON store
  — left for a separate HLD reconciliation."*
- `progress/CURRENT.md` (M4): *"`ARCHITECTURE.md` still describes pre-M4
  retrieval (separate HLD reconciliation, not edited here)."*
- `progress/CURRENT.md` (M5): same deferral for the M5 executor/audit work.

The deferral had no owner and no scheduled home, because the change that would
have performed it was itself archived before the work it needed to describe.

## 2. Evidence model

Every reconciliation statement is classified on two independent axes, following
`EVALUATION.md`'s "Evidence discipline for future acceptance" and the HLD's own
`ARCHITECTURE.md:32-39` legend.

**Axis 1 — architectural status** (unchanged, existing HLD legend):

| Label | Meaning |
|---|---|
| **C** | Current implementation — present source behavior. |
| **T** | Approved target direction — agreed, not delivered. |
| **U** | Unresolved implementation decision — needs an explicit decision. |
| **D** | Deferred capability — preserved future possibility. |

**Axis 2 — evidence state** (applied throughout this change):

| Label | Meaning |
|---|---|
| **Implemented** | Code exists. Says nothing about correctness in a real environment. |
| **Demonstrated** | Recorded evidence shows it works in the named environment/path, with date and artifact. |
| **Partially demonstrated** | Some part works; the complete contract, coverage or user experience is unproven. |
| **Unresolved** | Architecture, policy, quality threshold or evidence still open. |
| **Deferred** | Explicitly postponed by the project. |

### 2.1 The governing separation

Per `m7-review-report.md:30`, verbatim intent:

> no U-item is resolved — live testing success changes evidence states, never
> decision states

This change therefore applies a hard rule to every row it touches:

> **Implementation ≠ evidence ≠ architectural decision.**
> A milestone that exercises a mechanism does **not** resolve the U-item that
> governs it. Exercising U2's index ownership in M4 is evidence about U2, not a
> decision of U2.

Concretely, and stated explicitly in the U-register annotation:

- M2 **partially settled U4** (shared-secret service authentication is now a
  decided, implemented mechanism). U4's remaining scope — tool/provider/result
  contracts, version negotiation, streaming/realtime transport — is untouched.
- M4 exercised a **U2-shaped** mechanism (`rag/generations.py` owns publication,
  rollback and revocation) and a **U6-shaped** choke point
  (`rag/egress.py` is deny-by-default). Neither item is *decided*; both remain
  **U**, because no reviewed ADR selected them and no grant mechanism exists.
- M5 built a **U7-shaped** durable lifecycle. U7 remains **U**: the state
  machine, concurrency, idempotency and uncertain-outcome guarantees are still
  unselected, and live concurrency/second-actor/uncertain-outcome evidence is
  still missing.
- U1, U3, U5, U8, U9, U10 are **untouched by all post-2026-09-17 work**.

## 3. Source-anchor verification

Every anchor introduced by this change was verified read-only before use.

| Anchor | Verified state |
|---|---|
| `service/session_store.py` | **DELETED** (M3). `service/` = `__init__.py`, `auth.py`, `main.py`. The existing `ARCHITECTURE.md:582` citation is broken and is corrected. |
| `frappe_app/erpnext_ai_copilot/conversations.py:122` | `start_conversation(user, site, mode)` — Frappe-owned conversation creation. Replacement anchor. |
| `frappe_app/erpnext_ai_copilot/api.py:236` | `"execution_scope": "chat-only"` — Desk gateway hard-codes chat-only. Basis for the Developer Mode distinction. |
| `rag/acl.py:38` / `:127` | `stamp_metadata` / `scope_where` — M4 pre-retrieval ACL. |
| `rag/generations.py`, `rag/egress.py` | Present. M4 index generations and deny-by-default egress. |
| `tools/contracts.py` | Present (219 lines). M5 frozen tool contracts. |
| `frappe_app/erpnext_ai_copilot/{proposals,audit,debug}.py` | Present. M5 durable proposals, audit ledger, filtered Debug. |
| `orchestrator.py:830` | `erpnext.get_document(...)` — the read branch exercised by the 2026-09-26 evidence. |
| `orchestrator.py:1090` | Employee-mode `op == "schema"` denial. |
| `orchestrator.py:892`/`:913` | `chat_only` threaded through `handle_question`. |
| `apps.json` | `{"url": ..., "branch": "main", "directory": "frappe_app"}` — M6 Option A monorepo packaging. |
| DocType directories | 4 present: `nexmate_conversation`, `nexmate_conversation_turn`, `nexmate_tool_proposal`, `nexmate_audit_entry`. |

## 4. Per-file reconciliation design

### 4.1 `ARCHITECTURE.md`

Minimal, surgical edits. The document's structure, diagrams, approved target
design, trust boundaries and R01–R20 matrix are **not** rewritten — they remain
correct. Only current-state evidence is brought forward.

1. **Header (`:5-10`)** — record that the document was reconciled forward on
   2026-09-26 for project state after M7, documentation-only, no runtime
   executed, and that the approved target design sections are unchanged.
2. **Legend (`:32-39`)** — add one sentence making explicit that architectural
   status and evidence state are independent axes, and name the evidence
   vocabulary. No new architectural label is introduced.
3. **Evidence matrix row "Session continuity" (`:582`)** — re-anchor from the
   deleted `service/session_store.py:39` to `conversations.py:122`; record
   Frappe-owned state as implemented and live-verified per M3; retain M3's own
   recorded limits. The historical 2026-08-24 JSON-store row content is
   preserved as history, not deleted.
4. **New row — post-M7 routing stabilization** — placed adjacent to the existing
   routing row (`:586`) so the two are read together. Records the sequence
   M7 25/29 (historical, authoritative for M7) → `9f274ed` 26/29 → `ee8b0de`
   **28/29 passed, 1 failed, 0 harness errors** — the repository defines no
   "blocked" metric (`routing_cases.json` has no such field), so none is
   asserted; names the resolved defects; names `bye`/"see you later" as
   **unfixed model-output variance**; records that staging ERPNext was
   unreachable in that run so the read branch returned lookup-failure, which the
   archived evidence classifies as a read-branch/lookup-availability condition
   rather than a routing failure; states explicitly that this is post-M7
   stabilization evidence with no production-readiness, write, cloud, U/O or
   threshold implication.
5. **ERPNext reads row (`:584`)** — append the 2026-09-26 orchestrated
   populated-data demonstration. Retains the existing 2026-08-24 row content.
   Records the normal-user `Customer` schema 403 as still not demonstrated.
6. **New row — Developer Mode distinction** — the highest-risk addition.
   Four separate statements: inference-side developer capability
   **demonstrated**; Desk-facing Developer Mode experience **not demonstrated**
   because `api.py:236` fixes Desk to `chat-only`; full permission parity with
   the incoming Desk identity **unresolved** (U5 open, M4 shipped coarse tiers
   by intent); Developer Workbench **deferred** (R20, no milestone).
7. **Row `:591` replaced by four rows** — the single "Planned" row asserted that
   authenticated control, isolated knowledge, egress and complete audit were all
   unimplemented. Each is now split with its own anchor, evidence and — critically
   — its own retained missing-evidence list. Splitting rather than rewriting
   prevents one milestone's evidence from being read as another's.
8. **New row — M6 packaging** — `apps.json` directory workflow, fresh-site
   install/migrate exit 0, 4 DocTypes/tables. Docker parity, version matrix and
   CI/lint remain missing.
9. **U-register (`:613-622`)** — add a status-annotation paragraph above the
   table and a per-item note only where M2–M5 actually bear on the item, using
   the §2.1 rule. No row is deleted, reordered, reworded in substance or marked
   resolved.
10. **Closing note (`:650-652`)** — append a 2026-09-26 paragraph: no gate
    passed, no U/O resolved, no approval granted, M7 unchanged.

### 4.2 `ROADMAP.md`

- **`:19-21`** — retitle from **"Active pointer — 2026-09-19"** to a historical
  M5 closure heading. The body text is **preserved verbatim**; only the framing
  changes so the section no longer reads as an active pointer. This is the
  minimal fix for D3 — no M5/M6 history is rewritten.
- **New section after `:29`** — "Post-M7 stabilization — CLOSED (evidence and
  documentation only)": both routing changes, all four commit hashes, the
  28/29 result, the resolved defect list, `bye` unfixed, and an explicit
  statement that M7's 25/29 and its three decisions remain authoritative.
- **New consolidated position block** — M2–M7 closed; **no active
  implementation milestone**; **no M8 created or implied**; post-M7 work is
  evidence/documentation stabilization only; any future implementation requires a
  separately approved OpenSpec change.

### 4.3 `progress/CURRENT.md`

- **Header (`:3-5`)** — extend "Current task" to name the post-M7 stabilization
  state and the fact that no implementation milestone is active.
- **New dated section** — post-M7 routing stabilization, mirroring the ROADMAP
  entry with commit-level detail.
- **`:9` boundary paragraph** — extend with the four-way Developer Mode
  distinction, so the ERPNext demonstration cannot be misread as Developer Mode
  delivery.

### 4.4 `progress/BLOCKERS.md`

Restructured into three clearly-labelled groups, using only verified evidence:

1. **Closed evidence gaps** — routing defects (4 M7 + 3 regressions), populated
   ERPNext business-data retrieval, and the resolved-documentation entry
   preserved from the 2026-09-17 file.
2. **Still-open evidence** — held-out grounded/negative set (none exists),
   independent judging and per-question groundedness review, page-hint/minimal
   authorized field reads, transcript restore/streaming/realtime in real Desk,
   provider conformance matrix, M5 live concurrency/second actor/uncertain
   outcome, Docker custom image and version matrix, patch/upgrade/backup/restore/
   rollback, CI/lint, full intra-site ACL parity, normal integration-user
   `Customer` schema access, and the `bye` routing case.
3. **Governance blockers — unchanged** — M7's three decisions, staging-only,
   local-only, U1–U10, O2–O4. Reproduced with explicit "unchanged" framing.

The resolved ERPNext/Frappe doc-source entry at the file's tail is preserved.

### 4.5 `progress/JOURNAL.md`

One appended dated entry (newest at bottom, per the file's own convention)
recording what was reconciled, what was verified, and what was deliberately left
untouched.

## 5. Decision records

**DR-1 — Reconcile forward rather than rewrite.** `ARCHITECTURE.md`'s target
design, diagrams, trust boundaries and R01–R20 matrix are sound and are left
intact. Only current-state evidence is corrected. *Alternative rejected: a full
HLD rewrite would risk losing approved-direction content and would exceed a
documentation reconciliation.*

**DR-2 — Split the "Planned" row instead of editing it in place.** `:591`
bundled four independent capabilities under one status. Correcting it in place
would have let one milestone's evidence appear to cover another. *Alternative
rejected: a single combined "partially implemented" row loses per-capability
missing-evidence precision.*

**DR-3 — Evidence moves, decisions do not.** M4/M5 exercised U2/U6/U7-shaped
mechanisms. Recorded as evidence bearing on those items, with all three
remaining **U**. *Alternative rejected: inferring resolution from a working
implementation is exactly the failure mode `m7-review-report.md:30` forbids.*

**DR-4 — Explicit Developer Mode row.** The 2026-09-26 run used
`chat_only=False` on the inference side, bypassing `api.py:236`. Recorded as
four separate states rather than one verdict, because "Developer Mode" spans
four genuinely different claims.

**DR-5 — Retitle rather than delete the ROADMAP pointer.** `:19-21` is real M5
history. Deleting it would destroy the M5→M6 decision record; leaving it titled
"Active pointer" is what causes D3. Retitling fixes the defect with the smallest
possible change.

**DR-6 — Do not reconcile the open `bye` case.** M7's closure evidence
explicitly declined to relabel it fixed. Preserved as unfixed variance.

**DR-7 — Skip specs.** `skip_specs: true`, matching the archived
`reconcile-architecture-and-production-hld` precedent. No behavioral requirement
changes, and `openspec/specs/` is not modified.

## 6. Validation plan

Documentation-scope validation only:

- `git diff --check` (whitespace/conflict markers)
- `openspec validate reconcile-post-m7-project-state --type change --strict --no-interactive`
- Scope audit: `git status --short` and `git diff --stat` confirm only the six
  owned documentation paths plus this change record; zero changes under
  `openspec/specs/`, `evaluation/`, `tests/`, `frappe_app/`, `service/`, `rag/`,
  `tools/`, `orchestrator.py`, `config.py`, `.env`, or any `archive/` directory
- Credential/secret scan of the diff
- No runtime, migration, service, model, network, Docker or ERPNext action
- No out-of-scope repository accessed at any point
