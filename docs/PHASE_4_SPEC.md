# docs/PHASE_4_SPEC.md — Project Memory

**Historical Phase 4 requirements, not current build scope.** Functional
acceptance was recorded 2026-08-24 (`ROADMAP.md`). `ARCHITECTURE.md` is the
sole canonical HLD; post-roadmap work requires a user-approved OpenSpec
change. Original requirements and unchecked checklist below are history,
not a current build instruction or fresh verification claim.

Historical entry gate: Phase 3's Definition of Done had to be met, with
Phase 2's edit tool producing commits and the company corpus available.
The original per-user persistence and reopen requirements below are not
proof of authenticated ownership or browser transcript restoration. Those
remain future Frappe-owned state/Desk gates in `EVALUATION.md`. Resolution
memory remains distinct from session history and subject to `SECURITY.md`.

## Original requirements

## Principle: memory is a corpus, not a new subsystem

Don't build a separate memory database or a summarization/recall layer.
Two distinct things live under "memory" — handle them differently:

### 1. Session continuity (simple, needed regardless)

The conversation remembers what was asked earlier in the same thread so
follow-ups work without repeating context. Standard chat history, stored
per user, included in the prompt each turn. This is not a design decision
to deliberate over — just implement it as part of the service/session
layer alongside the UI's single-continuous-thread model (see
`docs/UI_SPEC.md`).

Store it server-side (not only in browser state) so refreshing the page or
reopening the sidebar doesn't lose the thread. "Start fresh" in the UI
clears it.

### 2. Project memory — the actual valuable part

Every confirmed edit from the Phase 2 code agent already produces a git
commit with a message and diff. Every resolved "why is this failing"
conversation is, in effect, a solved case. Feed these into the **same**
Chroma store already used for docs and company code, as a new tagged
source: `source_type: resolved_issue`.

Concretely:
- After a Phase 2 edit is committed, index the commit message + diff +
  the conversational context that led to it (the question that was asked,
  the explanation given) as a retrievable chunk.
- Optionally (only if it proves useful in practice, don't over-build this
  upfront): also index resolved Q&A exchanges that didn't involve a code
  edit, if the user marks them as "this helped" — a low-effort signal, not
  a required workflow step.
- These chunks retrieve alongside docs and company code — the assistant
  should be able to answer "we saw this before — here's how it was fixed"
  the same way it cites a doc, with the same citation mechanism.

## What NOT to build

- No separate memory API, no summarization pipeline that tries to compress
  history into "facts about the user" — that's a different (and much more
  failure-prone) approach than just retrieving the actual resolved cases.
- No cross-project memory — this stays scoped to the single project per
  `ARCHITECTURE.md`'s current scope, same as everything else.

## Definition of Done

- [ ] Session continuity verified: a follow-up question referencing earlier
      context in the same thread is answered correctly
- [ ] At least 3 real Phase 2 edits are indexed as `resolved_issue` chunks
      after commit
- [ ] A test question deliberately similar to a previously resolved issue
      retrieves and cites that resolution
- [ ] "Start fresh" in the UI clears visible thread state without deleting
      the underlying resolved-issue knowledge (those are permanent
      knowledge, not session state)
- [ ] `progress/CURRENT.md` updated
