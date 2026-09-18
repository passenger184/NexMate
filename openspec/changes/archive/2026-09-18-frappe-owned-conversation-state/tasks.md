# Tasks: frappe-owned-conversation-state

Planning only — no implementation started. Verification for each task is stated inline.

## 1. Frappe-owned records

- [x] 1.1 Define the conversation DocType (owner, site, persona, timestamps) with a child turn table (role, content, timestamp) and verify `bench --site <site> migrate` creates the tables with no errors.
- [x] 1.2 Seed no demo data and verify a fresh site shows zero conversation records via an owner-scoped query.
- [x] 1.3 Unit-test the turn/character budget helper (most-recent-wins truncation) with synthetic oversized threads and verify the bounded tail is returned.

## 2. Gateway lifecycle methods

- [x] 2.1 Implement non-guest whitelisted start/transcript/reset methods with explicit owner+site checks that privileged Frappe roles cannot bypass (NexMate API authorization is separate from administrative DocType access) and verify Guest calls, cross-user calls including by a privileged role, and cross-site calls are refused without touching records.
- [x] 2.2 Extend `ask()` with optional owned `conversation_id` (stateless single turn when absent) and verify unauthenticated, forged-owner, and cross-site identifiers are refused before any history read.
- [x] 2.3 Implement Frappe-side append discipline (user turn pre-append, assistant turn post-append on success only) and verify a failed inference call leaves the user turn without deleting history.
- [x] 2.4 Unit-test malformed identifiers, oversized questions, and invalid roles against the new methods with mocked Frappe and verify sanitized refusals.
- [x] 2.5 Verify concurrent appends to one conversation are serialized (document lock or revision-guarded update; conflicts fail loudly for retry) with a synthetic concurrency test and confirm no persisted turn is silently overwritten or lost.

## 3. Ownership-stateless inference

- [x] 3.1 Build the envelope with inline bounded history and conversation binding, and verify Frappe refuses forged owner/site/history bindings while inference validates envelope consistency only (structure, owner-equals-user, site-equals-trusted, budget, allowed roles, service/gateway provenance) without legacy downgrade.
- [x] 3.2 Make gateway `/orchestrate` use only supplied turns with no per-conversation persistence, and verify a service restart loses nothing (nothing was kept) while Frappe threads survive.
- [x] 3.3 Unit-test envelope consistency validation (owner/user mismatch, site mismatch, over-budget turns, disallowed roles, Guest, unauthenticated provenance) with synthetic payloads and verify refusal precedes routing/retrieval.

## 4. Legacy retirement

- [x] 4.1 Delete `service/session_store.py`, legacy `session_id` handling, and the JSON reset endpoint, and verify no remaining reference imports or routes them (grep + full test-suite pass).
- [x] 4.2 Verify leftover `data/sessions/` files are never read and legacy session paths fail explicitly (refused as unknown/removed, never silently stateless) and document manual cleanup.
- [x] 4.3 Verify standalone preview works statelessly under the dual development opt-in with no persistence claim.

## 5. Desk wiring

- [x] 5.1 Wire start-fresh to the owned reset method (local clear only when no owned conversation) and verify zero direct-inference requests in the Desk path.
- [x] 5.2 Wire transcript restore to the owner-bounded transcript fetch and verify a reloaded Desk shows only the owner's thread.
- [x] 5.3 Extend the stub-DOM/Node harness for the new Desk flows and verify all checks pass without touching network.

## 6. Live Bench verification (authorized test environment only)

- [x] 6.1 Install the app and migrate in the test Bench and verify owned threads persist across inference restarts while cross-user/cross-site/privileged-role/Guest negatives are refused live.
- [x] 6.2 Verify budget caps, orphan-turn-on-failure behavior, serialized concurrent mutation with no lost turns, and explicitly refused retired paths live, with sanitized logs (no secrets, no raw history in telemetry).
- [x] 6.3 Re-run the Task 6.3 boundary checks (auth, chat-only, health, no-direct-DI) against the new build and verify no regression.

## 7. Docs and handoff

- [x] 7.1 Document the cutover (threads restart once because ownership cannot be established for legacy sessions, JSON files ignored, preview stateless; no ownership migrated or fabricated) in README/DEVELOPMENT scope and verify the rollback path (revert build; Frappe threads simply unused).
- [x] 7.2 Record dated evidence and remaining gates in progress files and verify the archived predecessor change is left untouched.
