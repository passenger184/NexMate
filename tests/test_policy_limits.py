"""Administrator-configurable operational limits and immutable ceilings.

Covers the central `policy_limits` module directly: defaults, save-time
range validation, runtime ceiling enforcement (`min(admin, ceiling)`),
effective-value calculation for every numeric setting, and the locked
developer-role precedence/fallback semantics — all without touching
authorization, allowlists, or audit behavior.
"""

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

#: Sentinel for "settings unreadable" in the test driver below.
_UNSET = object()


def _load_policy_limits(frappe_module):
    spec = importlib.util.spec_from_file_location(
        "policy_limits_probe", APP / "policy_limits.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["policy_limits_probe"] = module
    with mock.patch.dict(sys.modules, {"frappe": frappe_module}):
        spec.loader.exec_module(module)
    return module


class FakeDoc:
    """Minimal Settings-record stand-in (attributes + child-table get)."""

    def __init__(self, values=None, rows=None):
        self._values = dict(values or {})
        self._rows = rows or {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name)

    def get(self, key, default=None):
        if key in self._rows:
            return self._rows[key]
        return self._values.get(key, default)


class FakeRoleRow:
    def __init__(self, target_role):
        self.target_role = target_role


class _UnreadableRowsDoc(FakeDoc):
    """A saved record whose role rows cannot be read."""

    def get(self, key, default=None):
        if key == "developer_role_rules":
            raise Exception("rows unreadable")
        return super().get(key, default)


class PolicyLimitsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frappe = types.ModuleType("frappe")
        self.frappe.conf = {}
        self.pl = _load_policy_limits(self.frappe)

    # --- table integrity -------------------------------------------------

    def test_ranges_defaults_and_ceilings_agree(self):
        for field, (minimum, admin_max) in self.pl.NUMERIC_RANGES.items():
            with self.subTest(field=field):
                self.assertIn(field, self.pl.NUMERIC_DEFAULTS)
                self.assertIn(field, self.pl.NUMERIC_CEILINGS)
                self.assertLessEqual(minimum, self.pl.NUMERIC_DEFAULTS[field])
                self.assertLessEqual(self.pl.NUMERIC_DEFAULTS[field], admin_max)
                self.assertEqual(admin_max, self.pl.NUMERIC_CEILINGS[field])

    def test_locked_table_values(self):
        self.assertEqual(
            (self.pl.DEFAULT_SCHEMA_FIELDS, self.pl.SCHEMA_FIELDS_CEILING), (300, 500))
        self.assertEqual(
            (self.pl.DEFAULT_SCHEMA_BYTES, self.pl.SCHEMA_BYTES_CEILING), (65536, 131072))
        self.assertEqual(
            (self.pl.DEFAULT_READ_ROWS, self.pl.READ_ROWS_CEILING), (20, 100))
        self.assertEqual(
            (self.pl.DEFAULT_READ_FIELDS, self.pl.READ_FIELDS_CEILING), (20, 50))
        self.assertEqual(
            (self.pl.DEFAULT_READ_BYTES, self.pl.READ_BYTES_CEILING), (65536, 131072))
        self.assertEqual(
            (self.pl.DEFAULT_READ_ROUNDS, self.pl.READ_ROUNDS_CEILING), (3, 5))

    # --- save-time validation --------------------------------------------

    def _validate(self, values):
        thrown = []
        self.pl.validate_numeric_settings(
            values.get, lambda message: thrown.append(message))
        return thrown

    def test_unset_and_blank_are_accepted(self):
        self.assertEqual(self._validate({}), [])
        self.assertEqual(self._validate({"max_schema_fields": None}), [])
        self.assertEqual(self._validate({"max_schema_fields": ""}), [])
        self.assertEqual(self._validate({"max_schema_fields": "   "}), [])

    def test_supported_values_are_accepted(self):
        self.assertEqual(self._validate({
            "max_schema_fields": 300,
            "max_schema_bytes": 65536,
            "max_read_rows": 20,
            "max_read_fields": 20,
            "max_read_bytes": 65536,
            "max_read_rounds": 3,
        }), [])
        self.assertEqual(self._validate({
            "max_schema_fields": "500",
            "max_read_rounds": "1",
        }), [])

    def test_out_of_range_values_are_rejected(self):
        for field, (minimum, maximum) in self.pl.NUMERIC_RANGES.items():
            with self.subTest(field=field):
                self.assertEqual(len(self._validate({field: minimum - 1})), 1)
                self.assertEqual(len(self._validate({field: maximum + 1})), 1)

    def test_non_integers_are_rejected(self):
        for bad in (True, False, 3.5, "many", "3.5", [], {}):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(len(self._validate({"max_read_rounds": bad})), 1)

    # --- runtime resolution -----------------------------------------------

    def test_defaults_apply_while_unconfigured(self):
        self.assertEqual(
            self.pl.effective_metadata_bounds(FakeDoc()),
            (300, 65536))
        self.assertEqual(
            self.pl.effective_read_bounds(FakeDoc()),
            (20, 20, 65536))
        self.assertEqual(self.pl.effective_rounds(FakeDoc()), 3)

    def test_supported_values_take_effect(self):
        doc = FakeDoc({"max_schema_fields": 150, "max_read_rows": 10,
                       "max_read_rounds": 5})
        self.assertEqual(
            self.pl.effective_metadata_bounds(doc), (150, 65536))
        self.assertEqual(
            self.pl.effective_read_bounds(doc), (10, 20, 65536))
        self.assertEqual(self.pl.effective_rounds(doc), 5)

    def test_above_ceiling_values_are_clamped_not_honored(self):
        doc = FakeDoc({"max_schema_fields": 9999, "max_schema_bytes": 10 ** 9,
                       "max_read_rows": 10 ** 6, "max_read_fields": 10 ** 6,
                       "max_read_bytes": 10 ** 9, "max_read_rounds": 99})
        self.assertEqual(
            self.pl.effective_metadata_bounds(doc), (500, 131072))
        self.assertEqual(
            self.pl.effective_read_bounds(doc), (100, 50, 131072))
        self.assertEqual(self.pl.effective_rounds(doc), 5)

    def test_below_minimum_values_resolve_to_the_default_not_the_minimum(self):
        """A below-minimum value must not silently tighten a setting.

        Frappe materialises an untouched ``Int`` on a Single as ``0`` on the
        write path, so ``0`` is what a never-configured setting looks like in
        the store. Resolving it to the minimum would collapse a documented
        default (300/20/3) to its most restrictive value (1/1/1) without any
        administrator action. The default already governs an unconfigured
        setting, so resolving to it is neutral; the minimum is not.
        """
        doc = FakeDoc({"max_schema_fields": 0, "max_read_rounds": -3,
                       "max_read_rows": 0, "max_read_fields": 0,
                       "max_read_bytes": 0})
        fields, size = self.pl.effective_metadata_bounds(doc)
        self.assertEqual(fields, self.pl.DEFAULT_SCHEMA_FIELDS)
        self.assertEqual(size, self.pl.DEFAULT_SCHEMA_BYTES)
        self.assertEqual(self.pl.effective_rounds(doc), self.pl.DEFAULT_READ_ROUNDS)
        self.assertEqual(
            self.pl.effective_read_bounds(doc),
            (self.pl.DEFAULT_READ_ROWS, self.pl.DEFAULT_READ_FIELDS,
             self.pl.DEFAULT_READ_BYTES))

    def test_below_minimum_strings_resolve_to_the_default(self):
        doc = FakeDoc({"max_read_rows": "0", "max_schema_fields": "  "})
        self.assertEqual(
            self.pl.effective_read_bounds(doc)[0], self.pl.DEFAULT_READ_ROWS)
        self.assertEqual(
            self.pl.effective_metadata_bounds(doc)[0],
            self.pl.DEFAULT_SCHEMA_FIELDS)

    def test_above_ceiling_still_clamps_rather_than_defaulting(self):
        """Clamping above the ceiling is a ceiling, not a corrupt value."""
        doc = FakeDoc({"max_read_rows": 10 ** 6})
        self.assertEqual(self.pl.effective_read_bounds(doc)[0], 100)

    # --- Defect 1: an untouched save must preserve the documented defaults --

    def test_unset_fields_normalise_to_their_documented_defaults(self):
        written = {}
        result = self.pl.normalise_numeric_settings(
            lambda name: None, lambda name, value: written.__setitem__(name, value))
        self.assertEqual(sorted(result), sorted(self.pl.NUMERIC_DEFAULTS))
        self.assertEqual(written, {
            "max_schema_fields": 300, "max_schema_bytes": 65536,
            "max_read_rows": 20, "max_read_fields": 20,
            "max_read_bytes": 65536, "max_read_rounds": 3})

    def test_blank_fields_normalise_but_configured_ones_are_untouched(self):
        values = {"max_schema_fields": 300, "max_schema_bytes": "",
                  "max_read_rows": None, "max_read_fields": 45,
                  "max_read_bytes": 65536, "max_read_rounds": "  "}
        state = dict(values)
        written = self.pl.normalise_numeric_settings(
            lambda name: state.get(name),
            lambda name, value: state.__setitem__(name, value))
        self.assertEqual(sorted(written),
                         ["max_read_rounds", "max_read_rows", "max_schema_bytes"])
        # An administrator-configured value is never overwritten.
        self.assertEqual(state["max_schema_fields"], 300)
        self.assertEqual(state["max_read_fields"], 45)
        self.assertEqual(state["max_read_bytes"], 65536)

    def test_normalisation_never_rewrites_an_explicit_zero(self):
        """Only unset is normalised, so an explicit 0 still reaches validation."""
        state = {name: 0 for name in self.pl.NUMERIC_DEFAULTS}
        written = self.pl.normalise_numeric_settings(
            lambda name: state.get(name),
            lambda name, value: state.__setitem__(name, value))
        self.assertEqual(written, [])

    def test_every_numeric_field_consistently_treats_unset(self):
        for fieldname in self.pl.NUMERIC_DEFAULTS:
            with self.subTest(field=fieldname):
                thrown = []
                self.pl.validate_numeric_settings(
                    lambda name: None, thrown.append)
                self.assertEqual(thrown, [])

    def test_malformed_values_fall_back_to_default(self):
        doc = FakeDoc({"max_schema_fields": "many", "max_read_rounds": True,
                       "max_read_rows": 2.5})
        self.assertEqual(
            self.pl.effective_metadata_bounds(doc), (300, 65536))
        self.assertEqual(self.pl.effective_rounds(doc), 3)
        rows, _, _ = self.pl.effective_read_bounds(doc)
        self.assertEqual(rows, 20)

    def test_unreadable_settings_resolve_to_defaults(self):
        self.assertEqual(
            self.pl.effective_metadata_bounds(None), (300, 65536))
        self.assertEqual(self.pl.effective_rounds(None), 3)

    # --- developer-role precedence -----------------------------------------

    def _roles(self, site_config=(), rows=_UNSET, saved=True, doc_error=False):
        """Drive resolve_developer_roles through the store, like production.

        ``rows=_UNSET`` means get_doc raises (unreadable settings);
        otherwise get_doc returns a record carrying those role rows, and
        ``saved`` controls whether tabSingles reports the record as saved.
        """
        self.frappe.conf = {"nexmate_developer_roles": site_config}
        if rows is _UNSET:
            self.frappe.get_doc = mock.Mock(side_effect=Exception("no settings"))
        else:
            self.frappe.get_doc = mock.Mock(
                return_value=FakeDoc(
                    {}, {"developer_role_rules": [FakeRoleRow(r) for r in rows]}))
        self.frappe.db = types.SimpleNamespace(
            sql=mock.Mock(return_value=[(1,)] if saved else []))
        if doc_error:
            self.frappe.get_doc = mock.Mock(side_effect=Exception("db down"))
            self.frappe.db = types.SimpleNamespace(
                sql=mock.Mock(side_effect=Exception("db down")))
        return self.pl.resolve_developer_roles()

    def test_settings_roles_take_precedence(self):
        roles, source = self._roles(site_config=["Other"], rows=["Engineer"])
        self.assertEqual(source, "settings")
        self.assertEqual(roles, ["Engineer"])

    def test_explicitly_empty_settings_roles_grant_nothing(self):
        roles, source = self._roles(site_config=["Engineer"], rows=[])
        self.assertEqual(source, "settings")
        self.assertEqual(roles, [])

    def test_absent_settings_fall_back_to_site_config(self):
        # Genuine absence is proven by the store: never saved means
        # site_config governs, regardless of whether a later read succeeds.
        for get_doc, label in (
                (mock.Mock(side_effect=Exception("no doc")), "raises"),
                (mock.Mock(return_value=FakeDoc({}, {})), "empty-doc")):
            with self.subTest(label=label):
                self.frappe.conf = {"nexmate_developer_roles": ["Engineer"]}
                self.frappe.get_doc = get_doc
                self.frappe.db = types.SimpleNamespace(
                    sql=mock.Mock(return_value=[]))
                roles, source = self.pl.resolve_developer_roles()
                self.assertEqual(source, "site_config")
                self.assertEqual(roles, ["Engineer"])

    def test_never_saved_settings_fall_back_to_site_config(self):
        roles, source = self._roles(site_config=["Engineer"], rows=[],
                                    saved=False)
        self.assertEqual(source, "site_config")
        self.assertEqual(roles, ["Engineer"])

    def test_unreadable_settings_fail_closed_without_fallback(self):
        # Every unreadable variant fails closed: no site_config substitution,
        # even when site_config would grant and the user holds the role.
        variants = {
            "get_doc raises": dict(
                get_doc=mock.Mock(side_effect=Exception("no doc")),
                sql=mock.Mock(return_value=[(1,)]),
            ),
            "store unreadable": dict(
                get_doc=mock.Mock(side_effect=Exception("down")),
                sql=mock.Mock(side_effect=Exception("db down")),
            ),
            "role rows unreadable": dict(
                get_doc=mock.Mock(return_value=_UnreadableRowsDoc({}, {})),
                sql=mock.Mock(return_value=[(1,)]),
            ),
        }
        for label, stubs in variants.items():
            with self.subTest(label=label):
                self.frappe.conf = {"nexmate_developer_roles": ["Engineer"]}
                self.frappe.get_doc = stubs["get_doc"]
                self.frappe.db = types.SimpleNamespace(sql=stubs["sql"])
                roles, source = self.pl.resolve_developer_roles()
                self.assertEqual(source, "unavailable")
                self.assertIsNone(roles)

    def test_non_string_entries_survive_for_downstream_fail_closed(self):
        roles, source = self._roles(rows=[42])
        self.assertEqual(source, "settings")
        # Passed through untouched: identity validation downstream refuses the
        # whole mapping rather than silently dropping the bad entry.
        self.assertEqual(roles, [42])

    def test_role_names_are_stripped(self):
        roles, _ = self._roles(rows=["  Engineer  "])
        self.assertEqual(roles, ["Engineer"])

    def test_resolve_never_raises(self):
        self.frappe.conf = None
        self.frappe.db = None
        self.frappe.get_doc = mock.Mock(side_effect=Exception("down"))
        roles, source = self.pl.resolve_developer_roles()
        # Every store access fails: unknown state fails closed, never falls
        # back, and never raises.
        self.assertIsNone(roles)
        self.assertEqual(source, "unavailable")

    # --- ceilings are not settings ------------------------------------------

    def test_no_ceiling_is_exposed_as_a_setting(self):
        for name in ("SCHEMA_FIELDS_CEILING", "SCHEMA_BYTES_CEILING",
                     "READ_ROWS_CEILING", "READ_FIELDS_CEILING",
                     "READ_BYTES_CEILING", "READ_ROUNDS_CEILING"):
            self.assertNotIn(name.lower(), self.pl.NUMERIC_RANGES)
            self.assertNotIn(name.lower(), self.pl.NUMERIC_DEFAULTS)

    def test_no_security_invariant_is_a_setting(self):
        surface = set(self.pl.NUMERIC_RANGES) | {"metadata_access_mode",
            "metadata_doctype_rules", "developer_role_rules"}
        for invariant in ("projection", "collapse", "allowlist", "denylist",
                          "audit", "envelope", "scope", "secret", "provider",
                          "timeout", "permission"):
            self.assertFalse(
                any(invariant in name for name in surface),
                invariant)


if __name__ == "__main__":
    unittest.main()
