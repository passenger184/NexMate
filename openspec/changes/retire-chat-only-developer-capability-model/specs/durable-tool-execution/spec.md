## ADDED Requirements

### Requirement: Metadata reads are not business reads and are capability-gated

A DocType metadata operation SHALL be classified as a metadata operation, not a
business read. It SHALL NOT be described by, or consume, the business-read
contract: it SHALL NOT return business record data, SHALL NOT be counted against
the business read's field, row or size bounds, and SHALL NOT share the business
read's authorization surface, because a DocType definition contains no business
record values. Metadata SHALL be gated by the authenticated user's NexMate
capability and by the site's administrator-controlled metadata access policy, both
of which SHALL be evaluated in the Frappe control plane against the live session
user, and SHALL NOT require, create or execute a durable proposal. A metadata
request SHALL NOT be permitted on any path that has not established an
authenticated Frappe session, and a denied metadata request SHALL NOT disclose
whether the DocType exists.

The authorized-context round trip MAY be shared between a business read and a
metadata request, and both SHALL share the same bounded round budget. Sharing the
transport does not merge the two contracts: a metadata result SHALL satisfy its
own declared shape and bounds, and a metadata request SHALL NOT be evaluated by
the business-read request validation, whose supported operation set deliberately
excludes metadata operations.

The existing business-read requirements remain unchanged by this addition,
including that a business read SHALL NOT require a durable proposal and SHALL be
authorized by the Frappe-native boundary against the live session user.

#### Scenario: Metadata is not a business read
- **WHEN** a DocType metadata operation is performed
- **THEN** it is not treated as a business read, returns no business record values, and shares no authorization surface or field, row and size bounds with business-record reads

#### Scenario: Metadata requires no proposal
- **WHEN** a permitted metadata request is served
- **THEN** it proceeds without a durable proposal, creates no proposal and no execution record, and does not enter the write approval lifecycle

#### Scenario: Metadata is capability-gated in the control plane
- **WHEN** a metadata request is made
- **THEN** the control plane checks the live session user's capability first and refuses the request without retrieving metadata when the capability is absent

#### Scenario: Metadata is policy-gated after capability
- **WHEN** a metadata request is made by a user who holds the developer capability
- **THEN** the control plane evaluates the site's administrator-controlled metadata access policy and refuses the request without retrieving metadata when the policy does not permit that DocType

#### Scenario: Unattributed metadata is refused
- **WHEN** a metadata request arrives without an authenticated Frappe session
- **THEN** it is refused before any metadata retrieval

#### Scenario: Refusal does not reveal DocType existence
- **WHEN** a metadata request is refused
- **THEN** the caller cannot distinguish a denied capability from a non-existent DocType, from a denied policy, or from any other metadata refusal

#### Scenario: Shared round trip keeps separate contracts
- **WHEN** a metadata request and a business read traverse the same bounded authorized-context round trip
- **THEN** the metadata result satisfies its own declared shape and bounds and is not validated or bounded by the business-read request contract

#### Scenario: Business read requirements unchanged
- **WHEN** the business-read contract requirements are inspected after this change
- **THEN** their permission declaration, minimization, audit and not-approval-gated behavior are unchanged, and their numeric bounds resolve from administrator settings within immutable ceilings with defaults preserving current behavior

### Requirement: Business-read operational limits are administrator-configured within immutable ceilings

The numeric operational limits governing business-record reads SHALL be
administrator settings on `NexMate Settings`, each validated at save time
against its supported range and each enforced at runtime as
`effective_limit = min(admin_configured_value, immutable_service_ceiling)`.
Runtime enforcement SHALL re-check the ceiling independently of Settings
validation. The ceilings SHALL NOT be editable through `NexMate Settings`,
site configuration, the request, the browser, or inference.

The settings, with defaults, minima, administrator maxima and immutable
service ceilings, SHALL be:

- `max_read_rows`: default 20, minimum 1, administrator maximum 100, service
  ceiling 100. Controls the maximum business-record rows returned for a read
  request.
- `max_read_fields`: default 20, minimum 1, administrator maximum 50, service
  ceiling 50. Controls the maximum business-record fields returned for a read
  request.
- `max_read_bytes`: default 65536 bytes (64 KB), minimum 4096 bytes (4 KB),
  administrator maximum 131072 bytes (128 KB), service ceiling 131072 bytes.
  Controls the maximum business-record read payload size. Desk may display and
  edit this value in KB; runtime enforcement is byte-based.

These limits SHALL narrow, never widen: the effective read request SHALL remain
constrained by the intersection of Frappe authorization and NexMate policy, and
no setting SHALL permit a record, field, row or byte that Frappe denies or
that the DocType and field allowlists exclude.

#### Scenario: Read-bound defaults preserve current behavior
- **WHEN** the numeric read settings have never been configured
- **THEN** reads enforce at most 20 rows, 20 fields and 65536 serialized bytes

#### Scenario: Saving Settings without editing the numeric bounds is a no-op
- **WHEN** an administrator saves `NexMate Settings` without modifying any
  numeric bound, including when none has ever been configured
- **THEN** each unset bound is stored as its documented default, the effective
  bounds are unchanged, and a second ordinary save also succeeds, because Frappe
  materialises an untouched `Int` as `0` on the write path

#### Scenario: An explicit out-of-range bound is still refused
- **WHEN** an administrator saves a numeric bound below its minimum or above
  its administrator maximum, including an explicit `0`
- **THEN** the save is refused, and only an unset or blank bound is treated as
  unconfigured

#### Scenario: Supported read bounds take effect on the next read
- **WHEN** an authorized administrator saves a supported value and the change
  is committed
- **THEN** the next business read enforces it, with no restart and no cache
  flush, up to the immutable service ceiling

#### Scenario: Read bounds never widen authorization
- **WHEN** an administrator raises a read bound within its supported range
- **THEN** reads may return more of what Frappe authorizes but never anything
  Frappe denies, and never above the service ceiling

#### Scenario: Out-of-range read bounds are rejected or clamped
- **WHEN** a read-bound value outside its supported range is saved, or reaches
  runtime enforcement by any path
- **THEN** the save is refused in the first case, and enforcement clamps to
  the ceiling in the second, so the ceiling value itself is never exceeded

#### Scenario: Adapter bounds match the service ceilings
- **WHEN** a business read carries rows, fields or bytes up to the immutable
  service ceiling (100 rows, 50 fields, 131072 bytes)
- **THEN** the business-record read adapter accepts it for authorization, and
  values above the ceilings are refused by the adapter itself with the
  standard collapsed denial, independent of any administrator setting

#### Scenario: No downstream consumer is narrower than the approved ceiling
- **WHEN** a Frappe-authorized business context within the approved ceilings
  (100 rows, 50 fields, 131072 bytes) reaches the inference service
- **THEN** it is admitted by the authorized-context validator, and only a
  context above those ceilings is refused, so a consumer bound may never
  discard a read Frappe already authorized
