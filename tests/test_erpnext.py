"""Unit tests for tools.erpnext (Phase 5 read-only live-API client).

Run: .venv/bin/python -m unittest discover -s tests -v

Transport mocked: these pin URL construction/quoting, auth handling,
limit caps, and error mapping. The live instance is exercised separately
in manual verification.
"""

import json
import os
import unittest
from unittest import mock

import config
from tools import erpnext


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else "err"
        self.content = self.text.encode()

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class ErpnextClientTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict("os.environ", {
            "ERPNEXT_BASE_URL": "http://erp.test:8081",
            "ERPNEXT_API_KEY": "k",
            "ERPNEXT_API_SECRET": "s",
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_credentials_fail_loud(self) -> None:
        for key in ("ERPNEXT_BASE_URL", "ERPNEXT_API_KEY",
                    "ERPNEXT_API_SECRET"):
            os.environ.pop(key, None)
        with self.assertRaises(erpnext.ErpnextUnavailable):
            erpnext.get_doctype_schema("Customer")

    def test_schema_builds_quoted_url_and_auth_header(self) -> None:
        captured = {}

        def fake_get(url, params=None, headers=None, timeout=None):
            captured.update(url=url, headers=headers)
            return FakeResponse(payload={"data": {"name": "Customer"}})

        with mock.patch.object(erpnext.requests, "get",
                               side_effect=fake_get):
            result = erpnext.get_doctype_schema("Sales Invoice")

        self.assertEqual(captured["url"],
                         "http://erp.test:8081/api/resource/DocType/Sales%20Invoice")
        self.assertEqual(captured["headers"]["Authorization"], "token k:s")
        self.assertEqual(result["data"]["name"], "Customer")

    def test_document_quotes_both_segments(self) -> None:
        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            return FakeResponse(payload={"data": {"name": "CUST/001"}})

        with mock.patch.object(erpnext.requests, "get",
                               side_effect=fake_get):
            erpnext.get_document("Customer", "CUST/001")
        self.assertEqual(
            captured["url"],
            "http://erp.test:8081/api/resource/Customer/CUST%2F001")

    def test_traversal_in_doctype_is_escaped_not_followed(self) -> None:
        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            return FakeResponse(payload={"data": {}})

        with mock.patch.object(erpnext.requests, "get",
                               side_effect=fake_get):
            erpnext.get_doctype_schema("../../admin")
        self.assertNotIn("/api/admin", captured["url"])

    def test_list_serializes_filters_fields_and_caps_limit(self) -> None:
        captured = {}

        def fake_get(url, params=None, **kwargs):
            captured["params"] = params
            return FakeResponse(payload={"data": [{"name": "X"}]})

        with mock.patch.object(erpnext.requests, "get",
                               side_effect=fake_get):
            result = erpnext.list_documents(
                "Sales Order", filters={"docstatus": 1},
                fields=["name", "total"], limit=9999)

        self.assertEqual(json.loads(captured["params"]["filters"]),
                         {"docstatus": 1})
        self.assertEqual(json.loads(captured["params"]["fields"]),
                         ["name", "total"])
        self.assertEqual(captured["params"]["limit_page_length"],
                         config.ERPNEXT_MAX_LIST_LIMIT)
        self.assertEqual(result["count"], 1)

    def test_non200_raises_with_status(self) -> None:
        with mock.patch.object(
                erpnext.requests, "get",
                return_value=FakeResponse(status=404,
                                          payload={"_server_messages":
                                                   "not found"})):
            with self.assertRaises(erpnext.ErpnextApiError) as ctx:
                erpnext.get_document("Customer", "NOPE")
        self.assertEqual(ctx.exception.status, 404)

    def test_client_is_read_only_by_construction(self) -> None:
        public = [n for n in dir(erpnext) if not n.startswith("_")]
        for verb in ("post", "put", "delete", "patch"):
            self.assertNotIn(verb, [p.lower() for p in public])


if __name__ == "__main__":
    unittest.main()
