# Design — Retire `chat-only`, capability model, Frappe-native schema

## Context

See `proposal.md` — Why. This section records only the current-state facts that
constrain the approach.

**The `chat_only` flag does two unrelated jobs.** Of 28 uses in
`orchestrator.py`, exactly one is a security gate (`:1141`). The rest are
cosmetic: capability wording (`:358`, `:374`, `:390`, `:415`), smalltalk
fallback (`:327`), and version-preamble suppression (`:1253`). Retiring the
concept without splitting these two jobs would either leave a security gate
hiding behind a cosmetic name, or silently change ~20 user-visible replies.

**`chat-only` is a two-sided contract literal.** `api.py:289` produces it;
`service/auth.py:227` rejects any other value with 422. Both sides must change
in the same deployment or the gateway breaks with a protocol error rather than a
safe refusal.

**The READ machinery already exists and is already correct.**
`api.py:308-332` runs a bounded `MAX_READ_ROUNDS` loop; `_authorized_read`
(`api.py:173-201`) hands an untrusted request to `erpnext_read.attempt_read`;
`orchestrator.py:931` emits the `_read_request` marker. Nothing in the *shape* of
that path changes. `erpnext_read.py` is modified in exactly three operational bound
constants (D17), and in nothing else.

**The metadata hole is reachable today.** `OrchestrateRequest.mode` defaults to
`"developer"` (`service/main.py:221`); `validate_gateway_envelope` returns
`False` — i.e. `chat_only=False` — when no envelope field is supplied
(`service/auth.py:218-219`); `_ERPNEXT_HINTS` includes `"what fields does"` and
`"schema of"` (`orchestrator.py:471-473`); `_extract_erpnext_request` maps that to
`op="schema"`; `run_erpnext_branch:904-908` calls `tools/erpnext.get_doctype_schema`,
an authenticated HTTP GET to `/api/resource/DocType/{name}` using the shared
`ERPNEXT_API_KEY`/`SECRET`. The only gate is the service credential.
`endpoint-access-control:44-46` currently permits this ("legacy behavior remains
available … without authenticated user attribution").

**The current user-facing schema summary is narrower than the current transport.**
`orchestrator.py:909-919` reduces the fetched DocType document to
`fieldname`/`fieldtype`/`label` before it reaches the model, so the model never
sees `permissions` or `options` on that path. The full document is nevertheless
fetched into the inference process, and `/tools/erpnext/schema`
(`tools/erpnext.py:105-108`) returns it to any service-credential holder
unchanged. The new projection is therefore a **narrowing of process and network
exposure** and a **small widening of what the model sees**, adding `reqd` and
`read_only`. Both facts belong in the record.

**Reads are already not approval-gated.** `durable-tool-execution:49` states a
business read "SHALL NOT require a durable human-approved proposal".
`endpoint-access-control:116` scopes approval to *tool execution*. No proposal is
required for either reads or metadata.

**Role lookup is duplicated per request.** `_mode_for_user` (`api.py:86`) and
`_authz_scope` (`api.py:105`) each call `frappe.get_roles()`.

**The authorized-context consumer contract is frozen and business-read specific.**
`service/auth.py:94-138` accepts only `operations=("document","list")`, and
before this change capped `fields_returned` at 20 entries, the `data` list at
20 rows and the serialized payload at 64 KiB.
`tests/test_u5_read_boundary.py:59-62` asserts `operation="schema"` is
**rejected**. The transport therefore already existing does **not** make reuse
free: the consumer contract must be extended, and the business-read bounds must
move **in step with** the producer's approved immutable ceilings, never set
behind them. D20 makes that coordination mandatory: a consumer narrower than
its producer rejects a Frappe-authorized read that Frappe had approved.

**A measured lower bound on metadata size.** `progress/CURRENT.md:85,737,785`
records a live full-schema answer for `Customer` with **87 fields**. Live
verification on 2026-09-29 further measured `Item` (132 fields), `Sales Order`
(170) and `Sales Invoice` (233) on the test site. Any metadata bound below
roughly 100 projected entries would refuse legitimate production DocTypes, so
the bounds are declared numerically rather than left implicit — and, by the
same evidence, they are administrator-configurable within immutable ceilings
(D16) instead of fixed constants.

## Goals / Non-Goals

**Goals**

- One generic authenticated execution scope, validated on both sides, granting
  nothing by itself.
- Capability derived live from real Frappe roles, re-derived per request, no
  NexMate role store and no cache.
- The inspectable DocType set is an administrator-controlled, per-site policy,
  read uncached, failing closed, and never exposed to the browser or inference.
- Schema served in-process by Frappe from live local metadata, capability-gated,
  minimized to a fixed five-field projection, audited, fail-closed.
- Operational limits (metadata shape/size, business-read rows/fields/size,
  read rounds, developer roles) administrator-configurable per site through
  `NexMate Settings`, each validated against an immutable service ceiling that
  is itself never configurable (D16–D20).
- The legacy unattributed metadata path closed **in the same change** as the
  metadata grant, together with the other two no-envelope authorization fields.
- The U5 business-record boundary untouched and its tests green.

**Non-Goals (design-level)**

- Not a rewrite of the orchestrator. `chat_only` is renamed/split, not
  restructured.
- Not a role-migration tool. `nexmate_developer_roles` already names real Frappe
  roles; moving to a role literally named `Developer` is a **site configuration
  change**, not code.
- Not removal of the shared ERPNext credential (see D8).
- Not a redesign of ERPNext business-record authorization, in any direction.
- Not a general NexMate settings framework. One Single DocType is introduced
  because one administrator policy needs to exist; a second policy does not
  thereby become authorized scope for this change.
- Not a request-timeout control. The existing inference/request timeout stays
  deployment/site configuration; timeouts, secrets, endpoints, provider
  configuration, infrastructure settings and deployment flags are not moved
  into Desk-editable settings by this change.
- Not a redefinition of security invariants. Administrator settings may narrow
  operational behavior within their supported ranges; they never redefine the
  invariants listed in D21.

## Decisions

### D1 — Execution scope value: `frappe-attributed`

The value replaces `chat-only` on both sides.

**Alternatives rejected.** `authenticated` is ambiguous — the service credential
is what authenticates the *hop*, while the envelope is what attributes the
*user*. `erp-authorized` asserts something the scope does not know. `frappe-attributed`
states exactly what is true and distinguishes the gateway path from the legacy
path: the presence of a validated Frappe identity, site, capability and scope.

### D2 — Keep `mode` on the wire; "capability" is a spec-level concept

The derived capability continues to travel in the existing `mode` envelope field.
No second capability field is introduced.

**Why.** `api.py:149` enforces `result["mode"] != envelope["mode"]` as a
protocol check; keeping one field preserves that invariant unchanged. Two fields
asserting the same fact would require a second equality invariant, and a field
the browser receives and displays invites reading it as an authority it is not.
`NexMate Conversation.persona` already stores the same two values in a closed
`Select`, so no persisted-state change is required either.

**Consequence.** The spec deltas refer to "capability" as a concept and to `mode`
as the field. They must not imply a field that does not exist. The requirement
header `Authoritative role-derived persona` is retained unchanged so the MODIFIED
delta continues to bind to the existing requirement.

### D3 — Split `chat_only` into an execution gate and a capability-advertising flag

The security gate (`:1141`) and the ~20 cosmetic uses are separated so the gate is
named for what it is and can be tested independently.

**Why not delete the cosmetic uses?** They are correct behaviour — a capability
reply should describe what the requester can actually do, and the version preamble
must stay suppressed.

**Consequence.** The new advertising flag is derived from capability, not from the
execution scope. Neither depends on the scope literal.

### D4 — The metadata access policy is administrator-controlled configuration

Which DocTypes may be inspected is a **product surface**, so it is not a
hard-coded constant in NexMate. It lives in a new `NexMate Settings` Single
DocType with a `metadata_access_mode` `Select` of `all` | `allowlist`, and a
`NexMate Metadata DocType Rule` child table whose rows are links to DocType
records.

**Alternatives rejected.**

- *A hard-coded `ALLOWED_METADATA_DOCTYPES` constant.* This was the previous
  decision in this change and is now superseded. A constant would make every
  site identical by construction and would require a code change and deployment
  to change what a customer may inspect.
- *`site_config.json`.* This is NexMate's existing pattern for
  `nexmate_developer_roles` and the gateway credential, and it is the right
  pattern for credentials and infrastructure. It is not administrator-editable,
  it records no actor or timestamp or diff, and `frappe/__init__.py:200` loads it
  with `cached=is_request` over a 60-second per-process cache
  (`frappe/config.py:149`) with no automatic invalidation. Using it for a
  disclosure policy would give the *least* fresh and *least* auditable of the
  available mechanisms.
- *Extending Frappe's `System Settings`.* `System Settings` is a core Frappe
  Single with 120 fields owned by the `frappe` app; adding application-specific
  fields from an ERPNext app couples two apps to one core form with no sanctioned
  extension point, and the form would accumulate unrelated fields.

**Why a Single plus a child table of links.** Frappe's own convention for
application settings is a Single DocType; ERPNext ships more than twenty of them
and nine carry child tables. A `Link` field to `DocType` makes existence and
exact-name validation framework behaviour rather than application code, and makes
a wildcard or partial name unstoreable. Only the structural exclusions and
duplicates need application validation.

**Why not a text field.** A text list would move existence validation, wildcard
rejection, and duplicate handling into NexMate code and would accept values that
are not DocType names.

### D5 — Metadata resolution moves to the Frappe control plane via `frappe.get_meta()`

`erpnext_ai_copilot` runs **inside** the Frappe request process, so
`frappe.get_meta()` returns the same DocType metadata with no HTTP hop, no
credential, and no extra round trip. This is strictly better than gating the
existing client: it removes a credential consumer rather than adding a check in
front of one, and it puts metadata authorization beside the module that already
owns business-record authorization.

**Rejected:** keep `tools/erpnext.get_doctype_schema` and add a policy check. It
leaves a shared credential in inference, leaves an HTTP hop, and cannot be
enforced — the client runs on the inference side, where capability and policy
would both be untrusted envelope-derived input.

**Minimization is mandatory.** The projection is `fieldname`, `fieldtype`,
`label`, `reqd`, `read_only` only. The attribute set is fixed and is not
administrator-configurable (D21); the shape and size bounds are
administrator-configurable within immutable ceilings (D16), refused rather
than truncated.

### D6 — Authorization order: capability, then structural exclusion, then policy

```
session user
  ↓ capability  (live frappe.get_roles() vs nexmate_developer_roles, fail-closed)
  ↓ DocType exists
  ↓ not istable, not issingle
  ↓ metadata policy permits
ALLOW
```

**Capability first, and why it cannot move.** Frappe's permission engine returns
an unconditional allow for the `Administrator` user as its first substantive check
(`frappe/permissions.py:104-110`). Any permission-based check placed ahead of the
capability gate would therefore short-circuit the capability model for exactly the
user most likely to hold a Developer role. The observed configuration makes this
concrete: `nexmate_developer_roles` is `["System Manager"]` on the test site.

**`frappe.has_permission(doctype, "read")` is deliberately not part of this
gate.** Business-record authorization and metadata capability are separate
surfaces, and `erpnext-authorized-reads` and `durable-tool-execution` both require
metadata not to share the business read's authorization surface. Making a Frappe
DocType permission the metadata gate would make metadata authorization a function
of the business-record model and would redefine that requirement.

**Structural exclusions precede policy** so that no policy value, and no
administrator mistake, can admit a child table or a Single DocType. The exclusions
are read from the same `get_meta()` object the read adapter already inspects
(`erpnext_read.py:247-250`) but are enforced independently; `erpnext_read.py` is
not modified and is not imported for this purpose.

### D7 — The policy fails closed in every ambiguous case

Absent settings, unset mode, unsupported mode, `allowlist` with zero entries,
unreadable settings, and otherwise-invalid configuration all **deny**. The policy
is never defaulted to the permissive mode.

**Why.** A configuration failure must never widen access. There is also a
mechanical reason: `frappe/model/document.py:259-266` shows that a Single DocType
that has never been saved returns an empty in-memory document rather than raising,
so "never configured" and "configured empty" are indistinguishable at the API
level. Only one rule — anything not positively configured is denied — is provably
safe. A rule that special-cased "unset means permissive" would create a state an
administrator could neither observe nor audit.

**Trade-off accepted.** In `all` mode a failed read reduces availability from
"everything" to "nothing". That is the intended direction of failure. Because the
caller-facing response is collapsed, the reason is surfaced only as an internal
operational signal, never to the caller.

### D8 — Credential goal is reduction, not removal

**Dependency map (all remaining consumers are inference-side; the U5 read path
uses none):**

| Consumer | Location | This change |
|---|---|---|
| Schema read | `orchestrator.py:908` | **removed** (D5) |
| Legacy read routes | `service/main.py:618,632,646` | **removed** (D9) |
| Write propose validation | `tools/erpnext_write.py:113` | retained — out of scope |
| Write propose/apply | `service/main.py:798,844` | retained — out of scope |
| Version lookup | `orchestrator.py:435` | retained — out of scope |

Because the write path is out of scope, **"inference holds no ERPNext credential"
cannot be an acceptance criterion** and is not written as one. The invariant that
is asserted is narrower and true: **no shared ERPNext credential is used on the
Frappe-attributed business-read or metadata path.**

**Why this matters beyond bookkeeping.** The write path is gated only by
`ERPNEXT_WRITE_ENABLED=false` in `.env`. A shared credential plus a single
environment boolean is a weak boundary for a side-effecting capability, and the
dependency map is now written down so the next change can close it with evidence
rather than assumption. `SECURITY.md` is updated to match.

### D9 — Legacy unattributed metadata access is closed in this change

The `/tools/erpnext/{schema,document,list}` routes are removed, and a no-envelope
`/orchestrate` request can no longer reach the metadata operation.

**Why this must be in the same change, not after it.** "Employee metadata denied"
is unenforceable on a path with no Employee and a default of `developer`. Shipping
the grant first means shipping a policy any service-key holder can bypass.

**Sequencing within the change.** Remove the routes and the no-envelope metadata
branch *before* enabling the capability-and-policy-gated path, so no interval
exists in which both are live.

### D10 — All three no-envelope authorization fields are refused together

`service/auth.py:218-219` returns before validating the conversation block, the
authorization scope, and the authorized-context field, so a request with no
envelope field supplied skips all three. Each is independently a way to assert
Frappe-derived authorization without an authenticated Frappe user: a fabricated
authorized context is consumed by the orchestrator as trusted instance data; a
structurally valid but forged retrieval scope passes `rag/acl.py:71-98`, which
checks shape rather than provenance, and can reach site-tier and restricted-tier
corpus; a conversation block with a null owner passes the owner comparison because
the envelope user is also null.

**Decision.** Refuse the presence of any of the three when a complete valid
envelope is absent, **before** the early return. These are not validated as if a
user existed, because no user exists to validate them against.

**Scope note.** The retrieval-scope and conversation exposures are pre-existing and
are outside this change's stated purpose. They are closed here because they share
one root cause and one code site with the authorized-context exposure, and because
leaving two of three open would make any claim that the no-envelope path is closed
false. The change records them as pre-existing rather than presenting them as new.

### D11 — Metadata reuses the round trip but not the request contract

`run_erpnext_branch` already returns a `_read_request` marker that `api.py`
consumes in a bounded loop. Metadata becomes a second request kind on that channel,
so the Browser → inference → Frappe → inference shape does not change and no new
transport is introduced.

**What this does *not* mean.** It does not mean the existing contract already
accepts metadata. `service/auth.py:94-138` is frozen to `document`/`list` with
20-entry field and row bounds, and `tests/test_u5_read_boundary.py:59-62` asserts
that a schema operation is rejected. The consumer contract is extended with a
metadata operation, a metadata shape, and metadata-specific bounds sized above the
observed 87-field case. The **business-read** bounds are a separate contract and are
moved only as D20 requires — to the producer's approved immutable ceilings, so a
consumer can never be narrower than what Frappe already authorized. Those ceilings
are 100 rows, 50 fields and 131072 bytes; the business-read **defaults** stay 20
rows, 20 fields and 65536 bytes, so unconfigured behavior is unchanged. The
metadata ceilings are 500 fields and 131072 bytes, and the two contracts are never
merged.

**Round budget.** The default bound is the existing `MAX_READ_ROUNDS = 3`, now
administrator-configurable as `max_read_rounds` within a hard ceiling (D18). A
read request, a metadata request and a follow-up share one budget rather than
receiving one each.

**Dispatch invariant.** The loop dispatches on request kind: metadata to the
metadata module, business reads to `erpnext_read`. `erpnext_read`'s contract
deliberately excludes metadata operations, so a metadata request must never reach
`attempt_read()`. Were it to, the adapter would reject it — correctly failing
closed — but would also record it as an `invalid_request` on the business-read
audit action, corrupting the distinction U5 evidence depends on.

### D12 — Metadata refusals collapse in the metadata module

The collapse lives in the new metadata module at its response-construction layer,
mirroring the U5 discipline of collapsing at the boundary rather than in the
adapter. The caller-visible shape is fixed: answer `Schema not found or access
denied.`, with `route_how` identifying a schema denial.

**Why not reuse `erpnext_read.collapse_for_caller()`.** It returns
`Document not found or access denied.` and `route_how="frappe-authorized-read+denied"`,
which would label a metadata refusal as a business-record refusal and contradict
the requirement that metadata share no authorization surface with business reads.
The metadata collapse therefore uses its own fixed values: answer
`Schema not found or access denied.`, `route_how="frappe-schema+denied"`.

**Anti-oracle.** Capability denial, policy denial, structural exclusion, invalid
request, oversized response, audit failure and a nonexistent DocType all collapse
to the same caller-visible result. The internal reason exists only in the audit
event. The nonexistent-DocType case is what prevents `all` mode from becoming a
DocType-existence oracle, since under `all` there is no configured list to consult
and existence would otherwise be the only gate.

### D13 — Metadata audit uses a dedicated action and is fail-closed on the call result

Business reads emit `erpnext_read`. Metadata emits a dedicated
`doctype_schema` action. Overloading `erpnext_read` would make record access and
metadata access indistinguishable in the ledger, which is the same conflation the
read action was introduced to avoid. The `NexMate Audit Entry` `action` field is a
closed `Select`, so a dedicated option requires an additive DocType schema
synchronization.

**Why the `outcome` vocabulary is unchanged.** `success`, `denied`,
`not_found`, `permission_denied` and `invalid_request` all exist. Metadata needs
no new outcome.

**Fail-closed on the call result, not on an exception.**
`frappe_app/erpnext_ai_copilot/audit.py:197-211` catches a failed Frappe insert,
sets `audit_pending = True`, writes a local JSON fallback, and **returns normally**.
It raises only when the durable store is unavailable outright. Therefore the
metadata module inspects the returned value and treats a pending or otherwise
unconfirmed durable write as failure, returning no schema. The live-verified
success signal is `audit_pending` being `None`.

**`audit.py` is not modified.** Consequently the existing business-read path's
treatment of `audit_pending` — `erpnext_read._audit` ignores the return value —
is unchanged. That is a pre-existing weakness, recorded as a limitation of the
delivered U5 boundary rather than silently repaired inside this change.

### D14 — Metadata policy changes are auditable, and the policy is not exposed

`NexMate Settings` sets `track_changes: 1`, so Frappe's `Version` records
configuration changes including child-table row additions and removals — which
Frappe's `Permission Log` would not, because that mechanism is opt-in per DocType
via `get_permission_log_options` and excludes child-table content from its diff.

Additionally a NexMate document event on policy change emits an audit event
recording actor, site, previous mode, new mode, and correlation. Business data is
never placed in a configuration audit; DocType names are structural, not business
values, and the full list is already durably recorded by `Version`.

The policy, its mode, its configured DocTypes and configuration authority are
**never** exposed through `extend_bootinfo` or any client-side configuration.
`boot.py` currently exposes `copilot_api_base`; a disclosure policy must not
travel the same path, and the browser determines nothing about metadata access.

### D15 — U5 is clarified, not weakened

`erpnext-authorized-reads` already says capability "SHALL NOT determine ERPNext
record authorization". The delta states that the rule governs **business records**,
that metadata is not a business record, that neither capability nor the metadata
policy confers business-record authorization, and that a metadata response
contains no business values and no `permissions` table. The business-record
boundary, the permission re-derivation, the minimization and the anti-oracle
behavior are all unchanged, and the read adapter's authorization, allowlist and
collapse logic is not modified.

**What is and is not byte-for-byte.** `erpnext_read.py`, the producer of
authorized context, is byte-for-byte unchanged except for the three operational
bound constants described in D17 — no authorization, allowlist, projection,
collapse, audit or error-semantic line moves. `service/auth.py`, the consumer-side
validation of Frappe-produced authorized data, **is** extended to admit a metadata
shape and to raise the business-read bounds to the same approved ceilings (D20).
Any statement that the U5 boundary is preserved byte-for-byte applies to the
producer; the consumer contract is a U5 security control that this change amends
deliberately and in a bounded way.

### D16 — Operational limits are administrator settings clamped by immutable ceilings

Every numeric operational limit in this change exists in two layers:

```
administrator-configured value  (NexMate Settings, Desk-editable)
        ↓ validated: inside the administrator-supported range, else rejected at save
effective_limit = min(admin_configured_value, immutable_service_ceiling)
        ↓ enforced at runtime, ceiling re-checked as defense-in-depth
enforcement
```

The service ceilings are constants in code. They are **never** editable through
`NexMate Settings`, never read from site configuration, and never supplied by
the caller, the browser, or inference. Settings validation rejects a value
outside the administrator-supported range at save time; runtime enforcement
re-checks the ceiling independently, so a malformed or bypassing configuration
that reaches runtime is still clamped rather than honored. Do not rely solely
on Settings validation.

A value **below** the minimum resolves to the **default**, never to the
minimum. Frappe materialises an untouched `Int` on a Single as `0` on the write
path, so the minimum would silently turn a never-configured setting into the
most restrictive value instead of the documented one. The default already
governs an unconfigured setting, so resolving to it is neutral. An explicit
out-of-range value, including an explicit `0`, is still refused at save time.

The settings and ceilings:

| Setting (NexMate Settings) | Default | Min | Admin max | Service ceiling |
|---|---|---|---|---|
| `max_schema_fields` | 300 | 1 | 500 | 500 |
| `max_schema_bytes` | 65536 (64 KB) | 4096 (4 KB) | 131072 (128 KB) | 131072 |
| `max_read_rows` | 20 | 1 | 100 | 100 |
| `max_read_fields` | 20 | 1 | 50 | 50 |
| `max_read_bytes` | 65536 (64 KB) | 4096 (4 KB) | 131072 (128 KB) | 131072 |
| `max_read_rounds` | 3 | 1 | 5 | 5 |

Byte-valued settings may be displayed and edited in KB on Desk, but runtime
enforcement is byte-based. The defaults for the read bounds (20/20/65536) and
the round default (3) preserve current behavior; the schema field default (300)
is raised from the previous constant (100) because live measurement shows real
transaction DocTypes at 132–233 fields, which the old constant refuses.

**Why ceilings as well as validation.** Settings validation runs at save time
in Desk; runtime reads the stored record uncached on every decision. A record
written by any path other than the validated save — or read while partially
updated — must still be unable to widen behavior past the ceiling. The ceiling
is the backstop, not the documentation.

### D17 — Live-data query bounds are administrator policy, not authorization

`max_read_rows`, `max_read_fields` and `max_read_bytes` bound how much a single
business-record read may return. They are data-minimization and operational
policy: they narrow what Frappe authorized, and they can never widen it. The
effective read request remains constrained by the intersection of Frappe
authorization and NexMate policy, exactly as before; only the numeric bounds
move from constants to settings-with-ceilings.

Nothing else about the business-read contract changes: operation set, DocType
and field allowlists, filter grammar, anti-oracle collapse, audit action and
fail-closed audit are untouched. `erpnext_read.py` *is* modified, but only in the
three operational backstop constants `MAX_LIST_LIMIT` 20→100, `MAX_FIELD_COUNT`
20→50 and `MAX_RESULT_BYTES` 65536→131072, so the adapter sits exactly at the
approved immutable ceilings instead of below them. This is a ceiling-alignment
change with no authorization effect: the adapter still refuses above its bounds
with the same collapsed denial, still owns identity, allowlists, projection and
collapse, and the adapter's `DEFAULT_LIST_LIMIT` of 20 keeps unconfigured reads at
the documented default.
An administrator who lowers a bound narrows answers; an administrator who
raises one can never exceed the ceiling and can never receive a record Frappe
denies.

**Adapter backstop matches the ceilings.** The business-record read adapter
enforces its own immutable bounds (`MAX_LIST_LIMIT = 100`,
`MAX_FIELD_COUNT = 50`, `MAX_RESULT_BYTES = 131072`), raised to the approved
ceilings in a scoped reviewed change that touched nothing else in the file.
The effective runtime formula is therefore `min(admin-or-default, service
ceiling, adapter bound)` with all three layers agreeing: an administrator
value up to the ceiling flows end to end, and anything above it is refused —
collapsed and audited — first by the api.py pre-check, and independently by
the adapter itself. No configured request can surprise the adapter with a
bound error it would not itself produce, and no request the adapter would
refuse can reach it unexamined.

### D18 — Read rounds are administrator-configurable within a hard ceiling

`max_read_rounds` bounds inference → Frappe round trips for one ask/request.
Each round is an inference HTTP call plus control-plane work, so an unclamped
value would be a cost and latency amplifier: the ceiling (5) is strictly
necessary, not advisory. The default (3) preserves current behavior.

### D19 — Developer roles: Settings precedence with locked fallback

`developer_roles` in `NexMate Settings` names Frappe roles, preferably through
a proper role-selection field (a child/table field of Role references where the
Settings design supports it; otherwise the list representation the design
already uses for DocTypes). Semantics, locked:

- Setting absent or unconfigured → fall back to the existing `site_config`
  `nexmate_developer_roles` configuration. Current behavior is preserved and
  upgrades are safe.
- Setting configured with one or more roles → the Settings value takes
  precedence over `site_config`.
- Setting explicitly configured as an empty list → no Developer roles are
  granted.
- Settings proven saved but unreadable, role rows unreadable, or store
  unreadable → fail closed to `employee` with NO `site_config` fallback. An
  unreadable configuration is a failure, not absence; the failure is logged
  distinctly (`developer_role_source_unavailable`, not the malformed-mapping
  code) so operators can tell the two apart.
- Invalid or malformed values → fail closed (`employee` for all).
- Deleted or nonexistent Frappe roles → never match, so they never grant
  capability. Role resolution stays live and per-request; no NexMate role cache
  is introduced, so role grants, revocations and deletions take effect on the
  next request with no invalidation mechanism needed.

### D20 — Cross-layer contracts stay coordinated

The Frappe control plane and the inference service enforce compatible limits,
or legitimate payloads die as protocol errors. Concretely, this change
requires all of the following, because each was found as a live defect class
in the current code:

- Coordinated metadata field ceiling and metadata byte ceiling on both sides,
  so Frappe never accepts a payload inference rejects with HTTP 422.
- Coordinated business-read row, field and byte ceilings on both sides, for
  the same reason.
- Coordinated read-round ceiling: the loop bound lives in the control plane
  and the contract bound lives in inference validation, and they must agree.
- Field-count enforcement where metadata authorization currently checks bytes
  only (`api.py:_authorized_metadata` re-checks serialized size but not field
  count): the resolved field bound must be enforced there too, so an
  over-ceiling projection cannot pass the control plane only to 422 downstream.
- Separate metadata payload constants from business-read payload constants on
  the inference side, even where their current numerical values are equal.
  Sharing one constant re-couples the two contracts D11 separated.

The exact implementation mechanism is not prescribed beyond these outcomes;
whatever reads the setting must clamp it with `min(admin, ceiling)` at the
point of enforcement.

### D21 — Security invariants stay hardcoded

Administrator settings narrow operational behavior within their supported
ranges. They never redefine the following, which remain constants, protocol
shapes, or code-path barriers:

- Frappe identity and session authority; Frappe permission enforcement.
- The capability model and its fail-closed behavior; no implicit elevation;
  capability evaluated before any permission bypass.
- Business-record DocType and field allowlists; forbidden APIs; filter deny
  rules; the anti-exfiltration projection discipline.
- The metadata projection **attribute set** (`fieldname`, `fieldtype`, `label`,
  `reqd`, `read_only`) — bounds are tunable, attributes are not.
- Audit vocabulary, audit integrity, and collapse behavior.
- Protocol envelope structure, execution-scope semantics, identity validation
  rules.
- Secrets, provider credentials, infrastructure endpoints, deployment and
  environment flags — these stay in environment and site configuration and are
  never moved into Desk-editable settings.

A future proposal to make any of these configurable is a new security decision,
not a settings addition.

## Trust boundaries

Unchanged from `ARCHITECTURE.md` §A. The change moves work *from* the inference
side *to* the control plane. Inference's authority is strictly reduced: it loses
the ability to obtain metadata at all, and it gains no configuration authority.

## Request flow (metadata, developer capability, permitted by policy)

```
Browser → api.ask()  [Frappe session + CSRF]
  → capability derived live from frappe.get_roles()
  → envelope: user, site, mode=<capability>, execution_scope=frappe-attributed
              (no policy data in the envelope)
  → POST /orchestrate (service credential)
  → validate_gateway_envelope → exact scope match, site match, capability shape
  → orchestrator: route=erpnext, op=schema  (no authorization performed here)
  → _read_request{kind: schema}
  → api.py loop (bounded by MAX_READ_ROUNDS), dispatch on kind
  → control plane, metadata module:
       capability → not istable → not issingle → DocType exists
       → read NexMate Settings uncached → policy permits?
       → deny (no metadata retrieved)
       → allow → frappe.get_meta() → five-field projection
       → resolved effective bounds min(admin, ceiling) (refuse, do not truncate)
       → audit doctype_schema (fail-closed on audit_pending) → authorized_context
  → inference answers from authorized_context only
  → response-field allowlist applied
  → Browser
```

## Failure behavior

| Failure | Behavior |
|---|---|
| Missing/invalid Frappe session | refused at `api.ask()`; no upstream call |
| Role config malformed / role lookup raises | fail closed to `employee`; metadata denied |
| Execution scope not exact | 422; no coercion |
| Site mismatch | 403; no routing or retrieval |
| Partial envelope | 422; no legacy fallback |
| Authorization-bearing field without a complete envelope | refused; not consumed or forwarded |
| Inference requests unauthorized metadata | control plane refuses; no metadata retrieved |
| Settings absent / mode unset / mode invalid | policy denies; no metadata retrieved |
| `allowlist` with zero entries | policy denies; no metadata retrieved |
| Settings unreadable | policy denies; no metadata retrieved |
| DocType is `istable` or `issingle` | denied regardless of policy mode |
| DocType does not exist | collapsed into the same denial as every other refusal |
| Metadata audit write fails or is pending | fail closed; no metadata returned |
| Metadata exceeds its resolved effective bound | refused, not truncated |
| Configured numeric value outside its supported range | rejected at Settings save; a value reaching runtime anyway is clamped to the ceiling above, or to the default below the minimum |
| Configured value above the service ceiling | clamped to the ceiling at enforcement; never honored above it |
| Untouched save of a Single with unset `Int` settings | documented default is written; the effective bounds are unchanged and a second save still succeeds |
| Round budget exhausted | existing `gateway_read_round_limit` behavior |
| `frappe.get_meta()` raises | collapsed denial; no partial metadata |

## Risks / Trade-offs

- **Enabling a previously denied path is the main risk.** → The U5 adapter is
  untouched and its 40 adapter tests plus 19 non-legacy boundary tests are the
  regression floor. Live verification is a required task, not optional.
- **`all` mode is a broad disclosure.** It exposes structural information from
  every eligible DocType, **including custom applications installed on the
  site**. Combined with a `nexmate_developer_roles` that names a broadly held role,
  that is a meaningful disclosure surface. It is recorded as a development and
  testing posture, and `SECURITY.md` states the risk rather than implying `all` is
  appropriate for production.
- **Policy is administrator-controlled, so a misconfiguration is a real
  availability risk.** → It fails closed, and the failure is visible to the
  administrator through the configuration record itself.
- **Two-sided literal change can 422 the gateway.** → Both sides change in one
  commit; a test asserts the producer's value equals the consumer's accepted
  value.
- **Rollback reopens the legacy routes and removes the policy entirely.** →
  Recorded as requiring a compensating control. A pre-change revision has no
  metadata policy at all, so a rollback must be assessed for what it permits.
- **Three additive DocType synchronizations are required.** → One migration gate,
  preserving every U5 safeguard, because the U5 run recorded a migration that
  orphaned all four NexMate DocTypes.
- **The write path retains the shared credential.** → Explicit non-goal with the
  dependency map recorded so it is not forgotten.
- **Closing the pre-existing retrieval-scope and conversation exposures widens
  this change's scope.** → Accepted, because they share one root cause and one
  code site, and because any narrower fix would leave the "no-envelope path is
  closed" claim false. Recorded as pre-existing rather than as new findings.
- **Removing the inference-side schema short-circuit costs employee users a round
  trip.** → Accepted. Enforcement must live in the plane that owns identity and
  can audit the decision.
- **Two sides can disagree about a bound.** → The coordinated ceilings (D20):
  Frappe must never accept a payload inference rejects with 422. The clamp rule
  plus matching ceilings on both sides is what makes a dynamic bound safe.
- **A new Settings field is a new disclosure knob.** → Each numeric setting only
  narrows within its ceiling, and the ceilings themselves are constants. The
  Desk organization below keeps the surface reviewable.

## Desk organization (intended; administrator-friendly labels, stable fieldnames)

`NexMate Settings`

1. Developer & Schema Settings — Metadata Access Mode, Max Schema Fields,
   Max Schema Payload Size, Developer Roles.
2. Live Data Query Bounds — Max Records per Query, Max Fields per Query,
   Max Read Payload Size.
3. Execution Settings — Max Read Rounds.
4. Existing Metadata Access Rules — Metadata DocType Rules (unchanged).

## Migration Plan

No data migration is required. Three additive Frappe DocType schema
synchronizations are required, under one approval gate:

1. Add `doctype_schema` to the `action` options on `NexMate Audit Entry`.
2. Add the `NexMate Settings` Single DocType.
3. Add the `NexMate Metadata DocType Rule` child DocType.

The numeric settings in D16 are additional **fields** on the already-new
`NexMate Settings` record, not additional DocTypes: they ride the same
additive synchronization and the same gate, and they require no separate
migration step. Any future field added to `NexMate Settings` follows the same
rule — additive field, same gate, never a data migration.

Every U5 safeguard is preserved and the gate is approval-gated:

1. Obtain explicit migration approval, recorded in `DECISIONS.md`.
2. Verify `sites/apps.txt` lists `erpnext_ai_copilot`. The U5 run recorded that
   its absence, combined with the Redis-cached module map, caused
   `remove_orphan_doctypes()` to delete all four NexMate DocTypes.
3. Verify the app and module cache state, and that the module map resolves a
   controller for every NexMate DocType.
4. Back up the DocType definitions and the NexMate DocType data.
5. Run `bench --site <site> migrate`.
6. Verify exit status, absence of orphan-deletion output, survival of all
   existing NexMate DocTypes, presence of the two new DocTypes, and preservation
   of the pre-existing audit `action` and `outcome` options.
7. Record the result in this change's `verification-notes.md`, including the
   rollback ordering constraint: reverting an option list after events using it
   have been written leaves those values orphaned.

**Rollback.** Revert the deployment. Reverting restores the removed routes, which
is a security regression and requires an explicit compensating control rather
than a silent revert. The adapter holds no persisted authorization state — it
derives every decision from the live Frappe session — so rollback carries no
authorization-state risk for business reads.

## Open Questions

- Whether the `Developer` Frappe Role should ship as a default fixture or be
  created by the installer. Deferrable: the capability mechanism is
  configuration-driven either way, and it affects setup documentation rather than
  the specs or the approach.
- Whether `NexMate Settings` should later expose additional NexMate policies.
  Deferrable and deliberately not authorized here: this change introduces one
  Single because one administrator policy must exist, not a settings framework.
- Whether the metadata projection needs a further structural field. Deferrable:
  it is a projection value inside an already-bounded, already-specified response,
  and adding one does not change the model.
- Whether `all` mode should be administratively distinguishable from a merely
  unset mode in reporting. Deferrable: both resolve to the same enforcement, and
  the configuration record shows the state directly.
