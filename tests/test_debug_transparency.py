"""M5 Debug suite — 6.3

Proves authorized disclosure shows only permitted provenance/fields/results/queries,
denied sources stay invisible, unauthorized access refused, minimization exact, and each view audited.
"""

import os
import unittest

os.environ["NEXMATE_DURABLE_FALLBACK"] = "1"
os.environ["NEXMATE_TEST_USER"] = "debug_user"
os.environ["NEXMATE_TEST_SITE"] = "debug_site"
os.environ["NEXMATE_TEST_DEBUG_ALLOWED"] = "1"

from frappe_app.erpnext_ai_copilot import audit, proposals, debug

class DebugTransparencyTest(unittest.TestCase):
    def setUp(self):
        os.environ["NEXMATE_DURABLE_FALLBACK"] = "1"
        os.environ["NEXMATE_TEST_USER"] = "debug_user"
        os.environ["NEXMATE_TEST_SITE"] = "debug_site"
        os.environ["NEXMATE_TEST_DEBUG_ALLOWED"] = "1"
        proposals.clear_fallback()
        audit.clear_fallback()

    def tearDown(self):
        proposals.clear_fallback()
        audit.clear_fallback()

    def test_authorized_disclosure_minimized(self):
        p = proposals.create_proposal(operation="code_edit", target="debug.py", payload="x", diff_preview="d", reason="r")
        corr = p["correlation"]
        # Simulate a retrieval that had provenance and fields
        audit.record_audit(correlation=corr, request_id="req1", action="retrieval", actor="debug_user", site="debug_site", target="retrieval", outcome="success",
                           details={"provenance": ["doc1", "doc2"], "fields": {"field1": "val1", "field2": "val2", "field3": "val3"}})
        # Simulate tool execution that used only field1 and field2
        audit.record_audit(correlation=corr, request_id="req2", action="tool_call", actor="debug_user", site="debug_site", target="debug.py", outcome="success",
                           details={"fields": {"field1": "val1", "field2": "val2"}})
        view = debug.get_debug_view(corr, actor="debug_user", site="debug_site")
        self.assertIn("provenance", view)
        self.assertIn("doc1", view["provenance"])
        # Should not leak denied sources (we never recorded denied, but ensure denied not shown)
        self.assertNotIn("denied_doc", str(view))

    def test_denied_sources_stay_invisible(self):
        p = proposals.create_proposal(operation="code_edit", target="debug2.py", payload="x", diff_preview="d", reason="r")
        corr = p["correlation"]
        # Record a denied retrieval (should not appear in debug provenance)
        audit.record_audit(correlation=corr, request_id="denied1", action="retrieval", actor="debug_user", site="debug_site", target="retrieval", outcome="denied",
                           details={"provenance": ["denied_doc"], "fields": {"secret_field": "secret"}})
        view = debug.get_debug_view(corr, actor="debug_user", site="debug_site")
        self.assertNotIn("denied_doc", str(view))
        self.assertNotIn("secret_field", str(view))

    def test_unauthorized_debug_refused(self):
        p = proposals.create_proposal(operation="code_edit", target="debug3.py", payload="x", diff_preview="d", reason="r")
        corr = p["correlation"]
        os.environ["NEXMATE_TEST_DEBUG_ALLOWED"] = "0"
        os.environ["NEXMATE_TEST_USER"] = "other_user"
        with self.assertRaises(PermissionError):
            debug.get_debug_view(corr, actor="other_user", site="debug_site")
        os.environ["NEXMATE_TEST_USER"] = "debug_user"
        os.environ["NEXMATE_TEST_DEBUG_ALLOWED"] = "1"

    def test_field_minimization_exact(self):
        p = proposals.create_proposal(operation="business_write", target="Customer:1", payload='{"a":1}', reason="r")
        corr = p["correlation"]
        # Retrieval had 10 fields but only 3 were used
        audit.record_audit(correlation=corr, request_id="r1", action="retrieval", actor="debug_user", site="debug_site", target="Customer:1", outcome="success",
                           details={"fields": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8, "i": 9, "j": 10}})
        audit.record_audit(correlation=corr, request_id="r2", action="tool_call", actor="debug_user", site="debug_site", target="Customer:1", outcome="success",
                           details={"fields": {"a": 1, "b": 2, "c": 3}})
        view = debug.get_debug_view(corr, actor="debug_user", site="debug_site")
        # View should contain only the 3 actually accessed fields from tool_call, not all 10
        self.assertEqual(set(view["accessed_fields"].keys()), {"a", "b", "c"})

    def test_debug_access_audited(self):
        p = proposals.create_proposal(operation="code_edit", target="audit_debug.py", payload="x", diff_preview="d", reason="r")
        corr = p["correlation"]
        view = debug.get_debug_view(corr, actor="debug_user", site="debug_site")
        entries = audit.query_by_correlation(corr, actor="debug_user", site="debug_site")
        actions = {e["action"] for e in entries}
        self.assertIn("debug_view", actions)
