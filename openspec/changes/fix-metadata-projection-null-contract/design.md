# Design — fix-metadata-projection-null-contract

## The gap

`retire-chat-only-developer-capability-model` created a two-sided contract:

```
Frappe control plane  ──produces──▶  authorized context  ──consumes──▶  inference validator
  doctype_meta.project_meta                                      service.auth.validate_metadata_context
```

D20 already requires that the two sides stay coordinated — it mandates
coordinated metadata field and byte ceilings "on both sides, so Frappe never
accepts a payload inference rejects with HTTP 422". What D20 did not say is how
the producer represents a value the schema allows to be absent. It coordinated
the **bounds**; it never specified the **value representation**. The consumer
therefore enforced a scalar guarantee its producer had never made, and the
mismatch only surfaced in production.

## D22 — The metadata producer owns a total scalar projection

**Decision.** `doctype_meta.project_meta` SHALL emit, for every projected field,
exactly the five declared attributes and no others, and SHALL emit each as a
concrete scalar:

| attribute | representation | null mapping |
|---|---|---|
| `fieldname` | `str` | `None` → `""` |
| `fieldtype` | `str` | `None` → `""` |
| `label` | `str` | `None` → `""` |
| `reqd` | `bool` | `None` → `false`; integer → `bool` |
| `read_only` | `bool` | `None` → `false`; integer → `bool` |

No other value is coerced. A value that is already a `str` or a `bool` crosses
unchanged. There is no general `str(value)` conversion, no key is dropped, and
no fieldtype — layout or otherwise — is special-cased.

**Why the producer.** The producer is the trust boundary at which the metadata
representation is created. A consumer that validates a value it cannot influence
has two options: accommodate the producer, or be right to refuse. The first
weakens the boundary; the second is only correct if the producer has made the
guarantee. Guarantee belongs with the creator of the value.

**Why the null is normal, not corruption.** Frappe's `DocField.label` column is
nullable and is left NULL whenever a field is saved without an explicit label.
That is the ordinary representation of "this field has no label". Emitting it
verbatim is a representation bug, not a data-integrity problem, and it needs a
representation fix rather than a relaxation of the check that caught it.

**Why the mapping is `""` and not a key drop.** The projection is a closed,
fixed-shape object. Dropping `label` would make the key set data-dependent and
would require the consumer to accept a variable key set, weakening the very
attribute-set guarantee D21 protects. `""` is an exact stand-in for "no label
was set" and discloses nothing the `null` did not.

**Why this closes a class, not one case.** Null labels are not confined to
layout fields. Measured over every `DocField` row on the site (13,673 rows,
2,211 null labels) they occur across **14 fieldtypes**: the 5 layout types
`Column Break` (1,561), `Section Break` (587), `HTML` (28), `Table` (12) and
`Text Editor` (4) account for 2,192 of them, and the remaining 19 fall on
ordinary data fieldtypes — `Data` (4), `Text` (3), `Code` (3), `Float` (3),
`Datetime` (2), `Image` (1), `Small Text` (1), `Select` (1), `Dynamic Link` (1).
Restricted to the 398 metadata-eligible DocTypes (8,602 fields, 1,393 null
labels) the same shape holds across 9 fieldtypes, and exactly one DocType
(`Success Action`) has its *only* null label on a non-layout `Data` field — so
a layout-fieldtype special case would still leave it failing. The rule is
therefore about the *attribute*, not the fieldtype.

**Why the existing code already points this way.** `project_meta` previously
carried the comment *"Normalize only the flag types, never any business value"*
and already normalised `reqd`/`read_only` from `None` to `False`. This change
generalises that one mechanism to the whole attribute set and removes the
incidental blanket `str(value)` conversion, so that the rule is the declared
contract and nothing more.

## The consumer stays strict

`service/auth.py` is **unchanged**. Its assertion that every projected value is
`str`, `bool` or `int` is the enforcement point that makes D20 verifiable rather
than assumed, and it must keep catching a genuinely malformed projection.

Relaxing it was considered and rejected:

- It would remove the second of two independent layers. The producer's
  guarantee is not observable from outside; the validator is.
- It would only fix `label`. Any future nullable projected attribute would
  re-break the round trip.
- It would make the validator strictly more permissive than its sibling
  `validate_authorized_context` for business reads (`service/auth.py:173`, a
  separate function that dispatches to the metadata validator rather than
  replacing it). That validator asserts no value types at all on the values in
  `data` — it checks only the container shape, the key subset against
  `fields_returned`, and the bounds — precisely because the business-read
  producer already guarantees `as_dict(no_nulls=True)`
  (`erpnext_read.py:425`). Making the producer total restores that symmetry;
  relaxing the consumer entrenches the asymmetry.
- It would admit a nullable value into a security-adjacent structure for no
  benefit: `""` conveys exactly what `None` did.

## Relationship to D21 — recorded here, not by editing the other change

D21 ("Security invariants stay hardcoded") already fixes the metadata
projection **attribute set** (`fieldname`, `fieldtype`, `label`, `reqd`,
`read_only`) as a hardcoded invariant, with the note "bounds are tunable,
attributes are not". It does not mention value representation, which is precisely
why the gap existed.

D21 is **not edited by this change.** It lives in the committed, pushed
`retire-chat-only-developer-capability-model` design ledger; rewriting a
delivered artifact of another change is out of scope, and that change's audit
trail must not be disturbed. The relationship is therefore recorded in exactly
two places in *this* change:

1. here, so a reader of D22 knows what D21 already covers; and
2. in the `doctype-schema-access` delta, which carries the operative
   clarification — the value representation "is a hardcoded producer guarantee
   and SHALL NOT be administrator-configurable".

D22 is not a restatement of D21. **D21 names the invariant that the projection
has a fixed attribute set; D22 is the producer-side mechanism by which those
attributes are made total.** D22 is stated once and only once.

## Safety

The change is serialization-only and runs strictly after every authorization
gate. It cannot widen access: it can only substitute `""`/`false` for a value
that carried no disclosure. No key is added, no attribute is added, no business
value, `options`, `permissions` or credential can enter the projection, and the
metadata capability gate, policy, structural exclusions and ceilings are all
untouched.

## Considered and rejected

- **Consumer accepts `None` for `label`.** Rejected for the reasons above.
- **Drop the `label` key when absent.** Rejected: makes the key set
  data-dependent and weakens D21's attribute-set guarantee.
- **Special-case `Section Break` / `Column Break`.** Rejected: 19 ordinary data
  fields also carry null labels and would still fail.
- **Blank `label` for every fieldtype, or omit layout fields entirely.** Layout
  fields are structural; omitting them would change `field_count` semantics and
  hide real schema shape from a developer who legitimately asked for it.
- **Relax the consumer for all five attributes.** Rejected: unnecessary; the
  observed nulls are `label`-only, and totalising all five costs nothing while
  removing a whole class of drift. Measured across the 8,602 fields of the 398
  metadata-eligible DocTypes, `fieldname`, `fieldtype`, `reqd` and `read_only`
  each had **zero** nulls. The contract nonetheless guarantees all five are
  non-null, because the guarantee is about what the producer will emit, not
  about what the current data happens to contain — the four other columns are
  nullable in the schema too, and D22 is stated as an invariant rather than as
  an observation.
