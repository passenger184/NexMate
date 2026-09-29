# Tasks — fix-metadata-projection-null-contract

Producer-side normalization only. `service/auth.py` stays strict and unchanged;
`audit.py` is untouched; no authorization, capability, identity, policy,
credential, business-read, ceiling or audit behavior changes; Task 16.3 is not
addressed.

## 1. Specification

- [x] 1.1 Create the change directory and `.openspec.yaml`
- [x] 1.2 Author `proposal.md`: why (measured producer/consumer representation
      mismatch), what changes, breaking changes (none), capabilities modified,
      impact
- [x] 1.3 Author `design.md` with **D22** (producer owns a total scalar
      projection), the rationale chain, why the consumer stays strict, why the
      null mapping is `""` not a key drop, and the rejected alternatives
- [x] 1.4 Record the D21 relationship without editing D21: D21 names the
      hardcoded attribute-set invariant, D22 is the producer-side mechanism that
      makes those attributes total; do not restate D21
- [x] 1.5 Delta `doctype-schema-access`: ADD "Schema projection values are total
      scalars" — five attributes exactly, none null, strings for
      fieldname/fieldtype/label, booleans for reqd/read_only, nullable string →
      `""`, nullable boolean → `false`, not administrator-configurable; four
      scenarios
- [x] 1.6 Delta `durable-tool-execution`: ADD "Frappe-authorized metadata
      payloads are admitted within the approved ceilings", with the consumer
      explicitly retained as strict; three scenarios, one asserting the
      business-read bounds, validator and adapter are unaffected
- [x] 1.7 Do not claim `fieldname`/`fieldtype`/flags currently produce nulls;
      the observed nulls are `label`-only, the spec states the invariant
- [x] 1.8 `openspec validate fix-metadata-projection-null-contract --strict`

## 2. Producer implementation

- [x] 2.1 Add `PROJECTION_FLAG_FIELDS` naming the two boolean attributes; no
      second normalization helper
- [x] 2.2 Generalize the existing inline normalization in `project_meta`:
      flags `int` → `bool`, flags `None` → `False`; non-flag `None` → `""`
- [x] 2.3 Remove the incidental blanket `str(value)` conversion so no unrelated
      scalar is coerced; a `str`/`bool` value crosses unchanged
- [x] 2.4 Document the total-projection guarantee in the `project_meta`
      docstring
- [x] 2.5 Change nothing else: authorization order, policy, access mode,
      exclusions, ceilings, audit, routing, response structure

## 3. Producer tests

- [x] 3.1 `label None -> ""`
- [x] 3.2 `fieldname None -> ""`
- [x] 3.3 `fieldtype None -> ""`
- [x] 3.4 `reqd None -> False`
- [x] 3.5 `read_only None -> False`
- [x] 3.6 integer `reqd`/`read_only` → `bool`
- [x] 3.7 all five keys remain present on every entry
- [x] 3.8 no projected value is `None`
- [x] 3.9 no key is dropped
- [x] 3.10 already-valid scalar values are preserved unchanged
- [x] 3.11 no `str(value)` coercion of a non-null, non-flag value

## 4. Regression / integration tests

- [x] 4.1 `Customer` projection is type-clean and accepted by the real
      `validate_metadata_context`
- [x] 4.2 `DocShare` remains accepted
- [x] 4.3 a representative Section Break / Column Break / unlabelled `Data`
      field succeeds
- [x] 4.4 projection remains exactly five keys per field
- [x] 4.5 `service/auth.py` is unchanged and still strict
- [x] 4.6 a deliberately constructed payload with `label=None` still returns 422
- [x] 4.7 employee remains denied metadata
- [x] 4.8 child table remains denied
- [x] 4.9 Single remains denied
- [x] 4.10 nonexistent DocType remains denied
- [x] 4.11 the metadata path makes zero `erpnext_read.attempt_read` calls
- [x] 4.12 metadata context contains no business values and no `permissions`
      table
- [x] 4.13 the producer references no shared ERPNext credential
- [x] 4.14 business-read authorization matrix non-regression rerun (live): 4/4
      for the two fixture users, a strict subset of the 6/6 baseline
      (3 users × 2 customers) established by the earlier investigation. The
      6/6 baseline is preserved, not replaced; `erpnext_read.py` is
      byte-identical to HEAD

## 5. Validation

- [x] 5.1 OpenSpec strict validation for the change
- [x] 5.2 focused suites: `test_doctype_schema_policy`,
      `test_gateway_metadata_dispatch`, `test_u5_read_boundary`,
      `test_erpnext_read_adapter`
- [x] 5.3 full test suite, zero failures
- [x] 5.4 `git diff --check` clean
- [x] 5.5 `openspec validate --changes` and `--specs`

## 6. Blast-radius sweep

- [x] 6.1 Sweep every eligible metadata DocType through the producer and the
      real consumer validator; do not author one test per DocType
- [x] 6.2 Record total metadata-eligible DocTypes (398, structural eligibility
      independent of the metadata access policy), previous failures (270),
      previous clean (128), current failures (0), current clean (398)
- [x] 6.3 Report any DocType failing for a reason other than the null contract
      separately; do not reinterpret it as a null-contract failure
- [x] 6.4 Use "eligible" consistently and never imply that the 398 are
      authorized independent of the metadata policy

## 7. Live verification on `frontend`

- [x] 7.1 `Customer` metadata round trip returns HTTP 200 with exactly one
      `doctype_schema` audit event
- [x] 7.2 `DocShare` metadata round trip still succeeds
- [x] 7.3 employee metadata denial
- [x] 7.4 child table / Single / nonexistent denial
- [x] 7.5 business-read authorization matrix re-verified as a subset rerun
      (4/4 fixture users); the 6/6 baseline is preserved and `erpnext_read.py`
      is byte-identical to HEAD
- [x] 7.6 security invariant verification, including no secrets in responses or
      logs

## 8. Out of scope (recorded, not implemented)

- [x] 8.1 Audit durability under request rollback is a separate future
      hardening item, recorded in `verification-notes.md` and not addressed here
- [x] 8.2 Task 16.3 remains unchecked; the browser-rendered Desk hop is still
      untested because no browser is available

## 9. Final verification review

Documentation-only pass. No source behavior was altered; no test was added,
removed or weakened.

- [x] 9.1 Confirm the producer contract matches the implementation exactly
- [x] 9.2 Confirm no artifact claims `fieldname`/`fieldtype`/`reqd`/`read_only`
      were observed null; record the measured zero-null figures
- [x] 9.3 Confirm both spec deltas define all eight required contract points
- [x] 9.4 Confirm the `durable-tool-execution` delta implies no change to
      authorization, audit durability or business-read behavior
- [x] 9.5 Confirm D22 neither duplicates nor contradicts D21, and that no
      artifact claims D21 was edited
- [x] 9.6 Confirm audit durability remains out of scope in every artifact
- [x] 9.7 Reconcile the 4/4 rerun against the 6/6 baseline without replacing
      either figure
- [x] 9.8 Record the post-change HTTP 417 as runtime module-reload evidence,
      not a product defect
- [x] 9.9 Correct the "15 fieldtypes" claim to the measured 14, and separate
      the site-wide and metadata-eligible null-label populations
- [x] 9.10 Replace the non-measurement "1,386 reconstructed" cross-check with
      the measured 1,393
- [x] 9.11 Correct the claim that existing requirements were extended; both
      deltas add new requirements
- [x] 9.12 Re-run OpenSpec strict validation, the focused suites, the full
      suite and `git diff --check` after the corrections
