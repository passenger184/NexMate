import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import importlib.util
import inspect
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

import requests


ROOT = Path(__file__).resolve().parents[1]
KEY = "9f81ba760235e4cd7b60a19dca57e8234802bf6159ce743a182b9fdce03657a4"


class GatewayError(Exception):
    pass


class GatewayPermissionError(GatewayError):
    pass


class GatewayNotFound(Exception):
    pass


class FakeRow:
    def __init__(self, role, content):
        self.role = role
        self.content = content


class FakeDoc:
    """Minimal Frappe-document stand-in with a real turns list."""

    def __init__(self, name="NM-00001", owner="synthetic-user",
                 site="synthetic-site", turns=()):
        self.name = name
        self.owner_user = owner
        self.site = site
        self.turns = [FakeRow(role, content) for role, content in turns]
        self.saved = 0
        self.inserted = False

    def get(self, key, default=None):
        return {"turns": self.turns}.get(key, default)

    def set(self, key, value):
        setattr(self, key, value)

    def append(self, key, value):
        getattr(self, key).append(FakeRow(value["role"], value["content"]))

    def save(self, *args, **kwargs):
        self.saved += 1

    def update(self, values):
        for key, value in values.items():
            setattr(self, key, value)

    def insert(self, *args, **kwargs):
        self.inserted = True
        return self


class FrappeGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frappe = types.ModuleType("frappe")
        self.frappe.conf = {
            "copilot_api_base": "http://inference.invalid:8000",
            "nexmate_service_key": KEY,
        }
        self.frappe.session = types.SimpleNamespace(user="synthetic-user")
        self.frappe.local = types.SimpleNamespace(site="synthetic-site")
        self.frappe.get_roles = mock.Mock(return_value=["System Manager", "Engineer"])
        self.frappe.PermissionError = GatewayPermissionError
        self.frappe.DoesNotExistError = GatewayNotFound
        self.frappe.whitelist = mock.Mock(return_value=lambda fn: fn)
        self.frappe.throw = mock.Mock(side_effect=self.throw)
        self.frappe.new_doc = mock.Mock(side_effect=lambda *a, **k: FakeDoc())
        self.frappe.get_doc = mock.Mock(side_effect=GatewayNotFound("no doc"))
        self.frappe.delete_doc = mock.Mock()
        self.frappe.db = mock.Mock()
        self.conversations = self.load_module("conversations")
        package = types.ModuleType("erpnext_ai_copilot")
        package.conversations = self.conversations
        self.modules_patch = mock.patch.dict(
            sys.modules, {"frappe": self.frappe,
                          "erpnext_ai_copilot": package,
                          "erpnext_ai_copilot.conversations": self.conversations})
        self.modules_patch.start()
        self.addCleanup(self.modules_patch.stop)
        self.api = self.load_module("api")
        self.warnings = self.enterContext(mock.patch.object(self.api.logger, "warning"))
        self.frappe.form_dict = {}
        self.client = mock.MagicMock()
        self.client.__enter__.return_value = self.client
        self.response = mock.MagicMock()
        self.response.__enter__.return_value = self.response
        self.client.post.return_value = self.response
        self.session = self.enterContext(mock.patch.object(
            self.api.requests, "Session", return_value=self.client))
        self.response.status_code = 200
        self.body = {
            "answer": "Synthetic answer [1].", "sources": [{"title": "Manual"}],
            "confidence": "high", "route": "rag", "mode": "employee",
            "conversation_id": None,
            "version_info": {"status": "unavailable", "frappe": None, "erpnext": None},
        }
        self.response.iter_content.side_effect = lambda **kwargs: iter([
            json.dumps(self.body).encode("utf-8")])

    @staticmethod
    def throw(message, exc=GatewayError):
        raise exc(message)

    def load_module(self, name):
        spec = importlib.util.spec_from_file_location(
            "gateway_test_" + name, ROOT / "frappe_app" / "erpnext_ai_copilot" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"frappe": self.frappe}):
            spec.loader.exec_module(module)
        return module

    def assert_safe_failure(self, expected, **kwargs):
        with self.assertRaises(GatewayError) as caught:
            self.api.ask("help", **kwargs)
        self.assertEqual(str(caught.exception), expected)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertNotIn("X-NexMate-Key", str(caught.exception))
        self.assertIsNone(caught.exception.__context__)

    def test_whitelist_is_non_guest_and_guest_refused(self) -> None:
        self.assertEqual(self.frappe.whitelist.call_count, 4)
        for call in self.frappe.whitelist.call_args_list:
            self.assertEqual(call, mock.call())
        self.frappe.session.user = "Guest"
        with self.assertRaises(GatewayPermissionError):
            self.api.ask("help")
        self.session.assert_not_called()

    def test_configured_key_required_without_fallback(self) -> None:
        for key in (None, "", " ", "bad", "g" * 64, "a" * 64, "abcd" * 16,
                    KEY + "\n", KEY[:-1], 123):
            with self.subTest(kind=type(key).__name__):
                self.frappe.conf["nexmate_service_key"] = key
                self.assert_safe_failure("NexMate gateway configuration error.")
        del self.frappe.conf["nexmate_service_key"]
        self.assert_safe_failure("NexMate gateway configuration error.")
        self.session.assert_not_called()

    def test_server_constructed_envelope_and_transport(self) -> None:
        self.assertEqual(self.api.ask("help"), self.body)
        self.client.post.assert_called_once_with(
            "http://inference.invalid:8000/orchestrate",
            json={"question": "help",
                  "user": "synthetic-user", "site": "synthetic-site",
                  "mode": "employee", "execution_scope": "chat-only"},
            headers={"X-NexMate-Key": KEY}, timeout=(5, 300),
            allow_redirects=False, stream=True)
        self.assertFalse(self.client.trust_env)
        self.assertNotIn(KEY, json.dumps(self.api.ask("help")))

    def test_absent_conversation_is_not_invented(self) -> None:
        self.api.ask("help")
        self.assertNotIn("conversation", self.client.post.call_args.kwargs["json"])

    def test_invalid_conversation_ids_are_refused_before_transport(self) -> None:
        for conv in ("", "../bad", "has space", "x" * 141, "valid\n", 123, [], {}):
            self.assert_safe_failure("Invalid conversation identifier.",
                                     conversation_id=conv)
        self.session.assert_not_called()

    def test_question_is_bounded_and_not_coerced(self) -> None:
        for question in (None, "", " \n", "x" * 2001, 42, {}, []):
            with self.assertRaisesRegex(GatewayError, "Invalid chat question"):
                self.api.ask(question)
        self.session.assert_not_called()
        for question in ("hi", "x" * 2000):
            self.api.ask(question)
            self.assertEqual(self.client.post.call_args.kwargs["json"]["question"], question)

    def test_default_employee_even_for_administrator(self) -> None:
        for user in ("synthetic-user", "Administrator"):
            self.frappe.session.user = user
            self.api.ask("help")
            self.assertEqual(self.client.post.call_args.kwargs["json"]["mode"], "employee")
        self.frappe.get_roles.assert_not_called()

    def test_explicit_matching_role_selects_developer_only(self) -> None:
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer"]
        self.body["mode"] = "developer"
        self.api.ask("help")
        self.frappe.get_roles.assert_called_once_with("synthetic-user")
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(payload["mode"], "developer")
        self.assertEqual(payload["execution_scope"], "chat-only")
        self.frappe.conf["nexmate_developer_roles"] = ["Other Role"]
        self.body["mode"] = "employee"
        self.api.ask("help")
        self.assertEqual(self.client.post.call_args.kwargs["json"]["mode"], "employee")

    def test_malformed_role_mapping_fails_closed(self) -> None:
        for mapping in (None, "Engineer", {"Engineer": True}, ("Engineer",), 42,
                        ["Engineer", None], ["Engineer", ""], [" Engineer"],
                        ["Engineer", []], ["Engineer", "bad\nrole"]):
            self.warnings.reset_mock()
            self.frappe.conf["nexmate_developer_roles"] = mapping
            self.api.ask("help")
            self.assertEqual(self.client.post.call_args.kwargs["json"]["mode"], "employee")
            self.warnings.assert_called_once_with("invalid_developer_roles_config")
        self.frappe.get_roles.assert_not_called()

    def dispatch_form(self):
        parameters = inspect.signature(self.api.ask).parameters
        return self.api.ask(**{k: v for k, v in self.frappe.form_dict.items() if k in parameters})

    def test_browser_fields_are_refused_despite_dispatch_filtering(self) -> None:
        self.assertEqual(list(inspect.signature(self.api.ask).parameters),
                         ["question", "conversation_id"])
        for field in ("identity", "user", "site", "execution_scope", "operation", "target", "url",
                      "session_id", "history", "turns",
                      "nexmate_inference_timeout", "unknown", KEY):
            for value in (None, "", KEY, [], {}):
                self.warnings.reset_mock()
                self.frappe.form_dict = {
                    "cmd": "erpnext_ai_copilot.api.ask", "question": "help", field: value,
                }
                with self.assertRaisesRegex(GatewayError, "^unsupported_gateway_fields$"):
                    self.dispatch_form()
                self.warnings.assert_called_once_with("unsupported_gateway_fields")
        self.session.assert_not_called()
        self.client.post.assert_not_called()
        self.frappe.get_roles.assert_not_called()

    def test_framework_cmd_and_browser_mode_are_not_forwarded(self) -> None:
        for mode in ("developer", "employee", None, {}, KEY):
            self.frappe.form_dict = {
                "cmd": "erpnext_ai_copilot.api.ask", "question": "help", "mode": mode,
            }
            self.dispatch_form()
            self.assertEqual(self.client.post.call_args.kwargs["json"], {
                "question": "help", "user": "synthetic-user",
                "site": "synthetic-site", "mode": "employee", "execution_scope": "chat-only",
            })
        self.warnings.assert_not_called()

    def test_empty_roles_mapping_is_valid_without_warning(self) -> None:
        self.frappe.conf["nexmate_developer_roles"] = []
        self.api.ask("help")
        self.warnings.assert_not_called()
        self.frappe.get_roles.assert_not_called()

    def test_roles_warning_never_logs_configuration_contents(self) -> None:
        self.frappe.conf["nexmate_developer_roles"] = ["Engineer", {"X-NexMate-Key": KEY}]
        self.api.ask("help")
        self.warnings.assert_called_once_with("invalid_developer_roles_config")
        self.assertEqual(self.client.post.call_args.kwargs["json"]["mode"], "employee")

    def test_timeout_setting_is_server_controlled_and_bounded(self) -> None:
        for value in (0.5, 1, 300, 600.5, 900):
            self.frappe.conf["nexmate_inference_timeout"] = value
            self.api.ask("help")
            self.assertEqual(self.client.post.call_args.kwargs["timeout"], (5, float(value)))
        self.warnings.assert_not_called()

    def test_invalid_timeout_setting_refuses_without_transport(self) -> None:
        for value in (None, True, False, "300", "", 0, -1, 900.1, 10 ** 1000,
                      float("nan"), float("inf"), float("-inf"), [], {}, KEY):
            self.warnings.reset_mock()
            self.frappe.conf["nexmate_inference_timeout"] = value
            self.assert_safe_failure("invalid_inference_timeout_config")
            self.warnings.assert_called_once_with("invalid_inference_timeout_config")
        self.session.assert_not_called()

    def test_current_site_is_canonical_not_public_hostname(self) -> None:
        self.frappe.conf["host_name"] = "https://public.invalid"
        self.api.ask("help")
        self.assertEqual(self.client.post.call_args.kwargs["json"]["site"], "synthetic-site")

    def test_bad_authoritative_identity_fails_without_repair(self) -> None:
        for field, obj in (("user", self.frappe.session), ("site", self.frappe.local)):
            original = getattr(obj, field)
            for invalid in (None, " ", " leading", "trailing ", "a\nb", "a\u200bb", "x" * 256):
                setattr(obj, field, invalid)
                with self.assertRaises(GatewayError):
                    self.api.ask("help")
            setattr(obj, field, original)
        self.session.assert_not_called()

    def test_invalid_destination_is_sanitized(self) -> None:
        for base in (None, "", "file:///tmp/test", "http://", "http://user:pass@host",
                     "http://host?target=other", "http://host#fragment", "http://host:bad",
                     "http://host\n", 123):
            self.frappe.conf["copilot_api_base"] = base
            self.assert_safe_failure("NexMate gateway configuration error.")
        self.session.assert_not_called()

    def test_upstream_errors_and_redirects_are_not_relayed(self) -> None:
        for status in (301, 302, 307, 308, 401, 403, 422, 500, 503):
            self.response.status_code = status
            self.response.headers = {"Location": "http://untrusted.invalid/" + KEY}
            self.assert_safe_failure("gateway_upstream_http_error")
            self.warnings.assert_called_with("gateway_upstream_http_error")
        self.response.iter_content.assert_not_called()
        self.assertEqual(self.client.post.call_count, 9)

    def test_transport_errors_do_not_leak_exception_context(self) -> None:
        cases = (
            (requests.Timeout(KEY), "gateway_upstream_timeout"),
            (requests.ConnectTimeout(KEY), "gateway_upstream_timeout"),
            (requests.ReadTimeout(KEY), "gateway_upstream_timeout"),
            (requests.ConnectionError(KEY), "gateway_upstream_transport_error"),
            (requests.exceptions.ChunkedEncodingError("X-NexMate-Key: " + KEY),
             "gateway_upstream_protocol_error"),
            (requests.exceptions.ContentDecodingError(KEY), "gateway_upstream_protocol_error"),
        )
        for error, code in cases:
            self.client.post.reset_mock()
            self.warnings.reset_mock()
            self.client.post.side_effect = error
            self.assert_safe_failure(code)
            self.warnings.assert_called_once_with(code)
            self.client.post.assert_called_once()

    def test_stream_failure_is_safe_and_does_not_retry(self) -> None:
        for error, code in (
                (requests.ReadTimeout(KEY), "gateway_upstream_timeout"),
                (requests.exceptions.ChunkedEncodingError(KEY), "gateway_upstream_protocol_error")):
            self.client.post.reset_mock()
            self.warnings.reset_mock()
            self.response.iter_content.side_effect = error
            self.assert_safe_failure(code)
            self.warnings.assert_called_once_with(code)
            self.client.post.assert_called_once()
            self.assertTrue(self.response.__exit__.called)

    def test_malformed_or_oversized_response_is_sanitized(self) -> None:
        for raw, code in (
                (b"not json", "gateway_upstream_protocol_error"),
                (b"[]", "gateway_upstream_protocol_error"),
                (b"{}", "gateway_upstream_protocol_error"),
                (b"\xff", "gateway_upstream_protocol_error"),
                (b"x" * (self.api.MAX_RESPONSE_BYTES + 1), "gateway_upstream_response_too_large")):
            self.response.iter_content.side_effect = lambda **kwargs: iter([raw])
            self.warnings.reset_mock()
            self.assert_safe_failure(code)
            self.warnings.assert_called_once_with(code)
        self.assertTrue(self.response.__exit__.called)

    def test_response_has_only_allowed_fields(self) -> None:
        self.body.update(headers={"X-NexMate-Key": KEY}, internal="not for browser")
        result = self.api.ask("help")
        self.assertEqual(set(result), set(self.api.RESPONSE_FIELDS))
        self.assertNotIn(KEY, json.dumps(result))
        self.assertEqual(result["version_info"]["status"], "unavailable")

    def test_reflected_transport_secret_is_never_returned(self) -> None:
        for answer in (KEY, KEY.upper(), "X-NexMate-Key: hidden"):
            self.body["answer"] = answer
            self.warnings.reset_mock()
            self.assert_safe_failure("gateway_upstream_protocol_error")
            self.warnings.assert_called_once_with("gateway_upstream_protocol_error")

    def test_owned_ask_flow_appends_both_turns(self) -> None:
        doc = FakeDoc(turns=[])
        self.frappe.get_doc = mock.Mock(return_value=doc)
        self.body["conversation_id"] = "NM-00001"
        result = self.api.ask("help", "NM-00001")
        self.assertEqual(result["conversation_id"], "NM-00001")
        sent = self.client.post.call_args.kwargs["json"]
        self.assertEqual(sent["conversation"], {
            "id": "NM-00001", "owner": "synthetic-user",
            "site": "synthetic-site", "turns": []})
        self.assertEqual([(row.role, row.content) for row in doc.turns],
                         [("user", "help"), ("assistant", "Synthetic answer [1].")])
        self.assertEqual(doc.saved, 2)
        # The user turn commits before the upstream call so a later
        # inference failure cannot silently discard it (Frappe rolls back
        # the request on error).
        self.frappe.db.commit.assert_called()
        lock_calls = [call for call in self.frappe.db.sql.call_args_list
                      if "FOR UPDATE" in str(call)]
        self.assertTrue(lock_calls)

    def test_ask_on_foreign_thread_refused(self) -> None:
        self.frappe.get_doc = mock.Mock(return_value=FakeDoc(owner="other-user"))
        self.assert_safe_failure(
            "Conversation is not owned by this user on this site.",
            conversation_id="NM-00001")
        self.session.assert_not_called()

    def test_ask_on_missing_thread_refused(self) -> None:
        self.frappe.get_doc = mock.Mock(side_effect=GatewayNotFound("gone"))
        self.assert_safe_failure("Unknown conversation.", conversation_id="NM-00001")
        self.session.assert_not_called()

    def test_privileged_role_cannot_use_others_thread(self) -> None:
        self.frappe.session.user = "Administrator"
        self.frappe.conf["nexmate_developer_roles"] = ["System Manager"]
        self.body["mode"] = "developer"
        self.frappe.get_doc = mock.Mock(return_value=FakeDoc(owner="synthetic-user"))
        self.assert_safe_failure(
            "Conversation is not owned by this user on this site.",
            conversation_id="NM-00001")
        self.session.assert_not_called()

    def test_conversation_id_echo_mismatch_is_protocol_error(self) -> None:
        self.frappe.get_doc = mock.Mock(return_value=FakeDoc())
        self.body["conversation_id"] = "NM-99999"
        self.assert_safe_failure("gateway_upstream_protocol_error",
                                 conversation_id="NM-00001")
        self.body["conversation_id"] = "NM-00001"
        result = self.api.ask("help", "NM-00001")
        self.assertEqual(result["conversation_id"], "NM-00001")

    def test_lock_conflict_fails_loud_without_losing_turns(self) -> None:
        doc = FakeDoc(turns=[("user", "prior")])
        self.frappe.get_doc = mock.Mock(return_value=doc)
        self.frappe.db.sql = mock.Mock(side_effect=Exception("Lock wait timeout"))
        self.assert_safe_failure("Conversation is busy; please retry.",
                                 conversation_id="NM-00001")
        self.assertEqual(doc.saved, 0)
        self.assertEqual([(row.role, row.content) for row in doc.turns],
                         [("user", "prior")])
        self.session.assert_not_called()

    def test_start_get_reset_lifecycle(self) -> None:
        created = self.api.start_conversation()
        self.assertEqual(created, {"conversation_id": "NM-00001"})
        doc = FakeDoc(turns=[("user", "q"), ("assistant", "a")])
        self.frappe.get_doc = mock.Mock(return_value=doc)
        fetched = self.api.get_conversation("NM-00001")
        self.assertEqual(fetched, {
            "conversation_id": "NM-00001",
            "turns": [{"role": "user", "content": "q"},
                      {"role": "assistant", "content": "a"}]})
        self.assertEqual(self.api.reset_conversation("NM-00001"), {"reset": True})
        self.frappe.delete_doc.assert_called_once_with(
            "NexMate Conversation", "NM-00001", ignore_permissions=True)

    def test_lifecycle_guest_and_malformed_refused(self) -> None:
        self.frappe.session.user = "Guest"
        for call in (lambda: self.api.start_conversation(),
                     lambda: self.api.get_conversation("NM-00001"),
                     lambda: self.api.reset_conversation("NM-00001")):
            with self.assertRaises(GatewayPermissionError):
                call()
        self.session.assert_not_called()
        self.frappe.session.user = "synthetic-user"
        for call in (lambda: self.api.get_conversation("../x"),
                     lambda: self.api.reset_conversation(""),
                     lambda: self.api.get_conversation(None)):
            with self.assertRaisesRegex(GatewayError, "^Invalid conversation identifier.$"):
                call()
        self.session.assert_not_called()

    def test_lifecycle_cross_user_and_cross_site_refused(self) -> None:
        self.frappe.get_doc = mock.Mock(return_value=FakeDoc(owner="other"))
        with self.assertRaisesRegex(GatewayError, "not owned"):
            self.api.get_conversation("NM-00001")
        with self.assertRaisesRegex(GatewayError, "not owned"):
            self.api.reset_conversation("NM-00001")
        self.frappe.delete_doc.assert_not_called()
        self.frappe.get_doc = mock.Mock(
            return_value=FakeDoc(site="other-site"))
        with self.assertRaisesRegex(GatewayError, "not owned"):
            self.api.get_conversation("NM-00001")
        self.session.assert_not_called()

    def test_budget_helper_bounds_most_recent_wins(self) -> None:
        bounded = self.conversations.bounded_tail
        self.assertEqual(bounded("nope"), [])
        turns = [{"role": "user", "content": f"q{i}"} for i in range(20)]
        tail = bounded(turns)
        self.assertLessEqual(len(tail), self.conversations.FORWARD_MAX_TURNS)
        self.assertEqual(tail[-1]["content"], "q19")
        huge = [{"role": "user", "content": "x" * 100000}]
        self.assertEqual(bounded(huge), huge)  # newest never dropped
        over = [{"role": "user", "content": "y" * 5000},
                {"role": "assistant", "content": "z" * 5000}]
        tail = bounded(over, max_chars=6000)
        self.assertEqual([t["content"] for t in tail], ["z" * 5000])

    def test_boot_contains_only_address_not_secret(self) -> None:
        bootinfo = types.SimpleNamespace()
        self.load_module("boot").boot_session(bootinfo)
        self.assertEqual(bootinfo.copilot_settings, {
            "api_base": "http://inference.invalid:8000"})
        self.assertNotIn(KEY, json.dumps(vars(bootinfo)))

    def test_bundle_gateway_and_preview_guards(self) -> None:
        bundle = (ROOT / "frappe_app/public/js/copilot.bundle.js").read_text()
        self.assertIn('window.location.pathname === "/ui/preview.html"', bundle)
        self.assertIn('fetch("/api/method/erpnext_ai_copilot.api.ask"', bundle)
        self.assertIn('credentials: "same-origin"', bundle)
        self.assertIn('headers["X-Frappe-CSRF-Token"] = frappe.csrf_token', bundle)
        post = bundle.split("  function post(path, body) {", 1)[1].split("  function chatRequest", 1)[0]
        self.assertLess(post.index("if (!isPreview)"), post.index("fetch(apiBase() + path"))
        chat = bundle.split("  function chatRequest(question) {", 1)[1].split("  function askOrchestrate", 1)[0]
        self.assertIn('if (isPreview) {\n      return post("/orchestrate"', chat)
        self.assertNotIn("session_id", chat)
        desk = chat.split('var headers =', 1)[1]
        self.assertNotIn("apiBase", desk)
        self.assertNotIn("mode:", desk)
        self.assertNotIn("post(", desk)
        self.assertIn("conversation_id", desk)
        self.assertEqual(bundle.count('post("/orchestrate"'), 1)
        self.assertIn('if (!isPreview) return fillAssistant(m, deskUnavailable);', bundle)
        self.assertIn('function approveBar(card, applySpec, onApplied) {\n    if (!isPreview)', bundle)
        self.assertIn('if (!isPreview) { freshDeskConversation(); return; }', bundle)
        self.assertIn('frappeCall("reset_conversation"', bundle)
        self.assertIn('frappeCall("start_conversation"', bundle)
        self.assertIn('frappeCall("get_conversation"', bundle)
        self.assertNotIn("/tools/session/reset", bundle)
        self.assertNotIn("copilot.session", bundle)
        self.assertIn('localStorage.removeItem("copilot.conversation")', bundle)
        self.assertIn('S.els.mode.disabled = true;', bundle)
        self.assertNotIn("nexmate_service_key", bundle)
        self.assertNotIn("X-NexMate-Key", bundle)
        self.assertNotIn(KEY, bundle)


if __name__ == "__main__":
    unittest.main()
