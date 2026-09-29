## MODIFIED Requirements

### Requirement: Authenticated constructed chat request
Frappe SHALL expose one non-guest whitelisted `ask()` method using standard Frappe authentication and applicable session CSRF checks. It SHALL construct a bounded upstream `/orchestrate` request from question, the authenticated user, authoritative current site, the capability derived from the authenticated user's actual roles carried in the existing `mode` field, the generic authenticated execution scope, the Frappe-derived authorization scope (site plus permitted visibility/roles for retrieval), and — when the caller supplies an owned conversation identifier — that identifier plus the bounded authorized turn history loaded from the Frappe-owned record. Calls without a conversation identifier SHALL be stateless single turns. Legacy caller-owned `session_id` forwarding and JSON storage SHALL NOT be used. It SHALL use a server-configured destination and credential, not forward arbitrary browser objects, headers, paths or URLs. Browser mode or capability SHALL be refused as unsupported fields rather than accepted and ignored; user/site/scope/operation/target/history/authorization override fields SHALL be refused. The envelope SHALL NOT introduce a second field asserting the same capability, and SHALL NOT carry any administrator-controlled NexMate configuration such as the metadata access policy or its mode or configured DocTypes. The authorization scope SHALL be validated like other envelope fields; conversation ownership SHALL NOT substitute for knowledge authorization. Errors SHALL be bounded and sanitized.

The gateway SHALL additionally act as the authorization enforcement point for ERPNext business-data reads requested during the turn. When the upstream turn requires ERPNext business data, Frappe SHALL service that read itself against the live authenticated session and SHALL place only the authorized, minimized result into a dedicated Frappe-produced authorized-context field carried back into the inference flow. That field SHALL be bounded in structure and size, SHALL contain no credential and no authorization-subject override, SHALL NOT be a generic arbitrary-context injection channel, and SHALL NOT be echoed back as an uncontrolled response field. Frappe SHALL preserve its existing response-field allowlist and upstream response size bounds, and SHALL NOT introduce a separate response-field design for authorized context. Inference SHALL remain a requester and consumer of authorized context; it SHALL NOT authorize or execute the read.

The gateway SHALL likewise act as the enforcement point for capability-gated DocType metadata. When the upstream turn requests DocType schema, Frappe SHALL resolve it itself under the live authenticated session, the user's derived capability and the current site's administrator-controlled metadata access policy, SHALL place only the bounded, minimized schema into the authorized-context field, and SHALL refuse the request when the user does not hold the `developer` capability or when the policy does not permit that DocType. Schema SHALL NOT be resolved by inference, and the same round-trip bound that governs business reads SHALL govern metadata. That round bound SHALL be the administrator-configured `max_read_rounds` setting (default 3, minimum 1, administrator maximum 5, immutable service ceiling 5), resolved as `min(admin_configured_value, ceiling)` and re-checked at enforcement.

The gateway's authorized-context round loop SHALL dispatch on the kind of authorized operation requested. A metadata request SHALL be routed to the metadata implementation and SHALL NOT be passed to the business-record read adapter, whose request contract does not accept metadata operations. A business read SHALL continue to be routed to the business-record read adapter unchanged. Where metadata authorization currently checks serialized size only, the resolved field-count bound SHALL also be enforced, so an over-ceiling projection cannot pass the control plane only to be rejected downstream.

The Frappe control plane and the inference service SHALL enforce coordinated limits: coordinated metadata field and byte ceilings, coordinated business-read row, field and byte ceilings, and a coordinated read-round ceiling, so the control plane never accepts a payload the inference contract rejects with HTTP 422. The inference-side metadata payload constants SHALL be separate from the business-read payload constants even where their current numerical values are equal, so the two contracts cannot be re-coupled by a shared edit.

#### Scenario: Authenticated question
- **WHEN** an authenticated Frappe user submits a valid question
- **THEN** Frappe forwards only its constructed chat envelope with server credential and returns the bounded response

#### Scenario: Guest or invalid session request
- **WHEN** a Guest/unauthenticated caller or a session request failing applicable CSRF validation invokes the method
- **THEN** Frappe refuses it without reaching inference

#### Scenario: Browser attempts envelope override
- **WHEN** a browser supplies user, site, execution scope, capability, mode, operation, target, history, authorization scope, or upstream destination overrides
- **THEN** Frappe refuses the unsupported fields and makes no upstream call

#### Scenario: Browser mode is refused rather than ignored
- **WHEN** a browser supplies a mode or capability field to the gateway method
- **THEN** Frappe refuses the request as an unsupported field and makes no upstream call

#### Scenario: Envelope carries no NexMate configuration
- **WHEN** the gateway envelope is constructed
- **THEN** it carries no metadata access mode, no configured DocType list, and no indicator of configuration authority

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

#### Scenario: Schema resolved by Frappe under capability and policy
- **WHEN** the turn requests DocType schema
- **THEN** Frappe resolves the minimized schema itself under the session user, the derived capability and the site's metadata access policy, and places it in the authorized-context field

#### Scenario: Schema request from a non-developer refused
- **WHEN** the turn requests DocType schema and the session user does not hold the developer capability
- **THEN** Frappe refuses the request, resolves no metadata, and returns no schema

#### Scenario: Schema request outside the metadata policy refused
- **WHEN** the turn requests DocType schema and the site's metadata access policy does not permit that DocType
- **THEN** Frappe refuses the request, resolves no metadata, and returns no schema

#### Scenario: Metadata never reaches the business-read adapter
- **WHEN** the round loop dispatches a metadata request
- **THEN** the request is handled by the metadata implementation and the business-record read adapter is never invoked for it

#### Scenario: Round budget is administrator-configured within its ceiling
- **WHEN** an authorized administrator configures `max_read_rounds` inside its supported range of 1 to 5
- **THEN** the next ask enforces that budget, the default of 3 applies while unconfigured, and a value reaching runtime above the ceiling of 5 is clamped to 5

#### Scenario: Field count is enforced alongside serialized size
- **WHEN** a permitted metadata projection exceeds the resolved effective field-count bound
- **THEN** it is refused in the control plane before any authorized context is produced, exactly as an oversized serialized payload is

#### Scenario: Coordinated limits never produce a contract rejection
- **WHEN** the control plane accepts a metadata or business-read payload under its resolved effective bounds
- **THEN** the inference contract accepts it as well, because both sides enforce the same ceilings and the effective limit can never exceed either side's ceiling

#### Scenario: Metadata and business-read constants stay separate
- **WHEN** the inference-side payload constants are inspected
- **THEN** the metadata field and byte constants are declared separately from the business-read row, field and byte constants, even where their numerical values are currently equal

### Requirement: Authoritative role-derived persona
Frappe SHALL derive capability from the authenticated user's actual roles against server-managed configuration naming real Frappe roles, default `[]`, and SHALL carry the derived value in the existing `mode` envelope field. Only an explicit matching role SHALL select the `developer` capability; otherwise select `employee`. The Frappe Role store SHALL remain the source of truth and NexMate SHALL NOT introduce a second role store or cache role membership. There SHALL be no implicit System Manager or Administrator elevation. Invalid mapping configuration or a role-lookup failure SHALL fail closed without elevation. No browser mapping-management endpoint SHALL be added. Capability SHALL NOT grant tool execution, document/corpus permission, ERPNext business-record authorization, ownership or cloud consent, and SHALL NOT grant authority to configure NexMate behaviour. Where the capability controls a NexMate feature such as DocType metadata, that control SHALL be enforced by Frappe and SHALL NOT be re-derived, second-guessed or widened by inference. A capability-gated feature that is additionally governed by an administrator-controlled policy SHALL evaluate the capability first and SHALL NOT let a Frappe permission bypass short-circuit the capability decision.

#### Scenario: Empty default includes administrators
- **WHEN** the mapping is empty and an authenticated user, including System Manager or Administrator, asks a question
- **THEN** the gateway supplies employee capability

#### Scenario: Explicit configured role match
- **WHEN** the authenticated user's roles match an explicitly configured developer role
- **THEN** the gateway supplies developer capability in the existing mode field, which enables capability-gated NexMate features but does not alter the authenticated execution scope, widen ERPNext business-record authorization, or confer configuration authority

#### Scenario: Browser mode ignored
- **WHEN** a user submits a browser-selected mode or capability
- **THEN** Frappe discards it and independently derives capability from the authenticated user's actual Frappe roles

#### Scenario: Invalid mapping
- **WHEN** the configured role mapping is malformed
- **THEN** the gateway fails closed without selecting developer capability

#### Scenario: Developer is not administrator
- **WHEN** a developer-capability user requests an ERPNext business record that Frappe denies that user
- **THEN** the read is refused exactly as for an employee-capability user

#### Scenario: Administrator bypass does not reach metadata
- **WHEN** the session user is one that the Frappe permission engine would allow unconditionally
- **THEN** capability is evaluated first and a user without a configured developer role is refused metadata regardless of that permission result

### Requirement: Validated identity and single-project site binding
Inference SHALL validate gateway context before history access, routing, retrieval or execution, not merely record it in telemetry. User and site SHALL be nonempty strings of at most 255 characters, without leading/trailing whitespace or control characters; Guest SHALL be refused. Capability SHALL be one of the supported values carried in the existing mode field. The execution scope SHALL be exactly the single generic authenticated value and SHALL be validated on both producer and consumer; any other value SHALL be refused rather than coerced. The scope value SHALL assert only that a credentialed, Frappe-attributed request may reach orchestration, and SHALL NOT itself assert or imply ERPNext access, metadata access, write access, code execution or tool execution. Site SHALL exactly match one trusted server-configured `NEXMATE_FRAPPE_SITE`; missing/invalid configuration or mismatch SHALL refuse gateway work. When a conversation is supplied, its identifier, owner, and site SHALL be validated against the envelope user and the trusted site before any supplied turn is used, and supplied turns SHALL be bounded. This fixed binding SHALL NOT implement tenant routing, repository selection, or site-isolated storage. Inference SHALL NOT persist per-conversation state; durable ownership lives in Frappe alone.

Any supplied gateway-envelope field (`user`, `site`, `execution_scope`, conversation identity/history) SHALL require a complete valid envelope and valid service credential; partial/invalid envelopes SHALL NOT fall back to legacy behavior. Unauthenticated development SHALL NOT establish gateway identity. Legacy requests without the envelope remain behind the service access rules without authenticated Frappe attribution, and SHALL NOT reach ERPNext business reads or capability-gated metadata. A request without a complete valid gateway envelope SHALL NOT be permitted to assert Frappe-derived authorization state: the presence of an authorized-context field, an authorization scope, or a conversation block without a complete valid envelope SHALL be refused rather than consumed unvalidated. Only validated gateway context MAY enter minimized attributed telemetry; raw invalid fields, secrets and transport headers SHALL NOT be logged or placed in prompts.

#### Scenario: Valid attributed request
- **WHEN** a service-authenticated gateway request has a valid user, a supported capability, the exact generic authenticated execution scope and exactly the configured site
- **THEN** inference accepts the bounded context and may record validated user/site metadata, without treating it as user-level data authorization

#### Scenario: Malformed or partial identity
- **WHEN** a gateway field is missing, incorrectly typed, blank, oversized, control-character-bearing, Guest or paired with an invalid scope/capability
- **THEN** inference refuses before history/routing/retrieval/execution with no legacy downgrade and no raw invalid-field logging

#### Scenario: Execution scope is exact
- **WHEN** the execution scope is any value other than the single generic authenticated value
- **THEN** the request is refused and is not coerced to a permitted value

#### Scenario: Wrong or unconfigured site
- **WHEN** the site differs from the trusted configured site or that configuration is missing/invalid
- **THEN** the gateway request is refused before work without selecting a different tenant, repository or store

#### Scenario: Development caller asserts gateway identity
- **WHEN** an unauthenticated development request supplies gateway-envelope fields
- **THEN** inference refuses gateway attribution and execution despite the general development exemption

#### Scenario: Forged conversation binding refused
- **WHEN** a supplied conversation names a different owner than the envelope user or a different site than the trusted site
- **THEN** inference refuses before any supplied turn is used, with no persistence side effect

#### Scenario: Partial envelope does not fall back
- **WHEN** a credentialed request supplies only some envelope fields
- **THEN** it is refused and does not degrade to legacy behavior

#### Scenario: Legacy unattributed request cannot reach ERPNext or metadata
- **WHEN** a credentialed legacy request without a gateway envelope asks for ERPNext business data or DocType metadata
- **THEN** the request is refused before any data or metadata is returned

#### Scenario: Unattributed request cannot assert authorization state
- **WHEN** a request without a complete valid gateway envelope supplies an authorized-context field, an authorization scope, or a conversation block
- **THEN** the request is refused and none of those fields is consumed, validated as if authenticated, or forwarded to the orchestrator

#### Scenario: No secrets in telemetry
- **WHEN** a valid gateway envelope is processed
- **THEN** only minimized attributed context reaches telemetry, with no raw invalid fields, secrets or transport headers

### Requirement: Deterministic backend chat-only execution guard
The `chat-only` execution scope SHALL be retired. The gateway SHALL instead carry a single generic authenticated execution scope that permits a credentialed, Frappe-attributed request to reach the inference and orchestration path, and that SHALL grant no capability by itself. Each NexMate operation SHALL be gated by its own explicit, deterministic, backend-code enforcement point applied BEFORE the operation executes, and no operation SHALL be reachable merely because the execution scope was accepted.

Business-record operations SHALL be gated by the Frappe-native authorization boundary in the control plane, which re-derives authorization from the live session user on every read. Capability-gated metadata operations SHALL be gated in the control plane by the user's derived capability and the site's administrator-controlled metadata access policy. Metadata authorization SHALL NOT be evaluated by inference, and inference SHALL NOT short-circuit a metadata request before the control plane evaluates it. Code reads, search, explain, file access, Git operations, business writes, proposals, apply, approval and session reset SHALL remain denied on the gateway path, and that denial SHALL be enforced in backend code regardless of capability, natural-language wording, troubleshooting, follow-ups, model-selected routes, fallbacks or slash syntax. Denial SHALL precede execution, not filter results afterward. UI restrictions or model instructions alone SHALL NOT satisfy this requirement. Incidental live ERPNext version lookups SHALL continue to be suppressed on the gateway path, and the response SHALL use unavailable-version semantics without fabricating installed versions.

Conversational replies and existing cited RAG SHALL remain chat behavior, without claiming ACL retrieval or granting new private-corpus permission. Capability replies SHALL describe only the operations actually available to the requester's capability, including distinguishing metadata inspection from business-record lookups so that a capability reply does not advertise an operation the requester will be refused. Legacy direct tool access remains governed separately and SHALL NOT become a gateway fallback.

#### Scenario: Natural-language code or business request
- **WHEN** a gateway question selects code/search/explain/file/Git, write, proposal, apply, approval or reset behavior, including in developer mode
- **THEN** deterministic backend enforcement returns unavailable-in-Desk behavior before any corresponding tool or client call

#### Scenario: Forced routes and fallbacks
- **WHEN** routing or mocked model output forces code, write, proposal, unauthorized-metadata, troubleshooting-to-code or a fallback/follow-up tool path
- **THEN** operation-specific enforcement refuses it regardless of wording or slash syntax, and the generic execution scope alone does not permit it

#### Scenario: Incidental version lookup
- **WHEN** gateway chat takes a RAG or other path normally fetching ERPNext versions
- **THEN** no live ERPNext call occurs and the response uses unavailable-version semantics without fabricated installed versions

#### Scenario: Explicit operation or approval
- **WHEN** a gateway request attempts search/explain/file/edit/business-write/reset/approval operation forwarding
- **THEN** it is refused with no tool endpoint proxy or execution path

#### Scenario: Authorized business read reaches the Frappe boundary
- **WHEN** a gateway turn requests an ERPNext business record read
- **THEN** the control plane authorizes and executes it under the live session user, and the result is minimized and audited

#### Scenario: Unauthorized business read refused
- **WHEN** a gateway turn requests a business record Frappe denies the session user
- **THEN** the read is refused before any field is returned, regardless of capability

#### Scenario: Capability-gated metadata reaches the control plane
- **WHEN** a developer-capability gateway turn requests DocType metadata
- **THEN** the control plane resolves the minimized metadata under the session user, the derived capability and the site's metadata access policy

#### Scenario: Metadata refused without developer capability
- **WHEN** a gateway turn requests DocType metadata and the session user lacks the developer capability
- **THEN** deterministic backend enforcement refuses before any metadata is resolved

#### Scenario: Metadata refused by policy
- **WHEN** a developer-capability gateway turn requests a DocType the site's metadata access policy does not permit
- **THEN** the control plane refuses before any metadata is resolved, for both the permissive and the restricted policy mode

#### Scenario: Inference performs no metadata authorization
- **WHEN** a turn requests DocType metadata
- **THEN** inference classifies and requests the metadata but performs no capability or policy decision, and the request reaches the control plane for authorization

#### Scenario: Execution scope is not a capability grant
- **WHEN** a request carries a valid generic authenticated execution scope
- **THEN** no ERPNext access, metadata access, write access, code execution or tool execution is thereby granted, and each remains separately gated
