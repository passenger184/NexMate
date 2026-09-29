## Why

The Frappe-native authorized ERPNext READ path (U5) is implemented, specified and
evidenced, but it is **unreachable from the Desk**. `frappe_app/erpnext_ai_copilot/api.py:289`
hard-codes `execution_scope="chat-only"`, and `orchestrator.py:1141` denies the
`erpnext` route before entry, so an authenticated browser session can never reach
`erpnext_read.attempt_read()`. The READ foundation shipped with a gate that
prevents its own use.

Investigation also found a **live capability hole** that blocks the intended
Developer model: `POST /orchestrate` with no gateway envelope yields
`chat_only=False` and `OrchestrateRequest.mode` defaults to `"developer"`
(`service/main.py:221`). Any holder of the service credential can therefore
request DocType schema through the shared ERPNext API key, with **no user
attribution**; and because Frappe's DocType permissions also apply to that
upstream account, the observed result on the test site was a `403` for the normal
integration user rather than an unconditional disclosure. Both facts must be
stated: the path is unauthenticated with respect to *any user*, and its actual
reach is bounded by the shared account's own Frappe permissions, which are not a
user authorization boundary. The "Employee schema denied" policy cannot be
enforced on a path that has no Employee, so the intended capability model is
currently unsound.

Now is the right time: the READ authorization boundary is already correct and
evidenced, so what remains is unblocking it and replacing a blanket deny with a
capability model that is enforced in Frappe, not inferred at the orchestrator.

The metadata capability itself is a **product surface**, so its scope is an
administrator decision rather than a fixed list shipped with the code. The
approved design makes the set of inspectable DocTypes a per-site
administrator-controlled **metadata access policy**.

## What Changes

- **Retire the `chat-only` execution scope.** Replace the fixed literal with a
  single generic authenticated execution scope. It means only "this is a
  credentialed request permitted to reach orchestration" and grants nothing. One
  scope replaces a growing list of hypothetical per-operation scopes, keeping the
  envelope a frozen shape.
- **Split the `chat_only` flag, which currently does two jobs.** ~20 of its 28
  uses in `orchestrator.py` are cosmetic (capability wording, smalltalk,
  version preamble), not security. Only `:1141` is the gate. Separate the two so
  the security gate is explicit and testable.
- **Introduce an explicit Employee/Developer capability** derived from the real
  Frappe Role named in the existing server-managed `nexmate_developer_roles`
  list. No new NexMate role store, no cache. The derived value is carried in the
  existing `mode` envelope field; no second capability field is added.
- **Add Developer metadata access on a Frappe-native path**
  (`frappe.get_meta()`, in-process, no HTTP hop, no shared credential), returning
  a **minimized** five-field projection. Employee metadata stays denied, and the
  denial is enforced in the control plane rather than by a conversational reply
  in the orchestrator.
- **Make the inspectable DocType set an administrator-controlled policy.** A new
  `NexMate Settings` Single DocType carries a `metadata_access_mode` of `all` or
  `allowlist`, plus a `NexMate Metadata DocType Rule` child table holding the
  configured DocTypes. The policy is read uncached per decision and **fails
  closed** in every ambiguous or unavailable case. It is never hard-coded, never
  read from site configuration, and never exposed to the browser or to inference.
- **Make operational limits administrator-configurable within immutable service
  ceilings.** `NexMate Settings` additionally carries numeric limits —
  `max_schema_fields` (default 300, ceiling 500), `max_schema_bytes` (default
  65536, ceiling 131072), `max_read_rows` (default 20, ceiling 100),
  `max_read_fields` (default 20, ceiling 50), `max_read_bytes` (default 65536,
  ceiling 131072), `max_read_rounds` (default 3, ceiling 5) — plus a
  `developer_roles` list that takes precedence over the `site_config`
  configuration when configured. Every limit resolves as
  `effective = min(admin value, ceiling)`, enforced at runtime as
  defense-in-depth. The ceilings themselves are constants and are never
  configurable. Security invariants (capability model, allowlists, projection
  attribute set, audit vocabulary, protocol shapes, secrets) stay hardcoded.
- **Keep configuration authority separate from capability.** Only a user with
  normal Frappe write permission on `NexMate Settings` may change the policy.
  Holding Developer capability confers no configuration authority, and
  configuration authority confers no capability.
- **Close the no-envelope exposure and retire the three legacy
  `/tools/erpnext/*` read routes** in this change. A request without a complete
  valid gateway envelope is refused if it supplies an authorized-context field,
  an authorization scope, or a conversation block, so it cannot assert
  Frappe-derived authorization state by any of them. This is required, not
  cosmetic: it is the only ordering in which the capability policy is
  enforceable.
- **Keep U5's business-record boundary unchanged.** `erpnext_read.py` is not
  modified, and metadata requests are dispatched away from it rather than through
  it. Capability and the metadata policy decide *which NexMate features exist*;
  Frappe native permissions continue to gate *which ERPNext business records are
  readable*.
- **Reduce, not eliminate, the shared ERPNext credential.** Schema and the legacy
  read routes stop needing it. The write path and the version lookup still do,
  and both are out of scope, so "inference holds no ERPNext credential" is
  explicitly **not** an acceptance criterion of this change. The invariant that
  *is* asserted is that no shared ERPNext credential is used on the
  Frappe-attributed business-read or metadata path.

### Breaking changes

- **BREAKING** The three `/tools/erpnext/{schema,document,list}` routes are
  removed. They were deprecated by U5 and never authorized a user; any remaining
  caller must move to the Frappe gateway.
- **BREAKING** A `/orchestrate` request with no gateway envelope can no longer
  reach ERPNext metadata, and can no longer supply an authorized-context field, an
  authorization scope, or a conversation block. Legacy no-envelope *chat* remains
  available.
- **BREAKING** The gateway envelope's `execution_scope` value changes. Both
  producer (`api.py`) and consumer (`service/auth.py`) must change together or
  inference answers 422.
- **BREAKING** A browser-supplied `mode` form field is now refused rather than
  accepted and ignored.
- **BREAKING** A deployment requires an approval-gated Frappe schema
  synchronization that adds the `doctype_schema` audit action and installs two
  new NexMate DocTypes. **No data migration is required.**

## Capabilities

### New Capabilities

- `nexmate-capability-model`: the Employee/Developer capability concept, its
  derivation from real Frappe roles, the rule that capability never widens
  ERPNext business-record authorization, the rule that capability is distinct
  from configuration authority, fail-closed derivation, and role-change
  immediacy without a NexMate-side cache.
- `doctype-schema-access`: Frappe-native, capability-gated, administrator-policy-
  governed, minimized DocType metadata access — the replacement for the
  shared-credential schema read.

### Modified Capabilities

- `frappe-api-gateway`: retires the "Deterministic backend chat-only execution
  guard" and the fixed `execution_scope` in the constructed request; carries the
  generic authenticated execution scope and the derived capability in the
  existing `mode` field; refuses browser-supplied mode; refuses authorization-
  bearing fields on the no-envelope path; and dispatches metadata away from the
  business-read adapter.
- `endpoint-access-control`: removes the three legacy ERPNext read routes from the
  retained inventory, closes the no-envelope authorization-assertion path,
  forbids exposing the metadata policy to the browser, and re-points the
  natural-language-denial scenario at the new control-plane gate.
- `erpnext-authorized-reads`: clarifies that "mode is not ERPNext authorization"
  governs **business records**, so it does not prohibit capability-gating or
  administrator-policy-gating of **metadata**. The authorization boundary itself
  is unchanged.
- `durable-tool-execution`: records that capability- and policy-gated DocType
  metadata is not a business read and is not approval-gated, and that sharing the
  authorized-context round trip does not merge the two request contracts.

## Impact

**Code (Frappe side).** `frappe_app/erpnext_ai_copilot/api.py` — scope literal,
capability derivation, browser-field refusal, and a new bounded metadata
round-trip inside the existing `MAX_READ_ROUNDS` loop with dispatch on request
kind. New Frappe-side metadata module beside `erpnext_read.py`, implementing the
capability gate, the structural exclusions, the policy read, the five-field
projection, the audit and the collapse. New `NexMate Settings` and
`NexMate Metadata DocType Rule` DocTypes. **No change to `erpnext_read.py` or
`audit.py`.**

**Code (inference side).** `service/auth.py` — accept the new scope literal;
refuse authorization-bearing fields without a complete valid envelope.
`orchestrator.py` — split the cosmetic `chat_only` uses from the security gate,
remove the inference-side employee schema short-circuit, and replace the
shared-credential schema call with a control-plane request.
`service/main.py` — remove the three routes; extend the authorized-context
contract with a metadata kind, shape and bounds that leave the business-read
bounds unchanged.

**Callers to update.** `tools/erpnext_write.py:113` calls `get_doctype_schema`
for write-propose validation and must not silently lose metadata; it is a reason
the credential cannot be removed entirely.

**DocTypes and migration.** Three additive Frappe schema synchronizations under
one approval gate: the `doctype_schema` option on the audit action vocabulary,
`NexMate Settings`, and `NexMate Metadata DocType Rule`. **No data migration.**
The numeric settings are additional fields on the already-new `NexMate Settings`
record, so they ride the same synchronization and gate. All existing U5 migration safeguards are preserved, including verifying
`sites/apps.txt` and app/module cache state before migrating, because the U5 run
recorded an incident in which a migration orphaned all four NexMate DocTypes.

**Docs and ledger.** `ARCHITECTURE.md` (wiring references are already stale —
`api.py:236`→289, `orchestrator.py:1038`→1141, `service/auth.py:164`→215 — plus
the Developer Mode claims and the route inventory). `SECURITY.md` states the
shared credential is retained for version lookup, schema, write and legacy
routes; that list shrinks, and the metadata policy must be documented as a
disclosure surface. A new `DECISIONS.md` ADR is **required** to supersede the
`:422` chat-only decision. `README.md`, `DEVELOPMENT.md`, `ROADMAP.md`,
`progress/*`.

**Tests.** `tests/test_chat_boundary.py`, `tests/test_frappe_gateway.py` and
`tests/test_legacy_replacement.py` depend on the current behavior.
`tests/test_employee_mode.py`, `tests/test_orchestrator.py`,
`tests/test_routing_eval.py`, `tests/test_routing_precision.py`,
`tests/test_post_live_regressions.py` and `tests/test_conversation.py` also
depend on the retired schema path. The 40 `test_erpnext_read_adapter.py` tests
and the 19 non-legacy `test_u5_read_boundary.py` tests remain the regression
floor; four legacy-group assertions in `test_u5_read_boundary.py` assert behavior
this change intentionally removes and MUST be updated rather than preserved.

**Explicitly out of scope.** ERPNext WRITE, full tool execution, code execution,
MCP, Developer Workbench, deployment redesign, new models, new RAG architecture,
multi-site routing, and any change to the existing business-record authorization
boundary.
