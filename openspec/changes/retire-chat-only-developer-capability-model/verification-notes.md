# U-change Notes — verification, decisions, and limitations

Running record for `retire-chat-only-developer-capability-model`.

---

## Implementation evidence — offline

**Date:** 2026-09-29 · **Environment:** project `.venv` (CPython 3.14), offline
(`PYTHON_DOTENV_DISABLED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
LITELLM_LOCAL_MODEL_COST_MAP=True`)

| Suite | Result |
|---|---|
| Full Python suite (`unittest discover -s tests`) | **566 tests OK (1 skipped)**, 0 failures, stable across 3 consecutive runs |
| `tests/test_erpnext_read_adapter.py` (regression floor) | **40 tests OK**, file not modified |
| `tests/test_u5_read_boundary.py` | **26 tests OK** — 20 of the original 25 unchanged; the 5 intentionally rewritten tests pass; 1 new test asserts the metadata contract does not relax any business-read bound |
| `tests/test_doctype_schema_policy.py` (new) | 46 tests OK |
| `tests/test_gateway_metadata_dispatch.py` (new) | 23 tests OK |
| `tests/test_capability_and_policy_surface.py` (new) | 34 tests OK |
| `openspec validate <change> --strict` | valid |
| `openspec validate --changes --strict` | 1 passed, 0 failed |
| `openspec validate --specs --strict` | 14 passed, 0 failed |
| `git diff --check` | clean |

### The five intentionally rewritten boundary tests

Rewritten to assert the post-change outcome, not deleted, and not weakened
(tasks 14.3, 14.9):

1. `test_12_1_routes_retained_in_inventory` — the three legacy ERPNext read
   routes are now **absent** from the inventory.
2. `test_12_1_routes_marked_deprecated` — no route remains marked deprecated.
3. `test_12_2_deprecation_policy_is_stated` — the deprecation markers are
   replaced by `RETIRED_ERPNEXT_READ_ROUTES`; the notice constants are gone.
4. `test_12_3_read_client_retained_for_legacy_consumers` — only
   `get_doctype_schema` and `call_method` remain required; `get_document` and
   `list_documents` lost their only consumer with the routes.
5. `test_7_2_operation_must_be_supported` — metadata is now an accepted
   operation with its own frozen shape; business-read operations and bounds are
   asserted unchanged, and a companion test asserts the metadata contract does
   not relax any business-read bound.

The three retained Group 12 assertions
(`test_12_4_version_lookup_still_resolves_credential`,
`test_12_4_write_path_still_uses_retained_client`,
`test_12_4_credential_consumer_set_unchanged_apart_from_reads`) pass unchanged,
because the version lookup and the write-path credential consumers are retained
out of scope.

### Defect found and fixed during implementation

**Flow bug in the first cut of the metadata branch.** The schema branch
originally emitted a request unconditionally and discarded any supplied
authorized context, which meant the answer leg of the round trip could never be
served: the orchestrator would ask, Frappe would answer, and the orchestrator
would ask again until the budget ran out. Fixed so the schema branch consumes a
`operation == "schema"` authorized context and otherwise emits a request. The
forge-prevention guarantee is unaffected and now rests where it belongs — on the
envelope validator refusing an authorized-context field without a complete valid
gateway envelope — rather than on branch ordering. Two tests pin the behaviour:
one supplies a schema context and asserts an answer is produced; the other
supplies a *business-read* context and asserts a request is still emitted.

### Behaviour reversals required by the approved decisions

These change previously-asserted behaviour and were not silently weakened:

- The orchestrator no longer declines employee schema in conversation. It emits a
  request so the Frappe control plane can authorize, refuse, **and audit** the
  decision (`orchestrator.py:1193-1206` removed; `tests/test_employee_mode.py`
  rewritten from `test_schema_lookup_denied_for_employees` to
  `test_schema_request_is_issued_for_employees_not_declined`).
- `tests/test_orchestrator.py`: the three schema-path tests that asserted the
  shared-credential 404/lookup-failure wording were replaced. Metadata no longer
  goes through the legacy client, so that wording no longer exists. One test
  gained as replacement asserts a nonexistent DocType collapses into a single
  denial that names nothing.
- The `erpnext` route is no longer denied pre-entry on the gateway path;
  authorized reads and metadata must reach the control plane. The `code` route
  is still denied. `tests/test_chat_boundary.py` was split accordingly:
  `test_forced_routes_in_both_personas` covers code-only denial, and
  `test_forced_erpnext_route_reaches_the_control_plane` asserts the read request
  reaches the control plane with no ERPNext client call.
- `_extract_erpnext_request` and `run_erpnext_branch` are no longer in the
  chat-boundary forbidden list, because the `erpnext` route now legitimately
  reaches them. The ERPNext client functions and the version lookup remain
  forbidden.

---

## MIGRATION — APPROVED, BACKED UP, EXECUTED 2026-09-29

Migration approval was given subject to the backup gate. The previously
recorded `installed_apps` inconsistency was already resolved before this run:
`frontend/site_config.json` now lists
`["frappe", "erpnext", "erpnext_ai_copilot"]`, agreeing with `sites/apps.txt`.

### Backup (verified complete before migrating)

```text
/tmp/opencode/nexmate-migrate-20260929T090136Z/
  SHA256SUMS
  defs/  nexmate_audit_entry.json  16f31a661cfa4c66b8a36865044b79464f4d1c90d8a8d903076f1486b5d2488a
         nexmate_conversation.json 6b662e3f1a088aed2c85c73c76f9132588b75834059d6f88371f5c7a30394f88
         nexmate_conversation_turn.json 244f4fb990580c6bc56001752f215cb3ee72f4472fdcde6c3236b5610ec8f522
         nexmate_metadata_doctype_rule.json 589062fec6df3eb5a46f1d6367ae94fca70c604e04046bbc84d565455ef4273a
         nexmate_settings.json fea0189d91c93ab74b75040ed9953dc25574dba3f236422243f410a690d97373
         nexmate_tool_proposal.json 45d96b6f58d0efa1b0f23a4b875cc900b459352911781bbb798e8808e04a20c5
  db/    tabDocType_nexmate4.json c58c8da2cf6cf0827e7308ad34ed7439d2d52d4c83d7ccbb997a91f936031af6
         data_nexmate_tables.json 19f79081cc4c88adfc45504f862d4da87efef3b2a7ec21bb30aa7be21f00c3b0
         rowcounts_and_vocab.json 5fa30903a52b3898cce7f3101a39440bb137b2aa0f71daa076e6a55e6c8de781
```

`sha256sum -c SHA256SUMS` passed. Baseline: 15 audit rows, 0/0/0 elsewhere;
action vocabulary 21 options, outcome vocabulary 11 options.

### Preflight immediately before migrating — CLEAN

`apps.txt` contains the app; site `installed_apps` contains the app;
`get_installed_apps()` with and without `_ensure_on_bench` contains the app;
app path resolves; module map consistent; all four existing DocTypes exist;
row counts unchanged at 15/0/0/0. No cache invalidation was required.

### Migration commands and results

```text
bench --site frontend migrate   -> exit 0, no NexMate orphan deletion
```

A second `bench --site frontend migrate` was run after the `target_doctype`
field rename below; it also exited 0 with no errors and no NexMate orphans.
(The DocType table was empty at that point, so the rename cost nothing.)

### The three additive synchronizations — APPLIED

1. `doctype_schema` appended to the `action` options on `NexMate Audit Entry`
   (22 options; `doctype_schema` last; all 21 prior options preserved).
2. `NexMate Settings` Single DocType — present (`issingle=1`, `istable=0`).
3. `NexMate Metadata DocType Rule` child DocType — present (`issingle=0`,
   `istable=1`).

### Post-migration integrity — VERIFIED

All six DocTypes exist in `tabDocType` with the correct module and flags; all
six controllers resolve through Frappe's native `get_controller()`; row counts
preserved at 15/0/0/0 for audit/conversation/turn/proposal; `outcome`
vocabulary unchanged at 11 options.

### Live defects found and fixed by this verification (new code only)

`erpnext_read.py` and `audit.py` were not modified at any point.

1. **Child-table Link field named `doctype` shadowed `Document.doctype`.**
   Every configured row read back as the child DocType's own name, so the
   duplicate check misfired and structural validation could not see the real
   value. The field was renamed to `target_doctype` in both DocType JSONs, both
   controllers, `doctype_meta.load_policy()`, `settings_audit._rule_names()`,
   and the affected tests. Verified live: duplicates refused, nonexistent names
   refused by Link validation, and the two bad rows saved before the fix were
   removed to restore the intended configuration.
2. **Parent save does not invoke child-row `validate()`.** The `istable` /
   `issingle` exclusions lived only in the child controller, so two excluded
   rows were saved live. The same check now also runs in
   `NexMateSettings.validate()` (`_validate_rules_are_inspectable`). Verified
   live: both exclusions refused at parent save with `ValidationError`.
   Authorization-time exclusion in `doctype_meta` was already in force
   regardless, so no unauthorized access occurred at any point.
3. **Settings-change audit read the latest `Version` row (off by one).** At
   `on_update` time the current save's version row does not exist yet, so the
   recorded previous mode belonged to an earlier save. The hook now uses
   `get_doc_before_save()`. Verified live: `all`→`allowlist` and
   `allowlist`→`all` transitions recorded exactly.

### Rollback ordering constraint (unchanged)

Reverting the `action` option list after `doctype_schema` events have been
written would orphan those values. Recorded here as required by task 15.10.

---

## Live evidence — test Bench `frontend` (tasks 16.3–16.8)

**Date:** 2026-09-29 · **Site:** `frontend` (test Bench only; the forbidden
repository was never accessed) · Live checks run as the stated session users
via the Frappe control plane with genuine session identity. The full
Desk→inference→Frappe round trip was not exercised live (the inference service
was not running in this environment); envelope validation, dispatch, and the
orchestrator legs are covered by the offline suites, including the three
no-envelope injection tests.

**Still unverified:** a live browser-to-inference-to-Frappe round trip. This is
recorded as a limitation, not as acceptance.

### VERIFIED live

- **Fail-closed baseline:** with no `NexMate Settings` row, a
  developer-capable Administrator is refused with `policy_unavailable` and the
  collapsed denial.
- **Developer + `all`:** Customer served with exactly the five projected
  attributes over 87 fields; no `options`, `permissions`, values or rows.
- **Employee denial:** three employee users refused with `capability_denied`
  and the identical caller-visible denial; Guest refused.
- **Structural exclusions:** child table, Single DocType and nonexistent
  DocType refused indistinguishably under `all` mode.
- **Allowlist:** listed Customer allowed; unlisted Lead and Company refused
  with `policy_denied`; save-time Link validation refused a nonexistent name;
  duplicates refused; `istable`/`issingle` refused at parent save after the
  fix above.
- **Immediacy:** every committed policy change (including `all`→`allowlist`,
  list edits, and the restore to `all`) was observed by the very next decision
  with no restart.
- **Audit accounting:** with explicit commits, 3 permitted + 1 refused
  resolutions produced exactly 4 new `doctype_schema` events (+2 → +6 across the
  run); each carries actor, site, target, outcome and metadata-only details.
  Policy changes emit `security_event` audit events with exact previous/new
  mode, plus Frappe `Version` rows capturing field and child-row diffs.
- **Credential boundary:** the backend environment and `site_config.json`
  contain no `ERPNEXT_*` credential, and neither `doctype_meta.py` nor `api.py`
  reads one. Metadata was served in-process with no outbound call. The
  inference-side credential for write/version consumers is retained out of
  scope and unchanged.
- **U5 regression:** `u5-allowed` list read allowed (2 rows);
  `u5-denied-cust` refused for the User-Permission-restricted user and allowed
  for the DocShare grantee — matching the U5 matrix exactly — with one
  caller-identical collapse. `erpnext_read.py` unmodified (verified by diff).

### NOT VERIFIED live (recorded, not claimed)

- Desk→inference→Frappe round trip for any row of the matrix.
- Forged-scope / unattributed-field negatives against a running inference
  service (covered offline only).
- Whether to raise the 100-field projection bound (open product decision).

## Evidence NOT obtained

None outstanding beyond the round-trip limitation above. Tasks 16.3–16.8 are
verified at the control plane; only the end-to-end Desk leg remains
unverified.

---

## Pre-existing limitations observed, NOT introduced and NOT fixed

- **The business-read audit path does not inspect `record_audit()`'s return
  value.** `erpnext_read._audit` ignores it, so a returned `audit_pending` does
  not deny a business read. The metadata module **does** inspect it and fails
  closed (task 7.5), which is why the two paths differ. `audit.py` was not
  modified, per task 7.6, so the U5 behaviour is unchanged. Recorded as a
  limitation of the delivered U5 boundary, not a defect introduced here.
- **`erpnext_read.py` was not modified at all.** Its request contract still
  excludes metadata operations, which is exactly why the gateway dispatches on
  kind and never routes metadata through `attempt_read()`. A metadata request
  reaching the adapter would be correctly rejected *and* mis-recorded as a
  business-read `invalid_request`, which is why the dispatch boundary is
  specified rather than incidental.
- **`tools/erpnext.py` still exports `get_document` and `list_documents`.** They
  lost their only consumers when the legacy routes were removed. Retaining them
  is deliberate: the client is retained for the enumerated remaining consumers
  and its surface is not narrowed in this change.
- **`nexmate_developer_roles` is `["System Manager"]` on the live test site.**
  Under `all` policy mode this means any System Manager could inspect every
  eligible DocType's structure. That is the documented development/testing
  posture (task 17.5), and it is why `all` is explicitly not presented as
  automatically appropriate for production.

---

## §18 Configurable operational limits — implemented, offline-verified

**Date:** 2026-09-29 · **Environment:** project `.venv`, offline
(`PYTHON_DOTENV_DISABLED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
LITELLM_LOCAL_MODEL_COST_MAP=True`) · **Source revision:** working tree,
uncommitted.

| Suite | Result |
|---|---|
| Full Python suite (`unittest discover -s tests`) | **608 tests OK (1 skipped), 0 failures** |
| `tests/test_policy_limits.py` (new) | 22 tests OK |
| `tests/test_doctype_schema_policy.py` | extended: settings-controller numeric validation (3 new), configured-bound and ceiling tests replace the old fixed-100 tests |
| `tests/test_gateway_metadata_dispatch.py` | extended: ceiling separation, 150-field coordination test, dynamic rounds, api-level read pre-checks, api-level metadata field-count check |
| `tests/test_capability_and_policy_surface.py` | extended: 7 api-level role-precedence tests (override, fallback, never-saved, empty, malformed, deleted-name, live re-resolution) |
| `openspec validate <change> --strict`, `--changes`, `--specs` | valid / pass |
| `git diff --check` | clean |

### What was implemented (tasks 18.1–18.11)

- New central module `frappe_app/erpnext_ai_copilot/policy_limits.py`: immutable
  ceilings, defaults, administrator ranges, `effective_*` resolution with
  `min(admin, ceiling)` clamping, save-time `validate_numeric_settings`, and
  the one authoritative `resolve_developer_roles()` (Settings-when-configured,
  `site_config` fallback, explicit-empty means none, malformed fails closed,
  deleted names never match, live per-request reads, no cache).
- `NexMate Settings` JSON gains `max_schema_fields` (300), `max_schema_bytes`
  (65536), `max_read_rows` (20), `max_read_fields` (20), `max_read_bytes`
  (65536), `max_read_rounds` (3) and the `developer_role_rules` table, organized
  under Developer & Schema / Live Data Query Bounds / Execution / Metadata
  Access Rules sections; new child DocType `NexMate Developer Role Rule`
  (`Link` → `Role`). Controller validates every numeric field at save.
- `doctype_meta.py` resolves bounds per decision (single settings read shared
  with the policy load); fixed 100/65536 constants removed.
- `api.py`: one `_developer_role_mapping()` path feeds both capability
  derivation and scope construction (the duplicated inline validation is
  gone); the round loop uses the resolved budget; `_authorized_read`
  pre-checks rows/fields and post-checks bytes against
  `min(admin, ceiling, frozen adapter bound)`; `_authorized_metadata`
  enforces the resolved field-count bound alongside bytes.
- `service/auth.py`: metadata contract raised to the 500-field / 131072-byte
  ceilings under **separate** constant names; every business-read bound
  byte-identical to before.

### Migration status for §18: STAGED, NOT RUN

The Settings JSON additions and the new child DocType are **additive schema
changes staged in the working tree only**. No migration was run in this pass
(per instruction). A future `bench --site <site> migrate` under the existing
approval gate will sync them alongside the already-migrated base DocTypes;
re-verify `installed_apps`, module map, backup, and orphan-deletion absence
at that time exactly as before.

### Open product decision carried forward (unchanged)

The 100-field-era tests now assert the new defaults and ceilings instead.
Whether the 100-field projection bound experience (refusing Item 132, Sales
Order 170, Sales Invoice 233 under an unconfigured site) should have been
kept versus the new 300 default is moot: the default is now 300 and the
ceiling 500, per the locked table. No live re-verification of §18 was
performed in this pass (offline only); the control-plane live matrix from the
previous pass stands for the pre-limits behavior.

---

## §19 Corrective review follow-ups — implemented, offline-verified

**Date:** 2026-09-29 · **Environment:** project `.venv`, offline (same flags
as above) · **Source revision:** working tree, uncommitted.

| Suite | Result |
|---|---|
| Full Python suite (`unittest discover -s tests`) | **615 tests OK (1 skipped), 0 failures** |
| `openspec validate <change> --strict`, `--changes`, `--specs` | valid / pass |
| `git diff --check` | clean |
| `git diff -- erpnext_read.py` | exactly the three constant-value changes, nothing else |

### Corrected: developer-role fallback semantics (tasks 19.1–19.3)

The previous `resolve_developer_roles()` treated every unreadable state as
absence and fell back to `site_config`, including a raising `get_doc`, a
raising role-rows read, and a raising store check. That is corrected: a
tri-state store check (`True` proven saved / `False` proven never saved /
`None` unknown) now separates the cases. Proven-never-saved is the ONLY
fallback case; proven-saved-but-unreadable, unreadable role rows, and an
unreadable store all return `(None, "unavailable")`, and the gateway logs a
distinct `developer_role_source_unavailable` line (never the malformed-mapping
code) and assigns `employee` without consulting roles. A sentinel-collision
bug found during this correction — malformed `site_config None` classified as
"unavailable" — was fixed by branching on the source, not on `None`.

Test doubles in three files now model genuine absence (`db.sql` → `[]`) by
default; configured and failure states are modeled explicitly per test. No
test was weakened: every rewritten test asserts the stricter behavior.

### Residual resolved: adapter backstop raised to the ceilings (this pass)

The scoped unfreeze was approved and executed: `erpnext_read.py` changed by
exactly three constant values (`MAX_LIST_LIMIT` 20→100, `MAX_FIELD_COUNT`
20→50, `MAX_RESULT_BYTES` 64×1024→128×1024) and nothing else — verified by
`git diff`, which shows only those three lines. All genuine controls are
orthogonal to those numbers (authorization, allowlists, projection-vs-document,
collapse, audit, error semantics, identity handling) and are byte-identical;
the adapter test suite passes unchanged in structure with bound assertions
moved to the new ceilings.

Complete trace after the change, verified against current source:

- `erpnext_read.py:47,52,55` — backstop now 100/50/131072, matching the
  approved ceilings exactly. Still rejects above-ceiling values with the
  standard collapsed denial; still no offset parameter.
- `api.py:_effective_read_bounds` — `min(admin-or-default, ceiling, adapter
  bound)` now resolves to the configured value all the way to the ceiling;
  pre-check denies narrowed bounds before the adapter.
- `service/auth.py` consumer — **was** the blocking defect, now corrected.
  Its business-read bounds sat at 20 rows / a hardcoded `>20` `fields_returned`
  literal / 64 KiB while the producer admitted 100 / 50 / 131072, so a
  Frappe-authorized read above 20 rows or 64 KiB was refused by the inference
  service with HTTP 422. Raised to the producer's approved immutable ceilings
  as named constants (`MAX_AUTHORIZED_CONTEXT_ROWS = 100`,
  `MAX_AUTHORIZED_CONTEXT_FIELDS = 50`, `MAX_AUTHORIZED_CONTEXT_BYTES =
  131072`). Metadata bounds deliberately untouched at 500 / 131072.
- `orchestrator.py` proposal cap — was `min(limit, 20)`, which made the
  approved 100-row ceiling unreachable end to end. Now
  `DEFAULT_READ_LIMIT = 20` (unchanged behaviour when a request names no
  limit) and `MAX_READ_LIMIT = 100`. It only *proposes*; the control plane still
  resolves the effective limit.
- `tools/erpnext.py` legacy client — its `ERPNEXT_MAX_LIST_LIMIT` belongs to
  the retired HTTP client (`/tools/erpnext/*` routes are removed), so it is not
  on the live read path and was left alone.

### Second defect fixed: untouched Settings save preserved no defaults

**Root cause.** `coerce_limit()` mapped a below-minimum integer to the
*minimum*, contradicting its own docstring, and Frappe's Single write path
materialises an unset `Int` as `"0"` in `get_valid_dict()` even though the Desk
client posts `null` (`ControlInt.parse` → `cint(value, null)`). An untouched
save therefore persisted six zeros: the runtime read a never-configured
setting as configured and collapsed every bound to its minimum (1 / 1 / 4096 /
1), and the next save was refused outright.

**Fix, two layers.**

1. `policy_limits.coerce_limit` — a below-minimum value now resolves to the
   **default**, matching its documented contract. Defence in depth: a residual
   or directly-written zero can no longer tighten a setting.
2. `policy_limits.normalise_numeric_settings` (new, called by the
   `NexMate Settings` controller before validation) — writes the documented
   default into every `None`/blank bound while it is still unset, so the
   stored state is exactly what an administrator sees before editing. An
   explicit value, including an explicit `0`, is left for
   `validate_numeric_settings` to judge.

Validation is unchanged: below minimum and above administrator maximum are
still refused, administrator maximums are still accepted, and the runtime
ceiling is still enforced independently.

**Live verification on site `frontend`, through the real DocType lifecycle
(never-configured → load → ordinary save → stored → effective):**

| Check | Result |
|---|---|
| Untouched save, never configured | stored 300/65536/20/20/65536/3; effective `(20, 20, 65536)`, meta `(300, 65536)`, rounds 3 |
| Second untouched save | ACCEPTED, defaults preserved |
| Third untouched save | ACCEPTED |
| Configured 450/100000/75/45/120000/4 then untouched save | all six preserved; effective `(75, 45, 120000)` |
| Desk client payload (`null` ×6) through `frappe.get_doc(body).save()` | defaults stored, effective unchanged |
| Explicit 0 and −5 | REJECTED |
| Explicit 501 / 101 / 51 / 6 / 131073 | REJECTED |
| Administrator maximums | ACCEPTED → effective `(100, 50, 131072)`, meta `(500, 131072)`, rounds 5 |
| Values forced past the ceilings straight into the DB | clamped to `(100, 50, 131072)` / `(500, 131072)` / 5 |
| Site already holding stored zeros | effective resolves to the **default** `(20, 20, 65536)`, not the minimum |

**### Cross-process live verification of the raised ceilings

The Frappe control plane and the inference service are separate processes, so
the consumer was verified against a context the **live site actually produced**,
not a synthesised one. A namespaced 100-row Customer fixture
(`zzverify-nxm-000..099`, since the site held only 3 Customers) was created,
`NexMate Settings` set to `max_read_rows=100 / max_read_fields=50 /
max_read_bytes=131072`, and a real authorized read performed as `Administrator`.
The resulting context was written out and fed to the real
`service.auth.validate_authorized_context` on the host:

| Context | Consumer verdict |
|---|---|
| Real Frappe context, 100 rows / 5 fields / 15366 bytes | **ACCEPTED** |
| Real narrowed context, 5 rows / 924 bytes (`max_read_rows=5`) | **ACCEPTED** |
| Same context with 101 rows | REJECTED 422 |
| Same context with 51 `fields_returned` | REJECTED 422 |
| Same context padded to 135350 bytes | REJECTED 422 |
| Metadata contexts of 300 / 500 / 501 fields | ACCEPTED / ACCEPTED / REJECTED 422 |

In the container, at the configured ceiling, `limit=100` returned `_context`
(100 rows) and `limit=101` returned `_denied`; at `max_read_rows=5`, `limit=5`
returned `_context` and `limit=6` returned `_denied`. The fixture was deleted
afterwards (`Customer` count back to 3).

**Consumer-adapter agreement, asserted in tests:** `MAX_LIST_LIMIT ==
MAX_AUTHORIZED_CONTEXT_ROWS == 100`, `MAX_FIELD_COUNT ==
MAX_AUTHORIZED_CONTEXT_FIELDS == 50`, `MAX_RESULT_BYTES ==
MAX_AUTHORIZED_CONTEXT_BYTES == 131072`, and each `NUMERIC_CEILINGS` entry
equals the matching consumer ceiling.

Recorded residual (not fixed by design).** A site that stored zeros *before*
this fix is no longer degraded at runtime, but its first subsequent save is
still refused, because the loaded value is a genuine `0` and the framework
offers no state that distinguishes it from an administrator having typed `0`.
Recovery is one explicit re-entry of the six documented values, after which
saves succeed normally. This is the price of not accepting `0` as valid input.

Design D17 and the durable-tool-execution backstop scenario describe the
matching backstop; new scenarios record the untouched-save no-op, the retained
rejection of explicit out-of-range values, and the consumer-not-narrower rule.
