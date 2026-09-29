## Purpose

Corrects the **value representation** of the minimized metadata projection. The
attribute set and the bounds are already defined by
`retire-chat-only-developer-capability-model`; this delta adds the missing value
contract, without which the producer could emit a `null` attribute that the
strictly-validating inference consumer is obliged to refuse.

## ADDED Requirements

### Requirement: Schema projection values are total scalars

Schema responses SHALL be a minimized, fixed-shape projection limited to the
structural field attributes `fieldname`, `fieldtype`, `label`, `reqd` and
`read_only`, and to no others, as established by the requirement "Schema output
is minimized and bounded". A response SHALL NOT include the DocType
`permissions` child table, role or permlevel mappings, Select or Link field
`options` values, custom or confidential field markers, field values, rows, or
any other content that reveals the site's access-control model or business
vocabulary.

The projection SHALL additionally be **total**: for every projected field, each
of the five declared attributes SHALL be present exactly once and SHALL never
be `null`. `fieldname`, `fieldtype` and `label` SHALL be strings, and `reqd` and
`read_only` SHALL be booleans. The producing control plane SHALL normalize a
nullable string attribute to the empty string and a nullable boolean attribute
to `false`, and SHALL coerce an integer flag to a boolean. It SHALL NOT emit any
other value for those attributes, SHALL NOT drop an attribute, and SHALL NOT
coerce any other value. This guarantee holds for every eligible DocType,
including those whose fields carry no label.

The value representation is a hardcoded producer guarantee and SHALL NOT be
administrator-configurable. No `NexMate Settings` value SHALL alter the null
mapping, the string/boolean typing of an attribute, the attribute set, or the
bounds; those remain service-controlled exactly as before.

#### Scenario: Projection is limited to the declared attributes

- **WHEN** a permitted schema resolution succeeds
- **THEN** the response contains only `fieldname`, `fieldtype`, `label`, `reqd`
  and `read_only` for each projected field, and no other attribute

#### Scenario: Every projected attribute is a total scalar

- **WHEN** a permitted schema resolution succeeds for any eligible DocType
- **THEN** each projected field carries exactly the five declared attributes,
  each exactly once; `fieldname`, `fieldtype` and `label` are strings, `reqd`
  and `read_only` are booleans, and no attribute is `null`

#### Scenario: Fields without a label are served, not refused

- **WHEN** a permitted DocType has fields stored without a label, including
  layout fields and ordinary data fields
- **THEN** the resolution succeeds, and each such `label` is the empty string
  rather than a null, so the projection is still admitted by the consumer

#### Scenario: Projection value representation is not configurable

- **WHEN** the administrator settings surface is inspected
- **THEN** there is no setting that changes the null mapping, the
  string/boolean typing of a projected attribute, the attribute set, or the
  effective bounds
