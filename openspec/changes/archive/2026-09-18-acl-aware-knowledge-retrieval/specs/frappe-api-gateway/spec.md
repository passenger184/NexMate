## MODIFIED Requirements

### Requirement: Authenticated constructed chat request
Frappe SHALL expose one non-guest whitelisted `ask()` method using standard Frappe authentication and applicable session CSRF checks. It SHALL construct a bounded upstream `/orchestrate` request from question, the authenticated user, authoritative current site, derived mode, fixed `execution_scope="chat-only"`, the Frappe-derived authorization scope (site plus permitted visibility/roles for retrieval), and — when the caller supplies an owned conversation identifier — that identifier plus the bounded authorized turn history loaded from the Frappe-owned record. Calls without a conversation identifier SHALL be stateless single turns. Legacy caller-owned `session_id` forwarding and JSON storage SHALL NOT be used. It SHALL use a server-configured destination and credential, not forward arbitrary browser objects, headers, paths or URLs. Browser mode SHALL be ignored; user/site/scope/operation/target/history/authorization override fields SHALL be refused. The authorization scope SHALL be validated like other envelope fields; conversation ownership SHALL NOT substitute for knowledge authorization. Errors SHALL be bounded and sanitized.

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
