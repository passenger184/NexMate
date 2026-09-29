"""Unit tests for orchestrator routing (Phase 6).

Run: .venv/bin/python -m unittest discover -s tests -v

LLM calls are mocked; the live instance is never touched here.
"""

import json
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

    def test_classifier_sees_history_for_followups(self) -> None:
        seen = {}

        def fake_complete(messages, **kwargs):
            seen["system"] = messages[0]["content"]
            seen["user"] = messages[1]["content"]
            return '{"route": "rag"}'

        hist = [{"role": "user",
                 "content": "How do I create a Sales Invoice?"},
                {"role": "assistant", "content": "Open ... [1]."}]
        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=fake_complete):
            route, how = orchestrator.decide_route(
                "what about Purchase Invoices?", hist)
        self.assertEqual((route, how), ("rag", "classifier"))
        # History rides in the user message; the system instruction stays
        # byte-identical so JSON discipline survives context.
        self.assertIn("How do I create a Sales Invoice?", seen["user"])
        self.assertNotIn("Conversation so far", seen["system"])

    def test_classifier_without_history_has_no_conversation_block(self) -> None:
        seen = {}

        def fake_complete(messages, **kwargs):
            seen["user"] = messages[1]["content"]
            return '{"route": "rag"}'

        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=fake_complete):
            orchestrator.decide_route("what about Purchase Invoices?")
        self.assertNotIn("Conversation so far", seen["user"])


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

    def test_run_branch_requests_schema_and_cites_minimized_context(self) -> None:
        """With no authorized context, a schema turn is a control-plane REQUEST."""
        with mock.patch.object(orchestrator.generator, "_complete",
                               return_value='{"op": "schema", "doctype": "Customer"}'), \
                mock.patch.object(orchestrator.erpnext, "get_doctype_schema",
                                  side_effect=AssertionError("client called")):
            result = orchestrator.run_erpnext_branch(
                "What fields does Customer have?")
        self.assertEqual(result["_read_request"],
                         {"kind": "schema", "doctype": "Customer"})

    def test_run_branch_answers_schema_from_authorized_context_only(self) -> None:
        """Given Frappe-produced authorized context, answer from it and cite."""
        captured = {}

        def fake_complete(messages, **kwargs):
            captured.setdefault("count", 0)
            captured["count"] += 1
            if captured["count"] == 1:  # extraction call
                return '{"op": "schema", "doctype": "Customer"}'
            return "The payload lists `fieldname` values [1]."

        authorized = {
            "doctype": "Customer", "operation": "schema", "field_count": 1,
            "fields": [{"fieldname": "customer_name", "fieldtype": "Data",
                        "label": "Name", "reqd": True, "read_only": False}],
        }
        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=fake_complete), \
                mock.patch.object(orchestrator.erpnext, "get_doctype_schema",
                                  side_effect=AssertionError("client called")), \
                mock.patch.object(orchestrator, "get_instance_versions",
                                  return_value={
                                      "frappe": "16.31.0",
                                      "erpnext": "16.32.3",
                                      "status": "live"}):
            result = orchestrator.run_erpnext_branch(
                "What fields does Customer have?",
                authorized_context=authorized)

        self.assertNotIn("_read_request", result)
        self.assertEqual(result["route_meta"]["op"], "schema")
        self.assertEqual(len(result["sources"]), 1)
        self.assertIn("live ERPNext: Customer", result["sources"][0]["title"])
        # first LLM call = extraction; second = grounded answer over payload
        self.assertGreaterEqual(captured["count"], 2)

    def test_run_branch_ignores_non_metadata_context_on_the_schema_branch(self) -> None:
        """A business-read context is never consumed as a metadata answer."""
        with mock.patch.object(orchestrator.generator, "_complete",
                               return_value='{"op": "schema", "doctype": "Customer"}'):
            result = orchestrator.run_erpnext_branch(
                "What fields does Customer have?",
                authorized_context={"doctype": "Customer", "operation": "list",
                                    "fields_returned": ["name"], "row_count": 0,
                                    "data": []})
        self.assertEqual(result["_read_request"],
                         {"kind": "schema", "doctype": "Customer"})


class HandleQuestionRouting(unittest.TestCase):
    # All routing through handle_question first passes the NLU layer;
    # these tests pin its decision so they assert wiring, not model output.
    TASK_NLU = {"kind": "task", "subtype": None, "topic": None,
                "context_dependency": "none", "confidence": 0.9}

    def test_rag_route_mirrors_ask_gates(self) -> None:
        fake_chunk = {"title": "T", "section": "s",
                      "url_or_path": "u", "source_type": "public_doc",
                      "score": 0.9, "text": "x"}
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(self.TASK_NLU)), \
                mock.patch.object(orchestrator.retriever, "retrieve",
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

    def test_bare_fragment_clarifies_before_rag_answer(self) -> None:
        # "vague thing" is a short verbless fragment, so the bare-fragment
        # guard clarifies before the RAG branch runs: generation never
        # executes and confidence stays low. Assertions unchanged — only
        # the path (guard, not the RAG confidence gate) is new.
        fake_chunk = {"title": "T", "section": "s",
                      "url_or_path": "u", "source_type": "public_doc",
                      "score": 0.75, "text": "x"}
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(self.TASK_NLU)), \
                mock.patch.object(orchestrator.retriever, "retrieve",
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


class LooksLikeListingTest(unittest.TestCase):
    def test_listing_questions_detected(self) -> None:
        for text in (
            "what files are inside the project",
            "list all files in the repo",
            "show me the project structure",
            "which directories exist at the project root",
        ):
            with self.subTest(text=text):
                self.assertTrue(orchestrator._looks_like_listing(text))

    def test_non_listing_questions_not_detected(self) -> None:
        for text in (
            "why does resolve_in_project raise on symlinks",
            "show me files that mention RRF_K",
            "list all API endpoints",
            "what does the error banner say",
        ):
            with self.subTest(text=text):
                self.assertFalse(orchestrator._looks_like_listing(text))


class ListingRouteTest(unittest.TestCase):
    """End-to-end listing answer uses the live index, never the LLM."""

    def test_listing_answers_from_git_index(self) -> None:
        import subprocess
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "app").mkdir()
            (root / "app" / "worker.py").write_text("x = 1\n")
            subprocess.run(["git", "init", "-q"], cwd=root,
                           capture_output=True)
            with mock.patch("config.PROJECT_ROOT", root), \
                    mock.patch.object(
                        orchestrator, "_understand_with_llm",
                        return_value={"kind": "task", "subtype": None,
                                      "topic": None,
                                      "context_dependency": "none",
                                      "confidence": 0.9}), \
                    mock.patch.object(orchestrator, "decide_route",
                                      return_value=("code", "heuristic")):
                out = orchestrator.handle_question(
                    "what files are inside the project")

        self.assertEqual(out["route"], "code")
        self.assertEqual(out["confidence"], "high")
        self.assertIn("app/worker.py", out["answer"])
        self.assertNotIn("Unexpected Behavior", out["answer"])
        self.assertNotIn("Recommendations", out["answer"])
        self.assertEqual(out["sources"][0]["title"], "project file tree")



class GreetingTest(unittest.TestCase):
    def test_greetings_detected(self) -> None:
        for text in ("hey", "Hello!", "hi", "thanks", "Thank you.",
                     "good morning", "bye", "yo?"):
            with self.subTest(text=text):
                self.assertTrue(orchestrator.is_greeting(text))

    def test_real_questions_are_not_greetings(self) -> None:
        for text in ("hey, how do I create a customer?",
                     "What fields does Customer have?",
                     "why does resolve_in_project raise on symlinks?",
                     "How do I create a Sales Invoice?",
                     "they said it was broken"):
            with self.subTest(text=text):
                self.assertFalse(orchestrator.is_greeting(text))

    def test_greeting_never_touches_tools_or_llm(self) -> None:
        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=AssertionError("LLM called")), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("retriever")), \
                mock.patch.object(orchestrator.explain,
                                  "locate_and_explain",
                                  side_effect=AssertionError("code tool")), \
                mock.patch.object(orchestrator.erpnext,
                                  "get_doctype_schema",
                                  side_effect=AssertionError("erpnext")):
            out = orchestrator.handle_question(
                "hey",
                history=[{"role": "user", "content": "How do I make X?"},
                         {"role": "assistant", "content": "Like this [1]."}])
        self.assertEqual(out["route"], "smalltalk")
        self.assertEqual(out["confidence"], "high")
        self.assertEqual(out["sources"], [])


class CondenseGateTest(unittest.TestCase):
    HIST = [{"role": "user", "content": "How do I create a Sales Invoice?"},
            {"role": "assistant",
             "content": "Open the Sales Order... [1]"}]

    def test_anaphoric_followup_condenses(self) -> None:
        for text in ("which constant did you just cite?",
                     "And what other constants sit next to it?",
                     "show me those in a list instead"):
            with self.subTest(text=text):
                self.assertTrue(
                    orchestrator.should_condense_followup(self.HIST, text))

    def test_greeting_never_condenses(self) -> None:
        for text in ("hello", "hey", "thanks!"):
            with self.subTest(text=text):
                self.assertFalse(
                    orchestrator.should_condense_followup(self.HIST, text))

    def test_standalone_topic_change_never_condenses(self) -> None:
        for text in ("How do I submit a Purchase Order?",
                     "What fields does Customer have?",
                     "How do I create a custom app?"):
            with self.subTest(text=text):
                self.assertFalse(
                    orchestrator.should_condense_followup(self.HIST, text))

    def test_empty_history_never_condenses(self) -> None:
        self.assertFalse(
            orchestrator.should_condense_followup(
                [], "which one did you mean?"))


class ExtractionNameValidationTest(unittest.TestCase):
    def test_document_op_without_name_is_rejected(self) -> None:
        with mock.patch.object(
                orchestrator.generator, "_complete",
                return_value='{"op": "document", "doctype": "Customer"}'):
            with self.assertRaises(ValueError):
                orchestrator._extract_erpnext_request(
                    "show me the customer")

    def test_document_op_with_name_passes(self) -> None:
        with mock.patch.object(
                orchestrator.generator, "_complete",
                return_value='{"op": "document", "doctype": "Customer", '
                              '"name": "CUST-001"}'):
            req = orchestrator._extract_erpnext_request("show me CUST-001")
        self.assertEqual(req["name"], "CUST-001")


class UnknownDoctypeTest(unittest.TestCase):
    """The ERPNext read and metadata paths never call the shared-credential client.

    Both a business-data read and a schema request are REQUESTS to the Frappe
    control plane. A business-data read of an unapproved DocType is refused by
    the Frappe adapter, and under the anti-oracle requirement a not-found and a
    permission-denied collapse to one indistinguishable denial that must NOT
    name the DocType. The same applies to metadata: a nonexistent DocType
    collapses into one denial that reveals nothing about which DocTypes exist.
    """
    TASK_NLU = {"kind": "task", "subtype": None, "topic": "invoices",
                "context_dependency": "none", "confidence": 0.9}

    def _run_schema(self, doctype="Invoices"):
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(self.TASK_NLU)), \
                mock.patch.object(orchestrator, "decide_route",
                                  return_value=("erpnext", "classifier")), \
                mock.patch.object(
                    orchestrator, "_extract_erpnext_request",
                    return_value={"op": "schema", "doctype": doctype}):
            return orchestrator.handle_question("show invoices for review")

    def _run_read(self, limit=None, op="list", doctype="Invoices"):
        request = {"op": op, "doctype": doctype}
        if limit is not None:
            request["limit"] = limit
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(self.TASK_NLU)), \
                mock.patch.object(orchestrator, "decide_route",
                                  return_value=("erpnext", "classifier")), \
                mock.patch.object(orchestrator, "_extract_erpnext_request",
                                  return_value=request):
            return orchestrator.handle_question("show invoices for review")

    def test_proposed_read_limit_is_not_narrower_than_the_producer_ceiling(self):
        """A cap below the approved ceiling makes it unreachable end to end.

        This service only *proposes* a limit; the Frappe control plane still
        resolves the effective one from ``NexMate Settings``. But a proposal
        cap sitting below the producer's immutable ceiling would mean an
        administrator's configured ``max_read_rows`` could never be exercised.
        """
        from frappe_app.erpnext_ai_copilot import erpnext_read as er
        self.assertEqual(orchestrator.DEFAULT_READ_LIMIT, 20)
        self.assertEqual(orchestrator.MAX_READ_LIMIT, er.MAX_LIST_LIMIT)
        self.assertEqual(orchestrator.MAX_READ_LIMIT, 100)
        # No limit named -> the default, unchanged from before.
        self.assertEqual(self._run_read()["_read_request"]["limit"], 20)
        # A proposed limit inside the ceiling is passed through verbatim.
        for proposed in (1, 20, 21, 50, 75, 100):
            with self.subTest(proposed=proposed):
                self.assertEqual(
                    self._run_read(limit=proposed)["_read_request"]["limit"],
                    proposed)
        # Above the ceiling is clamped to it, never above.
        for proposed in (101, 1000):
            with self.subTest(proposed=proposed):
                self.assertEqual(
                    self._run_read(limit=proposed)["_read_request"]["limit"],
                    100)

    def test_business_read_of_unapproved_doctype_is_a_read_request(self) -> None:
        """A plural DocType guess now produces a read request the adapter refuses."""
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=dict(self.TASK_NLU)), \
                mock.patch.object(orchestrator, "decide_route",
                                  return_value=("erpnext", "classifier")), \
                mock.patch.object(
                    orchestrator, "_extract_erpnext_request",
                    return_value={"op": "list", "doctype": "Invoices", "limit": 20}):
            out = orchestrator.handle_question("show invoices for review")
        self.assertIn("_read_request", out)
        # The adapter refuses it (not in the approved policy) and the caller
        # sees ONE collapsed denial that does not reveal existence.
        from frappe_app.erpnext_ai_copilot import erpnext_read as er
        with self.assertRaises(er.DocTypeNotAllowed):
            er.build_request(out["_read_request"])
        collapsed = er.collapse_for_caller(er.DocTypeNotAllowed("x"))
        self.assertNotIn("Invoices", collapsed["answer"])
        self.assertEqual(collapsed["answer"], "Document not found or access denied.")

    def test_schema_is_a_control_plane_request_not_a_client_call(self) -> None:
        """Inference REQUESTS metadata; it never retrieves or authorizes it."""
        out = self._run_schema()
        self.assertEqual(out["_read_request"],
                         {"kind": "schema", "doctype": "Invoices"})
        self.assertEqual(out["route"], "erpnext")
        self.assertEqual(out["route_how"], "classifier+read-requested")

    def test_schema_never_names_the_doctype_to_the_caller(self) -> None:
        """A nonexistent DocType collapses into one indistinguishable denial."""
        from frappe_app.erpnext_ai_copilot import doctype_meta as dm
        collapsed = dm.collapse_for_caller(dm.DocTypeNotFound("no such doctype"))
        self.assertNotIn("Invoices", collapsed["answer"])
        self.assertEqual(collapsed["answer"], "Schema not found or access denied.")
        self.assertEqual(collapsed["route_how"], "frappe-schema+denied")
        # The internal reason is never part of the caller-visible object.
        self.assertNotIn("not_found", json.dumps(collapsed))

    def test_schema_inference_makes_no_erpnext_call(self) -> None:
        with mock.patch.object(orchestrator.erpnext, "get_doctype_schema",
                               side_effect=AssertionError("client called")), \
                mock.patch.object(orchestrator.erpnext, "get_document",
                                  side_effect=AssertionError("client called")), \
                mock.patch.object(orchestrator.erpnext, "list_documents",
                                  side_effect=AssertionError("client called")):
            self._run_schema()
class NluTelemetryTest(unittest.TestCase):
    def test_every_result_carries_its_nlu_verdict(self) -> None:
        # Fast-path: deterministic marker, no model verdict.
        out = orchestrator.handle_question("hey")
        self.assertEqual(out["nlu_kind"], "exact:greeting")
        self.assertEqual(out["nlu_confidence"], 1.0)
        # NLU path: verdict attached for telemetry (logged, not shown).
        nlu = {"kind": "clarify", "subtype": None, "topic": "invoices",
               "context_dependency": "none", "confidence": 0.6}
        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=nlu):
            out = orchestrator.handle_question("invoices")
        self.assertEqual(out["nlu_kind"], "clarify")
        self.assertEqual(out["nlu_confidence"], 0.6)
        self.assertEqual(out["nlu_topic"], "invoices")


if __name__ == "__main__":
    unittest.main()
