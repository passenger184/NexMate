"""Unit tests for Phase 8 guarded writes (tools/erpnext_write).

Run: .venv/bin/python -m unittest discover -s tests -v

Transport mocked; the live instance is never touched here.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import erpnext, erpnext_write

SCHEMA = {"data": {
    "doctype": "ToDo",
    "fields": [{"fieldname": "description", "fieldtype": "Text"},
               {"fieldname": "priority", "fieldtype": "Select"}],
}}


class WriteTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        audit_log = self.root / "audit.jsonl"
        patches = [
            # patch the REAL config module attributes — that is exactly
            # where tools/erpnext_write reads them at call time
            mock.patch("config.ERPNEXT_WRITE_ENABLED", True),
            mock.patch("config.ERPNEXT_ENV_LABEL", "staging"),
            mock.patch("config.ERPNEXT_WRITE_AUDIT_LOG", audit_log),
            mock.patch.dict("os.environ", {
                "ERPNEXT_BASE_URL": "http://erp.test:8081",
                "ERPNEXT_API_KEY": "k",
                "ERPNEXT_API_SECRET": "s"}),
            mock.patch.object(erpnext, "get_doctype_schema",
                              return_value=SCHEMA),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.audit_path = audit_log

    def propose(self, **kw) -> dict:
        defaults = dict(action="create", doctype="ToDo",
                        payload={"description": "test"},
                        reason="verify the guarded write flow")
        defaults.update(kw)
        return erpnext_write.propose_write(**defaults)


class TestProposeGates(WriteTestBase):
    def test_disabled_by_default_refuses(self) -> None:
        with mock.patch("config.ERPNEXT_WRITE_ENABLED", False):
            with self.assertRaises(erpnext_write.WriteRefusal) as ctx:
                self.propose()
        self.assertEqual(ctx.exception.category, "writes_disabled")

    def test_delete_is_not_an_action(self) -> None:
        with self.assertRaises(erpnext_write.WriteRefusal) as ctx:
            self.propose(action="delete")
        self.assertEqual(ctx.exception.category, "unsupported_action")
        self.assertIn("delete is deliberately not implemented",
                      ctx.exception.detail)

    def test_unknown_fields_refused_before_any_http(self) -> None:
        with mock.patch.object(erpnext.requests,
                               "request") as should_not_send:
            with self.assertRaises(erpnext_write.WriteRefusal) as ctx:
                self.propose(payload={"descirption_typo": "x"})
        should_not_send.assert_not_called()
        self.assertIn("descirption_typo", ctx.exception.detail)

    def test_update_requires_name(self) -> None:
        with self.assertRaises(erpnext_write.WriteRefusal) as ctx:
            self.propose(action="update")
        self.assertEqual(ctx.exception.category, "bad_request")

    def test_short_reason_refused(self) -> None:
        with self.assertRaises(erpnext_write.WriteRefusal) as ctx:
            self.propose(reason="because")
        self.assertEqual(ctx.exception.category, "bad_reason")


class TestApplyFlow(WriteTestBase):
    def test_apply_requires_explicit_confirmation(self) -> None:
        proposal = self.propose()
        with self.assertRaises(erpnext_write.WriteRefusal) as ctx:
            erpnext_write.apply_write(proposal["proposal_id"],
                                      confirmed=False)
        self.assertEqual(ctx.exception.category, "confirmation_required")

    def test_create_happy_path_posts_and_audits(self) -> None:
        proposal = self.propose()
        captured = {}

        def fake_request(method, url, headers=None, data=None,
                         timeout=None):
            captured.update(method=method, url=url, headers=headers,
                            body=json.loads(data))
            resp = mock.Mock()
            resp.status_code = 200
            resp.content = b'{"data":{"name":"a1b2"}}'
            resp.json.return_value = {"data": {"name": "a1b2"}}
            return resp

        with mock.patch.object(erpnext_write.requests, "request",
                               side_effect=fake_request):
            result = erpnext_write.apply_write(proposal["proposal_id"],
                                               confirmed=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["name"], "a1b2")
        self.assertTrue(result["audited"])
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"],
                         "http://erp.test:8081/api/resource/ToDo")
        self.assertEqual(captured["headers"]["Authorization"], "token k:s")
        self.assertEqual(captured["body"], {"description": "test"})
        lines = Path(self.audit_path).read_text().splitlines()
        entry = json.loads(lines[-1])
        self.assertEqual(entry["doctype"], "ToDo")
        self.assertEqual(entry["result_name"], "a1b2")
        self.assertEqual(entry["env_label"], "staging")

    def test_update_uses_put_with_name_segment(self) -> None:
        proposal = self.propose(action="update", name="a1b2",
                                payload={"priority": "High"})
        captured = {}

        def fake_request(method, url, **kwargs):
            captured.update(method=method, url=url)
            resp = mock.Mock()
            resp.status_code = 200
            resp.content = b'{"data":{"name":"a1b2"}}'
            resp.json.return_value = {"data": {"name": "a1b2"}}
            return resp

        with mock.patch.object(erpnext_write.requests, "request",
                               side_effect=fake_request):
            erpnext_write.apply_write(proposal["proposal_id"],
                                      confirmed=True)
        self.assertEqual(captured["method"], "PUT")
        self.assertEqual(captured["url"],
                         "http://erp.test:8081/api/resource/ToDo/a1b2")

    def test_proposal_one_shot(self) -> None:
        proposal = self.propose()
        with mock.patch.object(erpnext_write.requests, "request",
                               return_value=self._ok_response()):
            erpnext_write.apply_write(proposal["proposal_id"],
                                      confirmed=True)
        with self.assertRaises(erpnext_write.WriteRefusal) as ctx:
            erpnext_write.apply_write(proposal["proposal_id"],
                                      confirmed=True)
        self.assertEqual(ctx.exception.category, "unknown_proposal")

    def _ok_response(self):
        resp = mock.Mock()
        resp.status_code = 200
        resp.content = b'{"data":{"name":"n1"}}'
        resp.json.return_value = {"data": {"name": "n1"}}
        return resp

    def test_flag_rechecked_at_apply_time(self) -> None:
        proposal = self.propose()
        with mock.patch("config.ERPNEXT_WRITE_ENABLED", False):
            with self.assertRaises(erpnext_write.WriteRefusal) as ctx:
                erpnext_write.apply_write(proposal["proposal_id"],
                                          confirmed=True)
        self.assertEqual(ctx.exception.category, "writes_disabled")


if __name__ == "__main__":
    unittest.main()
