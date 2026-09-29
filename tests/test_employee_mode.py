"""Unit tests for Phase 7 employee mode restrictions.

Run: .venv/bin/python -m unittest discover -s tests -v
"""

import unittest
from unittest import mock

import orchestrator
from rag.generator import PERSONAS


# Pinned NLU decision: these tests assert downstream wiring (denials,
# personas, retrieval scoping), not model output, so routing tests must
# not depend on a live LLM.
_TASK_NLU = {"kind": "task", "subtype": None, "topic": None,
             "context_dependency": "none", "confidence": 0.9}


class EmployeeModeTest(unittest.TestCase):
    def test_employee_persona_exists_and_differs(self) -> None:
        self.assertIn("employee", PERSONAS)
        self.assertIn("NOT a developer", PERSONAS["employee"])
        self.assertIn("developer", PERSONAS)

    def test_code_route_denied_for_employees(self) -> None:
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(_TASK_NLU)), \
            mock.patch.object(orchestrator, "decide_route",
                               return_value=("code", "heuristic")):
            out = orchestrator.handle_question(
                "Why does pathsafe raise on symlinks?", mode="employee")
        self.assertEqual(out["route_how"], "heuristic+denied")
        self.assertEqual(out["confidence"], "low")
        self.assertIn("employee mode", out["answer"])

    def test_listing_still_denied_for_employees(self) -> None:
        # The deterministic listing shortcut sits BEHIND the employee
        # denial: least privilege wins over convenience.
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(_TASK_NLU)), \
            mock.patch.object(orchestrator, "decide_route",
                               return_value=("code", "heuristic")):
            out = orchestrator.handle_question(
                "what files are inside the project", mode="employee")
        self.assertEqual(out["route_how"], "heuristic+denied")
        self.assertEqual(out["confidence"], "low")

    def test_code_route_still_works_for_developers(self) -> None:
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(_TASK_NLU)), \
            mock.patch.object(orchestrator, "decide_route",
                               return_value=("code", "heuristic")), \
                mock.patch.object(orchestrator.explain,
                                  "locate_and_explain",
                                  return_value={
                                      "located": True,
                                      "explanation": "it's in `f.py`",
                                      "sources": [
                                          {"path": "f.py",
                                           "line_start": 1,
                                           "line_end": 2}]}):
            out = orchestrator.handle_question(
                "why does f raise?", mode="developer")
        self.assertEqual(out["confidence"], "high")

    def test_schema_request_is_issued_for_employees_not_declined(self) -> None:
        """Inference makes NO capability decision for metadata.

        The employee schema short-circuit is removed: inference classifies and
        REQUESTS, and the Frappe control plane authorizes or refuses under the
        live session user's capability and the site's metadata policy. Declining
        here would make the policy unbindable and unauditable.
        """
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(_TASK_NLU)), \
            mock.patch.object(orchestrator, "decide_route",
                              return_value=("erpnext", "heuristic")), \
                mock.patch.object(
                    orchestrator, "_extract_erpnext_request",
                    return_value={"op": "schema", "doctype": "Customer"}):
            out = orchestrator.handle_question(
                "What fields does Customer have?", mode="employee")
        self.assertEqual(out["_read_request"],
                         {"kind": "schema", "doctype": "Customer"})
        self.assertEqual(out["route"], "erpnext")
        self.assertEqual(out["route_how"], "heuristic+read-requested")
        # A request, not a conversational decline: there is no answer at all.
        self.assertNotIn("answer", out)

    def test_document_list_allowed_for_employees(self) -> None:
        """U5: employees may read business data, via the Frappe-authorized path.

        The read is REQUESTED by inference and AUTHORIZED by Frappe. Mode does
        not change ERPNext authorization, so the same user gets the same
        authorized result in either mode.
        """
        extracted = {"op": "list", "doctype": "Customer", "limit": 20}
        authorized = {
            "doctype": "Customer", "operation": "list",
            "fields_returned": ["name", "customer_name"],
            "row_count": 0, "data": [],
        }
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(_TASK_NLU)), \
            mock.patch.object(orchestrator, "decide_route",
                               return_value=("erpnext", "heuristic")), \
                mock.patch.object(
                    orchestrator, "_extract_erpnext_request",
                    return_value=extracted), \
                mock.patch.object(orchestrator.generator, "_complete",
                                  return_value="You have none [1]."), \
                mock.patch.object(orchestrator, "get_instance_versions",
                                  return_value={"status": "unavailable",
                                                "frappe": "unknown",
                                                "erpnext": "unknown"}):
            # Leg 1: no ERPNext credential is used; a read is requested.
            request = orchestrator.handle_question(
                "Do I have any open ToDos?", mode="employee")
            self.assertIn("_read_request", request)
            self.assertEqual(request["_read_request"]["operation"], "list")
            # Leg 2: Frappe-produced authorized context is consumed.
            out = orchestrator.handle_question(
                "Do I have any open ToDos?", mode="employee",
                authorized_context=authorized)
            # Mode is not ERPNext authorization: identical result either way.
            out_dev = orchestrator.handle_question(
                "Do I have any open ToDos?", mode="developer",
                authorized_context=authorized)
        self.assertEqual(out["confidence"], "high")
        self.assertIn("[1]", out["answer"])
        self.assertEqual(out["confidence"], out_dev["confidence"])
        self.assertEqual(out["answer"], out_dev["answer"])

if __name__ == "__main__":
    unittest.main()
