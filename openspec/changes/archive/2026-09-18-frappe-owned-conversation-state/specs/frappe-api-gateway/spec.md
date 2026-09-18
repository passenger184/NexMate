## MODIFIED Requirements

### Requirement: Authenticated constructed chat request
Frappe SHALL expose one non-guest whitelisted `ask()` method using standard Frappe authentication and applicable session CSRF checks. It SHALL construct a bounded upstream `/orchestrate` request from question, the authenticated user, authoritative current site, derived mode, fixed `execution_scope="chat-only"`, and — when the caller supplies an owned conversation identifier — that identifier plus the bounded authorized turn history loaded from the Frappe-owned record. Calls without a conversation identifier SHALL be stateless single turns. Legacy caller-owned `session_id` forwarding and JSON storage SHALL NOT be used. It SHALL use a server-configured destination and credential, not forward arbitrary browser objects, headers, paths or URLs. Browser mode SHALL be ignored; user/site/scope/operation/target/history override fields SHALL be refused. Errors SHALL be bounded and sanitized.

#### Scenario: Authenticated question
- **WHEN** an authenticated Frappe user submits a valid question
- **THEN** Frappe forwards only its constructed chat envelope with server credential and returns the bounded response

#### Scenario: Guest or invalid session request
- **WHEN** a Guest/unauthenticated caller or a session request failing applicable CSRF validation invokes the method
- **THEN** Frappe refuses it without reaching inference

#### Scenario: Browser attempts envelope override
- **WHEN** a browser supplies user, site, execution scope, operation, target, history, or upstream destination overrides
- **THEN** Frappe refuses the unsupported fields and makes no upstream call

#### Scenario: Owned conversation continued
- **WHEN** an authenticated user supplies a conversation identifier they own on the current site
- **THEN** Frappe loads the bounded authorized history from the owned record and includes it in the envelope

#### Scenario: Foreign conversation identifier refused
- **WHEN** the identifier names a record owned by someone else or bound to another site
- **THEN** Frappe refuses without reading history or reaching inference

### Requirement: Validated identity and single-project site binding
Inference SHALL validate gateway context before history access, routing, retrieval or execution, not merely record it in telemetry. User and site SHALL be nonempty strings of at most 255 characters, without leading/trailing whitespace or control characters; Guest SHALL be refused. Mode SHALL be one of the supported personas and scope exactly `chat-only`. Site SHALL exactly match one trusted server-configured `NEXMATE_FRAPPE_SITE`; missing/invalid configuration or mismatch SHALL refuse gateway work. When a conversation is supplied, its identifier, owner, and site SHALL be validated against the envelope user and the trusted site before any supplied turn is used, and supplied turns SHALL be bounded. This fixed binding SHALL NOT implement tenant routing, repository selection, or site-isolated storage. Inference SHALL NOT persist per-conversation state; durable ownership lives in Frappe alone.

Any supplied gateway-envelope field (`user`, `site`, `execution_scope`, conversation identity/history) SHALL require a complete valid envelope and valid service credential; partial/invalid envelopes SHALL NOT fall back to legacy behavior. Unauthenticated development SHALL NOT establish gateway identity. Legacy requests without the envelope remain behind the service access rules without authenticated Frappe attribution. Only validated gateway context MAY enter minimized attributed telemetry; raw invalid fields, secrets and transport headers SHALL NOT be logged or placed in prompts.

#### Scenario: Valid attributed request
- **WHEN** a service-authenticated gateway request has valid user/mode/scope and exactly the configured site
- **THEN** inference accepts the bounded context and may record validated user/site metadata, without treating it as user-level data authorization

#### Scenario: Malformed or partial identity
- **WHEN** a gateway field is missing, incorrectly typed, blank, oversized, control-character-bearing, Guest or paired with an invalid scope/mode
- **THEN** inference refuses before history/routing/retrieval/execution with no legacy downgrade and no raw invalid-field logging

#### Scenario: Wrong or unconfigured site
- **WHEN** the site differs from the trusted configured site or that configuration is missing/invalid
- **THEN** the gateway request is refused before work without selecting a different tenant, repository or store

#### Scenario: Development caller asserts gateway identity
- **WHEN** an unauthenticated development request supplies gateway-envelope fields
- **THEN** inference refuses gateway attribution and execution despite the general development exemption

#### Scenario: Forged conversation binding refused
- **WHEN** a supplied conversation names a different owner than the envelope user or a different site than the trusted site
- **THEN** inference refuses before any supplied turn is used, with no persistence side effect

### Requirement: Desk communicates only through Frappe
Desk chat SHALL use the authenticated Frappe method and SHALL NEVER directly call inference, including on gateway failure, mode changes, slash commands, approval/rejection handlers, or transcript restore. Unavailable tools/cards SHALL be disabled/refused, including stale cards. Start-fresh SHALL invoke the owner-checked server-side reset of the current owned conversation and replace the local conversation reference; with no owned conversation it SHALL only clear locally. Transcript restore SHALL read only the owner's bounded transcript through Frappe. Standalone preview SHALL remain separate under the dual explicit development configuration; it SHALL receive no service credential, SHALL NOT enable Desk fallback, and SHALL be stateless.

#### Scenario: Desk chat and failure
- **WHEN** Desk sends chat or the Frappe gateway fails
- **THEN** traffic targets Frappe only and errors never trigger a direct FastAPI fallback

#### Scenario: Owned reset and stale approval card
- **WHEN** a Desk user starts fresh on an owned conversation or invokes a stale approval/rejection/tool handler
- **THEN** the reset deletes the owned thread server-side (or clears locally when none exists) and no direct inference request or approval occurs; only supported local UI behavior is reported otherwise

#### Scenario: Reset and stale approval card
- **WHEN** a Desk user starts fresh with no owned conversation, or invokes a stale approval/rejection/tool handler left over from before this change
- **THEN** only supported local UI behavior occurs: local transcript handling with no server deletion claim, and no direct inference request or approval is executed

#### Scenario: Preview isolation
- **WHEN** standalone preview is exercised under explicit development opt-in
- **THEN** no key is delivered to its browser, no thread is persisted, and the Desk-only-Frappe rule remains unchanged

## REMOVED Requirements

### Requirement: Transitional session forwarding and required successor
**Reason**: Superseded — this change delivers the Frappe-owned successor, so transitional caller-owned forwarding ends here.
**Migration**: Use owned conversation identifiers and lifecycle methods defined in `frappe-owned-conversation-state`; legacy `session_id` values are no longer accepted for continuity.
