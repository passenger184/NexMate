# U5 Change Notes — verification, decisions, and limitations

Running record for `frappe-native-authorized-erpnext-reads`. Appended as work completes.

---

## Group 1 — Frappe 16.31.0 read-contract re-verification (tasks 1.1–1.5)

Re-verified against the installed Frappe `16.31.0` source in the approved test Bench
(`frappe_docker_copilot_test-backend-1`, app path `/home/frappe/frappe-bench/apps/frappe/frappe`).
All paths below are relative to that app path. **No divergence from `design.md` Context was found**,
so the specified contract is unchanged and task 1.5 is satisfied without halting.

### 1.1 Permission-checking list API

| Concern | Anchor | Verified behavior |
|---|---|---|
| Enforcement switch | `database/query.py:260` | `self.apply_permissions = not ignore_permissions` |
| DocType gate | `database/query.py:1362-1367` (`check_select_permission`) | `frappe.has_permission(doctype, "select", …)`; raises `frappe.PermissionError` when denied |
| Row conditions | `database/query.py:1462` (`get_user_permission_conditions`), `query.py:1610` (`get_permission_query_conditions`) | user-permission conditions plus `permission_query_conditions` hooks and Server Script `permission_query` rows, AND-ed |
| Sharing | `database/query.py:1595` | comment *"shared docs trump all other restrictions"*; shared names OR-ed onto the accumulated criterion |
| Field projection filter | `database/query.py:353` | `self.fields = self.apply_field_permissions()`, called only when `apply_permissions` is true |
| Wildcard re-expansion | `database/query.py:1449-1451` | `*` is expanded to `parse_fields(list(permitted_fields_set))` — **not** a raw `SELECT *` |
| Dispatch chain | `__init__.py:1380` → `model/qb_query.py:18` → `database/query.py` | `get_list` routes through the query-builder `DatabaseQuery`, described at `qb_query.py:20` as a *"Copy of db_query.py DatabaseQuery, using query builder instead"* |
| Default asymmetry | `database/query.py:233` = `True`; `model/qb_query.py:40` = `False` | the low-level engine defaults to permissions **disabled**; the list path passes `False` explicitly |

### 1.2 Single-document read — three distinct steps

| Step | Anchor | Verified behavior |
|---|---|---|
| Default | `model/document.py:178-191` (`get_doc_permission_check`) | `if check_permission:` — the default `None` is falsy, so **no check runs**; the document is returned unchecked |
| DocType/document level | `model/document.py:395-412` (`check_permission` → `has_permission`) → `permissions.py:104` | validates DocType/document-level permission only; **no field-level logic** |
| Field level | `model/document.py:955-984` (`apply_fieldlevel_read_permissions`) | a **separate, explicit** method; `delattr`s unauthorized attributes, recurses into child tables (`document.py:977-984`), then applies masking |

The field-level step is **not** invoked by the document getter. It is invoked by the API/handler
layers, e.g. `api/v1.py:79-81`:

```
doc = frappe.get_doc(doctype, name)
doc.check_permission("read")
doc.apply_fieldlevel_read_permissions()
```

This confirms the three steps are distinct and that all three are required.

### 1.3 Serialization: key set from meta, value from the document

| Concern | Anchor | Verified behavior |
|---|---|---|
| Key source | `model/base_document.py:518` | `for fieldname in self.meta.get_valid_fields():` — the key set comes from the **DocType definition** |
| Value source | `model/base_document.py:519` | `value = field_values.get(fieldname)` — from the in-memory document, so a `delattr`-ed field yields `None` |
| Type coercion | `model/base_document.py:552-553` | `if fieldtype == "Check": value = 1 if cint(value) else 0` — `None` becomes `0` |

Consequence: a field removed by the field-level step **still appears in serialized output**, coerced
to its type default. Null-pruning is opt-in. The adapter therefore MUST build its own explicit field
list and prune nulls rather than relying on `as_dict()` alone. This is carried into tasks 5.3 and 10.6.

### 1.4 Forbidden APIs — anchors for each spec entry

| Forbidden API | Anchor | Verified behavior |
|---|---|---|
| `frappe.db.sql` | `database/database.py:183-197` | zero occurrences of `permission`/`has_perm`/`ignore_perm` in the body; no permission parameter exists |
| `frappe.get_all` | `__init__.py:1402-1405` | sets `kwargs["ignore_permissions"] = True` then calls `get_list` |
| `frappe.db.get_value` / `db.count` | thin wrappers over the same raw query path | no permission layer |
| Direct query-builder access | `database/query.py:233` | `ignore_permissions: bool = True` by default |
| Permission-suppressing document flags | `model/document.py:407-408` | `if self.flags.ignore_permissions: return True` |
| `frappe.set_user` | `__init__.py:386-387` | `local.session.user = username; local.session.sid = username` — rebinds the session and clears caches |
| Administrator bypass | `permissions.py:107-110` | `if user == "Administrator": … return True` — first check, unconditional |

`set_user` + the unconditional Administrator bypass together mean any read path able to set the session
user is a total authorization bypass. `set_user` is never used on the read path.

### 1.5 Divergence check

No divergence between the re-verified behavior and `design.md` Context. The specified contract stands
as written; no spec or design amendment is required.

---

## Group 2 — Audit vocabulary (tasks 2.1, 2.2, 2.4)

**Migration dependency (task 2.3 — APPROVAL GATED).** The audit DocType's `action` and `outcome`
fields are closed `Select` fields. Adding the dedicated ERPNext-read action and the read outcome
values requires a DocType option change plus `bench migrate` on the test site. Not run without
explicit approval.

**Rollback (task 2.4).** Revert the `action` and `outcome` option lists to their prior values.
Pre-existing entries remain valid because the added values are purely additive; no entry rewrite or
data migration is involved. Rolling back the option list after entries have been written with the new
values would leave those specific values orphaned, so rollback is only clean if performed before
read events are written, or followed by re-writing the affected entries. This ordering constraint is
recorded here because it is a real operational hazard, not a formality.

---

## Contract bounds recorded (task 4.6)

| Bound | Value | Source |
|---|---|---|
| General read contract maximum list size | 100 | `tools/contracts.py` `erpnext_read.bounded_inputs.limit.maximum` |
| Adapter-level maximum list size | 20 | `erpnext_read.py` `MAX_LIST_LIMIT` (stricter, as designed) |

The general contract maximum is **not** altered by this change.

---

## Implementation evidence — offline (groups 1–10, 12–14)

**Date:** 2026-09-27 · **Environment:** project `.venv`, offline
(`PYTHON_DOTENV_DISABLED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
LITELLM_LOCAL_MODEL_COST_MAP=True`) · **Source revision:** `9a688eb`
(uncommitted working tree)

| Suite | Result |
|---|---|
| Full Python suite (`unittest discover -s tests`) | **457 tests OK (1 skipped), 0 failures** |
| `tests/test_erpnext_read_adapter.py` (new) | 40 tests OK |
| `tests/test_u5_read_boundary.py` (new) | 25 tests OK |
| Gateway read-seam class (in `test_frappe_gateway.py`) | 8 tests OK |
| Node harness `node frappe_app/public/js/copilot.bundle.test.js` | 67 PASS, 0 FAIL |
| `node --check frappe_app/public/js/copilot.bundle.js` | clean |
| `openspec validate <change> --strict` | valid |
| `openspec validate --specs --strict` | 13 passed, 0 failed |
| `git diff --check` | clean |

### Defects found and fixed during implementation

1. **Anti-oracle leak (adapter, fixed).** `collapse_for_caller()` initially
   returned an internal `read_outcome` field. That would have handed the caller
   the very not-found/permission-denied distinction the function exists to
   remove. Removed from the caller-visible object; the distinction now lives
   only in the audit event and the authorized Debug view.
2. **Untranslated Frappe exceptions (adapter, fixed).** `_translate_erpnext_error()`
   was written but never wired in, so a raw `frappe.PermissionError` /
   `DoesNotExistError` would have propagated to the caller — leaking the
   existence oracle and bypassing the audit-on-refusal path. Now wrapped and
   translated.
3. **Two-layer orchestrator wrapper (fixed).** `handle_question` delegates to
   `_handle_question_inner`; the new parameter was initially threaded only
   through the outer layer, producing a `NameError` on the ERPNext branch.
4. **Test-harness module resolution (fixed).** The gateway harness's ad-hoc
   loader did not register the read adapter, and `from __future__ import
   annotations` made dataclass resolution depend on `sys.modules[cls.__module__]`.
   The future import was removed (PEP 604 is native at the project's Python
   floor), which is the more robust fix.

### Behaviour reversals required by the approved decisions

These change previously-asserted behaviour and were **not** silently weakened:

- `test_orchestrator.UnknownDoctypeTest` previously asserted that a 404
  **names the offending DocType**. The anti-oracle requirement (Decision 6)
  forbids exactly that. The business-data read of an unapproved DocType now
  yields one collapsed denial that does not reveal existence. The 404-naming
  regression coverage is **retained against the `schema` operation**, which
  Decision 12 leaves on the legacy client, so that path keeps its coverage.
- `tests/test_routing_eval.py` drives **both legs** of the new seam and asserts
  the read-request shape (no identity, no wildcard) before feeding authorized
  context back. The `evaluation/routing_cases.json` M7 baseline is **deliberately
  not edited**; the declared `tools_called` entry is satisfied by the authorized
  read path instead of a direct client call.
- `test_employee_mode.test_document_list_allowed_for_employees` now asserts
  mode **independence** explicitly: the same user gets the same authorized
  result in developer and employee mode (Decision 11 / L-9).

### Pre-existing issue observed, NOT introduced and NOT fixed here

`tests/test_audit_ledger.py` and `tests/test_durable.py` (both **unmodified** by
this change) leave an `frappe_app/erpnext_ai_copilot/private/durable_fallback/`
directory behind after a run. This is pre-existing M5 test hygiene, outside the
U5 diff scope, and is recorded rather than silently fixed.

### Evidence NOT obtained (approval-gated)

- Live two-user allowed/denied authorization matrix (role, User Permission,
  owner, sharing) — requires creating test data on the Bench.
- `bench migrate` for the audit DocType `action`/`outcome` option change.
- An inference run with the ERPNEXT credential absent.

**Consequence:** this change is **implemented and offline-verified only**. The
live authorization evidence is the same gap M5 left open, and unit/stub results
are **not** reported as live authorization acceptance.

---

## INCIDENT — `bench migrate` deleted the NexMate DocTypes (2026-09-27)

**What happened.** The first `bench --site frontend migrate` (task 2.3) reported:

```
Orphaned DocType(s) found: NexMate Audit Entry, NexMate Conversation,
                           NexMate Tool Proposal, NexMate Conversation Turn
Deleting orphaned DocTypes : [100%]
```

All four DocType **records** were removed. Frappe documents this step as
non-destructive to *data* ("Deleting the entry doesn't delete any data"), and
that held: the four `tabNexMate%` tables and their rows were never dropped.

**Root cause (fully established, source-anchored).** A pre-existing,
app-independent defect in this container's app registration:

1. `sites/apps.txt` did not list `erpnext_ai_copilot` (a container-side
   install gap already recorded in the U5 preflight as a blocker).
2. `get_installed_apps(_ensure_on_bench=True)` filters against
   `cache.get_value("all_apps", get_all_apps)` — a **Redis-cached** copy of
   `sites/apps.txt` (`frappe/__init__.py:938-940`).
3. `setup_module_map()` therefore built `frappe.local.module_app` from only
   `frappe` + `erpnext` (32 modules), omitting the app's module
   (`frappe/__init__.py:1050-1081`).
4. `get_module_app()` raises `frappe.DoesNotExistError` when the scrubbed module
   is absent from that map (`frappe/modules/utils.py:334-339`).
5. `get_controller()` → `load_doctype_module()` propagates that, and
   `remove_orphan_doctypes()` catches `(ImportError, frappe.DoesNotExistError)`
   and deletes the DocType (`frappe/model/sync.py:180-196`).

**Not caused by the U5 change.** Verified independently: every app module
imports cleanly (including the modified `api.py`), the controller import path
`erpnext_ai_copilot.erpnext_ai_copilot.doctype.<dt>.<dt>` resolves, and the
DocType JSONs at `HEAD` (`9a688eb`) are unchanged in this respect. **Any**
`bench migrate` on this site would have destroyed these DocTypes since the
2026-09-18 container-side install.

**Fix applied.** Added `erpnext_ai_copilot` to `sites/apps.txt` (backed up to
`sites/apps.txt.u5bak`) and cleared the Redis caches `all_apps`,
`app_modules` and `installed_app_modules`, then rebuilt the module map.

**Verification after fix.**
- `module_app` size 33, `erpnext_ai_copilot` present.
- `get_controller()` succeeds for all four DocTypes.
- `bench --site frontend migrate` completes with **no** orphan deletion.
- `record_audit()` now persists to the DB (`audit_pending: None`) with
  `action="erpnext_read"`, `outcome="success"`; the legacy `retrieval` action
  still writes correctly.

**Residual note:** `apps.txt` and the module map are environment state, not
repository state. The absent-`apps.txt` entry is the kind of container-side gap
M6 already recorded; it belongs to the M6/U8 packaging follow-up, not to U5.

---

## Live evidence — test Bench `frontend` (tasks 2.3, 10.2–10.5, 11.1–11.8)

**Date:** 2026-09-27 · **Site:** `frontend` (test Bench only; the forbidden
repository was never accessed) · **Frappe** 16.31.0 / **ERPNext** 16.33.0
· **Approval:** explicit project-owner approval for the migration, the
fixtures, and the live runs.

### Defect found by the live run (would have shipped broken)

`_audit()` originally imported the ledger as
`from frappe_app.erpnext_ai_copilot import audit`. That is the **repo** path;
the installed package is `erpnext_ai_copilot`. In the live site every read
therefore failed the audit write and — correctly, by design — **denied the
read** (fail-closed held; availability did not). Offline tests had mocked the
repo path, so they passed. Fixed to a sibling import `from . import audit`,
which resolves under both layouts. Re-verified: 457 tests OK, live reads pass.
**This is the single strongest argument in this change for the live gate.**

### Fixtures provisioned (all prefixed `u5-`)

| Fixture | Value | Purpose |
|---|---|---|
| User A | `u5-allowed@nexmate.test` — roles `Sales User`, `Desk User` (+`All`, `Guest`) | has Customer read |
| User B | `u5-restricted@nexmate.test` — roles `Desk User` only (+`All`, `Guest`) | no Customer read |
| Territories | `u5-territory-a`, `u5-territory-b` | User Permission discriminator |
| Customers | `u5-allowed-cust` (territory-a), `u5-denied-cust` (territory-b) | UP targets |
| User Permission | User A → `Territory` = `u5-territory-a`, `apply_to_all_doctypes=1` | L-4 |
| DocShare | User B ← read on `Customer/u5-denied-cust` | L-6 |
| Note | one `Note` created **as** A (owner = A) | L-5 `if_owner` |

### Results

| # | Check | Result |
|---|---|---|
| 2.3 | `bench --site frontend migrate` | exit 0; all 4 NexMate DocTypes persist; **no** orphan deletion; `erpnext_read` action (21 options, `retrieval` preserved) and `not_found`/`permission_denied`/`invalid_request` outcomes (11) live; `record_audit` persists to the DB (`audit_pending: None`) |
| 10.2 / L-3 | Role authorization, `list Customer` as A vs B | A → `['Test','u5-allowed-cust']`; B → `['u5-denied-cust']`. **Row sets differ.** |
| 10.3 / L-4 | User Permission (A restricted to territory-a) | A sees `u5-allowed-cust`; A does **not** see `u5-denied-cust` |
| 10.4 / L-5 | `if_owner` (Note owned by A, `Desk User` read=0/if_owner=1) | owner A `get_list` → the Note; non-owner B → `[]` |
| 10.5 / L-6 | DocShare (B has read on `u5-denied-cust`) | B sees `u5-denied-cust` and **not** `u5-allowed-cust` |
| 11.3 | Allowed/denied matrix, both users, document + list | as above; every refusal a typed `ReadRefusal` |
| 11.4 | Mode independence | adapter has no `mode` in `execute_read`; both modes share the one boundary (offline suite) |
| 11.5 | Field minimization | only requested fields returned; `u5-allowed-cust` read returned exactly `name`/`customer_name` |
| 11.6 | Audit for permitted + denied reads | exactly **3** `erpnext_read` events for 3 reads: `success` (actor A), `permission_denied` (actor B), `not_found` (actor A); all `site=frontend`; details metadata-only, no business values |
| 11.7 | Credential-absent authorized read | with `ERPNEXT_API_KEY`/`ERPNEXT_API_SECRET`/`ERPNEXT_BASE_URL` **unset**, the authorized read still returns the correct user-scoped rows. Static check: the orchestrator business branch calls neither `get_document` nor `list_documents`; only `get_doctype_schema` remains (documented temporary schema consumer) |
| — | Anti-oracle (L-8) | not-found and permission-denied produce **byte-identical** caller dicts |
| — | Hostile request rejection (L-11) | wildcard fields, unapproved doctype, forged `user`, `owner` filter, `schema` op → all rejected `invalid_request` |
| — | Regression | 457 Python tests OK (1 skipped); 67 Node PASS; `node --check` clean |

### Honesty notes and residual limits

1. **User A also sees `Test`.** `Test` has an **empty** territory, and
   `apply_strict_user_permissions` is `0` on this site, so Frappe's non-strict
   User Permission allows an empty link field through. This is Frappe's own
   documented behaviour, recorded during the Step 0 investigation, and it is
   **not** a U5 defect — but it is a real residual widening: a User Permission
   does not strictly exclude records whose restricted link field is empty. The
   U5 narrowing is therefore "cannot widen", not "always strictly narrow".
2. **L-7 field-level permlevel is still not live-demonstrated** through the
   adapter. No DocType in the approved read policy carries a `permlevel > 0`
   field, and `Appointment Booking Settings` is a Single doctype (outside the
   policy). The mechanism remains **source-proven + Step 0 live-proven on the
   engine**, and enforced by the adapter's explicit projection plus
   null-pruning. It is not adapter-level live evidence.
3. **The shared ERPNEXT credential is still present** for the version lookup
   and the legacy write path. This change does not remove it and does not
   reduce inference-side ERPNext risk to zero.
4. **Schema/metadata reads remain on the retained legacy client**, by Decision
   12; native metadata authorization is future work.
5. **Multi-site is untouched** (U1). The global `ERPNEXT_BASE_URL` problem is
   unchanged, and `sites/apps.txt` / module-map state remain **environment**
   facts, not repository facts — the absent `apps.txt` entry belongs to the
   M6/U8 packaging follow-up.
6. **Fixtures are left in place** on the test site so the evidence stays
   reproducible. They are `u5-`-prefixed test data with no real business
   content and can be removed by deleting the two `u5-*` users, the two
   territories, the two customers, the one User Permission, the one DocShare
   and the one Note.
