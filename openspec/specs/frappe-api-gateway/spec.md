# frappe-api-gateway Specification

## Purpose

Authenticated Frappe chat entry, authoritative persona selection, validated identity/site assertions and deterministic backend tool denial. Conversations are Frappe-owned records; inference is stateless about ownership.

## Requirements

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

### Requirement: Authoritative role-derived persona
Frappe SHALL derive mode from the authenticated user's actual roles against server-managed `nexmate_developer_roles`, default `[]`. Only an explicit matching role SHALL select `developer`; otherwise select `employee`. There SHALL be no implicit System Manager or Administrator elevation. Invalid mapping configuration SHALL fail closed without elevation. No browser mapping-management endpoint SHALL be added. Persona SHALL NOT grant tool access, document/corpus permission, ownership or cloud consent.

#### Scenario: Empty default includes administrators
- **WHEN** the mapping is empty and an authenticated user, including System Manager or Administrator, asks a question
- **THEN** the gateway supplies employee mode

#### Scenario: Explicit configured role match
- **WHEN** the authenticated user's roles match an explicitly configured developer role
- **THEN** the gateway supplies developer mode but still enforces chat-only scope

#### Scenario: Browser mode ignored
- **WHEN** a user submits a browser-selected mode
- **THEN** Frappe discards it and independently derives mode from the authenticated user

#### Scenario: Invalid mapping
- **WHEN** the configured role mapping is malformed
- **THEN** the gateway fails closed without selecting developer mode

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

### Requirement: Deterministic backend chat-only execution guard
Gateway context SHALL carry an immutable request-local empty tool allowance enforced in backend code BEFORE tool invocation. It SHALL forbid read/search/explain/file/code/Git operations, ERPNext schema/document/list reads, business writes, proposals/apply, approval and session reset. Natural-language, troubleshooting, follow-ups, model-selected routes, fallbacks and developer mode SHALL NOT bypass it. It SHALL suppress incidental live ERPNext version lookups even on RAG/conversational paths. Denial SHALL precede execution, not filter results afterward. UI restrictions or model instructions alone SHALL NOT satisfy this requirement.

Conversational replies and existing cited RAG SHALL remain chat behavior, without claiming ACL retrieval or granting new private-corpus permission. Capability replies SHALL describe only available chat operations. Legacy direct tool access remains governed separately, never a gateway fallback.

#### Scenario: Natural-language code or business request
- **WHEN** a gateway question selects code/search/explain, ERPNext schema/list/document or proposal/write behavior, including in developer mode
- **THEN** deterministic backend enforcement returns unavailable-in-Desk behavior before any corresponding tool/client call

#### Scenario: Forced routes and fallbacks
- **WHEN** routing or mocked model output forces code, ERPNext, troubleshooting-to-code or a fallback/follow-up tool path
- **THEN** the unchanged chat-only context prevents all tool invocations regardless of wording or slash syntax

#### Scenario: Incidental version lookup
- **WHEN** gateway chat takes a RAG or other path normally fetching ERPNext versions
- **THEN** no live ERPNext call occurs and the response uses unavailable-version semantics without fabricated installed versions

#### Scenario: Explicit operation or approval
- **WHEN** a gateway request attempts read/search/explain/file/edit/business/reset/approval operation forwarding
- **THEN** it is refused with no tool endpoint proxy or execution path

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

### Requirement: Durable tool proposal and approval via Frappe
Frappe SHALL expose authenticated, whitelisted methods to create, approve, reject, and query durable tool proposals for business writes and code edits, using standard Frappe authentication and session CSRF checks. Creation SHALL persist an immutable actor/site-bound proposal as defined in `durable-tool-execution` (exact payload/diff, target, reason, expiry, preconditions, correlation). Approval and rejection SHALL be explicit, durable, actor-bound, and require the same authentication; browser-supplied actor/site or direct inference proposal creation SHALL be refused. Execution SHALL only occur after Frappe authorization, permission recheck, and approval validity checks, and SHALL be performed through the separate confined executor for code. Direct browser-to-inference tool, proposal, or approval calls SHALL remain impossible.

#### Scenario: Durable proposal created via Frappe
- **WHEN** an authenticated Frappe user creates a business-write proposal with an exact payload, target, and reason
- **THEN** Frappe persists the immutable proposal with actor/site/expiry/correlation and returns the proposal identifier without executing it

#### Scenario: Approval required before execution
- **WHEN** a proposal exists but has not been explicitly approved by an authorized actor
- **THEN** any execution attempt is refused before tool invocation, even with a valid gateway envelope

#### Scenario: Direct inference proposal bypass refused
- **WHEN** a browser attempts to create or approve a proposal by calling inference directly
- **THEN** the request never reaches inference and no durable proposal is created or approved

### Requirement: Durable execution outcome correlation
Frappe SHALL correlate execution attempts and outcomes to the same proposal and audit ledger entry by correlation/request/action identifiers, including successes, denials, failures, and uncertain outcomes. Clients SHALL be able to query the proposal and its correlated audit state through Frappe, without gaining direct inference audit-store access.

#### Scenario: Outcome queryable through Frappe
- **WHEN** an observer queries a proposal identifier through Frappe after execution, denial, or uncertain-outcome reconciliation
- **THEN** Frappe returns the linked audit outcome (success/denied/failed/uncertain) with actor/site/timestamp, without exposing the underlying inference audit store directly

### Requirement: Installation does not regress gateway authentication and proposal flows
The `bench get-app`/`install-app`/`migrate` packaging change SHALL NOT regress `frappe-api-gateway` authentication, site binding, or durable proposal flows. After a fresh installation, `frappe-api-gateway` SHALL still enforce `Frappe` session `non-Guest`, `frappe.local.site` validated, `X-NexMate-Key` service authentication on `POST /api/method/erpnext_ai_copilot.api.create_tool_proposal` etc., and `actor/site` derived from `Frappe` (never browser `actor`/`site` fields).

#### Scenario: Gateway still enforced after fresh install
- **WHEN** a fresh-installed site handles `POST /api/method/erpnext_ai_copilot.api.create_tool_proposal` with `Guest` or with browser-supplied `actor` field
- **THEN** it is refused with `unsupported_gateway_fields` or `Authentication required` before any proposal is created, and no `tabNexMate Tool Proposal` row is created

### Requirement: Gateway scope remains Frappe-derived after packaging
After installation, retrieval `scope` (`site`, `tiers`, `roles`, `derived_by`) SHALL still be derived from `frappe.get_roles(user)` via `frappe_app/erpnext_ai_copilot/api.py:_authz_scope`, not from client `mode` or `scope` fields, and shall be validated before `retriever.retrieve`.

#### Scenario: Scope still server-derived after fresh install
- **WHEN** a fresh-installed site's `Administrator` with `System Manager` role calls `ask` via `Frappe` (`bench --site <site> execute` is not the gateway, but `POST /api/method/...` with session cookie is)
- **THEN** the `scope` envelope contains `tiers` `["public","site","restricted"]` and `roles` including `System Manager`, not just `["public"]`
