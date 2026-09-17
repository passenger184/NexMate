# service-authentication Specification

## Purpose

Server-only shared-secret authentication with production-default access, a minimal public health exception and explicit standalone development opt-in. This is authentication groundwork, not end-user authorization or production readiness.

## Requirements

### Requirement: Service credential validation
Except for exact `/health` and the explicit missing-header development exemption below, inference SHALL require `X-NexMate-Key` matching its configured `NEXMATE_SERVICE_KEY` before endpoint work. It SHALL use constant-time byte comparison with a strong random secret represented as 64 hexadecimal characters (at least 32 random bytes). Blank, placeholder or malformed configured keys SHALL be invalid. Empty, malformed, duplicate or nonmatching supplied credentials SHALL be rejected, including in development.

#### Scenario: Valid credential
- **WHEN** a protected request supplies the valid configured credential
- **THEN** the credential gate passes and endpoint validation and existing safeguards still apply; no end-user permission is inferred

#### Scenario: Invalid supplied credential
- **WHEN** a protected request supplies an empty, malformed, duplicate or nonmatching credential in any environment
- **THEN** it is rejected before endpoint work, even when development unauthenticated access is enabled

### Requirement: Production-default fail-closed configuration
`NEXMATE_ENV` SHALL default to `production`. Unknown environment values SHALL NOT enable development exemption. In production/default/unknown environments, every protected request with a missing or invalid credential, or an unset/invalid configured key, SHALL fail closed regardless of the dev flag. Configuration errors SHALL produce safe diagnostics without secret values. Per-request refusal SHALL preserve minimal `/health` access.

#### Scenario: Unset key in production
- **WHEN** production/default configuration has no service key
- **THEN** protected requests are rejected regardless of supplied headers or dev flag, while `/health` remains minimally accessible

#### Scenario: Missing credential in production
- **WHEN** a production request lacks the header even with a valid configured key
- **THEN** it is rejected before endpoint work

#### Scenario: Unknown environment with opt-in
- **WHEN** `NEXMATE_ENV` has an unknown value and `NEXMATE_DEV_UNAUTHENTICATED=1`
- **THEN** no unauthenticated protected request is allowed and a safe configuration diagnostic is surfaced

### Requirement: Dual explicit development opt-in
Unauthenticated protected requests SHALL be allowed only when `NEXMATE_ENV=development` AND `NEXMATE_DEV_UNAUTHENTICATED=1` are explicitly set in server configuration, the credential header is absent, and the configured key is either valid or unset (not malformed). The flag SHALL default off; invalid flag values SHALL NOT enable it. No request, origin, Host, forwarded header, address or localhost heuristic SHALL activate the exemption. This is an implementation-level configuration choice, not a deployment topology selection.

#### Scenario: Local standalone workflow explicitly enabled
- **WHEN** both exact development settings are enabled, the key is valid or unset, and the request has no credential header
- **THEN** the standalone development request may pass the gate without a browser-held secret

#### Scenario: Only one setting enabled
- **WHEN** only development environment or only the unauthenticated flag is enabled
- **THEN** a missing-header protected request is rejected

#### Scenario: Invalid configuration is not bypassed
- **WHEN** both settings are enabled but the configured key is malformed
- **THEN** protected requests are rejected with a safe configuration diagnostic

#### Scenario: Supplied header with unset key
- **WHEN** both settings are enabled, no key is configured, and a request supplies a credential header
- **THEN** the protected request is rejected because no configured key can authenticate it

#### Scenario: Valid header during development
- **WHEN** a request supplies the valid configured key under development settings
- **THEN** authentication succeeds normally rather than being treated as unauthenticated

#### Scenario: Request heuristics cannot bypass
- **WHEN** unauthenticated requests use localhost addresses, allowed-looking origins, forwarded headers or body/query flags without both server settings
- **THEN** all protected requests remain rejected

### Requirement: Minimal unauthenticated health exception
Exact `/health` SHALL remain unauthenticated in every configuration, including with an unset/invalid key or supplied invalid header. It SHALL return only fixed minimal liveness status, such as `{"status":"ok"}`, without dependency probes, credentials, environment/configuration, business/user/site data or sensitive diagnostics. It SHALL NOT assert readiness of protected endpoints or providers. The exception SHALL NOT cover other paths by prefix.

#### Scenario: Health when key unset
- **WHEN** `/health` is requested without credentials while the service key is unset
- **THEN** it returns minimal liveness only, while protected endpoints remain governed by the credential/dev rules

#### Scenario: Health disclosure review
- **WHEN** health responses are inspected across production, development and configuration-error cases
- **THEN** they contain no sensitive fields or configuration-dependent diagnostics, and similar non-health paths are not exempt

### Requirement: Secret remains server-side and out of diagnostics
Frappe SHALL read `nexmate_service_key` from server-side site configuration and send it only to its configured inference destination in `X-NexMate-Key`. It SHALL NOT relay browser headers or follow upstream redirects with this credential. Both servers SHALL exclude secrets and transport headers from logs, telemetry, prompts, responses/errors, boot data, browser storage and bundles. They SHALL use safe event codes for failures, not raw request/response dumps. Missing/invalid Frappe key SHALL refuse gateway requests without using development bypass. Rotation SHALL update both server configurations without client distribution or fail-open fallback.

#### Scenario: Browser and telemetry disclosure checks
- **WHEN** boot, assets, client storage, normal/error responses, model inputs and captured application logs/telemetry are inspected with synthetic credential markers
- **THEN** no credential or transport-header material is disclosed

#### Scenario: Missing Frappe key or rotated-key mismatch
- **WHEN** Frappe lacks a valid key or its key differs from inference's key
- **THEN** chat fails safely without sending secrets to clients, retrying unauthenticated or falling back to direct browser inference

#### Scenario: Redirect or transport failure
- **WHEN** the configured inference request redirects or fails
- **THEN** Frappe does not forward the credential to a redirected destination and returns a sanitized bounded failure without transport headers

### Requirement: Mechanism remains the accepted U4 subset
Service authentication SHALL use the shared-secret header only; this change SHALL NOT introduce mTLS or request-signing infrastructure or claim resolution of remaining U4 tool/result/provider, version-negotiation or streaming/realtime contracts.

#### Scenario: Mechanism review
- **WHEN** the boundary implementation is reviewed
- **THEN** it uses the shared-secret check and retains remaining U4 questions without new topology or protocol infrastructure
