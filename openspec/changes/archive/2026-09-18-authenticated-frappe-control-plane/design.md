# Design: authenticated-frappe-control-plane

## Context and approval

ARCHITECTURE.md is the canonical HLD; SECURITY.md remains standing policy. Current Desk calls FastAPI directly and current orchestration can execute code and shared-account ERPNext reads. A forwarding proxy or hidden slash buttons alone would still expose those operations.

The user's 2026-09-17 instruction resolves the four previously pending choices and approves implementation after internal planning consistency and strict validation. This invocation only revises planning files and appends provenance; implementation tasks remain unchecked. This is authentication groundwork plus a chat-only execution boundary, NOT complete G2/M2, authenticated conversation ownership, ACL retrieval or production readiness.

## Goals / Non-Goals

Goals: authenticated Frappe chat entry, authoritative role-derived persona, server credential validation, validated single-project user/site envelope, deterministic backend tool denial, retained transitional session forwarding and no direct Desk-to-inference traffic.

Non-goals: new tenancy/executor topology, per-user corpus ACLs, index isolation, conversation migration, durable approvals, tool authorization through Frappe, page context, streaming/realtime, MCP, Workbench, Docker certification, mTLS or signing. Existing persona/corpus behavior is not an ACL; this change grants no new private-corpus permission or cloud consent. Legacy shared JSON histories remain unsafe to treat as multi-user owned state.

## Decisions

### D0 — Four user-decided points (2026-09-17)

1. `nexmate_developer_roles` is a server-managed site-config list of role names, default `[]`. Only explicit membership selects developer persona; no broad System Manager default or special Administrator elevation. Authenticated Frappe identity decides mode, not browser data.
2. Preserve optional `session_id` forwarding for temporary continuity only, never authentication, authorization, ownership or site isolation. Do not redesign JSON storage here. Immediately after this boundary is verified, the separately approved `frappe-owned-conversation-state` change must address Frappe records, authenticated user ownership, site association, persistent state, removal of caller-controlled ownership, replacement of JSON storage and migration/compatibility strategy.
3. Gateway scope is chat-only: NO read/search/explain/file/code-edit/business-data tools, proposals, approvals or session reset. This includes natural-language orchestrator dispatch, not just explicit tool endpoints or slash commands.
4. `/health` remains unauthenticated minimal status in every configuration, even with no key. It is liveness only, not readiness, and exposes no sensitive diagnostics.

### D1 — Server-only shared credential (accepted U4 subset)

Frappe reads `nexmate_service_key` from server-side `site_config.json`; inference reads `NEXMATE_SERVICE_KEY` from environment configuration. Frappe sends it only in `X-NexMate-Key` to its fixed, operator-configured private inference address. Do not forward browser headers, cookies, Authorization, arbitrary paths, URLs or request objects. Do not follow upstream redirects carrying the credential. Keep protected transport/private-network deployment requirements; this selects no topology or new certificate infrastructure.

Provision a cryptographically random secret with at least 32 bytes of randomness (for example, 64 hexadecimal characters); document strength requirements and reject blank/placeholder/malformed values. Planned representation is 64 hexadecimal characters; both servers validate configuration and compare supplied credentials using constant-time byte comparison. Never create or print real keys during planning. Rotation updates both servers in a controlled window and fails closed on mismatch, without a second fallback key or browser distribution.

No keys, transport headers or raw request/response objects enter logs, telemetry, prompts, boot data, browser storage, bundles or errors. Authentication/config failures use safe event codes, not values. Missing Frappe credential is always a gateway error: it does not use inference's development bypass. mTLS and signing are excluded from this increment, not rejected for all future work.

### D2 — Production-default configuration and exact access truth table

Implementation-level configuration design (not a new approved topology):

- `NEXMATE_ENV` defaults to `production`. Only exact `development` enables consideration of a development exemption. Unknown/invalid values never enable it and produce a safe configuration diagnostic.
- `NEXMATE_DEV_UNAUTHENTICATED` defaults off. Only an explicit value `1` enables it, and only with `NEXMATE_ENV=development`.
- No request header, query/body field, browser origin, Host, forwarded header, client address or localhost test can enable exemption. Local binding remains a separate SECURITY.md constraint.

Apply the health exception FIRST, then the following protected-route rules:

| Environment / opt-in | Configured key | Presented header | Result |
|---|---|---|---|
| Any | Any, including unset/invalid | Any | Exact `/health` returns only minimal liveness status; no dependency/config diagnostics. |
| Any | Valid strong key | Valid matching key | Pass credential gate; endpoint validation and safeguards still apply. |
| Any | Any | Present but empty, malformed, duplicate or nonmatching | Reject protected request; development never tolerates an invalid supplied credential. |
| Production/default/unknown, regardless of dev flag | Valid key | Missing | Reject protected request. |
| Production/default/unknown, regardless of dev flag | Unset/invalid key | Missing or supplied | Reject protected request; safe configuration diagnostic. |
| Development, flag off/invalid | Any | Missing | Reject protected request. |
| Development, flag `1` | Valid or unset key | Missing | Allow standalone unauthenticated development request explicitly. |
| Development, flag `1` | Invalid configured key | Missing | Reject protected request and surface safe configuration error. |
| Development, any flag | Unset/invalid key | Supplied | Reject protected request; nothing can authenticate against an absent/invalid key. |

An unset key is tolerated ONLY for missing-header requests under both explicit development settings; it is never a production fallback. Failures are per-request and do not disable the minimal health route. `/health` returns a fixed status object such as `{"status":"ok"}`, not an empty body and not a claim that protected endpoints or dependencies are ready. All other routes/assets/docs/unknown paths remain behind the gate; no general prefix or OPTIONS exemption is introduced.

### D3 — Constructed gateway envelope and authoritative persona

`frappe_app/erpnext_ai_copilot/api.py` will expose `ask()` with `@frappe.whitelist()` (no guest access), using normal Frappe authentication and CSRF handling for session requests. It accepts bounded question and optional legacy session ID, ignores browser mode, and refuses extra operation/target/scope/user/site override fields rather than forwarding an arbitrary payload. Upstream failures return bounded sanitized errors without transport headers.

Frappe constructs `user` from `frappe.session.user`, `site` from its authoritative current site, `mode` from the user's actual roles, and `execution_scope="chat-only"`. `nexmate_developer_roles` defaults to an empty list. Invalid configuration fails closed without elevation; only trusted server operators change site configuration, with no browser mapping-management endpoint. Unmapped users, including System Manager or Administrator unless explicitly role-mapped, receive `employee`. Persona describes chat behavior, never tool permission or corpus ownership.

Inference accepts a gateway envelope only with valid service authentication (never dev bypass). For `/orchestrate`, any supplied gateway-envelope field (`user`, `site`, `execution_scope`) requires the complete valid envelope; malformed/partial envelopes cannot fall back to legacy behavior. Legacy direct requests without envelope remain available behind D2, with caller-mode behavior explicitly legacy and not authenticated end-user privilege.

### D4 — Identity/site validation is distinct from telemetry

Validate before history access, routing, retrieval or execution: gateway `user` and `site` must be nonempty strings, at most 255 characters, no leading/trailing whitespace or control characters; reject `Guest`. Validate mode against the two supported persona values and require scope exactly `chat-only`. Preserve canonical identifiers, do not repair malformed identity or derive it from an email/URL heuristic.

Inference compares `site` exactly against one required trusted server environment setting, proposed `NEXMATE_FRAPPE_SITE`, supplied by the operator to match the actual Frappe site identifier. Missing/invalid expected site or mismatch refuses gateway requests before work. This is a fixed single-project binding, not a request-selected root, tenant lookup table, public-index sharing decision or physical per-site deployment. It supplies neither session ownership nor site-isolated storage.

Only validated gateway metadata may be recorded as attributed user/site telemetry; legacy requests are not labeled as authenticated Frappe users. Log safe validation reason codes without echoing malformed fields or headers. Identity shape validation and binding authenticate the service assertion; they are NOT Frappe document permission checks, conversation ownership or corpus ACLs. No user/site envelope or transport metadata is included in model prompts merely for telemetry.

### D5 — Deterministic backend chat-only guard

A valid gateway envelope produces immutable request-local chat-only execution context. Frappe never accepts client-selected scope; inference never lets model output, follow-up condensation, persona or fallback change it. Before any tool invocation, backend code enforces an empty allowed-tool set for this context. Deny every code/read/search/explain/file action, schema/document/list business read, Git/business proposal/apply and reset, irrespective of route labels or developer persona.

At orchestrator dispatch, `code` and `erpnext` selections produce a bounded unavailable-in-Desk response BEFORE entering their handlers. Troubleshooting that resolves to code, natural-language requests such as listing invoices, follow-ups and degraded routing receive the same enforcement. Also guard incidental helpers: no live ERPNext version lookup on RAG or other chat paths; return existing unavailable version semantics without an upstream call. Guard before calls, not by dropping results afterward. Tests must force all such routes and assert zero tool/client invocations, including version lookup and proposal paths. A model-only policy or slash-command blacklist cannot satisfy this requirement.

Conversational responses and existing cited RAG remain chat operations; cached knowledge retrieval is distinct from live project file-search tools. Existing source-type/persona filtering is not upgraded into ACL retrieval. Capability help must describe only available chat behavior, not advertise executable tools. No general tool registry or new authorized tool interface is introduced. Legacy direct server/dev calls retain existing tool behavior and standing safeguards; they never become accessible as a Desk fallback.

### D6 — Desk and endpoint/action matrix

| Action / surface | Planned behavior |
|---|---|
| Desk chat | Authenticated Frappe `ask()` only, fixed gateway envelope and backend chat-only scope. |
| Desk mode selector | Cannot select authoritative mode; remove/disable misleading override behavior. |
| Desk read/search/explain/edit/business slash commands or cards | Unavailable/refused; no direct calls and no forwarding path through chat. |
| Desk reset/start-fresh | Local transcript clear and fresh local session identifier only; no server reset request or deletion claim. Old JSON history persists pending follow-up migration. |
| Desk approve/reject handlers, including stale cards | No FastAPI requests or execution; disabled/unavailable, without a false server-side approval/rejection claim. |
| Desk gateway failure | Display sanitized unavailable/error state; NEVER fall back to FastAPI. |
| Standalone `/ui` preview | Separate explicit dual-opt-in development workflow; no credential injected into browser. It cannot change Desk access or enable the service exemption through a request. |
| Existing direct `/ask`, `/orchestrate`, all `/tools/*` | Preserved behind D2; no new end-user authorization implied. |
| `/health` | Public minimal liveness even with key unset; no sensitive configuration/dependency/user/site diagnostics. |

The existing JSON store and session validation remain unchanged; a supplied valid `session_id` is forwarded, not converted into owner identity. No multi-user session safety or permission reauthorization is claimed. A fresh local ID is not access control and old records are not migrated/deleted here.

### D7 — Rollout and rollback preserve the boundary

Future rollout: provision matching server credentials and fixed expected site, deploy the protected inference service and guard, deploy Frappe API and updated Desk assets, then verify the bounded boundary with synthetic/local evidence. No deployment is performed by this planning pass. No data/index migration or cloud transmission is authorized by plan validation.

Rollback may disable Desk chat or revert its UI/API while retaining the service authentication and execution guard. Never roll inference back to an unauthenticated implementation, expose a key in the browser or enable development bypass as a production recovery mechanism. Controlled standalone local development remains separate. Coordinated key mismatch surfaces a sanitized failure, not direct-browser fallback.

## Risks and evidence boundaries

- Shared-secret possession authenticates a trusted server, not a human permission grant; header secrecy and controlled configuration remain essential.
- Dual configuration reduces accidental development exposure but cannot prove an environment is non-production; never infer that from traffic. A valid credential does not waive existing write/confirmation/locality safeguards.
- Caller-controlled JSON session IDs and non-ACL retrieval remain known limitations. Do not deploy this increment as multi-user/production-ready chat or reinterpret role mapping as private-data consent.
- Future verification must distinguish unit/mock and stub-DOM evidence from real Bench/Desk acceptance. It must include invalid/missing identity/site, all D2 rows, natural-language tool denial, zero incidental ERP calls, secret-safe failures and every Desk network action.

## Remaining questions and next gate

The four user-choice blockers are resolved. No substantive choice within this bounded plan remains pending; if implementation reveals one, stop and ask. The exact configuration names/validation shape above are implementation-level planning choices, not newly approved topology.

Immediately after verification of this bounded boundary, require separately approved `frappe-owned-conversation-state` for Frappe-owned records, user/site binding, persistence, JSON replacement and migration/compatibility. Its schema, retention, reset, concurrency and migration decisions remain for that change; it is not implemented or approved by this plan.

Remaining U4 tool/result/provider contracts, version negotiation and streaming/realtime transport remain unresolved. U1 tenancy/repository binding, U2 indexes, U3 executor, U5 ACLs, U6 egress and wider U7/U8 decisions stay future gates. This increment does not pass full G2/M2 or any production, release or production-write gate.
