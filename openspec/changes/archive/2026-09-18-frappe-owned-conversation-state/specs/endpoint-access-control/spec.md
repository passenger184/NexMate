## MODIFIED Requirements

### Requirement: Existing endpoint inventory retained
Existing direct routes SHALL remain present, except the retired session endpoints: legacy direct `/orchestrate` `session_id` continuity and the JSON-backed session reset path SHALL be removed. Every other inference route except exact `/health` SHALL pass the service-authentication gate, including `/ask`, `/orchestrate`, every remaining `/tools/*` route, preview assets, API documentation and unknown paths. There SHALL be no broad path-prefix or OPTIONS bypass. Production/default/unknown environment requests SHALL require a valid configured credential. Passing the gate SHALL NOT waive endpoint validation, confirmed-edit/write safeguards or confer end-user permissions.

#### Scenario: Direct legacy requests lack credentials
- **WHEN** unauthenticated production requests target `/ask`, `/orchestrate`, any `/tools/*` route, assets or documentation
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
