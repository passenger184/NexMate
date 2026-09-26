## Why

`ARCHITECTURE.md` is the sole canonical HLD (`AGENTS.md`), but it was reconciled
on 2026-09-17 — **before** milestones M2 through M7 and the post-M7 routing and
ERPNext evidence work existed. It now contradicts verified reality in ways that
every future reviewer, decision and agent session inherits:

- `ARCHITECTURE.md:591` classifies authenticated control, isolated knowledge,
  egress and complete audit as *"Planned; no target-boundary
  implementation/verification claimed."* All four are implemented and
  live-verified (M2, M4, M5).
- `ARCHITECTURE.md:582` cites **`service/session_store.py:39` as a live source
  anchor. That file was deleted by M3.** `service/` now contains only
  `__init__.py`, `auth.py`, `main.py`. The canonical HLD carries a broken
  citation.
- The same row still states *"No owner-bound Frappe state"*, which M3 delivered
  and live-verified.
- The U1–U10 register (`:613-622`) predates M4/M5 and does not record what those
  milestones actually settled.

Separately, the authoritative pointer files do not record the two post-M7
routing fixes at all. `ROADMAP.md`, `progress/CURRENT.md` and
`progress/BLOCKERS.md` contain no mention of
`fix-routing-precision-after-m7` or `fix-post-live-routing-regressions`, and no
mention of their final live result of **28/29 passed, 1 failed, 0
harness errors**. A reader consulting the pointer files would still treat M7's
historical 25/29 as the authoritative live routing figure.

`ROADMAP.md:19` additionally carries a live heading **"Active pointer —
2026-09-19"** whose body advances M5 to M6, directly contradicted by the M6 and
M7 CLOSED sections below it. `progress/BLOCKERS.md` is dated 2026-09-17 and
predates M4–M7 entirely.

The highest-risk omission is the Developer Mode distinction. The 2026-09-26
ERPNext evidence exercised `orchestrator.handle_question(..., mode="developer")`
with inference-side `chat_only=False`, bypassing the Desk gateway's hard-coded
`"execution_scope": "chat-only"` (`frappe_app/erpnext_ai_copilot/api.py:236`).
No document currently records that this demonstrates the **inference-side**
developer path and **not** a Desk-facing Developer Mode experience. Without that
distinction a reviewer could conclude Developer Mode is delivered.

The project is at a hard governance stop. This change makes the documentation
match what was actually built, tested and demonstrated, and nothing more.

## What Changes

Documentation only, in five authoritative files plus this change record.

- **`ARCHITECTURE.md`** — re-anchor and correct the stale current-state
  evidence: replace the deleted `service/session_store.py` citation with the
  M3 Frappe-owned conversation modules; split the single "Planned" row at `:591`
  into four milestone-accurate rows (M2 authenticated control, M3 owned state,
  M4 ACL/generations/egress, M5 durable audit/Debug); add rows for the M6
  packaging result, the post-M7 routing stabilization result, the 2026-09-26
  orchestrated populated-ERPNext demonstration, and an explicit **Developer Mode
  distinction row**; annotate the U1–U10 register with what M2–M5 settled versus
  what remains an undecided architectural choice, without resolving anything.
- **`ROADMAP.md`** — retitle the superseded 2026-09-19 "Active pointer" section
  as a historical M5 closure record so it no longer implies M6 is active; add a
  post-M7 stabilization section recording both routing changes, their commits and
  the 28/29 result; add a consolidated current-position statement (M2–M7 closed,
  no active implementation milestone, no M8).
- **`progress/CURRENT.md`** — add a dated post-M7 routing stabilization section
  and extend the 2026-09-26 boundary paragraph with the four-way Developer Mode
  distinction.
- **`progress/BLOCKERS.md`** — re-date and restructure into closed evidence /
  still-open evidence / governance blockers, using only verified current evidence.
- **`progress/JOURNAL.md`** — append one dated entry for this documentation unit.

The reconciliation uses one consistent evidence vocabulary throughout:
**implemented** (code exists), **demonstrated** (evidence shows it works in the
tested environment/path), **partially demonstrated** (some part works, complete
contract or user experience unproven), **unresolved** (architecture, policy,
threshold or evidence still open), **deferred** (explicitly postponed).

## Capabilities

### New Capabilities

None. This is a documentation-only reconciliation and introduces no runtime
behavior. `.openspec.yaml` declares `skip_specs: true`, matching the established
convention of the archived `reconcile-architecture-and-production-hld` change.
No speculative capability spec will be created or archived as delivered
functionality.

### Modified Capabilities

None. The twelve canonical specs under `openspec/specs/` are **not** touched.
This change records evidence state and documentation accuracy; it does not
change any behavioral requirement, and it must not be used to imply that an
unresolved architectural item is now specified.

## Impact

**Files owned by this change (documentation only):**

- `ARCHITECTURE.md`
- `ROADMAP.md`
- `progress/CURRENT.md`
- `progress/BLOCKERS.md`
- `progress/JOURNAL.md`
- `openspec/changes/reconcile-post-m7-project-state/` (this record)

**Explicitly out of scope and not modified:** all application and runtime code,
all tests, `.env` and any credential, ERPNext configuration, ERPNext
permissions, Docker configuration, provider configuration,
`evaluation/routing_cases.json` and every other evaluation artifact, routing
logic, `openspec/specs/`, `DECISIONS.md`, and every archived change directory
including the archived M7 decision artifacts.

## Non-goals

- No M8. No new implementation milestone. No approval of future work.
- No change to M7's decisions: release **NOT READY**, production writes
  **DENIED/PENDING**, private-data cloud/provider consent **NO GRANT**, staging-only
  review posture, local-only generation. M7 remains CLOSED and authoritative.
- No U-item or O-item resolved. Per `m7-review-report.md:30`, live testing
  success changes evidence states, never decision states; that rule governs this
  change.
- No re-labelling of the remaining `bye` routing failure as fixed. It is
  recorded as model-output variance, not a routing regression, and not fixed.
- No permission change of any kind, including the normal integration user's
  `Customer` schema 403.
- No claim that Developer Mode is delivered, that production writes are
  authorized, that held-out evaluation exists, or that any production gate
  passed.
- No modification of historical acceptance records, historical phase evidence or
  the M7 25/29 figure.
- No runtime, migration, service, model, network, Docker or ERPNext action of any
  kind.
- No commit, push or archive without explicit user instruction.
