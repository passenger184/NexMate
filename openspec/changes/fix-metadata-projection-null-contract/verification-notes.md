# Verification notes — fix-metadata-projection-null-contract

Date: 2026-09-29
Change: `fix-metadata-projection-null-contract`
Type: producer-side representation fix (serialization only)
Status: implemented and verified; **not committed, not pushed, not staged**

## Environment

| item | value |
|---|---|
| Repository | `~/ERPNext-AI` |
| Baseline commit | `54dc2915ba8099dec9a92d9d94d6b711afae3728` (`main` == `origin/main`) |
| Approved Docker test repo | `~/copilot/frappe_docker_copilot_test` |
| Site | `frontend`, Frappe 16.31.0 / ERPNext 16.33.0, host port 8081 |
| Inference service | `127.0.0.1:8000`, started with the real `NEXMATE_SERVICE_KEY` (not the `NEXMATE_DEV_UNAUTHENTICATED` exemption) |
| Generator | Ollama `qwen2.5-coder:7b` at `172.30.224.1:11434` (already present; **no model download performed**) |
| Test users | `u5-allowed@nexmate.test` (Sales User, developer while enabled), `u5-restricted@nexmate.test` (Desk User, employee) |

`~/projects/frappe_docker` was **never** accessed, inspected, referenced or
modified at any point.

## Files changed

| file | change | lines |
|---|---|---|
| `frappe_app/erpnext_ai_copilot/doctype_meta.py` | `PROJECTION_FLAG_FIELDS` constant + generalized inline normalization in `project_meta` + docstring | +28 / −11 |
| `tests/test_doctype_schema_policy.py` | new `ProjectionValueContractTest` (13 tests) + `_NullableField` stub | +132 / −0 |
| `tests/test_gateway_metadata_dispatch.py` | new `MetadataNullContractTest` (11 tests) | +141 / −0 |
| `openspec/changes/fix-metadata-projection-null-contract/` | new change: `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`, `verification-notes.md`, `specs/doctype-schema-access/spec.md`, `specs/durable-tool-execution/spec.md` | new |

Diffstat: `3 files changed, 301 insertions(+), 11 deletions(-)` plus the
untracked change directory. Confirmed by `git diff --numstat`.

Both test diffs are **purely additive**: 0 removed lines in each. The only
removed lines anywhere in the working tree are the 11 lines of the superseded
normalization block in `doctype_meta.py`. No existing test, helper, stub or
source file was modified, reordered or weakened. The `+24` tests is exactly the
`657 − 633` delta in the full suite (13 + 11), which independently confirms
nothing else was added or lost.

## The source change

Only the value-normalization block of `project_meta` was touched. Authorization
order, metadata policy, access mode, structural exclusions, ceilings, audit
behaviour, control-plane routing and response structure are unchanged.

```python
for key in PROJECTION_FIELDS:
    value = getattr(field, key, None)
    if key in PROJECTION_FLAG_FIELDS:
        # The declared flag attributes are boolean. Frappe stores
        # them as 0/1 ints, and the column is nullable.
        if isinstance(value, int):
            value = bool(value)
        elif value is None:
            value = False
    elif value is None:
        # A nullable string attribute, never a business value: the
        # projection carries structure only, so the empty string is
        # an exact stand-in for "no label was set".
        value = ""
    entry[key] = value
```

### Two behaviour changes inside the block, both deliberate

1. **The null mapping is new.** `label` (and defensively `fieldname`,
   `fieldtype`) `None` → `""`; the flag attributes already mapped `None` →
   `False` before this change.
2. **The blanket `str(value)` conversion was removed.** The previous code ended
   with `elif value is not None and key not in ("reqd", "read_only"): value =
   str(value)`. That is exactly the broad arbitrary scalar coercion the approved
   decision forbids ("do not coerce unrelated scalar values to strings";
   "otherwise preserve existing values unchanged"), so it is gone. A value that
   is already a `str` or a `bool` now crosses untouched. The two are
   observationally equivalent on the live site, because Frappe's
   `fieldname`/`fieldtype`/`label` columns are `varchar` and therefore always
   `str` or NULL — but the new behaviour is the declared contract rather than an
   incidental one. Pinned by
   `test_non_null_non_flag_value_is_not_coerced_to_string`.

The redundant `if key == "fieldname"` branch (identical to the `else` branch) was
folded into a single `getattr(field, key, None)`. Behaviour-identical.

## Test results

| run | result |
|---|---|
| `openspec validate fix-metadata-projection-null-contract --strict` | `Change 'fix-metadata-projection-null-contract' is valid` |
| `openspec validate --changes` | 2 passed, 0 failed |
| `openspec validate --specs` | 14 passed, 0 failed (one pre-existing ">500 characters" INFO) |
| focused: `test_doctype_schema_policy`, `test_gateway_metadata_dispatch`, `test_u5_read_boundary`, `test_erpnext_read_adapter` | **189 tests, OK** |
| full suite (`unittest discover -s tests`) | **657 tests, OK (skipped=1), 0 failures** — baseline was 633, so **+24 net** |
| `git diff --check` | clean |
| `audit.py` md5 | working tree `7b6b135a9a90a5113b7c5fd630bacba1` == `HEAD` == baseline |
| `service/auth.py` md5 | working tree `7057c18d7f04f2f82d02b1751f7c0a94` == `HEAD` |

No existing test was modified or weakened. The shared `_Field` stub in
`test_doctype_schema_policy.py` was left alone: it defaults `label` to
`fieldname`, which is precisely why the defect was never caught by that suite. A
separate `_NullableField` stub that can genuinely hold `None` was added instead.

## Blast-radius sweep (398 eligible DocTypes, no bespoke per-DocType tests)

**What "eligible" means here, precisely.** The 398 is a *structural* eligibility
set, derived from the DocType table alone: `istable = 0`, `issingle = 0`, and
`name NOT LIKE 'NexMate%'`. It is deliberately **independent of the metadata
access policy** — no `NexMate Settings` value was consulted to build it, and it
is **not** a claim that all 398 are authorized for any user. Authorization is
separately gated by capability, then by the metadata access mode, and the sweep
does not stand in for either.

The sweep ran with a developer-capability session
(`u5-allowed@nexmate.test`) and the site's existing `metadata_access_mode: all`,
so every one of the 398 was admitted by the control plane and reached the
consumer. That makes this a **schema-shape sweep of the whole reachable
surface**, not a test of who may see what. Had the mode been `ALLOWLIST`, only
the allowlisted DocTypes would have been served; the null-contract result below
is independent of that setting either way.

Every one of the 398 was projected by the real control plane and every resulting
payload was validated by the **real** `service/auth.py`
`validate_metadata_context`.

```
structurally eligible DocTypes (istable=0, issingle=0, non-NexMate) : 398
served by the control plane in this sweep configuration          : 398
denied by policy/capability in this sweep configuration          : 0
unrelated failures                                                : 0

PRE-FIX  (label passed through as null)
   null-contract failures                                         : 270
   clean                                                          : 128

POST-FIX (producer normalises null -> "")
   null-contract failures                                         : 0
   clean                                                          : 398
```

All 398 metadata-eligible DocTypes are now admitted. There were **no** DocTypes
failing for an unrelated reason, so nothing had to be reported separately. The
zero in "denied by policy/capability" reflects the sweep configuration
(`metadata_access_mode: all` plus a developer session), not an absence of
authorization gates; those gates were exercised separately, below and above.

**Reconciling 270 against 269.** A secondary reconstruction that re-injected
`null` only into *layout* fieldtypes counted 269. The authoritative figure is
**270 / 128**, taken from the sweep's own per-DocType null-label count, and it
reproduces the investigation baseline exactly. The one-DocType delta is itself a
confirmation of the design rationale, and that DocType has been identified: it is
`Success Action`, whose *only* null label sits on a non-layout `Data` field, so a
layout-fieldtype special case would still have left it failing. This is why D22
states the rule about the *attribute* rather than the fieldtype.

### Null-label measurement, by population

| population | DocTypes | fields | null labels | distinct fieldtypes |
|---|---|---|---|---|
| Site-wide, every `DocField` row | — | 13,673 | 2,211 | 14 |
| Metadata-eligible (the 398 swept) | 398 | 8,602 | 1,393 | 9 |

The earlier draft of these notes cited "1,386 null labels reconstructed" as a
cross-check. That number was the count of labels a *layout-only* reconstruction
injected, not a measurement, and it undercounts the true eligible figure; it has
been replaced by the measured 1,393. The 2,211 and 1,393 figures are not in
conflict: the first is site-wide and includes child-table and NexMate DocType
fields, the second is restricted to the DocTypes the metadata capability reaches.

Nulls in the other four projected attributes, across the eligible population:

| attribute | nulls |
|---|---|
| `fieldname` | 0 |
| `fieldtype` | 0 |
| `reqd` | 0 |
| `read_only` | 0 |

`label` is the only attribute with any observed null. The contract nevertheless
guarantees all five are non-null, and the specification states it as an
invariant, not as an observation about current data. No document in this change
claims the other four were observed to contain nulls.

## Live verification on `frontend`

### Customer — the previously failing case

```
POST /api/method/erpnext_ai_copilot.api.ask
  {"question": "What fields does the Customer DocType have?"}

HTTP 200   (previously HTTP 417, gateway_upstream_http_error)
route: erpnext | mode: developer | confidence: high
source: tools.erpnext://Customer
answer: "The Customer DocType in the ERPNext instance has 87 fields. ..."
```

Real control-plane projection for `Customer`, inspected in place:

```
field_count              : 87
keys per entry           : ['fieldname','fieldtype','label','read_only','reqd']   (exactly one shape)
any value is None        : false
string attrs are str     : true    (fieldname, fieldtype, label)
flag attrs are bool      : true    (reqd, read_only — exact type, not int)
empty labels             : 21      (21 of 87, matching the 21 null labels measured pre-fix)
top-level keys           : ['doctype', 'field_count', 'fields', 'operation']
forbidden keys present   : false   (no options / permissions / permlevel / default key)
erpnext_read calls       : 0
```

### Audit — one normal event, and now durable

```
2026-09-29 17:15:30.515782 | doctype_schema | success | u5-allowed@nexmate.test | Customer
                             corr=nexmate-schema | req=schema
2026-09-29 17:15:53.908760 | doctype_schema | success | u5-allowed@nexmate.test | DocShare
                             corr=nexmate-schema | req=schema
```

Exactly **one** `doctype_schema` event per successful request, with the ordinary
vocabulary and no compensating or duplicate write. `audit.py` is byte-identical
to HEAD.

### DocShare — regression

```
HTTP 200 | route: erpnext | mode: developer | confidence: high
source: tools.erpnext://DocShare
answer: "The DocShare DocType has the following fields: 1. user - Link, optional ..."
```

### Employee — still denied

```
POST /api/method/erpnext_ai_copilot.api.ask  (session: u5-restricted@nexmate.test)
HTTP 200
answer : "Schema not found or access denied."
sources: []
```

The metadata-specific collapse, with no metadata disclosed. In-process,
`api._authorized_metadata(...)` for that user returns `_denied`.

### Structural exclusions — all still denied

| request | result |
|---|---|
| child table (`NexMate Conversation Turn`) | `_denied` |
| Single (`NexMate Settings`) | `_denied` |
| nonexistent (`Definitely Not A DocType`) | `_denied` |
| wildcard (`*`) | `_denied` |

### Business-read authorization matrix — non-regression rerun

**The authoritative baseline is 6/6, and it is unchanged.** The original
investigation established native Frappe permission agreement across **3 users ×
2 fixture customers = 6 combinations**, each checked against
`frappe.has_permission(..., throw=False)`:

| user | capability | `has_permission(Customer)` | `u5-allowed-cust` | `u5-denied-cust` |
|---|---|---|---|---|
| `Administrator` | — | true | `_context` | `_context` |
| `u5-allowed@nexmate.test` | (Sales User) | true | `_context` | `_denied` |
| `u5-restricted@nexmate.test` | (Desk User) | true | `_denied` | `_context` |

**6/6 NexMate/native agreement. That is the baseline and it stands.**

**The rerun performed for this change was 4/4 — a strict subset, not a
replacement.** It re-exercised the two fixture users only, across the same two
customers:

| user | `u5-allowed-cust` | `u5-denied-cust` |
|---|---|---|
| `u5-allowed@nexmate.test` (Sales User) | `_context` (allowed) | `_denied` |
| `u5-restricted@nexmate.test` (Desk User) | `_denied` | `_context` (allowed) |

`matrix_as_required: true` — 4/4, every one of which matches both the
corresponding row of the 6/6 baseline and native
`frappe.has_permission(doc=...)`.

**Why the counts differ, stated plainly.** The rerun omitted the `Administrator`
row (the 2 combinations in which an administrator reads both customers), so 4/4
is a subset of the 6/6 baseline rather than a competing figure. The 6/6 is
**not** superseded, and neither count has been replaced by the other. Two
independent reasons make the 6/6 baseline still authoritative for this change:

1. **Structural.** `frappe_app/erpnext_ai_copilot/erpnext_read.py` is
   byte-identical to HEAD (`7106b8d0e3cd99405dde8c589b775a15`). No
   business-read code path could have changed, so the full 6/6 agreement is
   preserved by construction and the 4/4 is a spot confirmation, not new
   evidence of the baseline.
2. **The omitted row is not an authorization discriminator.** `Administrator`
   is a superuser whose `has_permission` is unconditionally true for both
   customers; the discriminating behaviour under test is the User Permission
   boundary that separates the two fixture users, and both of those rows were
   re-exercised and matched.

No new test was authored for this reconciliation, and the `Administrator` row
was deliberately not re-run live: it was omitted from the rerun's scope, and
recording that omission is the correct response rather than manufacturing a
number to match the earlier headline.

## Security invariants

| check | result |
|---|---|
| `frappe.set_user(` calls in `erpnext_read.py` | 0 (and the adapter declares it forbidden) |
| business-read subject is the session user | yes (`frappe.session.user`) |
| `frappe.db.sql` / `frappe.get_all` in the business-read adapter | absent (no privilege-elevation path) |
| `frappe.db.sql` in the metadata producer | absent |
| credential references in `erpnext_read.py` | none |
| credential references in `doctype_meta.py` | none |
| adapter backstop bounds | `100 rows / 50 fields / 131072 bytes` (unchanged) |
| effective read bounds | `20 / 20 / 65536` (unchanged) |
| effective metadata bounds | `300 / 65536` (unchanged) |
| service metadata ceilings | `500 fields / 131072 bytes` (unchanged) |
| no business value, `options` or `permissions` in metadata context | confirmed (see the false-positive note below) |
| metadata path calls `erpnext_read.attempt_read` | 0 times |

**False positive worth recording.** The automated anti-exfiltration probe
initially reported `customer_no_business_values: false`. It was a defect in the
probe, not in the payload: it grepped for the substrings `Tier` and `default`,
which legitimately occur inside the Customer fieldnames `loyalty_program_tier`,
`default_currency`, `default_bank_account`, `default_price_list` and
`default_receivable_accounts`. Re-checked structurally, `options`,
`permlevel` and `permissions` occur **zero** times, no forbidden key is present on
any entry, and the entry key set is exactly the five declared attributes. The
naive substring probe was discarded in favour of the structural check.

## Environment observations (not product changes)

1. **Runtime module reload — reload evidence, not a product defect.** The first
   post-change live `Customer` request still returned HTTP 417, even though the
   sweep run minutes earlier in the same container reported 398/398 clean.

   *Runtime/reload observation.* The cause is module lifetime, not logic. The
   bind-mounted app directory meant the container's file on disk was already
   correct before the request — the new `PROJECTION_FLAG_FIELDS` constant and
   the new normalization were both visible at
   `/home/frappe/frappe-bench/apps/erpnext_ai_copilot/erpnext_ai_copilot/doctype_meta.py`,
   and the `.pyc` had already been rebuilt. The long-running Frappe web process,
   however, had imported `doctype_meta` before the edit and kept the old module
   object in memory, so the Desk request executed pre-change code. The sweep ran
   in a fresh `bench console` interpreter, which imported the new code — hence
   the divergence between the two results.

   *Evidence.* The backend container was restarted, the module was re-imported
   from the unchanged file, and the identical request then returned **HTTP 200**
   with the correct answer, the `tools.erpnext://Customer` source, and exactly
   one committed `doctype_schema` audit event. No file was edited to obtain that
   result; the only action was a process restart.

   *Scope.* This is recorded purely so the run is reproducible by a future
   reader. It is a property of how the Frappe dev deployment loads app code, not
   a defect in this change, not a code fix, and not a product behaviour. It also
   means the post-change live HTTP evidence is valid only for a worker started
   after the edit — a live request issued against a stale worker is not evidence
   about the change either way.

2. **Audit durability under request rollback — FUTURE ITEM, NOT ADDRESSED HERE.**
   The investigation established that the `doctype_schema` row written for the
   *previously failing* `Customer` request was genuinely inserted and then
   destroyed by the ordinary Frappe request rollback at `frappe/app.py:147`
   (`db.rollback(chain=True)`) after `ask()` raised `gateway_upstream_http_error`
   in response to the consumer's HTTP 422. There was no bypass and no filtering:
   the writer always runs. The consequence is that a request which fails *after*
   its audit write leaves no trace of the attempt. This change does not address
   it — no compensating write, no `flags.commit()`, no out-of-band write, no new
   audit vocabulary, no duplicate event, no special rollback handling. It is
   recorded here as a **separate future hardening item**, to be raised as its own
   OpenSpec change with its own decision record. Note that the *observed* effect
   is now moot for this scenario, because the successful `Customer` request
   commits its single `doctype_schema` event as normal.

3. **Task 16.3 remains unchecked.** The browser-rendered Desk hop is still
   untested: no browser binary, no playwright/puppeteer cache, and the `browser`
   tool reports "No desktop browser is connected". This change does not address
   that requirement, and no attempt was made to work around it by installing a
   browser. All live evidence above is HTTP-level against the real Frappe site.

4. **Test-fixture state was restored exactly.** `developer_role_rules` was set
   to `Sales User` for the duration of the live metadata tests and restored
   afterwards: `MATCHES_PRE_STATE: true` (`developer_role_rules: []`,
   `metadata_access_mode: "all"`).

## OpenSpec authoring note

Both spec deltas are `ADDED`, not `MODIFIED`. `doctype-schema-access` does not
yet exist in `openspec/specs/` and the
`durable-tool-execution` requirement named in the approved plan is itself an
`ADDED` requirement from the still-unarchived
`retire-chat-only-developer-capability-model`. The first draft used
`MODIFIED` and the validator reported that the archive would refuse both deltas;
rewriting them as distinctly-named `ADDED` requirements makes them
archive-safe. The value contract is therefore stated in the same capability as
the minimized-projection requirement and explicitly cross-references it by
name, which is the archive-valid realisation of "extend the existing
requirement".

For the same reason **D21 was not edited**. D21 lives in the committed, pushed
`retire-chat-only-developer-capability-model` design ledger; rewriting a
delivered artifact of another change is out of scope, and that change's audit
trail must not be disturbed. The D21/D22 relationship is recorded in two places
in *this* change only: this `design.md`, under "Relationship to D21", and the
operative "not administrator-configurable" clause, which is carried in the
`doctype-schema-access` delta. D22 is stated once and only once, and does not
restate D21.

Both artifacts were reviewed for consistency with the implementation in this
final pass; see the corrections listed in the change's own report. The
relationship is described identically in `design.md` and here — no residual
claim anywhere states that D21 was edited.

## Success criteria

| criterion | status |
|---|---|
| Customer metadata round trip HTTP 200 | PASS |
| Customer projection exactly five keys per field | PASS |
| No projected value is `None` | PASS |
| `fieldname`/`fieldtype`/`label` are strings | PASS |
| `reqd`/`read_only` are booleans | PASS |
| Consumer still rejects `label=None` with 422 | PASS (4 strictness tests) |
| `service/auth.py` unchanged | PASS (md5 identical) |
| `audit.py` byte-identical | PASS (md5 identical) |
| Customer request produces exactly one `doctype_schema` audit event | PASS |
| Employee remains denied | PASS |
| Child table / Single / nonexistent remain denied | PASS (plus wildcard) |
| Metadata never calls `erpnext_read.attempt_read` | PASS (0 calls) |
| No business values, options or permissions in metadata context | PASS |
| No shared ERPNext credential introduced | PASS |
| Business-read authorization matrix unchanged | PASS — 6/6 baseline preserved; 4/4 subset rerun matched |
| No authorization or identity code changes | PASS |
| No metadata policy or ceiling changes | PASS |
| Full test suite, zero failures | PASS (657, 1 skipped) |
| OpenSpec validation passes | PASS |
| `git diff --check` clean | PASS |
| Task 16.3 complete | **NO — deliberately unchecked** |

## Limitations

- Unit and integration evidence uses synthetic Frappe doubles for the
  authorization and policy paths; only the HTTP-level evidence above ran against
  a live Frappe 16.31.0 / ERPNext 16.33.0 site. Mocked tests do not establish
  live NLU or Bench acceptance.
- Answer quality was not the subject of this change and was not evaluated beyond
  confirming the round trip returns a grounded answer with the correct
  `tools.erpnext://` source.
- The 398-DocType sweep exercised the real producer and the real consumer
  validator, but it called `api._authorized_metadata` directly in a console
  process rather than going through a Desk HTTP session. The Desk path was
  verified separately for `Customer`, `DocShare` and the employee denial.
- The single HTTP-level `Customer`/`DocShare`/`employee` runs do not prove
  behaviour under concurrency or under a multi-worker load-balancer restart
  mid-request.
- No claim of production readiness is made or implied.
