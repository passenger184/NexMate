"""Unit tests for Phase 7 employee mode restrictions.

Run: .venv/bin/python -m unittest discover -s tests -v
"""

import unittest
from unittest import mock

import orchestrator
from rag.generator import PERSONAS


class EmployeeModeTest(unittest.TestCase):
    def test_employee_persona_exists_and_differs(self) -> None:
        self.assertIn("employee", PERSONAS)
        self.assertIn("NOT a developer", PERSONAS["employee"])
        self.assertIn("developer", PERSONAS)

    def test_code_route_denied_for_employees(self) -> None:
        with mock.patch.object(orchestrator, "decide_route",
                               return_value=("code", "heuristic")):
            out = orchestrator.handle_question(
                "Why does pathsafe raise on symlinks?", mode="employee")
        self.assertEqual(out["route_how"], "heuristic+denied")
        self.assertEqual(out["confidence"], "low")
        self.assertIn("employee mode", out["answer"])

    def test_code_route_still_works_for_developers(self) -> None:
        with mock.patch.object(orchestrator, "decide_route",
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

    def test_schema_lookup_denied_for_employees(self) -> None:
        with mock.patch.object(orchestrator, "decide_route",
                               return_value=("erpnext", "heuristic")), \
                mock.patch.object(
                    orchestrator, "_extract_erpnext_request",
                    return_value={"op": "schema", "doctype": "Customer"}), \
                mock.patch.object(orchestrator, "run_erpnext_branch") as run:
            out = orchestrator.handle_question(
                "What fields does Customer have?", mode="employee")
        run.assert_not_called()
        self.assertEqual(out["confidence"], "low")
        self.assertIn("aren't available in employee mode", out["answer"])
        # the extraction still happened exactly once (no double call)
        self.assertEqual(out["route"], "erpnext")

    def test_document_list_allowed_for_employees(self) -> None:
        with mock.patch.object(orchestrator, "decide_route",
                               return_value=("erpnext", "heuristic")), \
                mock.patch.object(
                    orchestrator, "_extract_erpnext_request",
                    return_value={"op": "list", "doctype": "ToDo"}), \
                mock.patch.object(
                    orchestrator.erpnext, "list_documents",
                    return_value={"doctype": "ToDo", "count": 0,
                                  "rows": [], "limit": 20}), \
                mock.patch.object(orchestrator.generator, "_complete",
                                  return_value="You have none [1]."), \
                mock.patch.object(orchestrator, "get_instance_versions",
                                  return_value={"status": "unavailable",
                                                "frappe": "unknown",
                                                "erpnext": "unknown"}):
            out = orchestrator.handle_question(
                "Do I have any open ToDos?", mode="employee")
        self.assertEqual(out["confidence"], "high")
        self.assertIn("[1]", out["answer"])

    def test_employee_rag_uses_public_docs_only(self) -> None:
        captured = {}

        def fake_retrieve(question, k=None, include_company=True):
            captured["include_company"] = include_company
            return []

        with mock.patch.object(orchestrator, "decide_route",
                               return_value=("rag", "classifier")), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=fake_retrieve):
            orchestrator.handle_question("How do I make an invoice?",
                                         mode="employee")
        self.assertFalse(captured["include_company"])

    def test_employee_rag_generation_uses_employee_persona(self) -> None:
        chunk = {"title": "sales-invoice", "section": "Creating",
                 "url_or_path": "x", "source_type": "public_doc",
                 "score": 0.9, "text": "steps"}
        with mock.patch.object(orchestrator, "decide_route",
                               return_value=("rag", "heuristic")), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  return_value=[chunk]), \
                mock.patch.object(orchestrator.retriever,
                                  "classify_confidence",
                                  return_value="high"), \
                mock.patch.object(orchestrator.generator,
                                  "generate_answer") as gen, \
                mock.patch.object(orchestrator, "version_preamble",
                                  return_value=""):
            orchestrator.handle_question("How do I make an invoice?",
                                         mode="employee")
        self.assertEqual(gen.call_args.kwargs.get("persona"), "employee")

    def test_unknown_mode_refuses(self) -> None:
        out = orchestrator.handle_question("anything", mode="admin")
        self.assertEqual(out["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
