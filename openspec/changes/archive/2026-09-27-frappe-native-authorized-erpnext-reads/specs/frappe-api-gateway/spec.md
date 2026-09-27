## MODIFIED Requirements

### Requirement: Authenticated constructed chat request
Frappe SHALL expose one non-guest whitelisted `ask()` method using standard Frappe authentication and applicable session CSRF checks. It SHALL construct a bounded upstream `/orchestrate` request from question, the authenticated user, authoritative current site, derived mode, fixed `execution_scope="chat-only"`, the Frappe-derived authorization scope (site plus permitted visibility/roles for retrieval), and — when the caller supplies an owned conversation identifier — that identifier plus the bounded authorized turn history loaded from the Frappe-owned record. Calls without a conversation identifier SHALL be stateless single turns. Legacy caller-owned `session_id` forwarding and JSON storage SHALL NOT be used. It SHALL use a server-configured destination and credential, not forward arbitrary browser objects, headers, paths or URLs. Browser mode SHALL be ignored; user/site/scope/operation/target/history/authorization override fields SHALL be refused. The authorization scope SHALL be validated like other envelope fields; conversation ownership SHALL NOT substitute for knowledge authorization. Errors SHALL be bounded and sanitized.

Frappe SHALL additionally act as the authorization enforcement point for ERPNext business-data reads requested during the turn. When the upstream turn requires ERPNext business data, Frappe SHALL service that read itself against the live authenticated session and SHALL place only the authorized, minimized result into a dedicated Frappe-produced authorized-context field carried back into the inference flow. That field SHALL be bounded in structure and size, SHALL contain no credential and no authorization-subject override, SHALL NOT be a generic arbitrary-context injection channel, and SHALL NOT be echoed back as an uncontrolled response field. Frappe SHALL preserve its existing response-field allowlist and upstream response size bounds, and SHALL NOT introduce a separate response-field design for authorized context. Inference SHALL remain a requester and consumer of authorized context; it SHALL NOT authorize or execute the read.

#### Scenario: Authenticated question
- **WHEN** an authenticated Frappe user submits a valid question
- **THEN** Frappe forwards only its constructed chat envelope with server credential and returns the bounded response

#### Scenario: Guest or invalid session request
- **WHEN** a Guest/unauthenticated caller or a session request failing applicable CSRF validation invokes the method
- **THEN** Frappe refuses it without reaching inference

#### Scenario: Browser attempts envelope override
- **WHEN** a browser supplies user, site, execution scope, operation, target, history, authorization scope, or upstream destination overrides
- **THEN** Frappe refuses the unsupported fields and makes no upstream call

#### Scenario: Owned conversation continued
- **WHEN** an authenticated user supplies a conversation identifier they own on the current site
- **THEN** Frappe loads the bounded authorized history from the owned record and includes it in the envelope

#### Scenario: Foreign conversation identifier refused
- **WHEN** the identifier names a record owned by someone else or bound to another site
- **THEN** Frappe refuses without reading history or reaching inference

#### Scenario: Authorization scope derived and carried
- **WHEN** an authenticated user asks a retrieval-capable question
- **THEN** the envelope carries the Frappe-derived site plus permitted visibility/roles, validated before retrieval

#### Scenario: Malformed authorization scope refused
- **WHEN** the scope is missing, mistyped, or inconsistent with the authenticated user and site
- **THEN** the request is refused before history, routing, retrieval, or execution

#### Scenario: Authorized context produced only by Frappe
- **WHEN** the turn requires ERPNext business data
- **THEN** Frappe performs the authorized read itself and places only the bounded authorized, minimized result into the dedicated authorized-context field

#### Scenario: Browser cannot supply authorized context
- **WHEN** a browser supplies an authorized-context or ERPNext read field
- **THEN** Frappe refuses the unsupported field and performs no read

#### Scenario: Authorized context is not echoed back
- **WHEN** Frappe returns the response to the browser
- **THEN** the result contains only the existing allowed response fields and does not relay the authorized context upstream payload

#### Scenario: Inference cannot authorize the read
- **WHEN** inference proposes an ERPNext read
- **THEN** Frappe validates and authorizes it under the session user before any record is returned
