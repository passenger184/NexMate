"""Regression tests for fix-post-live-routing-regressions (live 26/29).

Run: .venv/bin/python -m unittest discover -s tests -v

All model/network transports are mocked; the live model is never called
here (live re-run is a separate authorized checkpoint). Each test fails
on commit 9f274ed and passes after the D1-D5 fix. No exact-string
special-casing: every class carries generalized variants.

Issues (from /tmp/live29 evidence):
  knowledge-journal  "what is a journal entry?" NLU-clarify -> must RAG
  followup-purchase  "what about purchase invoices?" + how-to history
                     NLU-clarify -> must condense -> RAG (not ERPNext)
  dead-port probe    provider down + how-to input escaped an uncaught
                     provider exception -> must clarify safely
"""

import unittest
from contextlib import ExitStack
from unittest import mock

import orchestrator

HIST_SALES_HOWTO = [
    {"role": "user", "content": "How do I create a Sales Invoice?"},
    {"role": "assistant", "content": "Open a Sales Order... [1]"},
]

HIST_CONFIGURE = [
    {"role": "user", "content": "How do I configure Sales Invoice?"},
    {"role": "assistant", "content": "Open Selling Settings... [1]"},
]


def _clarify_nlu(topic=None, confidence=0.9,
                 context_dependency="none"):
    return {"kind": "clarify", "subtype": None, "topic": topic,
            "context_dependency": context_dependency,
            "confidence": confidence}


def _fake_chunk():
    return {"title": "T", "section": "s", "url_or_path": "u",
            "source_type": "public_doc", "score": 0.9, "text": "x"}


def _rag_stubs(stack, calls):
    """Mocked RAG + classifier-rag + versions; record ERPNext silence."""
    def fail_erpnext(*a, **k):
        calls.append("erpnext")
        raise AssertionError("erpnext tool ran")

    stack.enter_context(mock.patch.object(
        orchestrator.generator, "_complete",
        return_value='{"route": "rag"}'))
    stack.enter_context(mock.patch.object(
        orchestrator.retriever, "retrieve",
        return_value=[_fake_chunk()]))
    stack.enter_context(mock.patch.object(
        orchestrator.retriever, "classify_confidence",
        return_value="high"))
    stack.enter_context(mock.patch.object(
        orchestrator.generator, "generate_answer",
        return_value="Canned grounded answer [1]."))
    stack.enter_context(mock.patch.object(
        orchestrator, "get_instance_versions",
        return_value={"status": "unavailable", "frappe": "unknown",
                      "erpnext": "unknown"}))
    for fn in ("get_doctype_schema", "get_document", "list_documents"):
        stack.enter_context(mock.patch.object(
            orchestrator.erpnext, fn, side_effect=fail_erpnext))


class CompleteInterrogativeTest(unittest.TestCase):
    """D2: complete questions survive an NLU-clarify verdict."""

    def test_complete_questions_route_rag(self) -> None:
        for text in (
            "what is a journal entry?",
            "What is a sales invoice?",
            "How does purchase invoice work?",
        ):
            with self.subTest(text=text):
                calls = []
                with ExitStack() as stack:
                    stack.enter_context(mock.patch.object(
                        orchestrator, "_understand_with_llm",
                        return_value=_clarify_nlu()))
                    _rag_stubs(stack, calls)
                    out = orchestrator.handle_question(text)
                self.assertEqual(out["route"], "rag")
                self.assertEqual(calls, [])

    def test_incomplete_inputs_still_clarify(self) -> None:
        for text in ("payments", "purchase invoices", "something vague"):
            with self.subTest(text=text):
                with mock.patch.object(
                        orchestrator, "_understand_with_llm",
                        return_value=_clarify_nlu(topic=text)), \
                     mock.patch.object(
                         orchestrator.retriever, "retrieve",
                         side_effect=AssertionError("RAG ran")):
                    out = orchestrator.handle_question(text)
                self.assertEqual(out["route"], "clarify")
                self.assertEqual(out["fallback"], "clarify")


class ClarifyFollowupTest(unittest.TestCase):
    """D3/D4: clarify-with-history condenses, then normal precedence."""

    def test_howto_followup_condenses_to_rag(self) -> None:
        calls = []
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_clarify_nlu(
                    topic="purchase invoices", context_dependency="follows_topic")))
            stack.enter_context(mock.patch.object(
                orchestrator.generator, "condense_followup",
                return_value="How do I create a Purchase Invoice?"))
            _rag_stubs(stack, calls)
            out = orchestrator.handle_question(
                "what about purchase invoices?",
                history=list(HIST_SALES_HOWTO))
        self.assertEqual(out["route"], "rag")
        self.assertEqual(calls, [])

    def test_status_followup_reaches_erpnext_on_explicit_signal(self) -> None:
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_clarify_nlu(
                    topic="Purchase Invoice status",
                    context_dependency="follows_topic")))
            stack.enter_context(mock.patch.object(
                orchestrator.generator, "condense_followup",
                return_value="What is the status of Purchase Invoice?"))
            stack.enter_context(mock.patch.object(
                orchestrator, "_extract_erpnext_request",
                return_value={"op": "list", "doctype": "Purchase Invoice",
                              "filters": {"docstatus": 1}, "limit": 20}))
            stack.enter_context(mock.patch.object(
                orchestrator.erpnext, "list_documents",
                return_value={"doctype": "Purchase Invoice", "count": 0,
                              "rows": [], "limit": 20}))
            stack.enter_context(mock.patch.object(
                orchestrator.generator, "_complete",
                return_value="None found [1]."))
            stack.enter_context(mock.patch.object(
                orchestrator, "get_instance_versions",
                return_value={"status": "unavailable", "frappe": "unknown",
                              "erpnext": "unknown"}))
            out = orchestrator.handle_question(
                "what about Purchase Invoice status?",
                history=list(HIST_CONFIGURE))
        self.assertEqual(out["route"], "erpnext")

    def test_condense_failure_still_clarifies(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_clarify_nlu(
                    topic="purchase invoices",
                    context_dependency="follows_topic")), \
             mock.patch.object(orchestrator.generator, "condense_followup",
                               return_value=None), \
             mock.patch.object(orchestrator.retriever, "retrieve",
                               side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question(
                "what about purchase invoices?",
                history=list(HIST_SALES_HOWTO))
        self.assertEqual(out["route"], "clarify")

    def test_no_history_clarifies_without_condensing(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_clarify_nlu(topic="purchase invoices")), \
             mock.patch.object(orchestrator.generator, "condense_followup",
                               side_effect=AssertionError("condense ran")):
            out = orchestrator.handle_question("what about purchase invoices?")
        self.assertEqual(out["route"], "clarify")

    def test_new_topic_control_never_condenses(self) -> None:
        calls = []
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value={"kind": "task", "subtype": None,
                              "topic": "purchase order submit",
                              "context_dependency": "none",
                              "confidence": 0.9}))
            stack.enter_context(mock.patch.object(
                orchestrator.generator, "condense_followup",
                side_effect=AssertionError("condense ran")))
            _rag_stubs(stack, calls)
            out = orchestrator.handle_question(
                "How do I submit a Purchase Order?",
                history=list(HIST_SALES_HOWTO))
        self.assertEqual(out["route"], "rag")
        self.assertEqual(calls, [])


class DegradedHowtoTest(unittest.TestCase):
    """D5: provider-down how-to clarifies; nothing escapes, nothing fabricates."""

    def test_provider_down_howto_clarifies_safely(self) -> None:
        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=RuntimeError("provider down")), \
             mock.patch.object(orchestrator.generator, "generate_answer",
                               side_effect=AssertionError(
                                   "generation attempted while down")), \
             mock.patch.object(orchestrator.retriever, "retrieve",
                               side_effect=AssertionError(
                                   "retrieval attempted while down")):
            out = orchestrator.handle_question(
                "How do I create a Sales Invoice?")
        self.assertEqual(out["route"], "clarify")
        self.assertEqual(out["route_how"], "degraded")
        self.assertEqual(out["confidence"], "low")
        self.assertEqual(out["sources"], [])


if __name__ == "__main__":
    unittest.main()
