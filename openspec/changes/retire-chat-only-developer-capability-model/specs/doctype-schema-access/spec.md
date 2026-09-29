## Purpose

Defines how an authenticated Frappe user with the Developer capability may
inspect ERPNext DocType metadata. Schema access is a metadata capability, not
a business-record read. Which DocTypes may be inspected is **not** a fixed
product list: it is an administrator-controlled, per-site **metadata access
policy** held in the `NexMate Settings` Single DocType. The policy is consulted
after capability, is evaluated before any `ALL`/`ALLOWLIST` decision, and
**fails closed** in every ambiguous or unavailable case.

## ADDED Requirements

### Requirement: Schema is capability-gated, not available by default

DocType schema/metadata access SHALL be available only to an authenticated
session holding the `developer` capability. The `employee` capability SHALL be
denied schema access, and that denial SHALL be enforced in the Frappe control
plane before any metadata is produced. A denial SHALL NOT be a conversational
string that happens to decline; it SHALL be an enforced refusal that performs
no metadata retrieval. Schema SHALL NOT be reachable by any caller that has not
established an authenticated Frappe session and a `developer` capability.

The capability gate SHALL be evaluated **before** any Frappe permission-based
check consulted for metadata, because Frappe's permission engine returns an
unconditional allow for the `Administrator` user as its first check. A
permission check performed ahead of the capability gate would therefore bypass
the capability model for that user.

#### Scenario: Developer receives schema

- **WHEN** a `developer`-capability user requests the schema of an eligible
  DocType and the metadata access policy permits it
- **THEN** the minimized schema is returned

#### Scenario: Employee denied schema

- **WHEN** an `employee`-capability user requests a DocType's schema
- **THEN** the request is refused and no metadata is produced or returned

#### Scenario: Unattributed caller denied schema

- **WHEN** a caller reaches the schema operation without an authenticated Frappe
  session and a derived developer capability
- **THEN** the request is refused before any metadata retrieval

#### Scenario: Forged capability does not grant schema

- **WHEN** a caller asserts developer capability without a matching real Frappe
  role
- **THEN** schema is refused and the asserted value is ignored

#### Scenario: Administrator bypass does not bypass the capability gate

- **WHEN** the session user is `Administrator`, which the Frappe permission
  engine would allow unconditionally
- **THEN** the capability gate is still evaluated first, and metadata is refused
  unless that user derives the `developer` capability from a configured role and
  the metadata access policy permits the DocType

### Requirement: Metadata access is governed by an administrator-controlled policy

Which DocTypes Developer metadata inspection may access SHALL be determined by a
**metadata access policy** held in the `NexMate Settings` Single DocType, and by
nothing else. The policy SHALL NOT be hard-coded in NexMate, SHALL NOT be read
from site configuration, SHALL NOT be extended into Frappe's core System
Settings, and SHALL NOT be supplied by the caller, the browser, or inference.

The policy SHALL carry a **metadata access mode** with exactly the supported
values `all` and `allowlist`, and, in `allowlist` mode, an administrator-
configured list of DocTypes held in the `NexMate Metadata DocType Rule` child
table. The list SHALL contain DocType references only: no field names, field
values, filter values, credentials, permission rows, or business data.

Only a user holding normal Frappe **write** permission on `NexMate Settings`
may modify the policy. Configuration authority SHALL be distinct from Developer
capability: a user who holds the `developer` capability obtains no authority to
change the policy, and a user who may change the policy gains no metadata access
by that fact.

The policy SHALL be read uncached for each metadata authorization decision so
that no stale policy can continue to grant access, and SHALL NOT be cached by
NexMate.

#### Scenario: Policy is server-side only

- **WHEN** the metadata access policy is consulted
- **THEN** it is read from the current site's `NexMate Settings` record in the
  Frappe control plane, and no policy value is accepted from the request, the
  browser, or the inference service

#### Scenario: All mode permits any eligible DocType

- **WHEN** the metadata access mode is `all`
- **THEN** a `developer`-capability user may inspect the metadata of any
  **eligible existing** DocType on the current site, where eligible means the
  DocType exists and is neither a child table nor a Single DocType

#### Scenario: Allowlist mode permits only configured DocTypes

- **WHEN** the metadata access mode is `allowlist`
- **THEN** a `developer`-capability user may inspect the metadata of only those
  DocTypes present in the `NexMate Metadata DocType Rule` child table, and any
  other DocType is refused

#### Scenario: Policy change takes effect on the next request

- **WHEN** an authorized user changes the metadata access mode or the configured
  DocType list and the change is committed
- **THEN** the next metadata authorization decision observes the new policy,
  with no restart and no cache flush

#### Scenario: Developer capability is not configuration authority

- **WHEN** a user holds the `developer` capability but lacks write permission on
  `NexMate Settings`
- **THEN** that user may not modify the policy, and their metadata access remains
  determined by the existing policy

#### Scenario: Policy is never exposed to the browser or to inference

- **WHEN** Desk boot information or the gateway envelope is constructed
- **THEN** neither carries the metadata access mode, the configured DocType list,
  nor any indication of configuration authority, and the browser cannot select or
  influence either policy mode

### Requirement: Metadata access policy fails closed

A metadata access policy that is absent, unset, invalid, unreadable, or
ambiguous SHALL deny metadata access. It SHALL NEVER default to the more
permissive mode. Specifically, a DENY SHALL result when the settings document
does not exist, when the mode is unset, when the mode is not a supported value,
when the mode is `allowlist` with zero configured entries, when the settings
record cannot be loaded, or when the configuration is otherwise invalid.

A configuration failure SHALL never widen metadata access. Because a Single
DocType that has never been saved is indistinguishable at the API level from one
saved with no rows, both SHALL resolve to the same denial.

#### Scenario: Settings document does not exist

- **WHEN** no `NexMate Settings` record exists on the site
- **THEN** metadata access is refused and no metadata is retrieved

#### Scenario: Mode is unset or invalid

- **WHEN** the metadata access mode is empty or is not one of the supported
  values
- **THEN** metadata access is refused and no metadata is retrieved

#### Scenario: Allowlist with zero entries

- **WHEN** the metadata access mode is `allowlist` and the configured DocType
  list contains no entries
- **THEN** metadata access is refused and no metadata is retrieved

#### Scenario: Settings cannot be loaded

- **WHEN** reading the settings record raises or returns unusable data
- **THEN** metadata access is refused and the failure is surfaced as an internal
  denial without partial metadata

#### Scenario: No stale policy continues to grant access

- **WHEN** a previously permissive policy has been narrowed
- **THEN** no cached value from an earlier request continues to permit metadata
  access after the change is committed

### Requirement: DocType eligibility excludes child tables and Single DocTypes

Child tables (`istable`) and Single DocTypes (`issingle`) SHALL be excluded from
the metadata capability regardless of the metadata access mode. These
exclusions SHALL be evaluated **before** the `all` or `allowlist` decision, so
that neither mode can admit them.

These exclusions are structural properties of the Frappe DocType definition,
not an administrator policy, and SHALL NOT be configurable. The metadata
implementation SHALL enforce them independently and SHALL NOT rely on the
business-record read adapter for them.

#### Scenario: Child table denied in all mode

- **WHEN** the metadata access mode is `all` and the requested DocType is a child
  table
- **THEN** the request is refused and no metadata is produced

#### Scenario: Child table denied in allowlist mode

- **WHEN** the metadata access mode is `allowlist`, the requested DocType appears
  in the configured list, and it is a child table
- **THEN** the request is refused and no metadata is produced

#### Scenario: Single DocType denied in all mode

- **WHEN** the metadata access mode is `all` and the requested DocType is a Single
  DocType
- **THEN** the request is refused and no metadata is produced

#### Scenario: Single DocType denied in allowlist mode

- **WHEN** the metadata access mode is `allowlist`, the requested DocType appears
  in the configured list, and it is a Single DocType
- **THEN** the request is refused and no metadata is produced

#### Scenario: Exclusions are not configurable

- **WHEN** an administrator inspects the policy surface
- **THEN** there is no setting that can admit a child table or a Single DocType to
  the metadata capability

### Requirement: Configured DocTypes are validated

A DocType placed in the configured metadata list SHALL be validated when the
policy is saved. The stored reference SHALL resolve to an existing Frappe
DocType, SHALL NOT be a child table, SHALL NOT be a Single DocType, and SHALL
NOT duplicate an entry already present. A value that cannot resolve to a DocType
name SHALL be rejected at save time rather than silently stored.

Validation SHALL be enforced by the framework where the framework provides it —
a link to the DocType record enforces existence and exact naming, and rejects
values that are not DocType names — and by application validation for the
structural exclusions and duplicates.

#### Scenario: Nonexistent DocType rejected at save

- **WHEN** an authorized user saves a configured entry naming a DocType that does
  not exist
- **THEN** the save is refused and the entry is not stored

#### Scenario: Wildcard rejected at save

- **WHEN** an authorized user saves a configured entry containing a wildcard or a
  partial name rather than an exact DocType name
- **THEN** the save is refused and the entry is not stored

#### Scenario: Child table rejected at save

- **WHEN** an authorized user saves a configured entry naming a child table
- **THEN** the save is refused and the entry is not stored

#### Scenario: Single DocType rejected at save

- **WHEN** an authorized user saves a configured entry naming a Single DocType
- **THEN** the save is refused and the entry is not stored

#### Scenario: Duplicate entry rejected at save

- **WHEN** an authorized user saves a configured DocType that is already present
  in the list
- **THEN** the save is refused and no duplicate entry is stored

### Requirement: Schema is served by Frappe in-process

Schema SHALL be produced by the Frappe control plane from live local DocType
metadata in the same request process, using the same request-time Frappe session
as every other gateway operation. It SHALL NOT be obtained through an outbound
HTTP call to the ERPNext instance, and SHALL NOT use a shared, site-wide or
per-user ERPNext API credential, master key, Administrator password or database
credential. The schema operation SHALL introduce no additional network hop
between Frappe and inference beyond the existing authorized round trip.

The policy and capability inputs to that decision SHALL both come from the
authenticated Frappe session. The policy SHALL NOT be supplied by, echoed to, or
re-derived by inference.

#### Scenario: No shared credential required for schema

- **WHEN** a developer-capability schema request is served
- **THEN** no shared ERPNext API credential is read, required or transmitted, and
  the operation succeeds with those credentials absent

#### Scenario: Metadata reflects live local state

- **WHEN** a schema request is served
- **THEN** the returned metadata is derived from the live local DocType definition
  rather than from a cached copy or a remote instance

#### Scenario: Policy is re-read for each decision

- **WHEN** two metadata authorization decisions are made for two different users
  on the same site
- **THEN** each decision reads the policy at the time it is made and neither
  observes the other's result

### Requirement: Schema output is minimized and bounded

Schema responses SHALL be a minimized, fixed-shape projection limited to the
structural field attributes `fieldname`, `fieldtype`, `label`, `reqd` and
`read_only`, and to no others. A response SHALL NOT include the DocType
`permissions` child table, role or permlevel mappings, Select or Link field
`options` values, custom or confidential field markers, field values, rows, or
any other content that reveals the site's access-control model or business
vocabulary.

The response SHALL be bounded in shape and serialized size, and SHALL be rejected
rather than truncated if it exceeds its bound. The effective bounds SHALL be
resolved from the administrator-configured `max_schema_fields` and
`max_schema_bytes` settings as `min(admin_configured_value,
immutable_service_ceiling)`, with defaults of 300 projected field entries and
65536 serialized bytes. The response SHALL be refused rather than truncated when
either effective bound is exceeded.

#### Scenario: Projection is limited to the declared attributes

- **WHEN** a permitted schema resolution succeeds
- **THEN** the response contains only `fieldname`, `fieldtype`, `label`, `reqd`
  and `read_only` for each projected field, and no other attribute

#### Scenario: Permissions table is not disclosed

- **WHEN** a developer-capability user requests a DocType's schema
- **THEN** the response contains no role permission rows, no permlevel mapping
  and no information from which the site's permission model could be reconstructed

#### Scenario: Field options are not disclosed

- **WHEN** a DocType contains Select or Link fields whose options carry business
  values
- **THEN** those option values are absent from the schema response

#### Scenario: Field values are never disclosed

- **WHEN** any schema response is produced
- **THEN** it contains no field values, no document rows, and no business record
  data of any kind

#### Scenario: Projected field bound is enforced

- **WHEN** a DocType's projection would exceed the resolved effective field bound
- **THEN** the response is refused rather than truncated or partially returned

#### Scenario: Serialized size bound is enforced

- **WHEN** a schema response would exceed the resolved effective serialized-byte bound
- **THEN** it is refused rather than truncated or partially returned

#### Scenario: Bounds resolve from administrator settings within ceilings

- **WHEN** an administrator configures `max_schema_fields` or `max_schema_bytes`
  inside the supported range
- **THEN** the next metadata decision enforces the configured value, and the
  defaults of 300 entries and 65536 bytes apply while unconfigured

### Requirement: Schema access is audited

Every schema resolution SHALL produce exactly one audit event using the dedicated
metadata audit action, recording the actor, the site, the operation, the DocType
and the outcome, and SHALL NOT record returned metadata content or field values.

Schema audit SHALL be fail-closed: if the audit event cannot be persisted, the
schema SHALL NOT be returned. The audit call's result SHALL be inspected, and a
pending or otherwise unconfirmed durable write SHALL be treated as failure. An
audit outcome SHALL NOT be shared with or invented by another action's vocabulary.

Schema refusals SHALL be externally indistinguishable from any other
unauthorized metadata refusal. The caller-visible refusal SHALL use the fixed
answer `Schema not found or access denied.` and the fixed route metadata value
`frappe-schema+denied`, SHALL NOT reuse the business-record denial wording or
route metadata, and SHALL NOT carry the internal reason. The internal reason
SHALL be preserved only in the audit event. A requested DocType that does not
exist SHALL collapse into the same caller-visible denial as every other metadata
refusal, so that the metadata capability cannot be used to discover which DocTypes
a site defines.

#### Scenario: Successful schema is audited

- **WHEN** a permitted schema resolution succeeds
- **THEN** exactly one metadata-only audit event is recorded with actor, site,
  DocType and outcome, and containing no field values

#### Scenario: Audit failure denies schema

- **WHEN** the schema audit event cannot be persisted, or the write is reported as
  pending
- **THEN** no schema is returned and the request fails closed

#### Scenario: Refusal does not disclose the reason

- **WHEN** a schema request is refused
- **THEN** the caller-facing response does not distinguish denied-by-capability
  from denied-by-policy from denied-by-structural-exclusion from not-found

#### Scenario: Nonexistent DocType is indistinguishable

- **WHEN** a schema request names a DocType that does not exist on the site
- **THEN** the caller-facing response is identical to the response for an existing
  but refused DocType, and the distinction is recorded only in the audit event

#### Scenario: Exactly one access event per resolution

- **WHEN** one metadata request is served, whether permitted or refused
- **THEN** exactly one metadata access audit event is recorded for that request and
  no additional metadata access action is emitted

### Requirement: Metadata operational limits are administrator-configured within immutable ceilings

The numeric operational limits governing metadata SHALL be administrator
settings on `NexMate Settings`, each validated at save time against its
supported range and each enforced at runtime as
`effective_limit = min(admin_configured_value, immutable_service_ceiling)`.
Runtime enforcement SHALL re-check the ceiling independently of Settings
validation, so a value reaching runtime outside its range is clamped rather
than honored. The ceilings SHALL NOT be editable through `NexMate Settings`,
site configuration, the request, the browser, or inference.

The settings, with defaults, minima, administrator maxima and immutable
service ceilings, SHALL be:

- `max_schema_fields`: default 300, minimum 1, administrator maximum 500,
  service ceiling 500. Controls the maximum number of metadata fields returned
  for a permitted DocType.
- `max_schema_bytes`: default 65536 bytes (64 KB), minimum 4096 bytes (4 KB),
  administrator maximum 131072 bytes (128 KB), service ceiling 131072 bytes.
  Controls the maximum serialized metadata payload size. Desk may display and
  edit this value in KB; runtime enforcement is byte-based.

Request and inference timeouts SHALL NOT be added to `NexMate Settings` in
this change; timeouts, secrets, endpoints, provider configuration,
infrastructure settings and deployment flags remain deployment and site
configuration.

#### Scenario: Defaults apply while unconfigured

- **WHEN** the numeric settings have never been configured
- **THEN** metadata decisions enforce 300 projected field entries and 65536
  serialized bytes

#### Scenario: Supported values take effect on the next decision

- **WHEN** an authorized administrator saves a supported value and the change
  is committed
- **THEN** the next metadata decision enforces it, with no restart and no
  cache flush

#### Scenario: Out-of-range values are rejected at save

- **WHEN** an authorized administrator attempts to save a numeric value outside
  its supported range
- **THEN** the save is refused and the previous value is retained

#### Scenario: Above-ceiling values are clamped at runtime

- **WHEN** a value above the service ceiling reaches runtime enforcement by any
  path
- **THEN** enforcement clamps it to the ceiling rather than honoring it, and
  the ceiling value itself is never exceeded

### Requirement: Security invariants are not administrator-configurable

Administrator settings SHALL narrow operational behavior within their supported
ranges and SHALL NOT redefine security invariants. The following SHALL remain
hardcoded and service-controlled, and no NexMate Settings value SHALL alter
them: Frappe identity and session authority; Frappe permission enforcement; the
capability model and its fail-closed behavior; no implicit elevation; the
business-record DocType and field allowlists; forbidden APIs; filter deny
rules; the anti-exfiltration projection discipline; the metadata projection
attribute set (`fieldname`, `fieldtype`, `label`, `reqd`, `read_only`); audit
vocabulary, audit integrity and collapse behavior; protocol envelope structure;
execution-scope semantics; identity validation rules; secrets, provider
credentials, infrastructure endpoints and deployment/environment flags.

#### Scenario: Projection attributes cannot be widened by configuration

- **WHEN** an administrator inspects the settings surface
- **THEN** there is no setting that adds an attribute to the metadata
  projection or admits business values, rows, options, permissions or
  credentials into it

#### Scenario: Ceilings cannot be raised by configuration

- **WHEN** an administrator inspects the settings surface
- **THEN** there is no setting, site-configuration key, request field or
  browser control that raises an immutable service ceiling
