"""Regression tests for fix-routing-precision-after-m7 (M7 3.2 defects).

Run: .venv/bin/python -m unittest discover -s tests -v

Strategy (per change design D4): live-observed WRONG verdicts are replayed
through mocks while the REAL routing logic runs — heuristic, decide_route,
and the bare-fragment guard are never mocked here. Each test fails on the
pre-fix implementation and passes after. No exact-string special-casing:
every defect class carries paraphrase/DocType variants.

The four M7 defects:
  code-where        "where is Sales Invoice implemented?" -> code (was rag)
  followup-purchase "what about purchase invoices?" + how-to history -> rag
                      (was erpnext)
  ambiguous-payments "payments" -> clarify (was erpnext)
  contam-newtopic   "How do I submit a Purchase Order?" + unrelated
                      history -> rag (was erpnext)

`evaluation/routing_cases.json` is intentionally untouched (M7 baseline).
"""

import unittest
from contextlib import ExitStack
from unittest import mock

import orchestrator

HIST_SALES_HOWTO = [
    {"role": "user", "content": "How do I create a sales invoice?"},
    {"role": "assistant", "content": "Open a Sales Order... [1]"},
]


def _task_nlu(topic=None, confidence=0.9, context_dependency="none"):
    return {"kind": "task", "subtype": None, "topic": topic,
            "context_dependency": context_dependency,
            "confidence": confidence}


def _fake_chunk():
    return {"title": "T", "section": "s", "url_or_path": "u",
            "source_type": "public_doc", "score": 0.9, "text": "x"}


class HeuristicSignalTest(unittest.TestCase):
    """Generalized signals on the real _heuristic_route (no mocks)."""

    def test_code_location_variants_route_code(self) -> None:
        for text in (
            "where is Sales Invoice implemented?",
            "where is Purchase Invoice implemented?",
            "where is Purchase Order implemented?",
            "where is this implemented?",
            "where is the code for Sales Invoice?",
            "where is Purchase Order implemented in the code?",
            "which function implements the pathsafe check",
        ):
            with self.subTest(text=text):
                self.assertEqual(orchestrator._heuristic_route(text), "code")

    def test_howto_variants_route_rag(self) -> None:
        for text in (
            "How do I create a Purchase Invoice?",
            "How do I submit a Purchase Order?",
            "How do I configure Purchase Invoice?",
            "how to create a sales invoice",
            "How do I create a Sales Invoice?",
        ):
            with self.subTest(text=text):
                self.assertEqual(orchestrator._heuristic_route(text), "rag")

    def test_live_data_variants_route_erpnext(self) -> None:
        for text in (
            "How many Purchase Invoices are submitted?",
            "Show me submitted Purchase Invoices.",
            "What is the status of PO-0001?",
            "What fields does Customer have?",
            "how many users are there in our erpnext instance",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    orchestrator._heuristic_route(text), "erpnext")

    def test_non_signals_abstain(self) -> None:
        for text in (
            "How is a DocType implemented in Frappe?",
            "What is a DocType in Frappe?",
            "payments",
            "purchase invoices",
            "invoices",
            "tell me a joke",
        ):
            with self.subTest(text=text):
                self.assertIsNone(orchestrator._heuristic_route(text))


class LiveVerdictReplayTest(unittest.TestCase):
    """Replay M7's wrong live verdicts against the real router."""

    def _run(self, message, nlu, history=None, condensed="unused",
             classifier_verdict='{"route": "erpnext"}',
             code_side_effect=None):
        calls = {"tools": []}

        def fake_complete(messages, **kwargs):
            # Replays the live model's WRONG route verdict. After the fix
            # the deterministic layer preempts the classifier, so this
            # verdict must never decide the outcome.
            return classifier_verdict

        def fail_erpnext(*a, **k):
            calls["tools"].append("erpnext")
            raise AssertionError("erpnext tool ran")

        if code_side_effect is None:
            code_side_effect = AssertionError("code tool ran")
        patches = [
            mock.patch.object(orchestrator, "_understand_with_llm",
                              return_value=nlu),
            mock.patch.object(orchestrator.generator, "_complete",
                              side_effect=fake_complete),
            mock.patch.object(orchestrator.generator, "condense_followup",
                              return_value=condensed),
            mock.patch.object(orchestrator.explain, "locate_and_explain",
                              side_effect=code_side_effect),
            mock.patch.object(orchestrator.erpnext, "get_doctype_schema",
                              side_effect=fail_erpnext),
            mock.patch.object(orchestrator.erpnext, "get_document",
                              side_effect=fail_erpnext),
            mock.patch.object(orchestrator.erpnext, "list_documents",
                              side_effect=fail_erpnext),
            mock.patch.object(orchestrator.retriever, "retrieve",
                              return_value=[_fake_chunk()]),
            mock.patch.object(orchestrator.retriever,
                              "classify_confidence", return_value="high"),
            mock.patch.object(orchestrator.generator, "generate_answer",
                              return_value="Canned grounded answer [1]."),
            mock.patch.object(orchestrator, "get_instance_versions",
                              return_value={"status": "unavailable",
                                            "frappe": "unknown",
                                            "erpnext": "unknown"}),
        ]
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            out = orchestrator.handle_question(message, history=history)
        return out, calls

    def test_code_where_routes_code(self) -> None:
        out, calls = self._run(
            "where is Sales Invoice implemented?",
            _task_nlu(topic="Sales Invoice implementation",
                      confidence=0.8),
            classifier_verdict='{"route": "rag"}',
            code_side_effect=lambda *a, **k: {
                "located": True, "explanation": "it's in `f.py`",
                "sources": [{"path": "f.py", "line_start": 1,
                             "line_end": 2}],
                "search_terms": ["Sales Invoice"], "total_hits": 1})
        self.assertEqual(out["route"], "code")
        self.assertEqual(calls["tools"], [])

    def test_followup_purchase_routes_rag(self) -> None:
        out, calls = self._run(
            "what about purchase invoices?",
            _task_nlu(topic="purchase invoices", confidence=0.85,
                      context_dependency="follows_topic"),
            history=list(HIST_SALES_HOWTO),
            condensed="How do I create a Purchase Invoice?")
        self.assertEqual(out["route"], "rag")
        self.assertEqual(calls["tools"], [])

    def test_contam_newtopic_routes_rag(self) -> None:
        out, calls = self._run(
            "How do I submit a Purchase Order?",
            _task_nlu(topic="purchase order submit", confidence=0.9,
                      context_dependency="none"),
            history=list(HIST_SALES_HOWTO),
            condensed="unused")
        self.assertEqual(out["route"], "rag")
        self.assertEqual(calls["tools"], [])


class BareFragmentGuardTest(unittest.TestCase):
    """Bare nouns clarify even when NLU claims task (M7 ambiguous-*)."""

    def test_bare_fragments_clarify_despite_task_nlu(self) -> None:
        for text in ("payments", "purchase invoices", "sales orders",
                     "invoices"):
            with self.subTest(text=text):
                with mock.patch.object(
                        orchestrator, "_understand_with_llm",
                        return_value=_task_nlu(topic=text,
                                               confidence=0.9)), \
                     mock.patch.object(
                         orchestrator.retriever, "retrieve",
                         side_effect=AssertionError("RAG ran")), \
                     mock.patch.object(
                         orchestrator.explain, "locate_and_explain",
                         side_effect=AssertionError("code ran")), \
                     mock.patch.object(
                         orchestrator.erpnext, "list_documents",
                         side_effect=AssertionError("erpnext ran")), \
                     mock.patch.object(
                         orchestrator.generator, "_complete",
                         side_effect=AssertionError("LLM ran")):
                    out = orchestrator.handle_question(text)
                self.assertEqual(out["route"], "clarify")
                self.assertEqual(out["fallback"], "clarify")
                self.assertEqual(out["confidence"], "low")

    def test_intent_bearing_fragments_pass_through(self) -> None:
        # Fragments carrying intent verbs/questions must NOT be swallowed
        # by the guard: NLU keeps deciding those.
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value={"kind": "out_of_scope", "subtype": None,
                              "topic": None, "context_dependency": "none",
                              "confidence": 0.95}):
            out = orchestrator.handle_question("tell me a joke")
        self.assertEqual(out["route"], "out_of_scope")


class DecideRoutePrecedenceTest(unittest.TestCase):
    """End-to-end precedence on the real decide_route (history included)."""

    def test_precedence_without_mocks(self) -> None:
        cases = [
            ("where is Purchase Order implemented?", "code"),
            ("How do I configure Purchase Invoice?", "rag"),
            ("Show me submitted Purchase Invoices.", "erpnext"),
            ("What is the status of PO-0001?", "erpnext"),
            ("How do I submit a Purchase Order?",
             "rag"),  # with unrelated history: no contamination
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                route, _ = orchestrator.decide_route(
                    text, history=list(HIST_SALES_HOWTO))
                self.assertEqual(route, expected)


if __name__ == "__main__":
    unittest.main()
