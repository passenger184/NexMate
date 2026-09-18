# Design: frappe-owned-conversation-state

## Context

See `proposal.md` (Why). Current state: gateway `ask()` forwards an
optional caller-chosen `session_id` (`frappe_app/erpnext_ai_copilot/api.py:117`);
inference keeps per-session JSON files (`service/session_store.py:39`) with
filename validation as the only protection — no owner, no site, readable by
any caller who guesses the name. The archived boundary explicitly deferred
ownership to this change and kept inference fail-closed and chat-only; those
guarantees stay untouched. Desk start-fresh is local-only; no transcript
restore exists.

## Goals / Non-Goals

Goals: one owner-bound thread abstraction enforced in Frappe; inference
stateless about ownership; bounded history budgets preserved; safe cutover
with no silent ownership reassignment and no privilege change. Legacy
threads are intentionally retired because ownership cannot be established
for them: nothing is migrated and no ownership is fabricated. Non-goals
(design adds no mechanism for): per-message ACLs beyond owner+site,
retention auto-expiry, streaming/realtime transport, transcript UI redesign,
corpus permission changes.

## Decisions

- **D0 — Record shape: parent DocType + child turns (chosen).** A `NexMate
  Conversation` document (owner, site, persona, timestamps) with a child
  table of ordered turns (role, content, timestamp) over a single DocType
  with a JSON blob: child rows are queryable, permission-aware, and render
  in standard Frappe forms; over one-row-per-turn: preserves thread
  atomicity and matches "one continuous thread" UX. Owner field defaults
  to the session user and is never accepted from the browser.
- **D1 — Enforcement point: gateway methods, not inference (chosen).**
  Owner/site checks live in the new whitelisted methods (`start`,
  `ask`-with-id, `transcript`, `reset`) using standard Frappe auth/CSRF
  plus explicit `owner == frappe.session.user` and `site == frappe.local.site`
  comparisons. Frappe is authoritative for authenticated user identity,
  current site, and conversation ownership. Privileged Frappe roles
  (System Manager, Administrator) do NOT bypass the NexMate API owner
  check; administrative DocType access outside the NexMate API is a
  separate concern and confers no gateway continuity. Alternative
  (row-level permission rules only) rejected: explicit checks give
  deterministic sanitized failures and cover the site dimension uniformly.
- **D2 — Write discipline: Frappe appends, inference computes (chosen).**
  On `ask()`: Frappe appends the user turn, forwards the bounded tail,
  then appends the assistant reply after a successful response. Appends
  mutate the conversation document serially under Frappe document locking
  (or an equivalent revision-guarded update): a conflicting concurrent
  mutation fails loudly for caller retry instead of overwriting persisted
  turns — last-writer-wins is not acceptable where it can lose turns. If
  inference fails, the user turn stands alone (documented, retried by
  resending — never auto-deleted): the pre-append is committed before the
  upstream call because Frappe rolls back errored requests. Alternative
  (inference writes back via a privileged callback) rejected: it would
  punch a write path through the service boundary the HLD keeps read-only
  from inference's side.
- **D3 — Envelope carries history, not a handle (chosen).** The gateway
  sends validated turns inline. Inference validates envelope consistency
  only — identifier present and well-formed, conversation owner equal to
  the envelope user, conversation site equal to the trusted site, turns
  within budget with allowed roles, and authenticated service/gateway
  provenance intact — then treats turns as ephemeral context. Inference
  never independently authorizes conversation ownership; Frappe's
  assertions are authoritative. Alternative (Frappe passes only an ID and
  inference fetches from Frappe) rejected: it needs a new privileged
  inference→Frappe read channel and couples inference availability to
  Frappe reads on every turn.
- **D4 — Legacy end: delete, don't migrate (chosen).** JSON files lack
  owner/site, so no faithful import exists; the store module, legacy
  `/orchestrate` `session_id` continuity, and the JSON reset endpoint are
  removed, old files left unread on disk with a documented manual cleanup.
  Legacy direct `session_id` continuity fails explicitly (refused as
  unknown/removed), never silently degrades to stateless. Alternative
  (bulk-import files as Administrator-owned threads) rejected: it would
  fabricate ownership. **BREAKING** for direct-API session users; Desk
  users only see threads restart once.
- **D5 — Budgets reuse existing semantics (chosen).** Per-conversation
  turn/character caps mirror `SESSION_MAX_TURNS`/`SESSION_MAX_CHARS`
  (most-recent-wins) so follow-up quality behavior is unchanged; only the
  backing store moves.
- **D6 — Reset is delete-by-owner (chosen).** `reset` hard-deletes the
  owned thread (resolved-issue knowledge is a separate corpus and is
  untouched). Alternative (soft-close flag) deferred: no retention policy
  exists yet to give "closed" a meaning.
- **D7 — Preview stays stateless (chosen).** Without Frappe there is no
  owner; dual-opt-in preview keeps working with no persistence rather than
  gaining a parallel store.

## Risks / Trade-offs

- [Risk] Two writes per turn (user pre-append + assistant post-append)
  can leave orphan user turns on inference failure → Mitigation: documented
  behavior; resend continues the thread; no silent deletion.
- [Risk] Concurrent asks on one conversation race on the same document →
  Mitigation: serialized mutation under Frappe document locking (or
  revision-guarded update); conflicts fail loudly for caller retry and
  persisted turns are never silently overwritten or lost.
- [Risk] Consumers of legacy `session_id` break → Mitigation: marked
  **BREAKING**; removal is fail-loud (explicitly refused as unknown/removed,
  never silently stateless); cutover note in docs.
- [Risk] History crossing to inference grows payloads → Mitigation: budget
  caps enforced before the envelope is built; oversized stored threads can
  never widen the wire format.

## Migration Plan

1. Ship DocType + methods + envelope behind existing service auth; JSON
   store still present but gateway stops using it — legacy `session_id`
   values are refused explicitly, never silently downgraded to stateless.
2. Delete `service/session_store.py`, legacy reset endpoint, and legacy
   `session_id` handling; Desk switches start-fresh/restore to owned
   methods.
3. Verify (unit + live Bench): ownership negatives (cross-user, cross-site,
   privileged-role-on-other-thread, Guest), serialized concurrent mutation,
   stateless inference (restart loses nothing because nothing is kept),
   budget caps, legacy paths explicitly refused.
4. Document cutover; operators may delete stale `data/sessions/` files by
   hand. Rollback: revert to prior app+service build (threads created
   meanwhile stay in Frappe and are simply unused by the old code).

## Open Questions

None that change specs, approach, or tasks. Exact DocType/field labels and
turn-budget numbers are set during implementation within the bounds above.
