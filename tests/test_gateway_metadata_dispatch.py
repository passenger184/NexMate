"""Envelope scope retirement, no-envelope refusal, and metadata kind dispatch.

Covers the single generic authenticated execution scope, the refusal of every
authorization-bearing field when no complete valid gateway envelope is
present, the metadata authorized-context contract beside (not merged with) the
business-read one, and the gateway's dispatch of a metadata request to the
metadata module rather than to the business-record read adapter.

Every module under test is loaded exactly once at import time and shared, so
the suite does not churn `sys.modules` per test.
"""

import json as jsonlib
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
KEY = "9f81ba760235e4cd7b60a19dca57e8234802bf6159ce743a182b9fdce03657a4"

SITE = "synthetic-site"
USER = "synthetic-user"


def _make_frappe():
    f = types.ModuleType("frappe")
    f.conf = {"copilot_api_base": "http://inference.invalid:8000",
              "nexmate_service_key": KEY}
    f.session = types.SimpleNamespace(user=USER)
    f.local = types.SimpleNamespace(site=SITE)
    f.form_dict = {}
    f.PermissionError = type("PermissionError", (Exception,), {})
    f.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
    f.whitelist = mock.Mock(return_value=lambda fn: fn)

    def _throw(message, exc=Exception):
        raise exc(message)

    f.throw = mock.Mock(side_effect=_throw)
    f.get_roles = mock.Mock(return_value=["Engineer"])
    f.new_doc = mock.Mock()
    f.db = mock.Mock()
    # Model genuine Settings absence: tabSingles proves the record was never
    # saved, so role resolution falls back to site_config.
    f.db.sql = mock.Mock(return_value=[])
    f.get_doc = mock.Mock(side_effect=Exception("no doc"))
    f.delete_doc = mock.Mock()
    return f


def _load(name, path, frappe_module, extra_modules=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    mapping = {"frappe": frappe_module}
    mapping.update(extra_modules or {})
    with mock.patch.dict(sys.modules, mapping):
        spec.loader.exec_module(module)
    return module


# --- shared module graph, built once ---------------------------------------

_FRAPPE = _make_frappe()


def _build():
    import config
    _CFG = mock.patch.multiple(config, NEXMATE_FRAPPE_SITE=SITE,
                               NEXMATE_SERVICE_KEY=KEY)
    _CFG.start()
    import atexit
    atexit.register(_CFG.stop)

    model = types.ModuleType("frappe.model")
    document = types.ModuleType("frappe.model.document")
    document.Document = object
    model.document = document

    conversations = _load("nm_disp.conversations", APP / "conversations.py", _FRAPPE)
    erpnext_read = _load("nm_disp.erpnext_read", APP / "erpnext_read.py", _FRAPPE)
    # The real limits module: dependency-free offline and shared by both the
    # control plane and these contract tests.
    policy_limits = _load("nm_disp.policy_limits", APP / "policy_limits.py", _FRAPPE)
    audit = _load("nm_disp.audit", APP / "audit.py", _FRAPPE,
                  {"frappe.model": model, "frappe.model.document": document})
    audit.record_audit = mock.Mock(return_value={"name": "NMAU-1"})
    audit._require_durable_store = mock.Mock(return_value=None)
    audit._should_use_frappe = mock.Mock(return_value=False)

    # api.py imports `from erpnext_ai_copilot import ...`, so the package must
    # be registered under that exact name, with each submodule bound to it.
    package = types.ModuleType("erpnext_ai_copilot")
    package.__path__ = []
    api_stub = types.ModuleType("erpnext_ai_copilot.api")
    api_stub.capability_for_user = mock.Mock(return_value="developer")

    mapping = {
        "erpnext_ai_copilot": package,
        "erpnext_ai_copilot.api": api_stub,
        "erpnext_ai_copilot.conversations": conversations,
        "erpnext_ai_copilot.erpnext_read": erpnext_read,
        "erpnext_ai_copilot.audit": audit,
        "erpnext_ai_copilot.policy_limits": policy_limits,
    }
    package.api = api_stub
    package.conversations = conversations
    package.erpnext_read = erpnext_read
    package.audit = audit
    package.policy_limits = policy_limits

    with mock.patch.dict(sys.modules, mapping):
        doctype_meta = _load("erpnext_ai_copilot.doctype_meta",
                             APP / "doctype_meta.py", _FRAPPE)
        package.doctype_meta = doctype_meta
        auth = _load("nm_disp.auth", ROOT / "service" / "auth.py", _FRAPPE)
        api = _load("erpnext_ai_copilot.api", APP / "api.py", _FRAPPE)

    return {
        "config": config, "cfg": _CFG, "frappe": _FRAPPE,
        "conversations": conversations, "erpnext_read": erpnext_read,
        "doctype_meta": doctype_meta, "audit": audit, "auth": auth, "api": api,
        "api_stub": api_stub, "model": model, "document": document,
        "policy_limits": policy_limits,
    }


_M = _build()


class _Shared(unittest.TestCase):
    """Base that restores shared module state between tests."""

    @classmethod
    def setUpClass(cls) -> None:
        # Other suites rebind this config; the envelope validator reads it at
        # call time, so re-assert it per class.
        _M["config"].NEXMATE_FRAPPE_SITE = SITE
        _M["config"].NEXMATE_SERVICE_KEY = KEY

    def setUp(self) -> None:
        self.frappe = _M["frappe"]
        self.audit = _M["audit"]
        self.audit.record_audit.reset_mock()
        self.audit.record_audit.return_value = {"name": "NMAU-1"}
        _M["api_stub"].capability_for_user.reset_mock()
        _M["api_stub"].capability_for_user.return_value = "developer"
        _M["frappe"].session.user = USER
        _M["frappe"].local.site = SITE
        _M["frappe"].get_roles.return_value = ["Engineer"]


class EnvelopeValidatorTest(_Shared):
    def setUp(self) -> None:
        super().setUp()
        self.auth = _M["auth"]
        self.request = types.SimpleNamespace(
            state=types.SimpleNamespace(service_authenticated=True))

    def _payload(self, **over):
        base = {"user": USER, "site": SITE, "mode": "developer",
                "execution_scope": "frappe-attributed"}
        base.update(over)
        return base

    def _validate(self, payload, supplied):
        HTTPException = self.auth.HTTPException
        try:
            return self.auth.validate_gateway_envelope(payload, set(supplied),
                                                        self.request), None
        except HTTPException as exc:
            return None, exc

    def test_the_single_authenticated_scope_is_accepted(self):
        ok, err = self._validate(self._payload(), self._payload())
        self.assertIsNone(err)
        self.assertTrue(ok)

    def test_any_other_scope_is_refused_without_coercion(self):
        HTTPException = self.auth.HTTPException
        for scope in ("chat-only", "authenticated", "frappe-attributed ",
                      "FRAPP-ATTRIBUTED", "", None, "erp-authorized"):
            with self.subTest(scope=scope):
                payload = self._payload(execution_scope=scope)
                with self.assertRaises(HTTPException):
                    self.auth.validate_gateway_envelope(
                        payload, set(payload), self.request)

    def test_retired_chat_only_literal_is_absent(self):
        source = (ROOT / "service" / "auth.py").read_text(encoding="utf-8")
        self.assertNotIn('"chat-only"', source)

    def test_no_envelope_and_no_authorization_field_is_legacy(self):
        ok, err = self._validate({"question": "hi"}, {"question"})
        self.assertIsNone(err)
        self.assertFalse(ok)

    def test_authorized_context_without_an_envelope_is_refused(self):
        HTTPException = self.auth.HTTPException
        payload = {"question": "hi",
                   "authorized_context": {"doctype": "Customer",
                                          "operation": "list",
                                          "fields_returned": ["name"],
                                          "row_count": 0, "data": []}}
        with self.assertRaises(HTTPException) as ctx:
            self.auth.validate_gateway_envelope(payload, set(payload), self.request)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_forged_scope_without_an_envelope_is_refused(self):
        HTTPException = self.auth.HTTPException
        payload = {"question": "hi",
                   "scope": {"site": SITE,
                             "tiers": ["public", "site", "restricted"],
                             "roles": ["System Manager"],
                             "derived_by": "frappe-gateway"}}
        with self.assertRaises(HTTPException):
            self.auth.validate_gateway_envelope(payload, set(payload), self.request)

    def test_conversation_without_an_envelope_is_refused(self):
        HTTPException = self.auth.HTTPException
        payload = {"question": "hi",
                   "conversation": {"id": "NM-1", "owner": None, "site": SITE,
                                    "turns": [{"role": "user", "content": "hi"}]}}
        with self.assertRaises(HTTPException):
            self.auth.validate_gateway_envelope(payload, set(payload), self.request)

    def test_all_three_channels_are_named_constants(self):
        self.assertEqual(self.auth.AUTHORIZATION_BEARING_FIELDS,
                         frozenset({"authorized_context", "scope", "conversation"}))

    def test_partial_envelope_still_refuses(self):
        HTTPException = self.auth.HTTPException
        payload = {"user": USER, "execution_scope": "frappe-attributed"}
        with self.assertRaises(HTTPException):
            self.auth.validate_gateway_envelope(payload, set(payload), self.request)


class AuthorizedContextContractTest(_Shared):
    def setUp(self) -> None:
        super().setUp()
        self.auth = _M["auth"]
        self.erpnext_read = _M["erpnext_read"]
        self.policy_limits = _M["policy_limits"]

    def _read_ctx(self, **over):
        base = {"doctype": "Customer", "operation": "list",
                "fields_returned": ["name"], "row_count": 0, "data": []}
        base.update(over)
        return base

    def _meta_ctx(self, **over):
        base = {"doctype": "Customer", "operation": "schema", "field_count": 1,
                "fields": [{"fieldname": "customer_name", "fieldtype": "Data",
                            "label": "Name", "reqd": True, "read_only": False}]}
        base.update(over)
        return base

    def test_metadata_context_is_accepted_with_its_own_shape(self):
        ctx = self._meta_ctx()
        self.assertEqual(self.auth.validate_authorized_context(ctx), ctx)

    def test_metadata_context_may_not_borrow_the_read_shape(self):
        HTTPException = self.auth.HTTPException
        with self.assertRaises(HTTPException):
            self.auth.validate_authorized_context(self._meta_ctx(data=[]))
        with self.assertRaises(HTTPException):
            self.auth.validate_authorized_context(
                self._meta_ctx(fields_returned=["name"]))

    def test_read_context_may_not_borrow_the_metadata_shape(self):
        HTTPException = self.auth.HTTPException
        with self.assertRaises(HTTPException):
            self.auth.validate_authorized_context(self._read_ctx(field_count=1))

    def test_metadata_projection_keys_are_closed(self):
        HTTPException = self.auth.HTTPException
        self.assertEqual(self.auth.METADATA_PROJECTION_KEYS,
                         frozenset({"fieldname", "fieldtype", "label", "reqd",
                                    "read_only"}))
        for extra in ("options", "permlevel", "value", "default"):
            with self.subTest(extra=extra):
                entry = dict(self._meta_ctx()["fields"][0])
                entry[extra] = "x"
                with self.assertRaises(HTTPException):
                    self.auth.validate_authorized_context(
                        self._meta_ctx(fields=[entry]))

    def test_metadata_bounds_are_declared(self):
        HTTPException = self.auth.HTTPException
        # Immutable service ceilings, deliberately separate constants from the
        # business-read bounds even where values could coincide.
        self.assertEqual(self.auth.METADATA_FIELDS_CEILING, 500)
        self.assertEqual(self.auth.METADATA_BYTES_CEILING, 131072)
        self.assertNotIn("MAX_METADATA_FIELDS",
                         {name for name in dir(self.auth) if not name.startswith("_")})
        with self.assertRaises(HTTPException):
            self.auth.validate_authorized_context(
                self._meta_ctx(field_count=self.auth.METADATA_FIELDS_CEILING + 1))
        with self.assertRaises(HTTPException):
            self.auth.validate_authorized_context(
                self._meta_ctx(field_count=2))

    def test_metadata_contract_accepts_what_frappe_may_produce(self):
        # Coordination requirement: a Frappe-accepted projection (e.g. 150
        # fields under a raised administrator bound) must never be rejected
        # here with HTTP 422. The contract ceiling, not the old fixed bound,
        # is the acceptance limit.
        HTTPException = self.auth.HTTPException
        many = [{"fieldname": f"f{i}", "fieldtype": "Data",
                 "label": f"F{i}", "reqd": False, "read_only": False}
                for i in range(150)]
        ctx = self._meta_ctx(field_count=150, fields=many)
        self.assertEqual(self.auth.validate_authorized_context(ctx), ctx)

    def test_business_read_bounds_match_the_producer_ceiling(self):
        HTTPException = self.auth.HTTPException
        self.assertEqual(self.auth.AUTHORIZED_CONTEXT_OPERATIONS,
                         ("document", "list"))
        # The consumer must never be narrower than the producer's approved
        # immutable ceilings, or a Frappe-authorized read is silently lost.
        self.assertEqual(self.auth.MAX_AUTHORIZED_CONTEXT_ROWS, 100)
        self.assertEqual(self.auth.MAX_AUTHORIZED_CONTEXT_FIELDS, 50)
        self.assertEqual(self.auth.MAX_AUTHORIZED_CONTEXT_BYTES, 131072)
        for bad in (self._read_ctx(fields_returned=[f"f{i}" for i in range(51)]),
                    self._read_ctx(row_count=10_000),
                    self._read_ctx(data=[{"name": "x" * 140000}])):
            with self.assertRaises(HTTPException):
                self.auth.validate_authorized_context(bad)

    def test_consumer_accepts_everything_the_producer_can_emit(self):
        """Consumer bounds are >= the adapter's backstop, row for row."""
        HTTPException = self.auth.HTTPException
        rows = self.erpnext_read.MAX_LIST_LIMIT
        fields = self.erpnext_read.MAX_FIELD_COUNT
        size = self.erpnext_read.MAX_RESULT_BYTES
        self.assertGreaterEqual(self.auth.MAX_AUTHORIZED_CONTEXT_ROWS, rows)
        self.assertGreaterEqual(self.auth.MAX_AUTHORIZED_CONTEXT_FIELDS, fields)
        self.assertGreaterEqual(self.auth.MAX_AUTHORIZED_CONTEXT_BYTES, size)
        # Exactly at the adapter's maximum the consumer still admits it.
        admitted = self._read_ctx(
            fields_returned=[f"f{i}" for i in range(fields)],
            row_count=rows,
            data=[{f"f{i}": "v" for i in range(fields)} for _ in range(rows)])
        self.assertEqual(self.auth.validate_authorized_context(admitted), admitted)

    def _sized_read_ctx(self, target_bytes):
        """A valid business-read context serialized to exactly target_bytes."""
        base = self._read_ctx(fields_returned=["name"], row_count=1,
                              data=[{"name": ""}])
        overhead = len(jsonlib.dumps(base, default=str))
        base["data"][0]["name"] = "x" * max(0, target_bytes - overhead)
        # Padding only ever undershoots by the JSON escaping of "x"; correct it.
        delta = target_bytes - self._serialized(base)
        if delta > 0:
            base["data"][0]["name"] += "x" * delta
        return base

    def _serialized(self, ctx):
        return len(jsonlib.dumps(ctx, default=str))

    def test_business_read_consumer_accepts_the_whole_approved_envelope(self):
        """Rows, fields and bytes are all admitted up to the approved ceiling."""
        HTTPException = self.auth.HTTPException
        # --- rows
        for n in (20, 21, 50, 100):
            with self.subTest(rows=n):
                ctx = self._read_ctx(row_count=n,
                                     data=[{"name": str(i)} for i in range(n)])
                self.assertEqual(self.auth.validate_authorized_context(ctx), ctx)
        for n in (101, 150):
            with self.subTest(rows=n):
                with self.assertRaises(HTTPException):
                    self.auth.validate_authorized_context(
                        self._read_ctx(row_count=n,
                                       data=[{"name": str(i)} for i in range(n)]))
        # --- fields
        for n in (20, 50):
            with self.subTest(fields=n):
                ctx = self._read_ctx(fields_returned=[f"f{i}" for i in range(n)])
                self.assertEqual(self.auth.validate_authorized_context(ctx), ctx)
        for n in (51, 80):
            with self.subTest(fields=n):
                with self.assertRaises(HTTPException):
                    self.auth.validate_authorized_context(
                        self._read_ctx(fields_returned=[f"f{i}" for i in range(n)]))
        # --- bytes
        for target in (65536, 131072):
            with self.subTest(bytes=target):
                ctx = self._sized_read_ctx(target)
                self.assertEqual(self._serialized(ctx), target)
                self.assertEqual(self.auth.validate_authorized_context(ctx), ctx)
        for target in (131073, 200000):
            with self.subTest(bytes=target):
                ctx = self._sized_read_ctx(target)
                self.assertEqual(self._serialized(ctx), target)
                with self.assertRaises(HTTPException):
                    self.auth.validate_authorized_context(ctx)

    def test_every_layer_reports_the_same_approved_ceiling(self):
        """Adapter, control plane and consumer must agree on the maximums."""
        er = self.erpnext_read
        self.assertEqual(er.MAX_LIST_LIMIT, 100)
        self.assertEqual(er.MAX_FIELD_COUNT, 50)
        self.assertEqual(er.MAX_RESULT_BYTES, 131072)
        self.assertEqual(self.auth.MAX_AUTHORIZED_CONTEXT_ROWS,
                         er.MAX_LIST_LIMIT)
        self.assertEqual(self.auth.MAX_AUTHORIZED_CONTEXT_FIELDS,
                         er.MAX_FIELD_COUNT)
        self.assertEqual(self.auth.MAX_AUTHORIZED_CONTEXT_BYTES,
                         er.MAX_RESULT_BYTES)
        for field, ceiling in (
            ("max_read_rows", self.auth.MAX_AUTHORIZED_CONTEXT_ROWS),
            ("max_read_fields", self.auth.MAX_AUTHORIZED_CONTEXT_FIELDS),
            ("max_read_bytes", self.auth.MAX_AUTHORIZED_CONTEXT_BYTES),
        ):
            with self.subTest(field=field):
                self.assertEqual(self.policy_limits.NUMERIC_CEILINGS[field],
                                 ceiling)
                self.assertLessEqual(
                    self.policy_limits.NUMERIC_RANGES[field][1], ceiling)

    def test_narrowing_below_the_ceiling_is_preserved_end_to_end(self):
        """An administrator value below the ceiling narrows and stays narrow.

        The control plane denies the request before the adapter, so the
        consumer never has to be involved -- and the narrower result it does
        see is comfortably inside its own ceiling.
        """
        original_get_doc = _M["frappe"].get_doc
        original_sql = _M["frappe"].db.sql

        class _Doc:
            def __init__(self, values):
                for key, value in values.items():
                    setattr(self, key, value)
                self.developer_role_rules = []
                self.metadata_doctype_rules = []

        narrowed = {"max_schema_fields": 300, "max_schema_bytes": 65536,
                    "max_read_rows": 5, "max_read_fields": 4,
                    "max_read_bytes": 8192, "max_read_rounds": 2}
        _M["frappe"].get_doc = mock.Mock(
            side_effect=lambda *a, **k: _Doc(narrowed))
        _M["frappe"].db.sql = mock.Mock(return_value=[(1,)])
        try:
            api = _M["api"]
            self.assertEqual(api._effective_read_bounds(), (5, 4, 8192))
            with mock.patch.object(
                    self.erpnext_read, "attempt_read",
                    side_effect=AssertionError("must not reach the adapter")):
                denied = api._authorized_read(
                    {"operation": "list", "doctype": "Customer", "name": None,
                     "fields": ["name"], "filters": {}, "limit": 6},
                    correlation="c", request_id="r")
            self.assertIn("_denied", denied)
            # What the narrowed policy does allow is admitted by the consumer.
            admitted = {"doctype": "Customer", "operation": "list",
                        "fields_returned": ["name"], "row_count": 5,
                        "data": [{"name": str(i)} for i in range(5)]}
            with mock.patch.object(self.erpnext_read, "attempt_read",
                                   return_value=admitted):
                allowed = api._authorized_read(
                    {"operation": "list", "doctype": "Customer", "name": None,
                     "fields": ["name"], "filters": {}, "limit": 5},
                    correlation="c", request_id="r")
            self.assertIn("_context", allowed)
            self.assertEqual(allowed["_context"], admitted)
            self.assertEqual(
                self.auth.validate_authorized_context(allowed["_context"]),
                admitted)
        finally:
            _M["frappe"].get_doc = original_get_doc
            _M["frappe"].db.sql = original_sql

    def test_default_read_bounds_still_sit_inside_the_consumer_ceiling(self):
        self.assertEqual(self.policy_limits.DEFAULT_READ_ROWS, 20)
        self.assertEqual(self.policy_limits.DEFAULT_READ_FIELDS, 20)
        self.assertEqual(self.policy_limits.DEFAULT_READ_BYTES, 65536)
        self.assertLessEqual(self.policy_limits.DEFAULT_READ_ROWS,
                             self.auth.MAX_AUTHORIZED_CONTEXT_ROWS)
        self.assertLessEqual(self.policy_limits.DEFAULT_READ_FIELDS,
                             self.auth.MAX_AUTHORIZED_CONTEXT_FIELDS)
        self.assertLessEqual(self.policy_limits.DEFAULT_READ_BYTES,
                             self.auth.MAX_AUTHORIZED_CONTEXT_BYTES)


class GatewayDispatchTest(_Shared):
    def setUp(self) -> None:
        super().setUp()
        self.api = _M["api"]
        self.erpnext_read = _M["erpnext_read"]
        self.doctype_meta = _M["doctype_meta"]
        self.policy_limits = _M["policy_limits"]

    def _configure_settings(self, numeric):
        """Temporarily serve numeric settings values, restored afterwards."""
        original_get_doc = _M["frappe"].get_doc
        original_sql = _M["frappe"].db.sql

        class _Doc:
            def __init__(self, values):
                self._values = values

            def get(self, key, default=None):
                if key == "metadata_doctype_rules":
                    return []
                if key == "developer_role_rules":
                    return []
                return self._values.get(key, default)

            def __getattr__(self, name):
                if name.startswith("_"):
                    raise AttributeError(name)
                try:
                    return self._values[name]
                except KeyError:
                    raise AttributeError(name)

        _M["frappe"].get_doc = mock.Mock(return_value=_Doc(numeric))
        _M["frappe"].db.sql = mock.Mock(return_value=[(1,)])
        self.addCleanup(setattr, _M["frappe"], "get_doc", original_get_doc)
        self.addCleanup(setattr, _M["frappe"].db, "sql", original_sql)

    def _post_sequence(self, decide):
        sent = []

        def post(url, json=None, **kwargs):
            sent.append(json)
            body = decide(sent, len(sent))
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.__exit__.return_value = False
            response.status_code = 200
            response.iter_content.side_effect = lambda **k: iter(
                [jsonlib.dumps(body).encode("utf-8")])
            return response

        client = mock.MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post.side_effect = post
        patcher = mock.patch.object(self.api.requests, "Session",
                                    return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client, sent

    def _post_requesting_schema(self):
        return self._post_sequence(
            lambda sent, n: {"read_request": {"kind": "schema",
                                              "doctype": "Customer"}})

    def _post_requiring_read(self):
        return self._post_sequence(lambda sent, n: {"read_request": {
            "operation": "document", "doctype": "Customer", "name": "T",
            "fields": ["name"], "filters": {}, "limit": 1}})

    def test_metadata_request_dispatches_to_the_metadata_module(self):
        projection = {"doctype": "Customer", "fields": []}
        read_attempt = mock.Mock(side_effect=AssertionError("read adapter called"))
        meta_attempt = mock.Mock(return_value=projection)
        self._post_requesting_schema()
        with mock.patch.object(self.erpnext_read, "attempt_read", read_attempt), \
                mock.patch.object(self.doctype_meta, "attempt_metadata", meta_attempt):
            with self.assertRaises(Exception):
                self.api.ask("What fields does Customer have?")
        meta_attempt.assert_called()
        read_attempt.assert_not_called()
        payload = meta_attempt.call_args.args[0]
        self.assertEqual(payload["doctype"], "Customer")
        self.assertNotIn("kind", payload)

    def test_business_read_dispatches_to_the_read_adapter_only(self):
        read_attempt = mock.Mock(return_value={"doctype": "Customer",
                                               "operation": "document",
                                               "fields_returned": ["name"],
                                               "row_count": None,
                                               "data": {"name": "T"}})
        meta_attempt = mock.Mock(side_effect=AssertionError("metadata called"))
        self._post_requiring_read()
        with mock.patch.object(self.erpnext_read, "attempt_read", read_attempt), \
                mock.patch.object(self.doctype_meta, "attempt_metadata", meta_attempt):
            with self.assertRaises(Exception):
                self.api.ask("What is the name of Customer T?")
        read_attempt.assert_called()
        meta_attempt.assert_not_called()

    def test_metadata_refusal_produces_the_metadata_collapse(self):
        refusal = self.doctype_meta.PolicyDenied("allowlist says no")
        self._post_requesting_schema()
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               side_effect=refusal):
            out = self.api.ask("What fields does Customer have?")
        self.assertEqual(out["answer"], "Schema not found or access denied.")
        self.assertNotIn("allowlist", out["answer"])
        self.assertNotIn("Customer", out["answer"])
        self.assertEqual(out["sources"], [])
        self.assertEqual(out["confidence"], "low")

    def test_metadata_refusal_is_not_labelled_a_business_record_denial(self):
        refusal = self.doctype_meta.CapabilityDenied("no developer capability")
        self._post_requesting_schema()
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               side_effect=refusal):
            out = self.api.ask("What fields does Customer have?")
        self.assertNotIn("Document not found", out["answer"])
        self.assertNotIn("frappe-authorized-read", jsonlib.dumps(out))

    def test_a_refused_metadata_request_ends_the_loop(self):
        client, _sent = self._post_requesting_schema()
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               side_effect=self.doctype_meta.PolicyDenied("x")):
            out = self.api.ask("What fields does Customer have?")
        self.assertEqual(out["answer"], "Schema not found or access denied.")
        self.assertEqual(client.post.call_count, 1)

    def test_metadata_and_reads_share_one_round_budget(self):
        client, _sent = self._post_requesting_schema()
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               return_value={"doctype": "Customer", "fields": []}):
            with self.assertRaises(Exception) as ctx:
                self.api.ask("What fields does Customer have?")
        self.assertEqual(client.post.call_count,
                           _M["policy_limits"].DEFAULT_READ_ROUNDS)
        self.assertIn("gateway_upstream_protocol_error", str(ctx.exception))
        self.assertNotIn("gateway_read_round_limit", str(ctx.exception))

    def test_configured_round_budget_is_honored_and_clamped(self):
        self._configure_settings({"max_read_rounds": 2})
        client, _sent = self._post_requesting_schema()
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               return_value={"doctype": "Customer", "fields": []}):
            with self.assertRaises(Exception):
                self.api.ask("What fields does Customer have?")
        self.assertEqual(client.post.call_count, 2)
        # Above-ceiling values clamp to the ceiling; below-minimum to 1.
        self._configure_settings({"max_read_rounds": 99})
        client, _sent = self._post_requesting_schema()
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               return_value={"doctype": "Customer", "fields": []}):
            with self.assertRaises(Exception):
                self.api.ask("What fields does Customer have?")
        self.assertEqual(client.post.call_count,
                         _M["policy_limits"].READ_ROUNDS_CEILING)

    def test_narrowed_read_rows_are_denied_before_the_adapter(self):
        self._configure_settings({"max_read_rows": 5})
        with mock.patch.object(self.erpnext_read, "attempt_read",
                               side_effect=AssertionError("adapter called")):
            outcome = self.api._authorized_read(
                {"operation": "list", "doctype": "Customer", "name": None,
                 "fields": ["name"], "filters": {}, "limit": 20},
                correlation="c", request_id="r")
        self.assertIn("_denied", outcome)
        self.assertEqual(outcome["_denied"]["answer"],
                         "Document not found or access denied.")

    def test_narrowed_read_fields_are_denied_before_the_adapter(self):
        self._configure_settings({"max_read_fields": 2})
        with mock.patch.object(self.erpnext_read, "attempt_read",
                               side_effect=AssertionError("adapter called")):
            outcome = self.api._authorized_read(
                {"operation": "list", "doctype": "Customer", "name": None,
                 "fields": ["name", "customer_name", "territory"],
                 "filters": {}, "limit": 5},
                correlation="c", request_id="r")
        self.assertIn("_denied", outcome)

    def test_default_read_bounds_match_adapter_behavior(self):
        # With no settings configured, the effective bounds equal the frozen
        # adapter bounds, so the pre-check changes nothing observable: the
        # request reaches the adapter.
        read_attempt = mock.Mock(return_value={
            "doctype": "Customer", "operation": "list",
            "fields_returned": ["name"], "row_count": 0, "data": []})
        with mock.patch.object(self.erpnext_read, "attempt_read", read_attempt):
            outcome = self.api._authorized_read(
                {"operation": "list", "doctype": "Customer", "name": None,
                 "fields": ["name"], "filters": {}, "limit": 20},
                correlation="c", request_id="r")
        read_attempt.assert_called_once()
        self.assertIn("_context", outcome)

    def test_effective_bounds_never_exceed_the_adapter_backstop(self):
        # Even with administrator values at or above the service ceilings, the
        # resolved effective bounds stay within what the frozen adapter
        # accepts, so a configured request can never trip the adapter's bound
        # errors as a surprise. The adapter remains the ultimate backstop.
        self._configure_settings({"max_read_rows": 100, "max_read_fields": 50,
                                  "max_read_bytes": 131072})
        rows, fields, size = self.api._effective_read_bounds()
        self.assertLessEqual(rows, self.erpnext_read.MAX_LIST_LIMIT)
        self.assertLessEqual(fields, self.erpnext_read.MAX_FIELD_COUNT)
        self.assertLessEqual(size, self.erpnext_read.MAX_RESULT_BYTES)
        self._configure_settings({"max_read_rows": 9999,
                                  "max_read_fields": 9999,
                                  "max_read_bytes": 10 ** 9})
        rows, fields, size = self.api._effective_read_bounds()
        self.assertLessEqual(rows, self.erpnext_read.MAX_LIST_LIMIT)
        self.assertLessEqual(fields, self.erpnext_read.MAX_FIELD_COUNT)
        self.assertLessEqual(size, self.erpnext_read.MAX_RESULT_BYTES)

    def test_adapter_backstop_refuses_beyond_service_ceiling(self):
        # The adapter backstop now matches the immutable service ceiling: a
        # list limit of 100 is accepted, 101 is refused with the standard
        # collapsed denial, independent of any administrator setting.
        self._configure_settings({"max_read_rows": 100})
        payload = {"operation": "list", "doctype": "Customer", "name": None,
                   "fields": ["name"], "filters": {}, "limit": 101}
        with mock.patch.object(self.erpnext_read, "attempt_read",
                               side_effect=AssertionError("must not reach")):
            outcome = self.api._authorized_read(
                dict(payload), correlation="c", request_id="r")
        self.assertIn("_denied", outcome)
        self.assertEqual(outcome["_denied"]["answer"],
                         "Document not found or access denied.")
        # The adapter itself refuses the same request independent of
        # any setting: ultimate backstop. The meta stub lets validation
        # reach the limit check.
        meta = types.SimpleNamespace(istable=False, issingle=False)
        original_get_meta = getattr(_M["frappe"], "get_meta", None)
        _M["frappe"].get_meta = mock.Mock(return_value=meta)
        self.addCleanup(delattr, _M["frappe"], "get_meta")
        if original_get_meta is not None:
            self.addCleanup(setattr, _M["frappe"], "get_meta", original_get_meta)
        with self.assertRaises(self.erpnext_read.InvalidRequest) as caught:
            self.erpnext_read.build_request(dict(payload))
        self.assertIn("adapter bound", str(caught.exception))

    def test_configured_read_values_reach_the_adapter(self):
        # Settings → effective → pre-check → adapter, with the adapter
        # observing the configured values verbatim.
        for admin_rows, limit in ((50, 50), (100, 100)):
            with self.subTest(admin_rows=admin_rows):
                self._configure_settings({"max_read_rows": admin_rows})
                seen = {}

                def attempt(payload):
                    seen.update(payload)
                    return {"doctype": "Customer", "operation": "list",
                            "fields_returned": ["name"], "row_count": 0,
                            "data": []}

                with mock.patch.object(self.erpnext_read, "attempt_read",
                                       side_effect=attempt):
                    outcome = self.api._authorized_read(
                        {"operation": "list", "doctype": "Customer",
                         "name": None, "fields": ["name"], "filters": {},
                         "limit": limit},
                        correlation="c", request_id="r")
                self.assertIn("_context", outcome)
                self.assertEqual(seen.get("limit"), limit)
        for admin_fields, nfields in ((40, 40), (50, 50)):
            with self.subTest(admin_fields=admin_fields):
                self._configure_settings({"max_read_fields": admin_fields})
                seen = {}

                def attempt(payload):
                    seen.update(payload)
                    return {"doctype": "Customer", "operation": "list",
                            "fields_returned": ["name"], "row_count": 0,
                            "data": []}

                with mock.patch.object(self.erpnext_read, "attempt_read",
                                       side_effect=attempt):
                    outcome = self.api._authorized_read(
                        {"operation": "list", "doctype": "Customer",
                         "name": None,
                         "fields": [f"f{i}" for i in range(nfields)],
                         "filters": {}, "limit": 5},
                        correlation="c", request_id="r")
                self.assertIn("_context", outcome)
                self.assertEqual(len(seen.get("fields", [])), nfields)

    def test_configured_byte_bound_reaches_the_adapter_boundary(self):
        # 120000 configured bytes: a ~110KB result passes the api layer
        # and would reach the adapter boundary check.
        self._configure_settings({"max_read_bytes": 120000})
        big_data = {"k": "x" * 110000}
        read_attempt = mock.Mock(return_value={
            "doctype": "Customer", "operation": "document",
            "fields_returned": ["k"], "row_count": None, "data": big_data})
        with mock.patch.object(self.erpnext_read, "attempt_read", read_attempt):
            outcome = self.api._authorized_read(
                {"operation": "document", "doctype": "Customer",
                 "name": "C-1", "fields": ["k"]},
                correlation="c", request_id="r")
        read_attempt.assert_called_once()
        self.assertIn("_context", outcome)
        # Above the immutable ceiling, runtime clamps: a forced 200000-byte
        # setting still enforces 131072 at this layer.
        self._configure_settings({"max_read_bytes": 200000})
        over = {"k": "x" * 131000}
        read_attempt = mock.Mock(return_value={
            "doctype": "Customer", "operation": "document",
            "fields_returned": ["k"], "row_count": None, "data": over})
        with mock.patch.object(self.erpnext_read, "attempt_read", read_attempt):
            outcome = self.api._authorized_read(
                {"operation": "document", "doctype": "Customer",
                 "name": "C-1", "fields": ["k"]},
                correlation="c", request_id="r")
        self.assertIn("_denied", outcome)

    def test_metadata_field_count_is_enforced_before_inference(self):
        big = {"doctype": "Customer",
               "fields": [{"fieldname": f"f{i}", "fieldtype": "Data",
                           "label": f"F{i}", "reqd": False, "read_only": False}
                          for i in range(301)]}
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               return_value=big):
            outcome = self.api._authorized_metadata(
                {"kind": "schema", "doctype": "Customer"}, request_id="0")
        self.assertIn("_denied", outcome)
        self.assertEqual(outcome["_denied"]["answer"],
                         "Schema not found or access denied.")
        # A Frappe-accepted projection within the default bound passes through.
        small = {"doctype": "Customer", "fields": big["fields"][:299]}
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               return_value=small):
            outcome = self.api._authorized_metadata(
                {"kind": "schema", "doctype": "Customer"}, request_id="0")
        self.assertIn("_context", outcome)
        self.assertEqual(outcome["_context"]["operation"], "schema")

    def test_metadata_authorized_context_reaches_the_envelope(self):
        projection = {"doctype": "Customer",
                      "fields": [{"fieldname": "name", "fieldtype": "Data",
                                  "label": "Name", "reqd": False,
                                  "read_only": False}]}

        def decide(sent, n):
            if n == 1:
                return {"read_request": {"kind": "schema", "doctype": "Customer"}}
            return {"answer": "Customer has field name [1].", "sources": [],
                    "confidence": "high", "route": "rag",
                    "mode": sent[0]["mode"], "conversation_id": None,
                    "version_info": {"status": "unavailable"}}

        _client, sent = self._post_sequence(decide)
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               return_value=projection), \
             mock.patch.object(self.erpnext_read, "attempt_read",
                               side_effect=AssertionError("read adapter called")):
            out = self.api.ask("What fields does Customer have?")
        self.assertEqual(len(sent), 2)
        context = sent[1]["authorized_context"]
        self.assertEqual(context["operation"], "schema")
        self.assertEqual(context["doctype"], "Customer")
        self.assertEqual(context["field_count"], 1)
        self.assertEqual(set(context["fields"][0]),
                         set(self.doctype_meta.PROJECTION_FIELDS))
        self.assertEqual(out["answer"], "Customer has field name [1].")
        blob = jsonlib.dumps(sent)
        for leak in ("metadata_access_mode", "metadata_doctype_rules",
                     "NexMate Settings", "allowlist", "policy_mode"):
            self.assertNotIn(leak, blob, leak)

    def test_authorized_context_is_not_echoed_to_the_browser(self):
        projection = {"doctype": "Customer",
                      "fields": [{"fieldname": "name", "fieldtype": "Data",
                                  "label": "Name", "reqd": False,
                                  "read_only": False}]}

        def decide(sent, n):
            if n == 1:
                return {"read_request": {"kind": "schema", "doctype": "Customer"}}
            return {"answer": "ok [1]", "sources": [], "confidence": "high",
                    "route": "rag", "mode": sent[0]["mode"],
                    "conversation_id": None,
                    "version_info": {"status": "unavailable"}}

        _client, _sent = self._post_sequence(decide)
        with mock.patch.object(self.doctype_meta, "attempt_metadata",
                               return_value=projection):
            out = self.api.ask("What fields does Customer have?")
        self.assertEqual(set(out) <= set(self.api.RESPONSE_FIELDS), True)
        self.assertNotIn("authorized_context", out)
        self.assertNotIn("fields", out)


class MetadataNullContractTest(_Shared):
    """Producer guarantees a total projection; the consumer stays strict.

    Both modules under test are the real ones: `doctype_meta` produces the
    projection and `service/auth.py` validates it. This is the cross-layer
    contract from design D22.
    """

    def setUp(self) -> None:
        super().setUp()
        self.dm = _M["doctype_meta"]
        self.auth = _M["auth"]
        self.erpnext_read = _M["erpnext_read"]

    def _field(self, name, fieldtype="Data", label=None, reqd=0, read_only=0,
               options="Secret,Business,Vocabulary"):
        return types.SimpleNamespace(fieldname=name, fieldtype=fieldtype,
                                     label=label, reqd=reqd, read_only=read_only,
                                     options=options, permlevel=0)

    def _projection(self, *fields, doctype="Customer"):
        meta = types.SimpleNamespace(name=doctype, istable=False, issingle=False,
                                      fields=list(fields))
        return self.dm.project_meta(meta, max_fields=500)

    def _context(self, projection):
        return {"doctype": projection["doctype"], "operation": "schema",
                "field_count": len(projection["fields"]),
                "fields": projection["fields"]}

    # --- producer: the projection is total --------------------------------

    def test_layout_and_unlabelled_fields_yield_a_total_projection(self):
        projection = self._projection(
            self._field("basic_info", "Section Break", label=None),
            self._field("column_break_xyz", "Column Break", label=None),
            self._field("html_block", "HTML", label=None),
            self._field("description", "Small Text", label=None, reqd=None),
        )
        for entry in projection["fields"]:
            self.assertEqual(sorted(entry),
                             ["fieldname", "fieldtype", "label", "read_only", "reqd"])
            for key, value in entry.items():
                self.assertIsNotNone(value, key)
        self.assertEqual(projection["fields"][0]["label"], "")
        self.assertEqual(projection["fields"][3]["reqd"], False)

    # --- the real consumer now admits it ----------------------------------

    def test_producer_output_is_accepted_by_the_real_consumer(self):
        projection = self._projection(
            self._field("section", "Section Break", label=None),
            self._field("col", "Column Break", label=None, reqd=1, read_only=0),
        )
        ctx = self._context(projection)
        self.assertEqual(self.auth.validate_metadata_context(ctx), ctx)
        # ... and through the same dispatch a real payload takes.
        self.assertEqual(self.auth.validate_authorized_context(ctx), ctx)

    def test_projection_remains_exactly_five_keys_per_field(self):
        projection = self._projection(
            self._field("a", "Section Break", label=None),
            self._field("b", "Data", label="B"))
        for entry in projection["fields"]:
            self.assertEqual(set(entry), set(self.dm.PROJECTION_FIELDS))
            self.assertEqual(len(entry), 5)

    # --- the consumer remains strict ---------------------------------------

    def test_consumer_still_rejects_a_deliberately_null_label(self):
        """Producer-side normalisation must not weaken the validator."""
        ctx = {"doctype": "Customer", "operation": "schema", "field_count": 1,
               "fields": [{"fieldname": "a", "fieldtype": "Section Break",
                           "label": None, "reqd": False, "read_only": False}]}
        with self.assertRaises(self.auth.HTTPException):
            self.auth.validate_metadata_context(ctx)
        with self.assertRaises(self.auth.HTTPException):
            self.auth.validate_authorized_context(ctx)

    def test_consumer_still_rejects_a_missing_declared_attribute(self):
        ctx = {"doctype": "Customer", "operation": "schema", "field_count": 1,
               "fields": [{"fieldname": "a", "fieldtype": "Data", "label": "A",
                           "reqd": False}]}
        with self.assertRaises(self.auth.HTTPException):
            self.auth.validate_metadata_context(ctx)

    def test_consumer_still_rejects_an_extra_attribute(self):
        ctx = {"doctype": "Customer", "operation": "schema", "field_count": 1,
               "fields": [{"fieldname": "a", "fieldtype": "Data", "label": "A",
                           "reqd": False, "read_only": False,
                           "default": "Business Value"}]}
        with self.assertRaises(self.auth.HTTPException):
            self.auth.validate_metadata_context(ctx)

    def test_consumer_value_type_rule_is_present_and_unchanged(self):
        """Pins the strictness this change deliberately does not relax."""
        import inspect
        source = inspect.getsource(self.auth.validate_metadata_context)
        self.assertIn("isinstance(entry.get(k), (str, bool, int))", source)
        self.assertIn("invalid_authorized_context", source)

    # --- anti-exfiltration preserved by the producer -----------------------

    def test_projection_carries_no_business_values_or_permissions(self):
        projection = self._projection(
            self._field("customer_name", "Data", label="Customer Name",
                        reqd=1, options="Tier A,Tier B"))
        serialized = jsonlib.dumps(projection, default=str)
        self.assertNotIn("options", serialized)
        self.assertNotIn("Secret", serialized)
        self.assertNotIn("permlevel", serialized)
        self.assertNotIn("permissions", serialized)
        for entry in projection["fields"]:
            self.assertEqual(set(entry), set(self.dm.PROJECTION_FIELDS))

    def test_producer_introduces_no_shared_erpnext_credential(self):
        import inspect
        source = inspect.getsource(self.dm)
        for token in ("ERPNEXT_API_KEY", "ERPNEXT_API_SECRET", "api_secret",
                      "urlopen", "requests.", "httpx"):
            self.assertNotIn(token, source, token)

    def test_metadata_path_makes_no_business_read_calls(self):
        calls = []
        real = self.erpnext_read.attempt_read
        self.erpnext_read.attempt_read = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
        try:
            self._projection(self._field("a", "Section Break", label=None))
        finally:
            self.erpnext_read.attempt_read = real
        self.assertEqual(calls, [])

    # --- bounds and ceilings untouched -------------------------------------

    def test_metadata_ceilings_are_unchanged_by_this_contract(self):
        self.assertEqual(self.auth.METADATA_FIELDS_CEILING, 500)
        self.assertEqual(self.auth.METADATA_BYTES_CEILING, 131072)
        self.assertEqual(sorted(self.auth.METADATA_PROJECTION_KEYS),
                         ["fieldname", "fieldtype", "label", "read_only", "reqd"])


if __name__ == "__main__":
    unittest.main()
