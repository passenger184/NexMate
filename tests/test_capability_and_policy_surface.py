"""Capability derivation, registry split, and the browser-mode refusal.

Covers capability derivation's fail-closed behaviour, no implicit elevation,
one live role read per request, the static split of the descriptive capability
registry, and the fact that the browser cannot select its own capability.
"""

import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import importlib.util
import inspect
import sys
import types
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frappe_app" / "erpnext_ai_copilot"
KEY = "9f81ba760235e4cd7b60a19dca57e8234802bf6159ce743a182b9fdce03657a4"
SITE = "synthetic-site"
USER = "synthetic-user"

import capabilities


class GatewayCapabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frappe = types.ModuleType("frappe")
        self.frappe.conf = {"copilot_api_base": "http://inference.invalid:8000",
                            "nexmate_service_key": KEY}
        self.frappe.session = types.SimpleNamespace(user=USER)
        self.frappe.local = types.SimpleNamespace(site=SITE)
        self.frappe.get_roles = mock.Mock(return_value=["System Manager", "Engineer"])
        self.frappe.PermissionError = type("PermissionError", (Exception,), {})
        self.frappe.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
        self.frappe.whitelist = mock.Mock(return_value=lambda fn: fn)
        self.frappe.form_dict = {}
        self.frappe.new_doc = mock.Mock()
        self.frappe.db = mock.Mock()
        # Model genuine Settings absence by default (see test_frappe_gateway:
        # a truthy db.sql would model "proven saved" and fail closed).
        self.frappe.db.sql = mock.Mock(return_value=[])
        self.frappe.get_doc = mock.Mock(side_effect=Exception("no doc"))
        self.frappe.delete_doc = mock.Mock()

        def throw(message, exc=Exception):
            raise exc(message)

        self.frappe.throw = mock.Mock(side_effect=throw)

        model = types.ModuleType("frappe.model")
        document = types.ModuleType("frappe.model.document")
        document.Document = object
        model.document = document

        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            with mock.patch.dict(sys.modules, {
                "frappe": self.frappe, "frappe.model": model,
                "frappe.model.document": document}):
                spec.loader.exec_module(module)
            return module

        self.conversations = load("nm_cap.conversations", APP / "conversations.py")
        self.erpnext_read = load("nm_cap.erpnext_read", APP / "erpnext_read.py")
        self.doctype_meta = load("nm_cap.doctype_meta", APP / "doctype_meta.py")
        self.policy_limits = load("nm_cap.policy_limits", APP / "policy_limits.py")
        self.audit = load("nm_cap.audit", APP / "audit.py")
        self.audit.record_audit = mock.Mock(return_value={"name": "NMAU-1"})
        self.audit._require_durable_store = mock.Mock(return_value=None)
        self.audit._should_use_frappe = mock.Mock(return_value=False)

        package = types.ModuleType("erpnext_ai_copilot")
        package.__path__ = []
        package.conversations = self.conversations
        package.erpnext_read = self.erpnext_read
        package.audit = self.audit
        package.doctype_meta = self.doctype_meta
        package.policy_limits = self.policy_limits
        api_stub = types.ModuleType("erpnext_ai_copilot.api")
        api_stub.capability_for_user = mock.Mock(return_value="developer")
        package.api = api_stub

        with mock.patch.dict(sys.modules, {
            "frappe": self.frappe, "frappe.model": model,
            "frappe.model.document": document,
            "erpnext_ai_copilot": package,
            "erpnext_ai_copilot.api": api_stub,
            "erpnext_ai_copilot.conversations": self.conversations,
            "erpnext_ai_copilot.erpnext_read": self.erpnext_read,
            "erpnext_ai_copilot.audit": self.audit,
            "erpnext_ai_copilot.doctype_meta": self.doctype_meta,
            "erpnext_ai_copilot.policy_limits": self.policy_limits}):
            self.api = load("erpnext_ai_copilot.api", APP / "api.py")

        self.warnings = self.enterContext(
            mock.patch.object(self.api.logger, "warning"))
        client = mock.MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False

        # The gateway asserts the upstream response echoes the envelope mode,
        # so the reply is built from the request it answers.
        def post(url, json=None, **kwargs):
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.__exit__.return_value = False
            response.status_code = 200
            body = ("{\"answer\":\"ok\",\"sources\":[],\"confidence\":\"high\","
                    "\"route\":\"rag\",\"mode\":\"%s\",\"conversation_id\":null,"
                    "\"version_info\":{\"status\":\"unavailable\"}}"
                    % (json or {}).get("mode", "employee"))
            response.iter_content.side_effect = lambda **k: iter(
                [body.encode("utf-8")])
            return response

        client.post.side_effect = post
        session = mock.Mock(return_value=client)
        self.enterContext(mock.patch.object(self.api.requests, "Session", session))
        self.client = client

    def _send(self, question="help"):
        return self.client.post.call_args.kwargs["json"]

    # --- derivation -------------------------------------------------------

    def test_configured_role_confers_developer(self):
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "developer")

    def test_unconfigured_user_is_employee(self):
        self.frappe.conf["nexmate_developer_roles"] = ["Some Other Role"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")

    def test_no_implicit_elevation_for_administrator_or_system_manager(self):
        for user in ("Administrator", "system-manager@example.invalid"):
            self.frappe.session.user = user
            self.frappe.conf["nexmate_developer_roles"] = []
            self.api.ask("help")
            self.assertEqual(self._send()["mode"], "employee", user)

    def test_malformed_configuration_fails_closed(self):
        for mapping in (None, "Engineer", {"Engineer": True}, ("Engineer",), 42,
                        ["Engineer", None], ["Engineer", ""], [" Engineer"],
                        ["Engineer", []], ["Engineer", "bad\nrole"]):
            with self.subTest(mapping=mapping):
                self.warnings.reset_mock()
                self.frappe.conf["nexmate_developer_roles"] = mapping
                self.api.ask("help")
                self.assertEqual(self._send()["mode"], "employee")
                self.warnings.assert_called_once_with(
                    "invalid_developer_roles_config")
                self.frappe.get_roles.assert_not_called()

    def test_role_lookup_failure_fails_closed(self):
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        self.frappe.get_roles = mock.Mock(side_effect=RuntimeError("db down"))
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")
        # The scope carries no roles either, so it cannot widen retrieval.
        self.assertEqual(self._send()["scope"]["tiers"], ["public"])

    def test_capability_is_re_derived_per_request(self):
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        self.frappe.get_roles.return_value = ["Engineer"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "developer")
        self.frappe.get_roles.return_value = ["Desk User"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")

    def test_exactly_one_role_read_per_request(self):
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        self.api.ask("help")
        self.assertEqual(self.frappe.get_roles.call_args_list,
                         [mock.call(USER)])
        self.frappe.get_roles.reset_mock()
        self.api.ask("help")
        self.assertEqual(len(self.frappe.get_roles.call_args_list), 1)

    def test_no_capability_cache(self):
        """A second module load re-reads configuration; no stored grant."""
        source = (APP / "api.py").read_text(encoding="utf-8")
        self.assertNotIn("frappe.cache", source)
        self.assertNotIn("local.capability", source)

    # --- developer-role precedence (Settings vs site_config) ---------------

    def _set_settings_roles(self, rows, saved=True):
        """Drive role resolution through the store.

        ``rows=None`` means the settings record is unreadable despite proven
        persistence (db.sql reports saved); that is a failure and fails
        closed. ``saved=False`` means the record was never saved: genuine
        absence, which falls back to site_config.
        """
        if rows is None:
            self.frappe.get_doc = mock.Mock(side_effect=Exception("no doc"))
        else:
            doc = mock.Mock()
            doc.get = mock.Mock(side_effect=lambda key, default=None: [
                types.SimpleNamespace(target_role=name) for name in rows
            ] if key == "developer_role_rules" else default)
            self.frappe.get_doc = mock.Mock(return_value=doc)
        self.frappe.db.sql = mock.Mock(return_value=[(1,)] if saved else [])

    def test_settings_roles_take_precedence_over_site_config(self):
        self._set_settings_roles(["Engineer"])
        self.frappe.conf["nexmate_developer_roles"] = ["Other"]
        self.frappe.get_roles.return_value = ["Engineer", "Desk User"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "developer")
        # And in the other direction: a non-matching Settings list wins too.
        self._set_settings_roles(["Other"])
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")

    def test_absent_settings_fall_back_to_site_config(self):
        # Genuine absence is proven by the store, not by a read failure: the
        # record was never saved, so site_config governs — whether or not a
        # later read would succeed.
        empty_doc = mock.Mock()
        empty_doc.get = mock.Mock(return_value=[])
        for get_doc in (
                mock.Mock(side_effect=Exception("no doc")),
                mock.Mock(return_value=empty_doc)):
            with self.subTest(get_doc=get_doc):
                self.frappe.get_doc = get_doc
                self.frappe.db.sql = mock.Mock(return_value=[])
                self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
                self.frappe.get_roles.return_value = ["Engineer"]
                self.api.ask("help")
                self.assertEqual(self._send()["mode"], "developer")

    def test_unreadable_settings_fail_closed_without_fallback(self):
        # The store proves the record was saved, but the record itself cannot
        # be read. This is a failure, not absence: site_config must NOT
        # substitute, even though it would grant.
        self._set_settings_roles(None)
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        self.frappe.get_roles.return_value = ["Engineer"]
        self.warnings.reset_mock()
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")
        self.warnings.assert_called_once_with("developer_role_source_unavailable")
        self.frappe.get_roles.assert_not_called()

    def test_never_saved_settings_fall_back_to_site_config(self):
        self._set_settings_roles([], saved=False)
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        self.frappe.get_roles.return_value = ["Engineer"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "developer")

    def test_explicitly_empty_settings_roles_grant_nothing(self):
        self._set_settings_roles([])
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        self.frappe.get_roles.return_value = ["Engineer", "System Manager"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")
        self.frappe.get_roles.assert_not_called()

    def test_malformed_settings_roles_fail_closed(self):
        doc = mock.Mock()
        doc.get = mock.Mock(return_value=[types.SimpleNamespace(target_role=42)])
        self.frappe.get_doc = mock.Mock(return_value=doc)
        self.frappe.db.sql = mock.Mock(return_value=[(1,)])
        self.warnings.reset_mock()
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")
        self.warnings.assert_called_once_with("invalid_developer_roles_config")

    def test_deleted_roles_never_grant_capability(self):
        # A configured name matches exactly or not at all: case differs, and
        # a role that no longer exists can never appear in a live lookup.
        self._set_settings_roles(["engineer"])
        self.frappe.get_roles.return_value = ["Engineer"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")
        # A role deleted from Frappe disappears from live lookups, so a stale
        # configured entry grants nothing to anyone holding only live roles.
        self._set_settings_roles(["GhostRole"])
        self.frappe.get_roles.return_value = ["Desk User", "All"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")

    def test_settings_roles_resolve_live_every_request(self):
        self._set_settings_roles(["Engineer"])
        self.frappe.conf["nexmate_developer_roles"] = ["Other"]
        self.frappe.get_roles.return_value = ["Engineer"]
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "developer")
        self._set_settings_roles(["Other"])
        self.api.ask("help")
        self.assertEqual(self._send()["mode"], "employee")
        # The settings record is re-read per ask: no stale grant survives.
        self.assertGreaterEqual(self.frappe.get_doc.call_count, 2)

    # --- wire field -------------------------------------------------------

    def test_mode_remains_the_only_capability_field(self):
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        envelope = self._send_after()
        self.assertIn("mode", envelope)
        self.assertNotIn("capability", envelope)
        for key in envelope:
            self.assertNotIn("capability", key.lower())

    def _send_after(self):
        self.api.ask("help")
        return self._send()

    def test_no_metadata_policy_is_placed_in_the_envelope(self):
        envelope = self._send_after()
        blob = repr(envelope)
        for leak in ("metadata_access_mode", "metadata_doctype_rules",
                     "NexMate Settings", "allowlist", "doctype_schema"):
            self.assertNotIn(leak, blob, leak)

    def test_execution_scope_is_the_generic_authenticated_value(self):
        envelope = self._send_after()
        self.assertEqual(envelope["execution_scope"], "frappe-attributed")

    def test_browser_mode_is_refused(self):
        for mode in ("developer", "employee", None, {}, KEY, ["developer"]):
            with self.subTest(mode=mode):
                self.frappe.form_dict = {
                    "cmd": "erpnext_ai_copilot.api.ask", "question": "help",
                    "mode": mode}
                with self.assertRaises(Exception):
                    self.api.ask(question="help", conversation_id=None)
        self.client.post.assert_not_called()

    def test_mode_is_not_an_allowed_form_field(self):
        self.assertNotIn("mode", self.api.ALLOWED_FORM_FIELDS)
        self.assertEqual(list(inspect.signature(self.api.ask).parameters),
                         ["question", "conversation_id"])


class CapabilityRegistryTest(unittest.TestCase):
    """The registry is descriptive: it advertises, it never authorizes."""

    def test_live_data_records_and_schema_are_separate_entries(self):
        ids = [c["id"] for c in capabilities.CAPABILITIES]
        self.assertIn("live_data_records", ids)
        self.assertIn("doctype_schema", ids)
        self.assertNotIn("live_data", ids)

    def test_schema_capability_is_developer_only(self):
        entry = next(c for c in capabilities.CAPABILITIES
                     if c["id"] == "doctype_schema")
        self.assertEqual(entry["modes"], ["developer"])

    def test_record_lookup_is_available_to_both_capabilities(self):
        entry = next(c for c in capabilities.CAPABILITIES
                     if c["id"] == "live_data_records")
        self.assertEqual(sorted(entry["modes"]), ["developer", "employee"])

    def test_employee_reply_does_not_advertise_schema(self):
        ids = {c["id"] for c in capabilities.for_mode("employee")}
        self.assertNotIn("doctype_schema", ids)
        self.assertIn("live_data_records", ids)

    def test_developer_reply_advertises_both(self):
        ids = {c["id"] for c in capabilities.for_mode("developer")}
        self.assertIn("doctype_schema", ids)
        self.assertIn("live_data_records", ids)

    def test_employee_rendered_answer_omits_schema(self):
        answer = capabilities.render_capability_answer("employee")
        self.assertNotIn("DocType schema", answer)
        self.assertIn("Authorized ERPNext records", answer)

    def test_developer_rendered_answer_includes_schema(self):
        self.assertIn("DocType schema",
                      capabilities.render_capability_answer("developer"))

    def test_schema_description_states_it_is_structural_only(self):
        entry = next(c for c in capabilities.CAPABILITIES
                     if c["id"] == "doctype_schema")
        text = entry["description"].lower()
        self.assertIn("never", text)
        self.assertIn("field values", text)
        self.assertIn("options", text)
        # It must not promise to disclose the access-control model.
        self.assertIn("permission settings", text)
        self.assertNotIn("you can read", text)
        self.assertNotIn("you are authorized", text)

    def test_registry_is_static_data_with_no_authorization_logic(self):
        import ast
        tree = ast.parse((ROOT / "capabilities.py").read_text(encoding="utf-8"))
        forbidden = {"has_permission", "get_roles", "get_single",
                     "get_doc", "frappe", "requests"}
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
        self.assertEqual(called & forbidden, set(), called & forbidden)

    def test_capability_reply_describes_no_per_doctype_authorization(self):
        """A reply must not imply any particular DocType will be permitted."""
        for entry in capabilities.CAPABILITIES:
            text = (entry["description"] + " " + entry["label"]).lower()
            self.assertNotIn("allowed doctype", text)
            self.assertNotIn("permitted doctype", text)


class BootExposureTest(unittest.TestCase):
    def test_boot_does_not_expose_the_metadata_policy(self):
        source = (APP / "boot.py").read_text(encoding="utf-8")
        for leak in ("metadata_access_mode", "metadata_doctype_rules",
                     "NexMate Settings", "capability_for_user"):
            self.assertNotIn(leak, source, leak)
        self.assertIn("copilot_api_base", source)

    def test_hooks_expose_no_policy_to_the_browser(self):
        source = (APP / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("extend_bootinfo", source)
        self.assertIn("doc_events", source)
        self.assertNotIn("metadata_access_mode", source)


class SettingsAuditTest(unittest.TestCase):
    """Configuration changes emit a NexMate audit event via doc_events."""

    def setUp(self) -> None:
        self.frappe = types.ModuleType("frappe")
        self.frappe.session = types.SimpleNamespace(user="manager@example.invalid")
        self.frappe.local = types.SimpleNamespace(site=SITE)
        self.frappe.get_all = mock.Mock(return_value=[])
        self.frappe.session.data = {}

        model = types.ModuleType("frappe.model")
        document = types.ModuleType("frappe.model.document")
        document.Document = object
        model.document = document

        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            with mock.patch.dict(sys.modules, {
                "frappe": self.frappe, "frappe.model": model,
                "frappe.model.document": document}):
                spec.loader.exec_module(module)
            return module

        self.audit = load("nm_sa.audit", APP / "audit.py")
        self.audit.record_audit = mock.Mock(return_value={"name": "NMAU-1"})
        self.audit._require_durable_store = mock.Mock(return_value=None)
        self.audit._should_use_frappe = mock.Mock(return_value=False)

        # Register the package for the lifetime of the test, not just the
        # import: the hook resolves `from . import audit` at call time.
        package = types.ModuleType("erpnext_ai_copilot")
        package.__path__ = []
        package.audit = self.audit
        registry = mock.patch.dict(sys.modules, {
            "frappe": self.frappe, "frappe.model": model,
            "frappe.model.document": document,
            "erpnext_ai_copilot": package,
            "erpnext_ai_copilot.audit": self.audit})
        registry.start()
        self.addCleanup(registry.stop)
        self.module = load("erpnext_ai_copilot.settings_audit",
                           APP / "settings_audit.py")

    def _doc(self, mode="allowlist", names=("Customer",)):
        class Row:
            def __init__(self, name):
                self.target_doctype = name

        class Doc:
            doctype = "NexMate Settings"
            name = "NexMate Settings"

            def get(self, key, default=None):
                if key == "metadata_doctype_rules":
                    return [Row(n) for n in names]
                return default

        doc = Doc()
        doc.metadata_access_mode = mode
        return doc

    def test_policy_change_emits_one_audit_event(self):
        self.module.log_settings_change(doc=self._doc())
        self.assertEqual(self.audit.record_audit.call_count, 1)
        kwargs = self.audit.record_audit.call_args.kwargs
        self.assertEqual(kwargs["action"], "security_event")
        self.assertEqual(kwargs["actor"], "manager@example.invalid")
        self.assertEqual(kwargs["site"], SITE)
        self.assertEqual(kwargs["details"]["new_mode"], "allowlist")
        self.assertEqual(kwargs["details"]["configured_doctype_count"], 1)

    def test_audit_records_the_mode_transition_not_the_list(self):
        self.module.log_settings_change(doc=self._doc(mode="all"))
        details = self.audit.record_audit.call_args.kwargs["details"]
        self.assertIn("previous_mode", details)
        self.assertIn("new_mode", details)
        self.assertNotIn("Customer", repr(details))
        self.assertNotIn("doctype_names", details)

    def test_a_non_settings_document_is_ignored(self):
        class Other:
            doctype = "NexMate Conversation"
            name = "NM-1"

        self.module.log_settings_change(doc=Other())
        self.assertEqual(self.audit.record_audit.call_count, 0)

    def test_an_audit_failure_never_raises(self):
        self.audit.record_audit = mock.Mock(side_effect=RuntimeError("down"))
        self.module.log_settings_change(doc=self._doc())

    def test_hooks_register_the_document_event(self):
        source = (APP / "hooks.py").read_text(encoding="utf-8")
        self.assertIn('"NexMate Settings"', source)
        self.assertIn("settings_audit.log_settings_change", source)

    def test_settings_doctype_enables_version_tracking(self):
        import json
        path = (APP / "erpnext_ai_copilot" / "doctype" / "nexmate_settings"
                / "nexmate_settings.json")
        spec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(spec["issingle"], 1)
        self.assertEqual(spec["istable"], 0)
        self.assertEqual(spec["track_changes"], 1)
        roles = {p["role"] for p in spec["permissions"]}
        self.assertEqual(roles, {"System Manager"})

    def test_rule_doctype_is_a_child_link_to_doctype(self):
        import json
        path = (APP / "erpnext_ai_copilot" / "doctype"
                / "nexmate_metadata_doctype_rule"
                / "nexmate_metadata_doctype_rule.json")
        spec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(spec["istable"], 1)
        fields = spec["fields"]
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["fieldtype"], "Link")
        self.assertEqual(fields[0]["options"], "DocType")
        self.assertEqual(fields[0]["fieldname"], "target_doctype")
        # A DocType reference cannot carry field-level data.
        self.assertNotIn("default", fields[0])

    def test_audit_action_vocabulary_is_additive(self):
        import json
        path = (APP / "erpnext_ai_copilot" / "doctype" / "nexmate_audit_entry"
                / "nexmate_audit_entry.json")
        spec = json.loads(path.read_text(encoding="utf-8"))
        options = next(f for f in spec["fields"]
                       if f["fieldname"] == "action")["options"].split("\n")
        self.assertIn("doctype_schema", options)
        for prior in ("retrieval", "erpnext_read", "security_event",
                      "tool_call", "tool_denied", "proposal_created"):
            self.assertIn(prior, options)
        self.assertEqual(options[-1], "doctype_schema")

    def test_audit_outcome_vocabulary_is_unchanged(self):
        import json
        path = (APP / "erpnext_ai_copilot" / "doctype" / "nexmate_audit_entry"
                / "nexmate_audit_entry.json")
        spec = json.loads(path.read_text(encoding="utf-8"))
        outcomes = next(f for f in spec["fields"]
                        if f["fieldname"] == "outcome")["options"].split("\n")
        for value in ("success", "denied", "not_found", "permission_denied",
                      "invalid_request", "audit_pending"):
            self.assertIn(value, outcomes)
        self.assertNotIn("doctype_schema", outcomes)


if __name__ == "__main__":
    unittest.main()
