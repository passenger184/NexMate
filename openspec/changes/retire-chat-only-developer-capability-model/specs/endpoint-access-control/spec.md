## MODIFIED Requirements

### Requirement: Existing endpoint inventory retained
Existing direct routes SHALL remain present, except the retired session endpoints: legacy direct `/orchestrate` `session_id` continuity and the JSON-backed session reset path SHALL be removed. Every other inference route except exact `/health` SHALL pass the service-authentication gate, including `/ask`, `/orchestrate`, every remaining `/tools/*` route, preview assets, API documentation and unknown paths. There SHALL be no broad path-prefix or OPTIONS bypass. Production/default/unknown environment requests SHALL require a valid configured credential. Passing the gate SHALL NOT waive endpoint validation, confirmed-edit/write safeguards or confer end-user permissions.

The three legacy ERPNext read routes — `/tools/erpnext/schema`, `/tools/erpnext/document` and `/tools/erpnext/list` — SHALL be removed. They were deprecated and never conferred end-user authorization; removal is now sequenced because their replacement is the Frappe-native authorization boundary for business reads and the control-plane capability and policy gate for DocType metadata, and because retaining them preserved a route that returned a complete DocType document, including its `permissions` child table, to any service-credential holder with no user attribution. Requests to the removed paths SHALL be refused as unknown operations. The shared-credential read client SHALL be retained only for enumerated remaining consumers and SHALL NOT be reachable from any Frappe-attributed business-user path. No new ERPNext read endpoint, and no new credential consumer, SHALL be introduced.

A credentialed request that carries no gateway envelope SHALL retain its legacy non-ERPNext behavior, but SHALL NOT reach ERPNext business-data reads or DocType metadata by any route, because those operations require an authenticated Frappe session and are authorized only in the control plane. Such a request SHALL NOT be permitted to assert Frappe-derived authorization state: it SHALL be refused if it supplies an authorized-context field, an authorization scope, or a conversation block, and none of those fields SHALL be consumed or forwarded.

#### Scenario: Direct legacy requests lack credentials
- **WHEN** unauthenticated production requests target `/ask`, `/orchestrate`, any remaining `/tools/*` route, assets or documentation
- **THEN** they are refused before endpoint work

#### Scenario: Authenticated direct tools retained
- **WHEN** a trusted server caller uses a valid credential on an existing direct tool endpoint
- **THEN** its existing validation and confirmation/flag safeguards still apply without new end-user authorization

#### Scenario: Path or method does not evade gate
- **WHEN** a protected request uses OPTIONS, an unknown path or a path merely beginning with `/health`
- **THEN** it does not receive the exact health authentication exception

#### Scenario: Route inventory comparison
- **WHEN** inference routes are compared before and after implementation
- **THEN** every previously existing route remains present behind its specified access rules, except the explicitly retired session-continuity, session-reset and legacy ERPNext read paths

#### Scenario: Legacy and gateway separation
- **WHEN** a valid direct legacy request has no gateway envelope
- **THEN** its legacy non-ERPNext behavior remains available under service access rules without authenticated user attribution, while a partial or malformed gateway envelope is refused and legacy `session_id` values confer no continuity

#### Scenario: Retired session paths stay gone
- **WHEN** a caller targets legacy `session_id` continuity or the removed session-reset path
- **THEN** the request is refused explicitly as an unknown/removed operation; no JSON session is created, read, or deleted and no continuity is silently provided

#### Scenario: Legacy ERPNext read routes retained but deprecated
- **WHEN** the route inventory is compared after this change
- **THEN** the three legacy ERPNext read routes are absent and requests to them are refused as unknown operations. The scenario name is retained verbatim because a modified requirement replaces the whole block and archiving refuses to drop an existing scenario name; the outcome it originally asserted, retention, no longer holds

#### Scenario: Legacy read routes confer no user authorization
- **WHEN** a caller reaches one of the removed legacy ERPNext read paths with a valid service credential
- **THEN** the call is refused as an unknown operation and confers no end-user authorization, exactly as it never did while retained

#### Scenario: Unattributed request cannot obtain DocType metadata
- **WHEN** a credentialed request with no gateway envelope requests a DocType's schema, fields or permissions
- **THEN** it is refused before any metadata is retrieved, and no DocType document is returned

#### Scenario: Unattributed request cannot assert authorization state
- **WHEN** a credentialed request with no gateway envelope supplies an authorized-context field, an authorization scope, or a conversation block
- **THEN** the request is refused and none of those fields is consumed, forwarded, or treated as Frappe-derived authorization

#### Scenario: User read path does not use legacy ERPNext read routes
- **WHEN** an authenticated Desk user triggers an ERPNext business read
- **THEN** the read is served by the Frappe-native authorization boundary and not by the legacy routes or the shared-credential read client

#### Scenario: Underlying client retained for enumerated consumers
- **WHEN** the shared-credential read client is still required by an enumerated remaining consumer
- **THEN** it is retained rather than deleted, and no Frappe-attributed business-user path remains connected to it

### Requirement: Desk cannot reach preserved direct paths
Desk SHALL send chat through authenticated Frappe only. It SHALL NOT call legacy/direct inference endpoints for approval/rejection, read/search/explain/file/code/business operations or error fallback. Desk reset and transcript restore SHALL go only to the Frappe-owned conversation methods, never to direct inference paths. Gateway scope SHALL also be enforced deterministically before natural-language orchestrator dispatch and incidental ERPNext version calls, not only in frontend handlers. ERPNext business reads and capability-gated DocType metadata SHALL be authorized only in the Frappe control plane, so a direct or unattributed request to inference cannot obtain either. Local start-fresh with no owned conversation SHALL make no deletion/ownership claim. Desk SHALL NOT receive the administrator-controlled metadata access policy, its mode, its configured DocTypes, or any indication of configuration authority through boot information or client-side configuration; the control plane determines all of these server-side.

#### Scenario: Desk actions and failure paths
- **WHEN** chat, tool slash commands, stale approval cards, or gateway failure are exercised in Desk
- **THEN** no direct browser-to-inference requests occur and unavailable operations do not execute

#### Scenario: Owned reset travels through Frappe
- **WHEN** a Desk user starts fresh on an owned conversation
- **THEN** the request goes to the Frappe-owned reset method only, deleting the owned thread server-side

#### Scenario: Natural language cannot reuse legacy tools
- **WHEN** Desk chat routes to code, write, proposal or metadata behavior through natural language, follow-ups or degraded routing
- **THEN** deterministic backend enforcement refuses before tool/client execution for unauthorized operations, and metadata is resolved only in the control plane for a developer-capability user whose site's metadata policy permits the DocType, instead of relying on hidden slash commands

#### Scenario: Metadata policy is not exposed to the browser
- **WHEN** Desk boot information is produced
- **THEN** it contains no metadata access mode, no configured DocType list, and no indication of who may change the policy

### Requirement: Rollback preserves protection
Rollback SHALL retain inference authentication and the operation-specific backend enforcement gates, or disable the affected Desk feature. It SHALL NOT restore an unauthenticated inference deployment, restore the removed legacy ERPNext read routes, reintroduce the retired `chat-only` execution scope as an authorization mechanism, restore a permissive or absent metadata access policy in place of a deliberately narrowed one, distribute a server secret to browsers or use development bypass in production.

Rollback that returns to a revision predating this change restores the removed routes and the unattributed metadata path, and those restorations are security regressions rather than missing features; they SHALL require an explicit compensating control rather than a silent revert. A rollback SHALL also not be read as restoring a metadata access policy: because an absent or invalid policy denies metadata access, a revision predating this change has no policy at all and must be assessed for what it permits rather than assumed to be restrictive.

#### Scenario: Gateway or bundle rollback
- **WHEN** an operator reverts the gateway or Desk deployment
- **THEN** protected inference routes remain gated, no direct-browser fallback is introduced, and unavailable Desk chat fails safely

#### Scenario: Rollback does not reopen unattributed ERPNext access
- **WHEN** a deployment is rolled back to a revision predating this change
- **THEN** the removal of the legacy ERPNext read routes and of unattributed metadata access is not silently reversed as part of a Desk rollback, or the rollback is accompanied by an explicit compensating control

### Requirement: Frappe-authorized tool execution on every entry point
Every tool execution path, including replacements for legacy/direct `/tools/*` endpoints, SHALL require Frappe-derived identity/site/permission and durable proposal approval before execution, never client-supplied mode, LLM classification, or post-execution filtering. The gateway envelope SHALL be validated like chat envelopes, and execution SHALL recheck authorization immediately before acting. Use of a durable proposal on an unauthorized site or by a non-owner SHALL be refused before retrieval or execution.

Side-effecting operations are the subject of this requirement. Authorized ERPNext business reads and capability-gated DocType metadata are not tool execution: they SHALL be served by the Frappe control plane under the live session user, SHALL NOT require, create or execute a durable proposal, and SHALL NOT share the write approval lifecycle. Their authorization SHALL still be re-derived from Frappe on every request rather than carried in a proposal or asserted by inference. For metadata, the re-derived authorization SHALL include the site's administrator-controlled metadata access policy, which SHALL NOT grant, widen or substitute for ERPNext business-record authorization.

#### Scenario: Unauthorized tool path refused before execution
- **WHEN** a caller presents a durable proposal owned by another user or bound to another site
- **THEN** Frappe refuses before any tool invocation, with no state change and with the denial audited

#### Scenario: Legacy direct tool replacement requires durable approval
- **WHEN** a legacy direct `/tools/*` call is replayed without a Frappe persistent proposal and explicit approval
- **THEN** it is refused before execution, even with a valid service credential, and the caller is directed to the Frappe durable flow

#### Scenario: Reads and metadata are not tool execution
- **WHEN** an authorized ERPNext business read or a permitted developer-capability metadata request is performed
- **THEN** it proceeds without a durable proposal and creates no proposal or execution record, while still being authorized against the live session user and, for metadata, the site's metadata access policy
