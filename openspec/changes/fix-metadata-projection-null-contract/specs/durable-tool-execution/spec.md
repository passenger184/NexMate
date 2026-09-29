## Purpose

Records the consumer side of the metadata representation contract. The
authorized-context round trip is shared between business reads and metadata
resolutions, and no downstream consumer may be narrower than the approved
ceiling. This delta makes explicit that a Frappe-authorized metadata payload
must not be refused by the inference validator because the producer's
representation did not match the validator's expectations, while the validator
itself remains strict.

## ADDED Requirements

### Requirement: Frappe-authorized metadata payloads are admitted within the approved ceilings

The authorized-context round trip MAY be shared between a business read and a
metadata resolution. The inference-side validator SHALL admit a Frappe-authorized
metadata payload that is within the approved metadata ceilings, which are 500
projected field entries and 131072 serialized bytes, and which the Frappe
control plane resolves per decision as `min(administrator_configured_value,
immutable_service_ceiling)`.

The producing control plane SHALL guarantee that a metadata projection is
total — exactly the declared attributes, each present once and each a non-null
string or boolean — so that a payload refused by the validator can never be
attributed to a producer representation mismatch. The validator's strict
assertion that every projected metadata value is a string, a boolean or an
integer SHALL be retained unchanged: it is the enforcement point that makes the
producer's guarantee observable, and it SHALL continue to refuse a malformed
payload. Admitting a conforming payload SHALL NOT require relaxing, disabling
or re-scoping that assertion, and the business-read bounds, the business-read
validator and the business-record adapter SHALL be unchanged by this
requirement.

#### Scenario: A conforming metadata payload is admitted within the ceilings

- **WHEN** a metadata payload produced by the Frappe control plane, within the
  approved metadata ceilings and conforming to the total projection contract,
  reaches the inference validator
- **THEN** it is admitted, and it SHALL NOT be refused because of a producer
  representation mismatch

#### Scenario: The consumer remains strict about the metadata projection

- **WHEN** a metadata payload reaches the inference validator with a missing
  declared attribute, an extra attribute, or a projected value that is not a
  string, boolean or integer
- **THEN** it is refused with the standard invalid-context response, unchanged
  by any producer guarantee

#### Scenario: Business-read contract is unaffected

- **WHEN** the business-read bounds, the business-read authorized-context
  validator and the business-record read adapter are inspected after this
  change
- **THEN** their row, field and byte bounds and their validation behavior are
  unchanged
