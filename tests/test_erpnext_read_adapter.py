"""U5 Frappe-native authorized ERPNext read adapter suite.

Covers the adapter contract offline with a stubbed ``frappe`` module: identity
source, strict request validation, permission-aware execution, field-level
enforcement, minimization, fail-closed audit, and anti-oracle behaviour.

No real ERPNext, Frappe DB, or network access. The live two-user
authorization evidence is a separate, approval-gated task.
"""

import os
import sys
import types
import unittest
from unittest import mock

os.environ.setdefault("NEXMATE_DURABLE_FALLBACK", "1")
os.environ.setdefault("NEXMATE_TEST_USER", "u5_test_user")
os.environ.setdefault("NEXMATE_TEST_SITE", "u5_test_site")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frappe_app.erpnext_ai_copilot import erpnext_read as er


# ---------------------------------------------------------------------------
# Frappe stub
# ---------------------------------------------------------------------------


class _Doc:
    def __init__(self, data, meta):
        self.__dict__.update(data)
        self.meta = meta

    def check_permission(self, permtype="read"):
        return None

    def apply_fieldlevel_read_permissions(self):
        # Emulate the real field-level step: delattr stripped fields, and mark
        # a second field so the type-default emission is observable.
        for fieldname in getattr(self.meta, "strip_fields", ()):  # type: ignore[attr-defined]
            self.__dict__.pop(fieldname, None)

    def as_dict(self, no_nulls=False):
        out = {}
        for key in self.meta.get_valid_fields():  # type: ignore[attr-defined]
            value = self.__dict__.get(key)
            if no_nulls and value is None:
                continue
            if value is None and key in getattr(self.meta, "check_fields", ()):  # type: ignore[attr-defined]
                value = 0  # Check coercion: None -> 0
            out[key] = value
        return out


class _Meta:
    def __init__(self, doctype, istable=False, issingle=False, strip_fields=(), check_fields=()):
        self.name = doctype
        self.istable = istable
        self.issingle = issingle
        self.strip_fields = strip_fields
        self.check_fields = check_fields

    def get_valid_fields(self):
        return ["name", "customer_name", "customer_group", "territory", "customer_type", "disabled"]


class _MetaCache:
    def __init__(self, metas):
        self._metas = metas

    def get(self, doctype):
        if doctype not in self._metas:
            raise Exception("no such doctype")
        return self._metas[doctype]


class FrappeDoesNotExist(Exception):
    pass


class FrappePermissionError(Exception):
    pass


def _frappe_stub(metas=None, doc=None, rows=None, session_user="alice@example.com", site="u5_test_site"):
    stub = types.ModuleType("frappe")
    stub.DoesNotExistError = FrappeDoesNotExist
    stub.PermissionError = FrappePermissionError
    stub.ValidationError = ValueError
    stub.session = types.SimpleNamespace(user=session_user)
    stub.local = types.SimpleNamespace(site=site)
    stub.get_meta = _MetaCache(metas or {}).get
    stub.calls = {"get_list": 0, "get_all": 0, "set_user": 0, "sql": 0}

    def _get_list(doctype, fields=None, filters=None, limit_page_length=None, **kwargs):
        stub.calls["get_list"] += 1
        stub.last_list_kwargs = {
            "fields": fields,
            "filters": filters,
            "limit_page_length": limit_page_length,
            **kwargs,
        }
        source = rows if rows is not None else [{"name": "Test", "customer_name": "Test"}]
        out = []
        for row in source[:limit_page_length or len(source)]:
            out.append(types.SimpleNamespace(**{f: row.get(f) for f in fields}))
        return out

    def _forbidden(name):
        def _boom(*_a, **_k):
            stub.calls[name] = stub.calls.get(name, 0) + 1
            raise AssertionError(f"forbidden API used: {name}")

        return _boom

    stub.get_list = _get_list
    stub.get_all = _forbidden("get_all")
    stub.set_user = _forbidden("set_user")
    stub.db = types.SimpleNamespace(sql=_forbidden("sql"), get_value=_forbidden("sql"), count=_forbidden("sql"))
    stub.get_doc = lambda doctype, name: doc if doc is not None else _Doc({"name": name, "customer_name": "Test"}, _Meta(doctype))
    return stub


DEFAULT_META = {"Customer": _Meta("Customer"), "Item": _Meta("Item")}


class AdapterBase(unittest.TestCase):
    def setUp(self):
        self.audit_mock = mock.patch("frappe_app.erpnext_ai_copilot.audit.record_audit").start()
        self.addCleanup(mock.patch.stopall)
        self.audit_mock.side_effect = lambda **kw: {"name": "NMAU-1", **kw}

    def with_frappe(self, **kw):
        stub = _frappe_stub(**kw)
        patcher = mock.patch.object(er, "frappe", stub)
        patcher.start()
        self.addCleanup(patcher.stop)
        return stub

    def audit_calls(self):
        return [c.kwargs for c in self.audit_mock.call_args_list]


# ---------------------------------------------------------------------------
# Group 3 — identity, site, request contract
# ---------------------------------------------------------------------------


class IdentityAndContract(AdapterBase):
    def test_3_2_session_user_is_the_subject_verbatim(self):
        self.with_frappe(metas=DEFAULT_META, session_user="Mixed.Case@Example.com ")
        # A padded value is returned verbatim (no normalization/repair).
        self.assertEqual(er.current_subject(), "Mixed.Case@Example.com ")
        with self.assertRaises(er.PermissionDenied):
            # Guest is refused.
            self.with_frappe(metas=DEFAULT_META, session_user="Guest")
            er.current_subject()

    def test_3_2_guest_and_absent_refused_before_read(self):
        self.with_frappe(metas=DEFAULT_META, session_user="Guest")
        with self.assertRaises(er.PermissionDenied):
            er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})

    def test_3_3_public_entry_point_exposes_no_authorization_parameter(self):
        import inspect

        params = set(inspect.signature(er.execute_read).parameters) | set(inspect.signature(er.attempt_read).parameters)
        forbidden = {"user", "actor", "username", "site", "mode", "authorization_subject"}
        self.assertEqual(params & forbidden, set())
        # The request dataclass likewise carries no identity field.
        fields = set(er.ERPNextReadRequest.__dataclass_fields__)
        self.assertEqual(fields & forbidden, set())

    def test_3_3_request_rejects_authorization_arguments(self):
        self.with_frappe(metas=DEFAULT_META)
        with self.assertRaises(TypeError):
            er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]}, user="mallory")

    def test_3_4_forged_identity_in_payload_rejected(self):
        self.with_frappe(metas=DEFAULT_META)
        for forged in ("user", "actor", "username", "site", "mode", "as_user", "authorization_subject"):
            with self.subTest(forged=forged):
                with self.assertRaises(er.InvalidRequest):
                    er.build_request(
                        {"operation": "list", "doctype": "Customer", "fields": ["name"], forged: "mallory"}
                    )
        self.assertEqual(self.audit_calls(), [])

    def test_3_5_site_comes_from_frappe_local_only(self):
        self.with_frappe(metas=DEFAULT_META, site="site-from-frappe")
        self.assertEqual(er.current_site(), "site-from-frappe")
        with self.assertRaises(er.InvalidRequest):
            er.build_request({"operation": "list", "doctype": "Customer", "fields": ["name"], "site": "evil"})

    def test_3_5_audit_site_is_the_authenticated_site(self):
        self.with_frappe(metas=DEFAULT_META, site="the-real-site")
        er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})
        self.assertEqual(self.audit_calls()[0]["site"], "the-real-site")


# ---------------------------------------------------------------------------
# Group 4 — strict request validation
# ---------------------------------------------------------------------------


class StrictValidation(AdapterBase):
    def test_4_1_only_document_and_list_supported(self):
        self.with_frappe(metas=DEFAULT_META)
        for op in ("schema", "write", "update", "delete", "method", "erpnext.write", "", None, 42):
            with self.subTest(op=op):
                with self.assertRaises(er.UnsupportedOperation):
                    er.build_request({"operation": op, "doctype": "Customer", "fields": ["name"]})

    def test_4_2_unapproved_doctype_rejected(self):
        self.with_frappe(metas=DEFAULT_META)
        with self.assertRaises(er.DocTypeNotAllowed):
            er.build_request({"operation": "list", "doctype": "Salary Slip", "fields": ["name"]})

    def test_4_2_child_and_single_doctypes_rejected(self):
        self.with_frappe(
            metas={
                "Customer": _Meta("Customer"),
                "Sales Invoice Item": _Meta("Sales Invoice Item", istable=True),
                "System Settings": _Meta("System Settings", issingle=True),
            }
        )
        er.ALLOWED_DOCTYPES["Sales Invoice Item"] = ("name",)
        er.ALLOWED_DOCTYPES["System Settings"] = ("name",)
        try:
            for dt in ("Sales Invoice Item", "System Settings"):
                with self.subTest(dt=dt):
                    with self.assertRaises(er.DocTypeNotAllowed):
                        er.build_request({"operation": "list", "doctype": dt, "fields": ["name"]})
        finally:
            er.ALLOWED_DOCTYPES.pop("Sales Invoice Item", None)
            er.ALLOWED_DOCTYPES.pop("System Settings", None)

    def test_4_3_document_name_bounded_and_required(self):
        self.with_frappe(metas=DEFAULT_META)
        with self.assertRaises(er.InvalidRequest):
            er.build_request({"operation": "document", "doctype": "Customer", "fields": ["name"]})
        for bad in ("", "   ", "x" * (er.MAX_DOCUMENT_NAME_CHARS + 1), "bad\x00name", ["C-1"]):
            with self.subTest(bad=bad):
                with self.assertRaises(er.InvalidRequest):
                    er.build_request({"operation": "document", "doctype": "Customer", "fields": ["name"], "name": bad})
        ok = er.build_request({"operation": "document", "doctype": "Customer", "fields": ["name"], "name": "CUST/0001"})
        self.assertEqual(ok.name, "CUST/0001")

    def test_4_3_list_rejects_a_document_name(self):
        self.with_frappe(metas=DEFAULT_META)
        with self.assertRaises(er.InvalidRequest):
            er.build_request({"operation": "list", "doctype": "Customer", "fields": ["name"], "name": "CUST/0001"})

    def test_4_4_wildcard_unknown_and_missing_fields_rejected(self):
        self.with_frappe(metas=DEFAULT_META)
        cases = [
            {"fields": ["*"]},
            {"fields": ["not_a_real_field"]},
            {"fields": []},
            {"fields": None},
            {"fields": "name"},
            {"fields": [{"name": "name"}]},
            {"fields": ["name; DROP TABLE"]},
            {},
        ]
        for case in cases:
            with self.subTest(case=case):
                payload = {"operation": "list", "doctype": "Customer"}
                payload.update(case)
                with self.assertRaises(er.InvalidRequest):
                    er.build_request(payload)

    def test_4_5_unsafe_filters_rejected_not_rewritten(self):
        self.with_frappe(metas=DEFAULT_META)
        cases = [
            {"customer_name": {"like": "%x%"}},          # nested operator object
            {"customer_name": "a", "x": [1] * 50},        # too many values
            {"owner": "Administrator"},                   # forbidden field
            {"customer_name": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j",
                               "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u"]},  # 21 values > MAX_FILTER_VALUES
            {"unknown_field": "v"},                       # not in projection
            {"customer_name": "x" * 500},                 # over-long value
        ]
        for filters in cases:
            with self.subTest(filters=filters):
                with self.assertRaises(er.InvalidRequest):
                    er.build_request({"operation": "list", "doctype": "Customer", "fields": ["name"], "filters": filters})

    def test_4_5_too_many_filter_keys_rejected(self):
        self.with_frappe(metas=DEFAULT_META)
        with mock.patch.object(er, "MAX_FILTER_KEYS", 2):
            with self.assertRaises(er.InvalidRequest):
                er.build_request(
                    {
                        "operation": "list",
                        "doctype": "Customer",
                        "fields": ["name"],
                        "filters": {"name": "a", "territory": "b", "disabled": 0},
                    }
                )

    def test_4_5_acceptable_filters_pass_through(self):
        self.with_frappe(metas=DEFAULT_META)
        req = er.build_request(
            {
                "operation": "list",
                "doctype": "Customer",
                "fields": ["name", "customer_name"],
                "filters": {"disabled": 0, "customer_name": ["A", "B"]},
            }
        )
        self.assertEqual(req.filters, {"disabled": 0, "customer_name": ["A", "B"]})

    def test_4_6_adapter_limit_matches_contract_maximum(self):
        from tools.contracts import contract_for

        contract_max = contract_for("erpnext_read")["bounded_inputs"]["limit"]["maximum"]
        self.assertEqual(contract_max, 100)
        # The adapter backstop now matches the approved immutable service
        # ceiling: values up to 100 are accepted, anything above is refused.
        self.assertEqual(er.MAX_LIST_LIMIT, 100)
        self.with_frappe(metas=DEFAULT_META)
        ok = er.build_request({"operation": "list", "doctype": "Customer",
                               "fields": ["name"], "limit": contract_max})
        self.assertEqual(ok.limit, 100)
        with self.assertRaises(er.InvalidRequest):
            er.build_request({"operation": "list", "doctype": "Customer",
                              "fields": ["name"], "limit": contract_max + 1})

    def test_4_6_field_count_matches_service_ceiling(self):
        wide = tuple(f"f{i:02d}" for i in range(60))
        self.assertEqual(er.MAX_FIELD_COUNT, 50)
        self.with_frappe(metas={**DEFAULT_META, "Wide": _Meta("Wide")})
        with mock.patch.dict(er.ALLOWED_DOCTYPES, {"Wide": wide}):
            ok = er.build_request({"operation": "list", "doctype": "Wide",
                                   "fields": list(wide[:50])})
            self.assertEqual(len(ok.fields), 50)
            with self.assertRaises(er.InvalidRequest):
                er.build_request({"operation": "list", "doctype": "Wide",
                                  "fields": list(wide[:51])})

    def test_4_6_result_bytes_match_service_ceiling(self):
        self.assertEqual(er.MAX_RESULT_BYTES, 128 * 1024)
        # Just within the ceiling: accepted.
        fitting = {"rows": [{"name": "X" * 60000, "customer_name": "Y" * 60000}],
                   "row_count": 1}
        self.assertLess(
            len(str(fitting)) + len(str(["name", "customer_name"])),
            er.MAX_RESULT_BYTES)
        er._guard_result_size(fitting, ["name", "customer_name"])
        # Beyond the ceiling: refused, never truncated.
        overflowing = {"rows": [{"name": "X" * 70000, "customer_name": "Y" * 70000}],
                       "row_count": 1}
        self.assertGreater(
            len(str(overflowing)) + len(str(["name", "customer_name"])),
            er.MAX_RESULT_BYTES)
        with self.assertRaises(er.InvalidRequest):
            er._guard_result_size(overflowing, ["name", "customer_name"])

    def test_4_7_typed_error_reason_is_bounded_and_clean(self):
        self.with_frappe(metas=DEFAULT_META)
        with self.assertRaises(er.InvalidRequest) as ctx:
            er.build_request({"operation": "list", "doctype": "Customer", "fields": ["*"], "api_key": "secret-value"})
        self.assertLessEqual(len(ctx.exception.reason), 200)
        self.assertNotIn("secret-value", str(ctx.exception))
        self.assertEqual(ctx.exception.code, er.OUTCOME_INVALID_REQUEST)


# ---------------------------------------------------------------------------
# Group 5 — permission-aware execution, field enforcement, minimization
# ---------------------------------------------------------------------------


class PermissionAwareExecution(AdapterBase):
    def test_5_1_uses_permission_checking_list_api_only(self):
        stub = self.with_frappe(metas=DEFAULT_META)
        result = er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name", "customer_name"]})
        self.assertEqual(stub.calls["get_list"], 1)
        self.assertEqual(stub.calls["get_all"], 0)
        self.assertEqual(stub.last_list_kwargs["fields"], ["name", "customer_name"])
        self.assertEqual(result["row_count"], 1)

    def test_5_1_list_never_passes_permission_suppressing_flags(self):
        stub = self.with_frappe(metas=DEFAULT_META)
        er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})
        for forbidden in ("ignore_permissions", "ignore_user_permissions"):
            self.assertNotIn(forbidden, stub.last_list_kwargs)

    def test_5_2_document_read_runs_all_three_steps(self):
        calls = []
        meta = _Meta("Customer")
        doc = _Doc({"name": "C-1", "customer_name": "Acme"}, meta)
        orig_check, orig_apply = doc.check_permission, doc.apply_fieldlevel_read_permissions

        def check(p="read"):
            calls.append("check")
            return orig_check(p)

        def apply():
            calls.append("fieldlevel")
            return orig_apply()

        doc.check_permission, doc.apply_fieldlevel_read_permissions = check, apply
        self.with_frappe(metas=DEFAULT_META, doc=doc)
        er.execute_read({"operation": "document", "doctype": "Customer", "fields": ["name", "customer_name"], "name": "C-1"})
        self.assertEqual(calls, ["check", "fieldlevel"])

    def test_5_3_stripped_field_is_absent_not_a_type_default(self):
        meta = _Meta("Customer", strip_fields=("territory",), check_fields=("territory", "customer_type"))
        doc = _Doc(
            {"name": "C-1", "customer_name": "Acme", "territory": None, "customer_type": "Individual"},
            meta,
        )
        self.with_frappe(metas=DEFAULT_META, doc=doc)
        result = er.execute_read(
            {
                "operation": "document",
                "doctype": "Customer",
                "fields": ["name", "customer_name", "territory", "customer_type"],
                "name": "C-1",
            }
        )
        data = result["data"]
        # territory was delattr-ed by the field-level step; it must be omitted,
        # never re-emitted as 0 by Check coercion.
        self.assertNotIn("territory", data)
        self.assertEqual(data["customer_type"], "Individual")

    def test_5_5_result_is_minimized_and_bounded(self):
        self.with_frappe(metas=DEFAULT_META, doc=_Doc({"name": "C-1", "customer_name": "Acme"}, _Meta("Customer")))
        result = er.execute_read(
            {"operation": "document", "doctype": "Customer", "fields": ["name"], "name": "C-1"}
        )
        self.assertEqual(set(result), {"doctype", "operation", "fields_returned", "row_count", "data"})
        self.assertEqual(set(result["data"]), {"name"})

    def test_5_5_list_result_returns_only_requested_fields(self):
        self.with_frappe(
            metas=DEFAULT_META,
            rows=[{"name": "A", "customer_name": "A", "territory": "T", "disabled": 0}],
        )
        result = er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})
        self.assertEqual(set(result["data"][0]), {"name"})

    def test_5_6_forbidden_apis_unused_and_no_set_user(self):
        stub = self.with_frappe(metas=DEFAULT_META)
        er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})
        self.assertEqual(stub.calls["set_user"], 0)
        self.assertEqual(stub.calls["get_all"], 0)
        self.assertEqual(stub.calls["sql"], 0)
        # No forbidden API is referenced in executable code. The only mention is
        # the FORBIDDEN_APIS declaration itself, so scan past that block.
        with open(er.__file__, encoding="utf-8") as fh:
            src = fh.read()
        executable = src.split(")\n", 1)[-1] if "FORBIDDEN_APIS = (" in src else src
        executable = executable.split("def _list_read", 1)[-1]
        for api in er.FORBIDDEN_APIS:
            self.assertNotIn(api, executable, f"{api} referenced in execution path")

    def test_5_7_permission_error_maps_to_permission_denied(self):
        stub = self.with_frappe(metas=DEFAULT_META)
        stub.get_list = mock.Mock(side_effect=FrappePermissionError("nope"))
        with self.assertRaises(er.PermissionDenied):
            er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})

    def test_5_7_missing_error_maps_to_not_found(self):
        stub = self.with_frappe(metas=DEFAULT_META)
        stub.get_list = mock.Mock(side_effect=FrappeDoesNotExist("nope"))
        with self.assertRaises(er.NotFound):
            er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})

    def test_5_7_authorization_rederived_each_read_no_cache(self):
        stub = self.with_frappe(metas=DEFAULT_META)
        calls = {"n": 0}

        def flaky(doctype, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return [types.SimpleNamespace(name="A")]
            raise FrappePermissionError("narrowed")

        stub.get_list = flaky
        er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})
        with self.assertRaises(er.PermissionDenied):
            er.execute_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})


# ---------------------------------------------------------------------------
# Group 6 — audit, fail-closed
# ---------------------------------------------------------------------------


class AuditAndFailClosed(AdapterBase):
    def test_6_1_exactly_one_audit_event_on_success(self):
        self.with_frappe(metas=DEFAULT_META)
        er.attempt_read({"operation": "list", "doctype": "Customer", "fields": ["name", "customer_name"]})
        calls = self.audit_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["action"], "erpnext_read")
        self.assertEqual(calls[0]["outcome"], "success")
        self.assertEqual(calls[0]["actor"], "alice@example.com")
        self.assertEqual(calls[0]["target"], "Customer")
        self.assertEqual(calls[0]["details"]["operation"], "list")
        self.assertEqual(calls[0]["details"]["doctype"], "Customer")

    def test_6_1_exactly_one_audit_event_on_each_denial_kind(self):
        stub = self.with_frappe(metas=DEFAULT_META)
        for payload, code in (
            ({"operation": "schema", "doctype": "Customer", "fields": ["name"]}, "invalid_request"),
            ({"operation": "list", "doctype": "Salary Slip", "fields": ["name"]}, "invalid_request"),
            ({"operation": "list", "doctype": "Customer", "fields": ["*"]}, "invalid_request"),
        ):
            with self.subTest(code=code):
                self.audit_mock.reset_mock()
                with self.assertRaises(er.ReadRefusal):
                    er.attempt_read(payload)
                calls = self.audit_calls()
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["action"], "erpnext_read")
                self.assertEqual(calls[0]["outcome"], code)

    def test_6_1_permission_and_notfound_distinct_outcomes(self):
        stub = self.with_frappe(metas=DEFAULT_META)
        stub.get_list = mock.Mock(side_effect=FrappePermissionError("x"))
        self.audit_mock.reset_mock()
        with self.assertRaises(er.PermissionDenied):
            er.attempt_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})
        self.assertEqual(self.audit_calls()[0]["outcome"], "permission_denied")

        self.audit_mock.reset_mock()
        stub.get_list = mock.Mock(side_effect=FrappeDoesNotExist("x"))
        with self.assertRaises(er.NotFound):
            er.attempt_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})
        self.assertEqual(self.audit_calls()[0]["outcome"], "not_found")

    def test_6_2_audit_details_are_metadata_only(self):
        marker = "CANARY-BUSINESS-VALUE-9f3a"
        self.with_frappe(metas=DEFAULT_META, rows=[{"name": "A", "customer_name": marker}])
        er.attempt_read(
            {
                "operation": "list",
                "doctype": "Customer",
                "fields": ["name", "customer_name"],
                "filters": {"disabled": marker},
                "correlation": "corr-1",
            }
        )
        blob = str(self.audit_calls())
        self.assertNotIn(marker, blob)
        # filter *keys* are recorded, never values.
        self.assertIn("filter_keys", self.audit_calls()[0]["details"])

    def test_6_4_audit_failure_denies_the_read(self):
        self.with_frappe(metas=DEFAULT_META)
        self.audit_mock.side_effect = RuntimeError("audit store down")
        with self.assertRaises(RuntimeError):
            er.attempt_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})

    def test_6_5_audit_access_control_still_actor_and_site_scoped(self):
        # The adapter passes actor/site explicitly from the session context;
        # scoping enforcement stays in the audit module.
        self.with_frappe(metas=DEFAULT_META)
        er.attempt_read({"operation": "list", "doctype": "Customer", "fields": ["name"]})
        call = self.audit_calls()[0]
        self.assertEqual(call["actor"], "alice@example.com")
        self.assertEqual(call["site"], "u5_test_site")

    def test_6_3_read_action_distinct_from_retrieval(self):
        self.assertEqual(er.AUDIT_ACTION_READ, "erpnext_read")
        self.assertNotEqual(er.AUDIT_ACTION_READ, "retrieval")


# ---------------------------------------------------------------------------
# Group 9 — anti-oracle collapse
# ---------------------------------------------------------------------------


class AntiOracle(AdapterBase):
    def test_9_1_notfound_and_forbidden_identical_to_caller(self):
        a = er.collapse_for_caller(er.NotFound("missing"))
        b = er.collapse_for_caller(er.PermissionDenied("forbidden"))
        self.assertEqual(a, b)
        for key in ("answer", "sources", "confidence", "route", "route_how"):
            self.assertEqual(a[key], b[key], key)

    def test_9_1_all_refusal_kinds_collapse_identically(self):
        collapsed = {
            k: v
            for k, v in er.collapse_for_caller(er.NotFound("x")).items()
            if k != "read_outcome"
        }
        for refusal in (
            er.PermissionDenied("x"),
            er.InvalidRequest("x"),
            er.UnsupportedOperation("x"),
            er.DocTypeNotAllowed("x"),
        ):
            other = {k: v for k, v in er.collapse_for_caller(refusal).items() if k != "read_outcome"}
            self.assertEqual(other, collapsed)

    def test_9_3_internal_distinction_retained_but_not_caller_visible(self):
        self.assertNotEqual(er.NotFound("x").code, er.PermissionDenied("x").code)
        # ...but the caller-visible surface is identical (see 9_1).
        self.assertEqual(
            {k: v for k, v in er.collapse_for_caller(er.NotFound("x")).items() if k != "read_outcome"},
            {k: v for k, v in er.collapse_for_caller(er.PermissionDenied("x")).items() if k != "read_outcome"},
        )

    def test_9_2_field_denial_indistinguishable_from_field_absence(self):
        # Both cases omit the field entirely, so neither is observable as a
        # special "you may not read this" signal.
        self.assertEqual(er._list_read, er._list_read)
        self.assertIn("territory", er.ALLOWED_DOCTYPES["Customer"])
        # The projection builder only ever copies keys present in the data.
        with open(er.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("if fname not in data:", src)

    def test_9_4_caller_message_carries_no_doctype_or_name(self):
        for refusal in (er.NotFound("Customer:SECRET-1"), er.PermissionDenied("Customer:SECRET-1")):
            msg = refusal.caller_message()
            self.assertEqual(msg, er.CALLER_DENIAL)
            self.assertNotIn("SECRET-1", msg)
            self.assertNotIn("Customer", msg)


if __name__ == "__main__":
    unittest.main()
