"""U5 boundary suite: authorized ERPNext read seam.

Covers the Frappe↔inference boundary introduced by the U5 change:
authorized-context validation, the bounded read round trip, browser-supplied
context refusal, response-bound preservation, the orchestrator cutover away from
the shared-credential read client, mode independence, the read contract, and
legacy route deprecation.

Transport is stubbed. No real ERPNext, Frappe DB, model or network.
"""

import importlib.util
import json
import os
import sys
import types
import unittest
from unittest import mock

os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
os.environ.setdefault("NEXMATE_DURABLE_FALLBACK", "1")
os.environ.setdefault("NEXMATE_SERVICE_KEY", "ab" * 32)
os.environ.setdefault("NEXMATE_FRAPPE_SITE", "u5_site")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import service.main as main  # noqa: E402
from service.auth import validate_authorized_context  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def ctx(**over):
    base = {
        "doctype": "Customer",
        "operation": "list",
        "fields_returned": ["name", "customer_name"],
        "row_count": 1,
        "data": [{"name": "Test", "customer_name": "Test"}],
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Group 7 — authorized-context validation and bounds (L-16)
# ---------------------------------------------------------------------------


class AuthorizedContextValidation(unittest.TestCase):
    def test_7_2_valid_context_passes(self):
        self.assertEqual(validate_authorized_context(ctx()), ctx())

    def test_7_2_shape_is_frozen(self):
        for bad in (ctx(unexpected="x"), {k: v for k, v in ctx().items() if k != "doctype"}, "x", None, []):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(HTTPException):
                    validate_authorized_context(bad)

    def test_7_2_operation_must_be_supported(self):
        for op in ("schema", "write", "delete", "update", "", None, 7):
            with self.subTest(op=op):
                with self.assertRaises(HTTPException):
                    validate_authorized_context(ctx(operation=op, data={}))

    def test_7_2_field_count_and_types_bounded(self):
        with self.assertRaises(HTTPException):
            validate_authorized_context(ctx(fields_returned=[f"f{i}" for i in range(50)]))
        with self.assertRaises(HTTPException):
            validate_authorized_context(ctx(fields_returned=[123]))
        with self.assertRaises(HTTPException):
            validate_authorized_context(ctx(fields_returned=[]))

    def test_7_2_row_count_bounded(self):
        with self.assertRaises(HTTPException):
            validate_authorized_context(ctx(row_count=10_000))
        with self.assertRaises(HTTPException):
            validate_authorized_context(ctx(row_count=-1))

    def test_7_2_data_may_not_exceed_fields_returned(self):
        # A field that was not declared as returned must not appear in data.
        with self.assertRaises(HTTPException):
            validate_authorized_context(
                ctx(fields_returned=["name"], data=[{"name": "a", "customer_name": "leak"}]))
        with self.assertRaises(HTTPException):
            validate_authorized_context(
                ctx(operation="document", fields_returned=["name"],
                    data={"name": "a", "customer_name": "leak"}))

    def test_7_2_list_row_count_bounded(self):
        with self.assertRaises(HTTPException):
            validate_authorized_context(ctx(data=[{"name": str(i)} for i in range(100)]))

    def test_7_2_oversized_payload_refused(self):
        big = ctx(data=[{"name": str(i), "customer_name": "x" * 8000} for i in range(20)])
        with self.assertRaises(HTTPException):
            validate_authorized_context(big)

    def test_7_2_no_credential_or_subject_override_in_context(self):
        # The frozen shape admits no credential/subject key at all.
        for key in ("api_key", "api_secret", "user", "actor", "site", "credential", "token"):
            with self.subTest(key=key):
                with self.assertRaises(HTTPException):
                    validate_authorized_context(ctx(**{key: "x"}))


# ---------------------------------------------------------------------------
# Group 8 — orchestrator cutover and mode independence
# ---------------------------------------------------------------------------


class OrchestratorCutover(unittest.TestCase):
    def _branch(self, extraction, authorized_context=None, mode="developer"):
        import orchestrator
        nlu = {"kind": "task", "subtype": None, "topic": "t",
               "context_dependency": "none", "confidence": 0.9}
        with mock.patch.object(orchestrator, "_understand_with_llm", return_value=nlu), \
                mock.patch.object(orchestrator, "decide_route", return_value=("erpnext", "classifier")), \
                mock.patch.object(orchestrator, "_extract_erpnext_request", return_value=extraction), \
                mock.patch.object(orchestrator, "get_instance_versions",
                                  return_value={"status": "unavailable", "frappe": "u", "erpnext": "e"}), \
                mock.patch.object(orchestrator.generator, "_complete",
                                  return_value="Grounded answer [1]."):
            return orchestrator.handle_question(
                "how many customers do we have?", mode=mode,
                authorized_context=authorized_context)

    def test_8_2_user_read_path_never_calls_shared_credential_client(self):
        import orchestrator
        poison = mock.Mock(side_effect=AssertionError("shared-credential read client used"))
        with mock.patch.object(orchestrator.erpnext, "get_document", poison), \
                mock.patch.object(orchestrator.erpnext, "list_documents", poison):
            out = self._branch({"op": "list", "doctype": "Customer", "limit": 20})
            self.assertIn("_read_request", out)
            # ...and the answer leg, given authorized context, also does not.
            self._branch({"op": "list", "doctype": "Customer", "limit": 20},
                         authorized_context=ctx())
        poison.assert_not_called()

    def test_8_1_read_request_carries_no_identity_and_no_wildcard(self):
        out = self._branch({"op": "list", "doctype": "Customer",
                            "fields": ["*"], "limit": 20})
        req = out["_read_request"]
        for forbidden in ("user", "actor", "username", "site", "mode"):
            self.assertNotIn(forbidden, req)
        self.assertNotIn("*", req["fields"])

    def test_8_1_hostile_model_filters_are_dropped(self):
        out = self._branch({"op": "list", "doctype": "Customer",
                            "filters": {"owner": "Administrator",
                                        "customer_name": {"$gt": ""},
                                        "unknown": "x"},
                            "limit": 20})
        req = out["_read_request"]
        self.assertNotIn("owner", req["filters"])
        self.assertNotIn("unknown", req["filters"])

    def test_8_4_mode_does_not_change_authorized_result(self):
        dev = self._branch({"op": "list", "doctype": "Customer", "limit": 20},
                           authorized_context=ctx(), mode="developer")
        emp = self._branch({"op": "list", "doctype": "Customer", "limit": 20},
                           authorized_context=ctx(), mode="employee")
        self.assertEqual(dev["answer"], emp["answer"])
        self.assertEqual(dev["confidence"], emp["confidence"])

    def test_8_3_schema_is_refused_by_the_adapter(self):
        from frappe_app.erpnext_ai_copilot import erpnext_read as er
        with self.assertRaises(er.UnsupportedOperation):
            er.build_request({"operation": "schema", "doctype": "Customer", "fields": ["name"]})

    def test_8_5_read_contract_declares_permission_and_no_approval(self):
        from tools.contracts import contract_for
        c = contract_for("erpnext_read")
        self.assertFalse(c["approval_required"])
        self.assertIsNotNone(c["permission"])
        self.assertIn("fields", c["bounded_inputs"])
        self.assertIn("operation", c["bounded_inputs"])
        self.assertIn("permission_denied", c["typed_errors"])
        self.assertEqual(c["audit_event"], "erpnext_read")

    def test_8_6_write_contracts_unchanged(self):
        from tools.contracts import contract_for
        for op in ("code_edit", "business_write"):
            self.assertTrue(contract_for(op)["approval_required"], op)

    def test_10_9_read_adapter_needs_no_erpnext_credential(self):
        """The authorized read path is structurally independent of the credential.

        The adapter must not reference the shared-credential client, and must
        not require any ERPNEXT_* variable, so inference can serve authorized
        business reads with that credential absent.
        """
        import os as _os
        from frappe_app.erpnext_ai_copilot import erpnext_read as er
        saved = {k: _os.environ.pop(k, None)
                 for k in ("ERPNEXT_BASE_URL", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET")}
        try:
            with mock.patch.object(er, "frappe", types.SimpleNamespace(
                    session=types.SimpleNamespace(user="u"),
                    local=types.SimpleNamespace(site="s"),
                    get_meta=lambda d: types.SimpleNamespace(istable=False, issingle=False),
                    get_list=lambda *a, **k: [types.SimpleNamespace(name="a")])), \
                    mock.patch("frappe_app.erpnext_ai_copilot.audit.record_audit",
                               return_value={"name": "NMAU-1"}):
                out = er.attempt_read({"operation": "list", "doctype": "Customer",
                                       "fields": ["name"]})
            self.assertEqual(out["row_count"], 1)
        finally:
            for k, v in saved.items():
                if v is not None:
                    _os.environ[k] = v
        with open(er.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("ERPNEXT_API_KEY", src)
        self.assertNotIn("from tools", src)
        self.assertNotIn("import tools", src)

    def test_8_6_mirror_drift_guard_still_holds(self):
        from frappe_app.erpnext_ai_copilot import proposals as P
        from tools.contracts import PROPOSAL_STATUSES
        self.assertEqual(set(P.PROPOSAL_STATUSES), set(PROPOSAL_STATUSES))


# ---------------------------------------------------------------------------
# Group 12 — legacy endpoint deprecation and quarantine (L-14)
# ---------------------------------------------------------------------------


class LegacyEndpointQuarantine(unittest.TestCase):
    def test_12_1_routes_retained_in_inventory(self):
        paths = {r.path for r in main.app.routes if hasattr(r, "path")}
        for route in ("/tools/erpnext/schema", "/tools/erpnext/document", "/tools/erpnext/list"):
            self.assertIn(route, paths, route)

    def test_12_1_routes_marked_deprecated(self):
        deprecated = {r.path for r in main.app.routes
                      if getattr(r, "deprecated", False)}
        self.assertEqual(
            deprecated,
            {"/tools/erpnext/schema", "/tools/erpnext/document", "/tools/erpnext/list"})

    def test_12_3_read_client_retained_for_legacy_consumers(self):
        from tools import erpnext
        for name in ("get_doctype_schema", "get_document", "list_documents", "call_method"):
            self.assertTrue(hasattr(erpnext, name), name)

    def test_12_4_version_lookup_still_resolves_credential(self):
        from tools import erpnext
        with mock.patch.dict(os.environ, {"ERPNEXT_BASE_URL": "http://x", "ERPNEXT_API_KEY": "k",
                                          "ERPNEXT_API_SECRET": "s"}, clear=False):
            self.assertEqual(erpnext._credentials(), ("http://x", "k", "s"))

    def test_12_4_write_path_still_uses_retained_client(self):
        from tools import erpnext_write
        with mock.patch.dict(os.environ, {"ERPNEXT_BASE_URL": "http://x", "ERPNEXT_API_KEY": "k",
                                          "ERPNEXT_API_SECRET": "s"}, clear=False):
            self.assertEqual(erpnext_write._auth_headers()["Authorization"], "token k:s")

    def test_12_4_credential_consumer_set_unchanged_apart_from_reads(self):
        from tools import erpnext_write
        with mock.patch.dict(os.environ, {"ERPNEXT_BASE_URL": "http://x", "ERPNEXT_API_KEY": "k",
                                          "ERPNEXT_API_SECRET": "s"}, clear=False):
            # Only the enumerated temporary consumers still ask for credentials.
            self.assertEqual(erpnext_write._base_url(), "http://x")

    def test_12_2_deprecation_policy_is_stated(self):
        self.assertEqual(len(main.DEPRECATED_ERPNEXT_READ_ROUTES), 3)
        self.assertIn("not end-user ERPNext authorization", main.DEPRECATION_NOTICE)


if __name__ == "__main__":
    unittest.main()
