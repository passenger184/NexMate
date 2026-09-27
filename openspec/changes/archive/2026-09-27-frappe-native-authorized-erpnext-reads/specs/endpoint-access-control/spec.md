## MODIFIED Requirements

### Requirement: Existing endpoint inventory retained
Existing direct routes SHALL remain present, except the retired session endpoints: legacy direct `/orchestrate` `session_id` continuity and the JSON-backed session reset path SHALL be removed. Every other inference route except exact `/health` SHALL pass the service-authentication gate, including `/ask`, `/orchestrate`, every remaining `/tools/*` route, preview assets, API documentation and unknown paths. There SHALL be no broad path-prefix or OPTIONS bypass. Production/default/unknown environment requests SHALL require a valid configured credential. Passing the gate SHALL NOT waive endpoint validation, confirmed-edit/write safeguards or confer end-user permissions.

The three legacy ERPNext read routes — `/tools/erpnext/schema`, `/tools/erpnext/document` and `/tools/erpnext/list` — SHALL be retained in the route inventory and SHALL continue to pass the service-authentication gate, but SHALL be designated deprecated/quarantined for authenticated user business-data reads. They SHALL NOT be removed by this change, and the underlying read client SHALL be retained while any enumerated temporary legacy or system consumer still depends on it. The authenticated user business-read path SHALL NOT be served by these routes and SHALL NOT call the shared-credential read client. Their remaining access policy SHALL be explicit: they remain service-authenticated, are not a target architecture for authenticated Desk business reads, confer no end-user permission, and SHALL NOT be represented as a user-authorized interface. Deprecation SHALL be recorded so their removal can be sequenced separately after dependency proof. No new ERPNext read endpoint, and no new credential consumer, SHALL be introduced.

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

#### Scenario: Legacy ERPNext read routes retained but deprecated
- **WHEN** the route inventory is compared after this change
- **THEN** the three legacy ERPNext read routes are still present, still service-authenticated, and recorded as deprecated/quarantined rather than removed

#### Scenario: User read path does not use legacy ERPNext read routes
- **WHEN** an authenticated Desk user triggers an ERPNext business read
- **THEN** the read is served by the Frappe-native authorization boundary and not by the legacy routes or the shared-credential read client

#### Scenario: Legacy read routes confer no user authorization
- **WHEN** a caller reaches a deprecated legacy ERPNext read route with a valid service credential
- **THEN** the call is treated as service access without authenticated user attribution and is not presented as a user-authorized read

#### Scenario: Underlying client retained for enumerated consumers
- **WHEN** the legacy read client is still required by a temporary legacy or system consumer
- **THEN** it is retained rather than deleted, and the user read path remains disconnected from it
