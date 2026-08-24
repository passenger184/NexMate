"""Unit tests for orchestrator routing (Phase 6).

Run: .venv/bin/python -m unittest discover -s tests -v

LLM calls are mocked; the live instance is never touched here.
"""

import unittest
from unittest import mock

import orchestrator


class DecideRouteTest(unittest.TestCase):
    def test_erpnext_heuristic_wins_on_live_data_phrasing(self) -> None:
        route, how = orchestrator.decide_route(
            "How many users are there in our erpnext instance and what "
            "is the status of each?")
        self.assertEqual((route, how), ("erpnext", "heuristic"))

    def test_code_heuristic_on_repo_question(self) -> None:
        route, how = orchestrator.decide_route(
            "In this project, where is it implemented — the pathsafe "
            "check in tools/?")
        self.assertEqual((route, how), ("code", "heuristic"))

    def test_classifier_fallback_for_conceptual_question(self) -> None:
        with mock.patch.object(orchestrator.generator, "_complete",
                               return_value='{"route": "rag"}'):
            route, how = orchestrator.decide_route(
                "What is a DocType in Frappe?")
        self.assertEqual((route, how), ("rag", "classifier"))

    def test_classifier_failure_defaults_to_rag(self) -> None:
        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=RuntimeError("down")):
            route, how = orchestrator.decide_route("something odd?")
        self.assertEqual((route, how), ("rag", "default"))

    def test_classifier_garbage_route_defaults_to_rag(self) -> None:
        with mock.patch.object(orchestrator.generator, "_complete",
                               return_value='{"route": "phase8"}'):
            route, _ = orchestrator.decide_route("something odd?")
        self.assertEqual(route, "rag")


class VersionPreambleTest(unittest.TestCase):
    def setUp(self) -> None:
        orchestrator._versions_cache.update({"fetched_at": 0.0,
                                             "data": None})

    def test_live_versions_inject_preamble(self) -> None:
        with mock.patch.object(
                orchestrator.erpnext, "call_method",
                return_value={"message": {
                    "frappe": {"version": "16.31.0"},
                    "erpnext": {"version": "16.32.3"}}}):
            v = orchestrator.get_instance_versions()
        self.assertEqual(v["status"], "live")
        preamble = orchestrator.version_preamble()
        self.assertIn("Frappe 16.31.0", preamble)
        self.assertIn("ERPNext 16.32.3", preamble)

    def test_unreachable_instance_degrades_honestly(self) -> None:
        with mock.patch.object(orchestrator.erpnext, "call_method",
                               side_effect=RuntimeError("nope")):
            v = orchestrator.get_instance_versions()
        self.assertEqual(v["status"], "unavailable")
        self.assertEqual(orchestrator.version_preamble(), "")


class ErpnextBranchTest(unittest.TestCase):
    def test_extraction_validation_rejects_garbage(self) -> None:
        with mock.patch.object(orchestrator.generator, "_complete",
                               return_value="not json at all"):
            with self.assertRaises(Exception):
                orchestrator._extract_erpnext_request("junk")

    def test_run_branch_builds_payload_and_cites(self) -> None:
        captured = {}

        def fake_complete(messages):
            captured.setdefault("count", 0)
            captured["count"] += 1
            if captured["count"] == 1:  # extraction call
                return ('{"op": "schema", "doctype": "Customer"}')
            return f"The payload lists `fieldname` values [1]."

        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=fake_complete), \
                mock.patch.object(
                    orchestrator.erpnext, "get_doctype_schema",
                    return_value={"data": {
                        "doctype": "Customer", "module": "Selling",
                        "naming_rule": "By Naming Series field",
                        "is_submittable": 0,
                        "fields": [
                            {"fieldname": "customer_name",
                             "fieldtype": "Data", "label": "Name"}]}}), \
                mock.patch.object(orchestrator, "get_instance_versions",
                                  return_value={
                                      "frappe": "16.31.0",
                                      "erpnext": "16.32.3",
                                      "status": "live"}):
            result = orchestrator.run_erpnext_branch(
                "What fields does Customer have?")

        self.assertEqual(result["route_meta"]["op"], "schema")
        self.assertEqual(len(result["sources"]), 1)
        self.assertIn("live ERPNext: Customer",
                      result["sources"][0]["title"])
        # first LLM call = extraction; second = grounded answer over payload
        self.assertGreaterEqual(captured["count"], 2)


class HandleQuestionRouting(unittest.TestCase):
    def test_rag_route_mirrors_ask_gates(self) -> None:
        fake_chunk = {"title": "T", "section": "s",
                      "url_or_path": "u", "source_type": "public_doc",
                      "score": 0.9, "text": "x"}
        with mock.patch.object(orchestrator.retriever, "retrieve",
                               return_value=[fake_chunk]), \
                mock.patch.object(orchestrator.retriever,
                                  "classify_confidence",
                                  return_value="high"), \
                mock.patch.object(orchestrator.generator,
                                  "generate_answer",
                                  return_value="grounded [1]") as gen, \
                mock.patch.object(orchestrator, "decide_route",
                                  return_value=("rag", "classifier")), \
                mock.patch.object(orchestrator, "version_preamble",
                                  return_value="\n\nVERSION LINE"):
            out = orchestrator.handle_question("How do I make a DocType?")

        self.assertEqual(out["confidence"], "high")
        self.assertEqual(out["answer"], "grounded [1]")
        # version authority injected into the RAG system prompt
        self.assertIn("VERSION LINE",
                      gen.call_args.kwargs.get("extra_system", ""))

    def test_low_confidence_rag_refuses_without_llm_answer(self) -> None:
        fake_chunk = {"title": "T", "section": "s",
                      "url_or_path": "u", "source_type": "public_doc",
                      "score": 0.75, "text": "x"}
        with mock.patch.object(orchestrator.retriever, "retrieve",
                               return_value=[fake_chunk]), \
                mock.patch.object(orchestrator.retriever,
                                  "classify_confidence",
                                  return_value="low"), \
                mock.patch.object(orchestrator.generator,
                                  "generate_answer") as should_not_run, \
                mock.patch.object(orchestrator, "decide_route",
                                  return_value=("rag", "heuristic")):
            out = orchestrator.handle_question("vague thing")

        should_not_run.assert_not_called()
        self.assertEqual(out["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
