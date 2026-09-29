## Why

`retire-chat-only-developer-capability-model` introduced a two-sided metadata
contract: Frappe produces a five-attribute projection, and the inference service
validates it before answering. The specification defined the **attribute set**
but never defined the **value representation**, so the two sides could disagree
about a value without either being in breach of a written rule.

They do disagree, and the disagreement breaks the product.

Frappe stores a `DocField.label` as NULL when the field was saved without one.
That is normal for every `Section Break`, `Column Break` and `HTML` field, and
it also occurs on ordinary data fields. `doctype_meta.project_meta` passed the
value through unchanged, so a null label crossed the trust boundary. The
inference validator requires every projected value to be `str`, `bool` or
`int`, so it refused the payload with HTTP 422.

Measured on the test site (`frontend`, Frappe 16.31.0 / ERPNext 16.33.0), over
two distinct populations:

- **Site-wide**, every `DocField` row in the database, including child tables
  and NexMate's own DocTypes: **2,211 null `label` values across 13,673 rows**,
  spanning 14 fieldtypes.
- **Metadata-eligible**, the 398 non-child, non-Single, non-NexMate DocTypes the
  metadata capability can reach: **270 of 398** produced a projection the
  consumer refused and **128** were clean, from 1,393 null labels across 8,602
  fields. `Customer` — a representative master DocType — has 21 null labels in
  87 fields.

Only `label` is affected. Across the eligible population `fieldname`,
`fieldtype`, `reqd` and `read_only` each had **zero** nulls; the contract below
nonetheless guarantees all five are non-null, because the guarantee is about what
the producer will emit rather than about what the current data happens to hold.

The 128 that passed did so only because none of their fields lacked a label.

Every affected DocType fails the *same single check*, at
`service/auth.py:165`. Nothing about authorization, capability, policy or
allowlists is involved: the Frappe control plane resolves and serves the
projection successfully, and the failure happens afterwards, in the consumer.
This is a producer/consumer **representation-contract** mismatch.

The consumer is correct to be strict. The producer is the side that creates the
value, so it is the side that must guarantee the representation.

## What Changes

- `doctype_meta.project_meta` emits a **total** projection: every one of the
  `fieldname`, `fieldtype`, `label`, `reqd`, `read_only` attributes is a
  concrete scalar and never `null`.
- Nullable string metadata (`label`, and defensively `fieldname`/`fieldtype`)
  is normalized to `""`. Nullable boolean metadata (`reqd`, `read_only`) is
  normalized to `false`. Integer flag values remain coerced to `bool`.
- **Nothing else is coerced.** A value that is already a string or a boolean
  crosses unchanged. There is no general `str(value)` conversion and no
  fieldtype special-casing.
- The specification now states the value contract explicitly, in a new
  requirement added to `doctype-schema-access`, and the matching
  consumer-boundary requirement added to `durable-tool-execution`. Both are
  `ADDED` rather than `MODIFIED`, because neither target capability/requirement
  exists in `openspec/specs/` yet — see the OpenSpec authoring note in
  `verification-notes.md`.
- The `durable-tool-execution` delta records that a Frappe-authorized metadata
  payload within the approved ceilings must not be rejected by the inference
  validator because of a producer representation mismatch, and that the
  validator stays strict.

### Breaking changes

None. The wire shape is unchanged — same five keys, same order, same bounds. A
`label` that was `null` is now `""`. No endpoint, envelope, field name,
ceiling, policy or status code changes, and nothing is removed.

## Capabilities

### New Capabilities

None. This corrects an existing contract; it introduces no capability.

### Modified Capabilities

Neither delta modifies an existing requirement. Both add a new one, because
both capabilities are still owned by the unarchived
`retire-chat-only-developer-capability-model` and a `MODIFIED` delta against a
not-yet-archived target would be refused at archive time.

- **doctype-schema-access**: adds **"Schema projection values are total
  scalars"** alongside, and cross-referencing by name, the existing
  "Schema output is minimized and bounded". It states the value contract —
  five attributes exactly, none ever null, strings for
  `fieldname`/`fieldtype`/`label`, booleans for `reqd`/`read_only`, nullable
  string → `""`, nullable boolean → `false`, no other coercion — and records
  that the representation is not administrator-configurable. Four scenarios
  are added.
- **durable-tool-execution**: adds **"Frappe-authorized metadata payloads are
  admitted within the approved ceilings"**. It states that a Frappe-authorized
  metadata payload within the approved ceilings is admitted by the inference
  validator, that the producer's totality guarantee is what makes it so, and
  that the validator's strict value assertion is retained unchanged. Three
  scenarios are added, including one asserting the business-read bounds,
  validator and adapter are unaffected.

## Impact

- **Affected capability behavior:** DocType metadata for DocTypes that contain an
  unlabelled field becomes reachable end to end instead of failing closed at the
  consumer. This is a strict availability improvement and a widening of nothing:
  the same five structural attributes are returned, with no business value,
  `options`, `permissions` or credential in any of them.
- **Code:** `frappe_app/erpnext_ai_copilot/doctype_meta.py`, the
  `project_meta` value-normalization block only. Authorization order, metadata
  policy, access mode, structural exclusions, ceilings, audit behaviour,
  control-plane routing and response structure are untouched.
- **Unchanged by decision:** `service/auth.py` stays strict; `audit.py` is
  byte-identical; the business-read adapter, allowlists and authorization matrix
  are untouched; no credential, permission mechanism or setting is added.
- **Out of scope:** audit durability. The investigation established that the
  audit row written for the previously failing `Customer` request was inserted
  before the consumer saw the payload and then destroyed by the normal Frappe
  request rollback after the 422. That rollback behaviour is recorded in
  `verification-notes.md` as a separate future hardening item and is deliberately
  not addressed here.
- **Task 16.3:** remains unchecked. This change does not exercise the
  browser-rendered Desk hop, which is still untested because no browser is
  available in the environment.
