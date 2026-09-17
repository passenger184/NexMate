# frappe-api-gateway Specification

## Purpose

Authenticated Frappe chat entry, authoritative persona selection, validated identity/site assertions and deterministic backend tool denial. Transitional session continuity is not ownership; this increment does not complete G2/M2.

## Requirements

### Requirement: Authenticated constructed chat request
Frappe SHALL expose one non-guest whitelisted `ask()` method using standard Frappe authentication and applicable session CSRF checks. It SHALL construct a bounded upstream `/orchestrate` request from question and optional legacy session ID, authenticated user, authoritative current site, derived mode and fixed `execution_scope="chat-only"`. It SHALL use a server-configured destination and credential, not forward arbitrary browser objects, headers, paths or URLs. Browser mode SHALL be ignored; user/site/scope/operation/target override fields SHALL be refused. Errors SHALL be bounded and sanitized.

#### Scenario: Authenticated question
- **WHEN** an authenticated Frappe user submits a valid question
- **THEN** Frappe forwards only its constructed chat envelope with server credential and returns the bounded response

#### Scenario: Guest or invalid session request
- **WHEN** a Guest/unauthenticated caller or a session request failing applicable CSRF validation invokes the method
- **THEN** Frappe refuses it without reaching inference

#### Scenario: Browser attempts envelope override
- **WHEN** a browser supplies user, site, execution scope, operation, target or upstream destination overrides
- **THEN** Frappe refuses the unsupported fields and makes no upstream call

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
Inference SHALL validate gateway context before history access, routing, retrieval or execution, not merely record it in telemetry. User and site SHALL be nonempty strings of at most 255 characters, without leading/trailing whitespace or control characters; Guest SHALL be refused. Mode SHALL be one of the supported personas and scope exactly `chat-only`. Site SHALL exactly match one trusted server-configured `NEXMATE_FRAPPE_SITE`; missing/invalid configuration or mismatch SHALL refuse gateway work. This fixed binding SHALL NOT implement tenant routing, repository selection, session ownership or site-isolated storage.

Any supplied gateway-envelope field (`user`, `site`, `execution_scope`) SHALL require a complete valid envelope and valid service credential; partial/invalid envelopes SHALL NOT fall back to legacy behavior. Unauthenticated development SHALL NOT establish gateway identity. Legacy requests without the envelope remain behind the service access rules without authenticated Frappe attribution. Only validated gateway context MAY enter minimized attributed telemetry; raw invalid fields, secrets and transport headers SHALL NOT be logged or placed in prompts.

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

### Requirement: Transitional session forwarding and required successor
The gateway SHALL preserve optional valid legacy `session_id` forwarding with existing validation and JSON storage. It SHALL NOT treat the identifier as authentication, authorization, user ownership or site isolation, nor claim safe authenticated multi-user continuity. Immediately after this bounded boundary is verified, a separately approved `frappe-owned-conversation-state` change SHALL be the next milestone: Frappe-owned records, user ownership, site association, persistence, replacement of caller-controlled ownership and JSON storage, plus migration/compatibility. That successor SHALL NOT be implemented here.

#### Scenario: Legacy identifier forwarded
- **WHEN** a gateway request supplies a valid legacy session identifier
- **THEN** it is forwarded for temporary continuity without modifying JSON storage or assigning authenticated ownership

#### Scenario: Invalid or absent identifier
- **WHEN** a session identifier fails existing validation or is absent
- **THEN** invalid values are refused under existing rules and absent values retain existing no-session behavior; neither case invents ownership binding

#### Scenario: Successor handoff
- **WHEN** verification of this bounded boundary is recorded
- **THEN** the next separately approved change is `frappe-owned-conversation-state` with all stated record/ownership/site/persistence/replacement/migration requirements, not a claim that this change delivered them

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
Desk chat SHALL use the authenticated Frappe method and SHALL NEVER directly call inference, including on gateway failure, mode changes, slash commands, reset/start-fresh or approval/rejection handlers. Unavailable tools/cards SHALL be disabled/refused, including stale cards. Start-fresh SHALL only clear local transcript and replace the local session identifier, with no server deletion claim. Standalone preview SHALL remain separate under the dual explicit development configuration; it SHALL receive no service credential and SHALL NOT enable Desk fallback.

#### Scenario: Desk chat and failure
- **WHEN** Desk sends chat or the Frappe gateway fails
- **THEN** traffic targets Frappe only and errors never trigger a direct FastAPI fallback

#### Scenario: Reset and stale approval card
- **WHEN** a Desk user starts fresh or invokes a stale approval/rejection/tool handler
- **THEN** no direct inference request or server reset/approval occurs; only supported local UI behavior is reported

#### Scenario: Preview isolation
- **WHEN** standalone preview is exercised under explicit development opt-in
- **THEN** no key is delivered to its browser and the Desk-only-Frappe rule remains unchanged
