# Proposal: authenticated-frappe-control-plane

## Why

Desk currently calls unauthenticated FastAPI directly, with caller-selected mode and session identifiers. ARCHITECTURE.md R04/R13 requires authenticated Frappe control and private inference. This bounded change establishes authentication groundwork and a deterministic chat-only boundary, not full G2/M2 acceptance or production readiness.

## Approval and present scope

The user's 2026-09-17 instruction approves subsequent implementation once these plans are internally consistent and strictly validated. This pass is PLANNING ONLY: existing change artifacts, an appended DECISIONS.md entry and a minimal ROADMAP.md update. No implementation, runtime/config/test/progress changes, model/network activity, deployment or task completion is claimed. Standing SECURITY.md restrictions remain in force.

## What Changes

- Add one authenticated Frappe whitelisted chat method forwarding only a constructed chat request to `/orchestrate`. Frappe supplies its authenticated user, current site and fixed `chat-only` scope; browser fields cannot override them or choose an upstream URL/path.
- Derive persona from the authoritative Frappe user's roles using server-side `nexmate_developer_roles`, default `[]`. No implicit System Manager or Administrator privilege. Browser `mode` is ignored. Persona does not grant tool access, document permissions or ownership.
- Authenticate inference requests with the server-only shared secret `X-NexMate-Key`: inference environment `NEXMATE_SERVICE_KEY`, Frappe site configuration `nexmate_service_key`. Use a strong random secret, constant-time comparison and no secret or transport-header logging/disclosure.
- Default to production. Missing/invalid credentials or an unconfigured key fail closed on protected routes. The only public exception is minimal `/health`, including when the key is unset. Standalone unauthenticated development requires BOTH `NEXMATE_ENV=development` and `NEXMATE_DEV_UNAUTHENTICATED=1` (default off); no request/origin/localhost heuristic bypass. These are implementation-level configuration choices, not a deployment topology decision.
- Validate the gateway identity/site envelope before work, including exact matching to one trusted server-configured Frappe site. Validated identity can inform minimized telemetry; telemetry is not validation or per-user authorization. No shared-workspace routing, session ownership or site-isolated index is introduced.
- Enforce chat-only scope deterministically in the backend BEFORE any code/file/read/search/explain or ERPNext execution, including natural-language orchestrator dispatch, troubleshooting, fallbacks and incidental live version lookups. No edit/business proposals, approval, reset or tool forwarding through the gateway. Disabling slash commands or prompting the model alone is insufficient.
- Preserve `session_id` forwarding temporarily for legacy continuity only, never authentication, authorization, user ownership or site isolation. Keep the JSON store unchanged. Immediately after this boundary is verified, require the separately approved `frappe-owned-conversation-state` change for Frappe records, user/site binding, persistence, replacement of caller-controlled ownership and JSON storage, and migration/compatibility.
- Desk makes no direct inference calls, including reset and approval handlers; unavailable actions stay disabled/refused without fallback. The standalone preview remains a separate explicit development workflow and receives no secret.
- Preserve existing direct endpoints, including legacy `/ask`, `/orchestrate`, `/tools/*` and preview assets, behind the credential or explicit dual development opt-in. Existing tool safeguards still apply; a key is not end-user authorization.
- No mTLS or signing. Remaining U4 contracts and other HLD decisions stay unresolved; append provenance without rewriting historical ADRs.

## Capabilities

### New Capabilities
- `service-authentication`: shared-secret validation, production-default configuration, dual development opt-in, minimal health exception and server-only secret handling.
- `frappe-api-gateway`: authenticated chat-only entry, role-derived persona, validated user/site context, deterministic tool denial and transitional sessions.
- `endpoint-access-control`: protected legacy endpoints, no direct Desk calls, public health exception and no implicit bypass.

### Modified Capabilities

None; these delta specs introduce the bounded requirements.

## Impact

Future implementation affects the Frappe API/boot plumbing, inference middleware/config/request schema, orchestrator execution guards, Desk bundle, tests and development documentation. The inference address and credential come from server configuration, not browser requests. Boot/client code never receives the credential and Desk no longer depends on a public inference address.

Existing chat retrieval behavior is not converted into ACL-aware retrieval by this change; source tags/persona are not permissions. The existing JSON history and company retrieval limitations remain explicit blockers to multi-user/production claims. No new corpus grants or private-data cloud consent are provided. No state/index migration, durable approval, authorized page context, site-isolated search, Docker certification, MCP, Workbench or streaming work is included.
