# endpoint-access-control Specification

## Purpose

Credential-gated inference endpoints, a minimal public health exception, explicit dual-opt-in development and no direct Desk access. Retired session endpoints stay removed; endpoint retention does not authorize end users or complete G2/M2.

## Requirements

### Requirement: Protected direct endpoints
Every inference route except exact `/health` SHALL pass the service-authentication gate, including `/ask`, `/orchestrate`, every `/tools/*` route, preview assets, API documentation and unknown paths. There SHALL be no broad path-prefix or OPTIONS bypass. Production/default/unknown environment requests SHALL require a valid configured credential. Passing the gate SHALL NOT waive endpoint validation, confirmed-edit/write safeguards or confer end-user permissions.

#### Scenario: Direct legacy requests lack credentials
- **WHEN** unauthenticated production requests target `/ask`, `/orchestrate`, any `/tools/*` route, assets or documentation
- **THEN** they are refused before endpoint work

#### Scenario: Authenticated direct tools retained
- **WHEN** a trusted server caller uses a valid credential on an existing direct tool endpoint
- **THEN** its existing validation and confirmation/flag safeguards still apply without new end-user authorization

#### Scenario: Path or method does not evade gate
- **WHEN** a protected request uses OPTIONS, an unknown path or a path merely beginning with `/health`
- **THEN** it does not receive the exact health authentication exception

### Requirement: Existing endpoint inventory retained
Existing direct routes SHALL remain present, except the retired session endpoints: legacy direct `/orchestrate` `session_id` continuity and the JSON-backed session reset path SHALL be removed. Every other inference route except exact `/health` SHALL pass the service-authentication gate, including `/ask`, `/orchestrate`, every remaining `/tools/*` route, preview assets, API documentation and unknown paths. There SHALL be no broad path-prefix or OPTIONS bypass. Production/default/unknown environment requests SHALL require a valid configured credential. Passing the gate SHALL NOT waive endpoint validation, confirmed-edit/write safeguards or confer end-user permissions.

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
- **THEN** every previously existing route remains present behind its specified access rules, except the explicitly retired session-continuity and session-reset paths

#### Scenario: Legacy and gateway separation
- **WHEN** a valid direct legacy request has no gateway envelope
- **THEN** legacy behavior remains available under service access rules without authenticated user attribution, while a partial or malformed gateway envelope is refused; legacy `session_id` values confer no continuity

#### Scenario: Retired session paths stay gone
- **WHEN** a caller targets legacy `session_id` continuity or the removed session-reset path
- **THEN** the request is refused explicitly as an unknown/removed operation; no JSON session is created, read, or deleted and no continuity is silently provided

### Requirement: Minimal public health is the sole default exception
Exact `/health` SHALL be unauthenticated in every environment and even with no configured key, returning only fixed minimal liveness status. It SHALL expose no secrets, headers, environment/configuration, business/user/site information, dependency probes or sensitive diagnostics and SHALL NOT certify readiness.

#### Scenario: Default configuration
- **WHEN** all authentication settings are unset
- **THEN** `/health` returns minimal liveness and every protected request fails closed

#### Scenario: Health response invariance
- **WHEN** health is queried with invalid credentials or broken authentication configuration
- **THEN** it remains minimally accessible without disclosing those conditions or exempting other routes

### Requirement: Development access is configuration-only
A missing-header protected request SHALL be allowed unauthenticated only with BOTH exact `NEXMATE_ENV=development` and `NEXMATE_DEV_UNAUTHENTICATED=1`, and a valid or unset configured key. Malformed configured keys or invalid supplied credentials SHALL still fail closed. The environment SHALL default production and the flag off. Request/origin/Host/forwarded/local-address heuristics SHALL NOT bypass authentication. Standalone development SHALL NOT make a gateway identity assertion valid without a service credential.

#### Scenario: Dual opt-in permits standalone preview
- **WHEN** both development settings are enabled, key configuration is valid or unset and a standalone request has no credential
- **THEN** the protected development workflow may proceed under existing endpoint safeguards without providing a key to the browser

#### Scenario: One flag or invalid credential
- **WHEN** only one development setting is enabled, configuration is malformed, or a supplied credential is invalid
- **THEN** the protected request is refused as specified by the service-authentication truth table

#### Scenario: Localhost cannot imply permission
- **WHEN** a request appears local or supplies trusted-looking origin/forwarded headers without the required server configuration
- **THEN** it remains credential-gated

### Requirement: Desk cannot reach preserved direct paths
Desk SHALL send chat through authenticated Frappe only. It SHALL NOT call legacy/direct inference endpoints for approval/rejection, read/search/explain/file/code/business operations or error fallback. Desk reset and transcript restore SHALL go only to the Frappe-owned conversation methods, never to direct inference paths. Gateway scope SHALL also be enforced deterministically before natural-language orchestrator tool dispatch and incidental ERPNext version calls, not only in frontend handlers. Local start-fresh with no owned conversation SHALL make no deletion/ownership claim.

#### Scenario: Desk actions and failure paths
- **WHEN** chat, tool slash commands, stale approval cards, or gateway failure are exercised in Desk
- **THEN** no direct browser-to-inference requests occur and unavailable operations do not execute

#### Scenario: Owned reset travels through Frappe
- **WHEN** a Desk user starts fresh on an owned conversation
- **THEN** the request goes to the Frappe-owned reset method only, deleting the owned thread server-side

#### Scenario: Natural language cannot reuse legacy tools
- **WHEN** Desk chat routes to code or ERPNext tools through natural language, follow-ups or degraded routing
- **THEN** backend chat-only enforcement refuses before tool/client execution instead of relying on hidden slash commands

### Requirement: Rollback preserves protection
Rollback SHALL retain inference authentication and chat-only guard enforcement or disable the affected Desk feature. It SHALL NOT restore an unauthenticated inference deployment, distribute a server secret to browsers or use development bypass in production.

#### Scenario: Gateway or bundle rollback
- **WHEN** an operator reverts the gateway or Desk deployment
- **THEN** protected inference routes remain gated, no direct-browser fallback is introduced, and unavailable Desk chat fails safely
