## Why

Gateway chat still rides on caller-supplied `session_id` values backed by unauthenticated JSON files on the inference host: filename validation is not ownership, any caller can read or collide with another user's thread, and history cannot survive inference restarts as anyone's property. G3 of the HLD requires conversations to become Frappe-owned records bound to the authenticated user and site, with FastAPI stateless about ownership.

## What Changes

- Add Frappe-owned conversation records (new DocType with owner + site binding) holding bounded turn history; all gateway history reads/writes go through them with owner checks.
- Extend the whitelisted gateway: `ask()` accepts an optional owned `conversation_id` (stateless single-turn when absent); add owner-checked conversation start, transcript fetch (bounded, for restore), and reset (server-side delete) methods. Non-guest only, CSRF-protected, sanitized errors.
- Change the gateway envelope: Frappe supplies the bounded authorized history and conversation identity; inference validates owner/site binding, uses history purely, and stores nothing per-conversation.
- **BREAKING**: remove the legacy inference JSON session store (`service/session_store.py`, `data/sessions/`, `POST /tools/session/reset` legacy behavior); legacy direct `/orchestrate` `session_id` continuity is retired. Leftover JSON files are left untouched on disk and never read again.
- Desk start-fresh becomes a real server-side reset of the owned conversation (replacing the local-only behavior); transcript restore reads the owned transcript.
- Migration/compatibility: no automatic import of ownerless JSON files; documented cutover (old threads end, new owned threads begin); preview/standalone development becomes stateless.

## Capabilities

### New Capabilities

- `frappe-owned-conversation-state`: Frappe-owned conversation records, owner/site binding, bounded history, lifecycle methods, FastAPI statelessness, migration from the JSON store.

### Modified Capabilities

- `frappe-api-gateway`: envelope now carries owned-conversation identity and authorized history instead of the legacy `session_id`; the transitional-session requirement is superseded (successor delivered); start-fresh gains a real server-side reset claim.
- `endpoint-access-control`: legacy direct `/orchestrate` session continuity and the JSON-backed session reset endpoint are removed from the retained inventory; Desk reset now reaches a Frappe-owned server operation.

## Impact

- Frappe app: new DocType + whitelisted methods + Desk wiring (start-fresh, restore); new server-side state covered by standard Frappe permissions plus explicit owner/site checks.
- Inference service: `service/session_store.py` deleted; `/orchestrate` gateway path becomes ownership-stateless; legacy `/tools/session/reset` removed; direct legacy `session_id` support retired.
- Operators: one-time cutover (history restart); no data migration of JSON files.
- Out of scope: ACL-aware retrieval, streaming/realtime, MCP, multi-workspace, retention auto-expiry, transcript UI redesign.
