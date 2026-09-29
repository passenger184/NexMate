"""Capability- and policy-gated, Frappe-native DocType metadata access.

Covers the metadata module's authorization order, the administrator-controlled
policy with its fail-closed behaviour, the exact five-field projection, the
declared bounds, the dedicated audit action with fail-closed audit-result
handling, and the metadata-specific anti-oracle collapse.

`erpnext_read.py` and `audit.py` are NOT exercised for authorization here; the
metadata surface is deliberately separate and this module asserts that.
"""

import json
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import importlib.util
import sys
import types
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frappe_app" / "erpnext_ai_copilot"


def _load(name: str, path: Path, frappe_module):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with mock.patch.dict(sys.modules, {"frappe": frappe_module}):
        spec.loader.exec_module(module)
    return module


class _Field:
    def __init__(self, fieldname, fieldtype="Data", label=None,
                 reqd=0, read_only=0, options=None, permlevel=0):
        self.fieldname = fieldname
        self.fieldtype = fieldtype
        self.label = label if label is not None else fieldname
        self.reqd = reqd
        self.read_only = read_only
        # Present in the real meta object; MUST NOT reach the projection.
        self.options = options
        self.permlevel = permlevel


class _Meta:
    def __init__(self, name, istable=False, issingle=False, fields=()):
        self.name = name
        self.istable = istable
        self.issingle = issingle
        self.fields = list(fields)


class _Row:
    def __init__(self, doctype):
        # Mirrors the child-table Link field; named target_doctype because a
        # field literally named "doctype" would shadow Document.doctype.
        self.target_doctype = doctype


class _Settings:
    def __init__(self, mode=None, rows=None, numeric=None):
        self.metadata_access_mode = mode
        self._rows = [ _Row(r) for r in (rows or []) ]
        for key, value in (numeric or {}).items():
            setattr(self, key, value)

    def get(self, key, default=None):
        if key == "metadata_doctype_rules":
            return self._rows
        return default


class MetadataTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.frappe = types.ModuleType("frappe")
        self.frappe.conf = {}
        self.frappe.session = types.SimpleNamespace(user="synthetic-user")
        self.frappe.local = types.SimpleNamespace(site="synthetic-site")
        self.records = {}
        self.audit_entries = []
        self.audit_result = {"name": "NMAU-1"}

        def get_meta(doctype):
            if doctype not in self.records:
                raise Exception("does not exist")
            return self.records[doctype]

        self.frappe.get_meta = mock.Mock(side_effect=get_meta)
        self.get_doc_calls = []

        def get_doc(doctype, name=None, **kwargs):
            self.get_doc_calls.append((doctype, name))
            if doctype not in self.settings_by_doctype:
                raise Exception("no settings")
            return self.settings_by_doctype[doctype]

        self.settings_by_doctype = {}
        self.frappe.get_doc = mock.Mock(side_effect=get_doc)

        self.audit = _load("erpnext_ai_copilot.audit_probe", APP / "audit.py", self.frappe)
        self.audit.record_audit = mock.Mock(side_effect=self._record_audit)
        self.audit._require_durable_store = mock.Mock(return_value=None)
        self.audit._should_use_frappe = mock.Mock(return_value=False)

        # The real limits module: dependency-free offline, and the single
        # source of truth the metadata module resolves bounds from.
        self.policy_limits = _load(
            "erpnext_ai_copilot.policy_limits_probe", APP / "policy_limits.py",
            self.frappe)

        package = types.ModuleType("erpnext_ai_copilot")
        package.audit = self.audit
        package.policy_limits = self.policy_limits
        api = types.ModuleType("erpnext_ai_copilot.api")
        api.capability_for_user = mock.Mock(return_value="developer")
        package.api = api
        self.api = api

        patcher = mock.patch.dict(sys.modules, {
            "frappe": self.frappe,
            "erpnext_ai_copilot": package,
            "erpnext_ai_copilot.audit": self.audit,
            "erpnext_ai_copilot.api": api,
            "erpnext_ai_copilot.policy_limits": self.policy_limits,
        })
        patcher.start()
        self.addCleanup(patcher.stop)

        self.dm = _load("erpnext_ai_copilot.doctype_meta", APP / "doctype_meta.py",
                        self.frappe)
        self.dm.frappe = self.frappe

    def _record_audit(self, **kwargs):
        self.audit_entries.append(kwargs)
        return self.audit_result

    def add_meta(self, name, **kwargs):
        self.records[name] = _Meta(name, **kwargs)
        return self.records[name]

    def set_policy(self, mode=None, rows=None, numeric=None):
        self.settings_by_doctype[self.dm.SETTINGS_DOCTYPE] = _Settings(mode, rows, numeric)

    def set_capability(self, capability):
        self.api.capability_for_user = mock.Mock(return_value=capability)


class AuthorizationOrderTest(MetadataTestBase):
    def test_capability_is_evaluated_before_existence_and_policy(self):
        self.add_meta("Customer", fields=[_Field("name")])
        self.set_policy("all")
        self.set_capability("employee")
        with self.assertRaises(self.dm.CapabilityDenied):
            self.dm.attempt_metadata({"doctype": "Customer"})
        # No metadata lookup and no policy read happened.
        self.frappe.get_meta.assert_not_called()
        self.assertEqual(self.get_doc_calls, [])

    def test_administrator_bypass_cannot_reach_metadata(self):
        """Frappe allows Administrator unconditionally; the gate runs first."""
        self.add_meta("Customer", fields=[_Field("name")])
        self.set_policy("all")
        self.set_capability("employee")
        self.frappe.session.user = "Administrator"
        with self.assertRaises(self.dm.CapabilityDenied):
            self.dm.attempt_metadata({"doctype": "Customer"})
        # The refusal is audited against the real session actor.
        self.assertEqual(len(self.audit_entries), 1)
        self.assertEqual(self.audit_entries[0]["actor"], "Administrator")
        self.assertEqual(self.audit_entries[0]["outcome"], "permission_denied")
        self.frappe.get_meta.assert_not_called()

    def test_guest_and_absent_session_are_refused(self):
        for user in ("Guest", "", None):
            self.frappe.session.user = user
            with self.assertRaises(self.dm.CapabilityDenied):
                self.dm.attempt_metadata({"doctype": "Customer"})

    def test_doctype_must_exist(self):
        self.set_policy("all")
        with self.assertRaises(self.dm.DocTypeNotFound):
            self.dm.attempt_metadata({"doctype": "NoSuchDocType"})

    def test_istable_denied_in_all_mode(self):
        self.add_meta("Sales Invoice Item", istable=True)
        self.set_policy("all")
        with self.assertRaises(self.dm.NotStructurallyInspectable):
            self.dm.attempt_metadata({"doctype": "Sales Invoice Item"})

    def test_issingle_denied_in_all_mode(self):
        self.add_meta("System Settings", issingle=True)
        self.set_policy("all")
        with self.assertRaises(self.dm.NotStructurallyInspectable):
            self.dm.attempt_metadata({"doctype": "System Settings"})

    def test_istable_denied_even_when_listed_in_allowlist(self):
        self.add_meta("Sales Invoice Item", istable=True)
        self.set_policy("allowlist", ["Sales Invoice Item"])
        with self.assertRaises(self.dm.NotStructurallyInspectable):
            self.dm.attempt_metadata({"doctype": "Sales Invoice Item"})

    def test_issingle_denied_even_when_listed_in_allowlist(self):
        self.add_meta("System Settings", issingle=True)
        self.set_policy("allowlist", ["System Settings"])
        with self.assertRaises(self.dm.NotStructurallyInspectable):
            self.dm.attempt_metadata({"doctype": "System Settings"})

    def test_structural_exclusions_precede_the_policy_decision(self):
        """An unlisted child table is refused as a structural exclusion, not policy."""
        self.add_meta("Sales Invoice Item", istable=True)
        self.set_policy("allowlist", ["Customer"])
        with self.assertRaises(self.dm.NotStructurallyInspectable):
            self.dm.attempt_metadata({"doctype": "Sales Invoice Item"})

    def test_has_permission_is_not_the_metadata_gate(self):
        self.add_meta("Customer", fields=[_Field("name")])
        self.set_policy("all")
        self.frappe.has_permission = mock.Mock(side_effect=AssertionError("used"))
        out = self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual(out["doctype"], "Customer")
        self.frappe.has_permission.assert_not_called()

    def test_module_does_not_import_the_business_read_adapter(self):
        import ast
        source = (APP / "doctype_meta.py").read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("erpnext_read", imported)

    def test_policy_never_grants_business_record_access(self):
        """A permitted DocType confers no record permission."""
        self.add_meta("Customer", fields=[_Field("name")])
        self.set_policy("all")
        self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual(self.audit_entries[-1]["action"], self.dm.AUDIT_ACTION_METADATA)
        # No business-read audit action was emitted and no read was performed.
        self.assertNotIn("erpnext_read",
                         json.dumps([e["action"] for e in self.audit_entries]))


class PolicySemanticsTest(MetadataTestBase):
    def setUp(self):
        super().setUp()
        self.add_meta("Customer", fields=[_Field("name")])
        self.add_meta("Item", fields=[_Field("name")])
        self.add_meta("Sales Order", fields=[_Field("name")])

    def test_all_permits_any_eligible_existing_doctype(self):
        self.set_policy("all")
        for doctype in ("Customer", "Item", "Sales Order"):
            out = self.dm.attempt_metadata({"doctype": doctype})
            self.assertEqual(out["doctype"], doctype)

    def test_allowlist_permits_only_configured_doctypes(self):
        self.set_policy("allowlist", ["Customer", "Item"])
        self.assertEqual(self.dm.attempt_metadata({"doctype": "Customer"})["doctype"], "Customer")
        with self.assertRaises(self.dm.PolicyDenied):
            self.dm.attempt_metadata({"doctype": "Sales Order"})

    def test_missing_settings_denies(self):
        self.settings_by_doctype = {}
        with self.assertRaises(self.dm.PolicyUnavailable):
            self.dm.attempt_metadata({"doctype": "Customer"})

    def test_unset_mode_denies(self):
        for mode in (None, "", "   "):
            self.set_policy(mode)
            with self.subTest(mode=mode):
                with self.assertRaises(self.dm.PolicyUnavailable):
                    self.dm.attempt_metadata({"doctype": "Customer"})

    def test_unsupported_mode_denies(self):
        for mode in ("ALLOWLIST", "everything", "none", "allowlist "):
            self.set_policy(mode if mode != "allowlist " else "allowlist ")
            with self.subTest(mode=mode):
                if mode.strip() in self.dm.SUPPORTED_MODES:
                    continue
                with self.assertRaises(self.dm.PolicyUnavailable):
                    self.dm.attempt_metadata({"doctype": "Customer"})

    def test_empty_allowlist_denies_and_never_defaults_to_all(self):
        self.set_policy("allowlist", [])
        with self.assertRaises(self.dm.PolicyUnavailable):
            self.dm.attempt_metadata({"doctype": "Customer"})

    def test_unreadable_settings_denies(self):
        self.frappe.get_doc = mock.Mock(side_effect=RuntimeError("boom"))
        with self.assertRaises(self.dm.PolicyUnavailable):
            self.dm.attempt_metadata({"doctype": "Customer"})

    def test_policy_read_is_uncached(self):
        self.set_policy("all")
        self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual(self.get_doc_calls, [(self.dm.SETTINGS_DOCTYPE,
                                              self.dm.SETTINGS_DOCTYPE)])
        # `frappe.get_doc`, never a cached variant.
        for call in self.frappe.get_doc.call_args_list:
            self.assertNotIn("cache", call.kwargs)

    def test_committed_change_affects_the_next_decision(self):
        self.set_policy("allowlist", ["Customer"])
        self.assertEqual(self.dm.attempt_metadata({"doctype": "Customer"})["doctype"], "Customer")
        self.set_policy("allowlist", ["Item"])
        with self.assertRaises(self.dm.PolicyDenied):
            self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual(self.dm.attempt_metadata({"doctype": "Item"})["doctype"], "Item")

    def test_policy_is_not_read_from_site_config(self):
        """A site-config key of the same name has no effect whatsoever."""
        self.add_meta("Sales Order", fields=[_Field("name")])
        self.set_policy("allowlist", ["Customer"])
        # Even when site config claims allowlist mode, the settings record is the
        # only source of truth; Sales Order stays refused.
        self.frappe.conf["nexmate_metadata_access_mode"] = "all"
        with self.assertRaises(self.dm.PolicyDenied):
            self.dm.attempt_metadata({"doctype": "Sales Order"})
        source = (APP / "doctype_meta.py").read_text(encoding="utf-8")
        self.assertNotIn("frappe.conf", source)

    def test_site_isolation_is_per_site_settings_record(self):
        # Two sites resolve different settings records; one site's policy does
        # not influence the other because the record is read per request from
        # the current site's context.
        self.frappe.local.site = "site-a"
        self.set_policy("all")
        self.assertEqual(self.dm.attempt_metadata({"doctype": "Sales Order"})["doctype"],
                         "Sales Order")
        self.frappe.local.site = "site-b"
        self.set_policy("allowlist", ["Customer"])
        with self.assertRaises(self.dm.PolicyDenied):
            self.dm.attempt_metadata({"doctype": "Sales Order"})
        self.assertEqual(self.audit_entries[-1]["site"], "site-b")


class ProjectionTest(MetadataTestBase):
    def test_projection_is_exactly_five_structural_attributes(self):
        self.add_meta("Customer", fields=[
            _Field("customer_name", "Data", "Customer Name", reqd=1),
            _Field("disabled", "Check", "Disabled", read_only=1),
        ])
        self.set_policy("all")
        out = self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual([f["fieldname"] for f in out["fields"]],
                         ["customer_name", "disabled"])
        for entry in out["fields"]:
            self.assertEqual(set(entry), set(self.dm.PROJECTION_FIELDS))
        self.assertIs(out["fields"][0]["reqd"], True)
        self.assertIs(out["fields"][1]["read_only"], True)

    def test_projection_excludes_options_and_permlevel(self):
        self.add_meta("Item", fields=[
            _Field("status", "Select", "Status", options="Draft\nOpen\nClosed"),
            _Field("item_group", "Link", "Item Group", options="All Item Groups"),
            _Field("cost", "Currency", "Cost", permlevel=1),
        ])
        self.set_policy("all")
        out = self.dm.attempt_metadata({"doctype": "Item"})
        blob = json.dumps(out)
        self.assertNotIn("Draft", blob)
        self.assertNotIn("All Item Groups", blob)
        self.assertNotIn("options", blob)
        self.assertNotIn("permlevel", blob)
        self.assertNotIn("permissions", blob)

    def test_projection_carries_no_values_or_rows(self):
        self.add_meta("Customer", fields=[_Field("name")])
        self.set_policy("all")
        out = self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual(set(out), {"doctype", "fields"})
        self.assertNotIn("data", out)
        self.assertNotIn("rows", out)

    def test_field_bound_is_declared_and_enforced(self):
        # Default 300 applies while unconfigured: 101 fields fit, 301 do not.
        self.add_meta("Wide", fields=[_Field(f"f{i}") for i in range(101)])
        self.set_policy("all")
        out = self.dm.attempt_metadata({"doctype": "Wide"})
        self.assertEqual(len(out["fields"]), 101)
        self.add_meta("TooWide", fields=[_Field(f"f{i}") for i in range(301)])
        with self.assertRaises(self.dm.OversizedProjection):
            self.dm.attempt_metadata({"doctype": "TooWide"})

    def test_field_bound_at_the_limit_is_served(self):
        self.add_meta("Wide", fields=[_Field(f"f{i}") for i in range(300)])
        self.set_policy("all")
        out = self.dm.attempt_metadata({"doctype": "Wide"})
        self.assertEqual(len(out["fields"]), 300)

    def test_configured_field_bound_is_enforced(self):
        self.add_meta("Wide", fields=[_Field(f"f{i}") for i in range(60)])
        self.set_policy("all", numeric={"max_schema_fields": 50})
        with self.assertRaises(self.dm.OversizedProjection):
            self.dm.attempt_metadata({"doctype": "Wide"})
        self.set_policy("all")
        out = self.dm.attempt_metadata({"doctype": "Wide"})
        self.assertEqual(len(out["fields"]), 60)

    def test_service_ceiling_bounds_even_a_permissive_setting(self):
        self.add_meta("Huge", fields=[_Field(f"f{i}") for i in range(501)])
        self.set_policy("all", numeric={"max_schema_fields": 500})
        with self.assertRaises(self.dm.OversizedProjection):
            self.dm.attempt_metadata({"doctype": "Huge"})

    def test_a_production_sized_doctype_fits(self):
        # Customer carries 87 fields on the live test site; the declared bound
        # must not refuse it.
        self.add_meta("Customer", fields=[_Field(f"f{i}") for i in range(87)])
        self.set_policy("all")
        self.assertEqual(len(self.dm.attempt_metadata({"doctype": "Customer"})["fields"]), 87)

    def test_serialized_size_bound_is_declared(self):
        self.assertEqual(self.policy_limits.SCHEMA_BYTES_CEILING, 131072)
        self.assertEqual(self.policy_limits.DEFAULT_SCHEMA_FIELDS, 300)
        self.assertEqual(self.policy_limits.DEFAULT_SCHEMA_BYTES, 65536)


class _NullableField:
    """A DocField double that can genuinely hold ``None``.

    The shared ``_Field`` used by the other suites defaults ``label`` to the
    fieldname, so it can never represent an unlabelled field. Frappe leaves
    ``label`` NULL for every Section Break, Column Break and HTML field, and
    for some ordinary data fields, so the contract has to be exercised against
    a real ``None`` rather than a stand-in.
    """

    def __init__(self, fieldname, fieldtype="Data", label=None,
                 reqd=0, read_only=0, options=None, permlevel=0):
        self.fieldname = fieldname
        self.fieldtype = fieldtype
        self.label = label
        self.reqd = reqd
        self.read_only = read_only
        self.options = options
        self.permlevel = permlevel


class ProjectionValueContractTest(MetadataTestBase):
    """The projection is total: no attribute is ever ``None`` (design D22)."""

    STRING_KEYS = ("fieldname", "fieldtype", "label")
    FLAG_KEYS = ("reqd", "read_only")

    def _project(self, *fields):
        self.add_meta("Customer", fields=list(fields))
        return self.dm.project_meta(self.records["Customer"], max_fields=300)

    def test_null_label_becomes_empty_string(self):
        out = self._project(_NullableField("section_break", "Section Break", label=None))
        self.assertEqual(out["fields"][0]["label"], "")

    def test_null_fieldname_becomes_empty_string(self):
        out = self._project(_NullableField(None, "Data", label="X"))
        self.assertEqual(out["fields"][0]["fieldname"], "")

    def test_null_fieldtype_becomes_empty_string(self):
        out = self._project(_NullableField("f", None, label="X"))
        self.assertEqual(out["fields"][0]["fieldtype"], "")

    def test_null_flags_become_false(self):
        out = self._project(_NullableField("f", "Data", label="X", reqd=None, read_only=None))
        self.assertIs(out["fields"][0]["reqd"], False)
        self.assertIs(out["fields"][0]["read_only"], False)

    def test_integer_flags_become_booleans(self):
        out = self._project(
            _NullableField("a", "Data", label="A", reqd=1, read_only=0),
            _NullableField("b", "Data", label="B", reqd=0, read_only=1))
        self.assertIs(out["fields"][0]["reqd"], True)
        self.assertIs(out["fields"][0]["read_only"], False)
        self.assertIs(out["fields"][1]["reqd"], False)
        self.assertIs(out["fields"][1]["read_only"], True)

    def test_all_five_keys_present_on_every_entry(self):
        out = self._project(
            _NullableField("a", "Column Break", label=None),
            _NullableField("b", "Data", label="B", reqd=1))
        self.assertEqual(len(out["fields"]), 2)
        for entry in out["fields"]:
            self.assertEqual(set(entry), set(self.dm.PROJECTION_FIELDS))
            self.assertEqual(sorted(entry), sorted(self.dm.PROJECTION_FIELDS))

    def test_no_projected_value_is_none(self):
        out = self._project(
            _NullableField("a", "Section Break", label=None, reqd=None, read_only=None),
            _NullableField("b", None, None, None, None),
            _NullableField("c", "Data", label="C"))
        for entry in out["fields"]:
            for key, value in entry.items():
                self.assertIsNotNone(value, "%s must not be None" % key)

    def test_no_key_is_dropped_when_every_value_is_null(self):
        out = self._project(_NullableField(None, None, None, None, None))
        self.assertEqual(sorted(out["fields"][0]), sorted(self.dm.PROJECTION_FIELDS))
        self.assertEqual(out["fields"][0],
                         {"fieldname": "", "fieldtype": "", "label": "",
                          "reqd": False, "read_only": False})

    def test_valid_scalars_are_preserved_unchanged(self):
        out = self._project(
            _NullableField("customer_name", "Data", label="Customer Name", reqd=1))
        entry = out["fields"][0]
        self.assertEqual(entry["fieldname"], "customer_name")
        self.assertEqual(entry["fieldtype"], "Data")
        self.assertEqual(entry["label"], "Customer Name")
        self.assertIs(entry["reqd"], True)
        self.assertIs(entry["read_only"], False)

    def test_non_null_non_flag_value_is_not_coerced_to_string(self):
        """No blanket ``str(value)``: an unflagged value crosses untouched."""
        marker = ["not", "a", "scalar"]
        out = self._project(_NullableField("f", "Data", label=marker))
        self.assertIs(out["fields"][0]["label"], marker)

    def test_string_attributes_are_str_and_flags_are_bool(self):
        out = self._project(
            _NullableField("a", "Section Break", label=None, reqd=None, read_only=None),
            _NullableField("b", "Data", label="B", reqd=1, read_only=0))
        for entry in out["fields"]:
            for key in self.STRING_KEYS:
                self.assertIs(type(entry[key]), str, key)
            for key in self.FLAG_KEYS:
                # Exact type: a raw 0/1 integer from Frappe must have become
                # a real bool. isinstance() alone cannot prove this, because
                # bool is a subclass of int.
                self.assertIs(type(entry[key]), bool, key)

    def test_flag_field_set_is_declared_and_matches_the_projection(self):
        self.assertEqual(set(self.dm.PROJECTION_FLAG_FIELDS), set(self.FLAG_KEYS))
        self.assertTrue(set(self.dm.PROJECTION_FLAG_FIELDS)
                        < set(self.dm.PROJECTION_FIELDS))

    def test_attempt_metadata_also_yields_a_total_projection(self):
        """End of the producer path, not just the helper: no null survives."""
        self.add_meta("Customer", fields=[
            _NullableField("section_break", "Section Break", label=None),
            _NullableField("column_break", "Column Break", label=None),
            _NullableField("description", "Small Text", label=None, reqd=None),
        ])
        self.set_policy("all")
        out = self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual(len(out["fields"]), 3)
        for entry in out["fields"]:
            self.assertEqual(sorted(entry), sorted(self.dm.PROJECTION_FIELDS))
            for key, value in entry.items():
                self.assertIsNotNone(value)


class AuditTest(MetadataTestBase):
    def setUp(self):
        super().setUp()
        self.add_meta("Customer", fields=[_Field("name")])
        self.set_policy("all")

    def test_exactly_one_access_event_per_permitted_request(self):
        self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual(len(self.audit_entries), 1)
        entry = self.audit_entries[0]
        self.assertEqual(entry["action"], "doctype_schema")
        self.assertEqual(entry["outcome"], "success")
        self.assertEqual(entry["actor"], "synthetic-user")
        self.assertEqual(entry["site"], "synthetic-site")
        self.assertEqual(entry["target"], "Customer")

    def test_access_event_carries_no_metadata_payload(self):
        self.dm.attempt_metadata({"doctype": "Customer"})
        details = self.audit_entries[0]["details"]
        self.assertEqual(set(details) <= set(self.dm.AUDIT_DETAIL_KEYS), True)
        self.assertNotIn("fields", details)
        self.assertNotIn("data", details)
        self.assertNotIn("name", json.dumps(details))

    def test_exactly_one_access_event_per_refusal(self):
        self.set_policy("allowlist", ["Item"])
        with self.assertRaises(self.dm.PolicyDenied):
            self.dm.attempt_metadata({"doctype": "Customer"})
        self.assertEqual(len(self.audit_entries), 1)
        self.assertEqual(self.audit_entries[0]["outcome"], "permission_denied")

    def test_audit_failure_denies_schema(self):
        self.audit.record_audit = mock.Mock(side_effect=RuntimeError("audit down"))
        with self.assertRaises(RuntimeError):
            self.dm.attempt_metadata({"doctype": "Customer"})

    def test_pending_audit_result_denies_schema(self):
        """record_audit can return normally with audit_pending; fail closed."""
        self.audit_result = {"name": "NMAU-1", "audit_pending": True}
        with self.assertRaises(self.dm.AuditUnavailable):
            self.dm.attempt_metadata({"doctype": "Customer"})

    def test_non_dict_audit_result_denies_schema(self):
        self.audit_result = None
        with self.assertRaises(self.dm.AuditUnavailable):
            self.dm.attempt_metadata({"doctype": "Customer"})

    def test_outcomes_reuse_existing_audit_vocabulary(self):
        existing = {"success", "denied", "not_found", "permission_denied",
                    "invalid_request", "audit_pending"}
        for code in self.dm._audit_outcome.__globals__ and (
                self.dm.CAPABILITY_DENIED, self.dm.POLICY_DENIED,
                self.dm.POLICY_UNAVAILABLE, self.dm.NOT_FOUND,
                self.dm.INVALID_REQUEST, self.dm.OVERSIZED,
                self.dm.OUTCOME_SUCCESS):
            self.assertIn(self.dm._audit_outcome(code), existing)


class CollapseTest(MetadataTestBase):
    def test_every_refusal_reason_collapses_to_one_response(self):
        self.add_meta("Customer", fields=[_Field("name")])
        self.add_meta("Item", fields=[_Field("name")])
        self.add_meta("Sales Invoice Item", istable=True)
        self.add_meta("System Settings", issingle=True)
        self.set_policy("allowlist", ["Item"])

        cases = [
            self.dm.CapabilityDenied("capability denied"),
            self.dm.PolicyDenied("policy denied"),
            self.dm.PolicyUnavailable("policy unavailable"),
            self.dm.NotStructurallyInspectable("istable"),
            self.dm.NotStructurallyInspectable("issingle"),
            self.dm.DocTypeNotFound("not found"),
            self.dm.InvalidRequest("invalid"),
            self.dm.OversizedProjection("oversized"),
            self.dm.AuditUnavailable("audit unavailable"),
        ]
        collapsed = {json.dumps(self.dm.collapse_for_caller(c), sort_keys=True)
                     for c in cases}
        self.assertEqual(len(collapsed), 1, collapsed)

    def test_collapse_uses_the_metadata_wording_and_route(self):
        out = self.dm.collapse_for_caller(self.dm.CapabilityDenied("x"))
        self.assertEqual(out["answer"], "Schema not found or access denied.")
        self.assertEqual(out["route_how"], "frappe-schema+denied")

    def test_collapse_never_labels_a_business_record_denial(self):
        out = self.dm.collapse_for_caller(self.dm.PolicyDenied("x"))
        self.assertNotIn("Document not found", out["answer"])
        self.assertNotIn("frappe-authorized-read", out["route_how"])

    def test_collapse_hides_the_internal_reason(self):
        for refusal in (self.dm.CapabilityDenied("capability denied"),
                        self.dm.NotStructurallyInspectable("child table"),
                        self.dm.DocTypeNotFound("Sales Order missing")):
            out = self.dm.collapse_for_caller(refusal)
            blob = json.dumps(out)
            self.assertNotIn(refusal.code, blob)
            self.assertNotIn("Sales Order", blob)
            self.assertNotIn("child table", blob)

    def test_nonexistent_doctype_is_indistinguishable_from_a_refused_one(self):
        missing = self.dm.collapse_for_caller(self.dm.DocTypeNotFound("x"))
        refused = self.dm.collapse_for_caller(self.dm.PolicyDenied("x"))
        self.assertEqual(missing, refused)


class SettingsDocumentTest(MetadataTestBase):
    """The `NexMate Settings` controller's own validation."""

    def _load_settings(self):
        path = (APP / "erpnext_ai_copilot" / "doctype" / "nexmate_settings"
                / "nexmate_settings.py")
        module = types.ModuleType("nexmate_settings_probe")
        module.__dict__["__name__"] = "nexmate_settings_probe"
        module.__dict__["__file__"] = str(path)
        self.frappe._ = lambda s: s
        self.frappe.throw = mock.Mock()
        self.frappe.model = types.ModuleType("frappe.model")
        document = types.ModuleType("frappe.model.document")
        document.Document = object
        self.frappe.model.document = document
        with mock.patch.dict(sys.modules, {
            "frappe": self.frappe,
            "frappe.model": self.frappe.model,
            "frappe.model.document": document,
        }):
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"),
                 module.__dict__)
        return module

    def test_supported_modes_are_exactly_all_and_allowlist(self):
        module = self._load_settings()
        self.assertEqual(module.SUPPORTED_METADATA_ACCESS_MODES, ("all", "allowlist"))

    def test_unsupported_mode_is_refused(self):
        module = self._load_settings()
        thrown = []

        def throw(message, **kwargs):
            thrown.append(message)

        self.frappe.throw = throw
        self.frappe._ = lambda s: s
        doc = module.NexMateSettings.__new__(module.NexMateSettings)
        doc.metadata_access_mode = "ALLOWLIST"
        doc.metadata_doctype_rules = []
        doc._validate_metadata_access_mode()
        self.assertEqual(len(thrown), 1)
        self.assertIn("ALLOWLIST", thrown[0])

    def test_supported_modes_are_accepted(self):
        module = self._load_settings()
        self.frappe.throw = lambda message, **kwargs: self.fail(message)
        self.frappe._ = lambda s: s
        for mode in module.SUPPORTED_METADATA_ACCESS_MODES + ("", None):
            doc = module.NexMateSettings.__new__(module.NexMateSettings)
            doc.metadata_access_mode = mode
            doc._validate_metadata_access_mode()

    def test_duplicate_rule_is_refused(self):
        module = self._load_settings()
        thrown = []
        self.frappe.throw = lambda message, **kwargs: thrown.append(message)
        self.frappe._ = lambda s: s
        doc = module.NexMateSettings.__new__(module.NexMateSettings)
        doc.metadata_access_mode = "allowlist"
        doc.metadata_doctype_rules = [_Row("Customer"), _Row("Item"), _Row("Customer")]
        doc._validate_no_duplicate_rules()
        self.assertEqual(len(thrown), 1)
        self.assertIn("Customer", thrown[0])

    def _numeric_doc(self, module, **values):
        """A `NexMate Settings` probe carrying Frappe's `Document.set()`.

        The controller fills an unset numeric limit with its documented
        default, so the probe must provide the base-class method that a real
        `Document` supplies.
        """
        doc = module.NexMateSettings.__new__(module.NexMateSettings)
        doc.set = lambda name, value: setattr(doc, name, value)
        doc.metadata_access_mode = "all"
        doc.metadata_doctype_rules = []
        for name, value in values.items():
            setattr(doc, name, value)
        return doc

    def test_numeric_limits_accept_supported_values(self):
        module = self._load_settings()
        self.frappe.throw = lambda message, **kwargs: self.fail(message)
        self.frappe._ = lambda s: s
        fields = ("max_schema_fields", "max_schema_bytes",
                  "max_read_rows", "max_read_fields",
                  "max_read_bytes", "max_read_rounds")
        for values in (
            {},
            {"max_schema_fields": None, "max_read_rounds": ""},
            {"max_schema_fields": 1, "max_schema_bytes": 4096,
             "max_read_rows": 1, "max_read_fields": 1,
             "max_read_bytes": 4096, "max_read_rounds": 1},
            {"max_schema_fields": 500, "max_schema_bytes": 131072,
             "max_read_rows": 100, "max_read_fields": 50,
             "max_read_bytes": 131072, "max_read_rounds": 5},
            {"max_schema_fields": "300"},
        ):
            with self.subTest(values=values):
                doc = self._numeric_doc(module)
                for key, value in values.items():
                    setattr(doc, key, value)
                # Reset the fields not under test to unconfigured.
                for key in fields:
                    if key not in values:
                        setattr(doc, key, None)
                doc._validate_numeric_limits()

    def test_numeric_limits_reject_out_of_range_values(self):
        module = self._load_settings()
        cases = {
            "max_schema_fields": (0, 501),
            "max_schema_bytes": (4095, 131073),
            "max_read_rows": (0, 101),
            "max_read_fields": (0, 51),
            "max_read_bytes": (4095, 131073),
            "max_read_rounds": (0, 6),
        }
        for field, (low, high) in cases.items():
            for bad in (low, high):
                with self.subTest(field=field, bad=bad):
                    thrown = []
                    self.frappe.throw = lambda message, **kwargs: thrown.append(message)
                    self.frappe._ = lambda s: s
                    doc = self._numeric_doc(module)
                    setattr(doc, field, bad)
                    doc._validate_numeric_limits()
                    self.assertEqual(len(thrown), 1)
                    self.assertIn(field, thrown[0])

    def test_numeric_limits_reject_non_integers(self):
        module = self._load_settings()
        for bad in (True, 3.5, "many", [20], {"v": 20}):
            with self.subTest(bad=repr(bad)):
                thrown = []
                self.frappe.throw = lambda message, **kwargs: thrown.append(message)
                self.frappe._ = lambda s: s
                doc = self._numeric_doc(module)
                doc.max_read_rows = bad
                doc._validate_numeric_limits()
                self.assertEqual(len(thrown), 1)

    # --- Defect 1: an untouched save must preserve the documented defaults --
    #
    # Frappe's Single write path materialises an unset `Int` as "0", so a save
    # that touches nothing used to persist six zeros: the runtime then read a
    # never-configured setting as configured and collapsed every bound to its
    # minimum, and the next save was refused outright.

    def test_untouched_save_writes_the_documented_defaults(self):
        module = self._load_settings()
        self.frappe.throw = lambda message, **kwargs: self.fail(message)
        self.frappe._ = lambda s: s
        doc = self._numeric_doc(module)
        for field in ("max_schema_fields", "max_schema_bytes", "max_read_rows",
                      "max_read_fields", "max_read_bytes", "max_read_rounds"):
            setattr(doc, field, None)
        doc._validate_numeric_limits()
        self.assertEqual(doc.max_schema_fields, 300)
        self.assertEqual(doc.max_schema_bytes, 65536)
        self.assertEqual(doc.max_read_rows, 20)
        self.assertEqual(doc.max_read_fields, 20)
        self.assertEqual(doc.max_read_bytes, 65536)
        self.assertEqual(doc.max_read_rounds, 3)

    def test_second_untouched_save_still_succeeds(self):
        """The state an untouched save leaves behind must be valid input."""
        module = self._load_settings()
        self.frappe.throw = lambda message, **kwargs: self.fail(message)
        self.frappe._ = lambda s: s
        doc = self._numeric_doc(module)
        for field in ("max_schema_fields", "max_schema_bytes", "max_read_rows",
                      "max_read_fields", "max_read_bytes", "max_read_rounds"):
            setattr(doc, field, None)
        doc._validate_numeric_limits()
        # Second ordinary save, exactly as Frappe would re-submit the form.
        doc2 = self._numeric_doc(module)
        for field in ("max_schema_fields", "max_schema_bytes", "max_read_rows",
                      "max_read_fields", "max_read_bytes", "max_read_rounds"):
            setattr(doc2, field, getattr(doc, field))
        doc2._validate_numeric_limits()
        self.assertEqual(doc2.max_read_rows, doc.max_read_rows)

    def test_existing_valid_settings_are_preserved_by_an_untouched_save(self):
        module = self._load_settings()
        self.frappe.throw = lambda message, **kwargs: self.fail(message)
        self.frappe._ = lambda s: s
        configured = {"max_schema_fields": 450, "max_schema_bytes": 100000,
                      "max_read_rows": 75, "max_read_fields": 45,
                      "max_read_bytes": 120000, "max_read_rounds": 4}
        doc = self._numeric_doc(module, **configured)
        doc._validate_numeric_limits()
        for field, value in configured.items():
            self.assertEqual(getattr(doc, field), value)

    def test_partial_configuration_keeps_its_value_and_defaults_the_rest(self):
        module = self._load_settings()
        self.frappe.throw = lambda message, **kwargs: self.fail(message)
        self.frappe._ = lambda s: s
        doc = self._numeric_doc(module, max_read_rows=75)
        for field in ("max_schema_fields", "max_schema_bytes", "max_read_fields",
                      "max_read_bytes", "max_read_rounds"):
            setattr(doc, field, None)
        doc._validate_numeric_limits()
        self.assertEqual(doc.max_read_rows, 75)
        self.assertEqual(doc.max_read_fields, 20)
        self.assertEqual(doc.max_schema_fields, 300)

    def test_every_field_treats_untouched_the_same_way(self):
        module = self._load_settings()
        self.frappe.throw = lambda message, **kwargs: self.fail(message)
        self.frappe._ = lambda s: s
        defaults = {"max_schema_fields": 300, "max_schema_bytes": 65536,
                    "max_read_rows": 20, "max_read_fields": 20,
                    "max_read_bytes": 65536, "max_read_rounds": 3}
        for field, default in defaults.items():
            with self.subTest(field=field):
                doc = self._numeric_doc(module)
                for other in defaults:
                    setattr(doc, other, None)
                doc._validate_numeric_limits()
                self.assertEqual(getattr(doc, field), default)

    def test_parent_save_refuses_child_table_and_single(self):
        """Frappe does not run a child row's validate() on parent save, so the
        parent enforces the structural exclusions itself."""
        module = self._load_settings()

        class Meta:
            def __init__(self, istable=False, issingle=False):
                self.istable = istable
                self.issingle = issingle

        def get_meta(name):
            if name == "Sales Invoice Item":
                return Meta(istable=True)
            if name == "System Settings":
                return Meta(issingle=True)
            return Meta()

        self.frappe.get_meta = get_meta
        self.frappe._ = lambda s: s
        for bad in ("Sales Invoice Item", "System Settings"):
            with self.subTest(bad=bad):
                thrown = []
                self.frappe.throw = lambda message, **kwargs: thrown.append(message)
                doc = module.NexMateSettings.__new__(module.NexMateSettings)
                doc.metadata_access_mode = "allowlist"
                doc.metadata_doctype_rules = [_Row("Customer"), _Row(bad)]
                doc._validate_rules_are_inspectable()
                self.assertEqual(len(thrown), 1)
                self.assertIn(bad, thrown[0])

    def test_parent_save_accepts_eligible_doctypes(self):
        module = self._load_settings()

        class Meta:
            istable = False
            issingle = False

        self.frappe.get_meta = lambda name: Meta()
        self.frappe.throw = lambda message, **kwargs: self.fail(message)
        self.frappe._ = lambda s: s
        doc = module.NexMateSettings.__new__(module.NexMateSettings)
        doc.metadata_access_mode = "allowlist"
        doc.metadata_doctype_rules = [_Row("Customer"), _Row("Item")]
        doc._validate_rules_are_inspectable()


if __name__ == "__main__":
    unittest.main()
