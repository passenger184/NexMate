"""Behavior tests for conversational routing (greetings, capability,
clarification, scope, troubleshooting, degraded NLU).

Run: .venv/bin/python -m unittest discover -s tests -v

All assertions are behavioral (route taken, capability used, whether
RAG/tools/LLM ran, clarification vs answer) — never exact response
wording. The LLM is always mocked; nothing here touches the network.
"""

import json
import unittest
from unittest import mock

import orchestrator


def _nlu(kind, subtype=None, topic=None, confidence=0.9,
         context_dependency="none"):
    return {"kind": kind, "subtype": subtype, "topic": topic,
            "context_dependency": context_dependency,
            "confidence": confidence}


def _no_llm_or_tools(testcase):
    """Context managers asserting zero LLM/tool calls on a path."""
    return (
        mock.patch.object(
            orchestrator.generator, "_complete",
            side_effect=AssertionError("unexpected LLM call")),
        mock.patch.object(
            orchestrator.retriever, "retrieve",
            side_effect=AssertionError("unexpected retrieval")),
        mock.patch.object(
            orchestrator.explain, "locate_and_explain",
            side_effect=AssertionError("unexpected code tool")),
        mock.patch.object(
            orchestrator.erpnext, "get_doctype_schema",
            side_effect=AssertionError("unexpected erpnext tool")),
    )


class ExactFastPathTest(unittest.TestCase):
    def test_canonical_greetings_answer_without_llm(self) -> None:
        for text in ("hey", "hi", "hello", "bye", "thanks",
                     "ok", "okay", "got it"):
            with self.subTest(text=text):
                p1, p2, p3, p4 = _no_llm_or_tools(self)
                with p1, p2, p3, p4:
                    out = orchestrator.handle_question(text)
                self.assertEqual(out["route"], "smalltalk")
                self.assertEqual(out["route_how"], "heuristic")
                self.assertEqual(out["confidence"], "high")
                self.assertEqual(out["sources"], [])

    def test_canonical_help_answers_from_registry_without_llm(self) -> None:
        p1, p2, p3, p4 = _no_llm_or_tools(self)
        with p1, p2, p3, p4:
            out = orchestrator.handle_question("help")
        self.assertEqual(out["route"], "capability")
        for label in ("documentation", "Live ERPNext data lookups",
                      "source code"):
            self.assertIn(label, out["answer"])


class NluConversationalTest(unittest.TestCase):
    def _run(self, text, nlu, history=None):
        calls = []

        def fake_complete(messages, **kwargs):
            calls.append(messages)
            if "route messages for NexMate" in messages[0]["content"]:
                return json.dumps(nlu)
            return "Hey there! What can I do for you?"

        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=fake_complete), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")), \
                mock.patch.object(orchestrator.explain,
                                  "locate_and_explain",
                                  side_effect=AssertionError("code ran")):
            out = orchestrator.handle_question(text, history=history)
        return out, calls

    def test_variant_greeting_uses_nlu_then_short_reply(self) -> None:
        out, calls = self._run(
            "hiii",
            {"kind": "conversational", "subtype": "greeting", "topic": None,
             "context_dependency": "none", "confidence": 0.97})
        self.assertEqual(out["route"], "smalltalk")
        self.assertEqual(len(calls), 2)  # classify + short reply only

    def test_conversational_llm_failure_uses_static_fallback(self) -> None:
        def fake(messages, **kwargs):
            if "route messages for NexMate" in messages[0]["content"]:
                return json.dumps({"kind": "conversational",
                                   "subtype": "thanks", "topic": None,
                                   "context_dependency": "none",
                                   "confidence": 0.9})
            raise RuntimeError("gen down")

        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=fake):
            out = orchestrator.handle_question("thx a lot")
        self.assertEqual(out["route"], "smalltalk")
        self.assertIn("welcome", out["answer"].lower())


class CapabilityTest(unittest.TestCase):
    def test_capability_lists_only_real_registry_entries(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_nlu("capability")), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question("what can u do")
        self.assertEqual(out["route"], "capability")
        for label in ("documentation", "Live ERPNext data lookups",
                      "source code"):
            self.assertIn(label, out["answer"])

    def test_capability_answer_excludes_code_for_employees(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_nlu("capability")):
            out = orchestrator.handle_question(
                "what can you do", mode="employee")
        self.assertNotIn("source code", out["answer"])
        self.assertIn("documentation", out["answer"])


class ClarifyAndScopeTest(unittest.TestCase):
    def test_ambiguous_noun_clarifies_without_retrieval(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_nlu("clarify", topic="invoices",
                                  confidence=0.6)), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question("invoices")
        self.assertEqual(out["route"], "clarify")
        self.assertEqual(out["confidence"], "low")
        self.assertEqual(out["fallback"], "clarify")
        self.assertIn("invoices", out["answer"])

    def test_out_of_scope_answers_without_rag(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_nlu("out_of_scope", confidence=0.95)), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question("tell me a joke")
        self.assertEqual(out["route"], "out_of_scope")
        self.assertEqual(out["fallback"], "scope")

    def test_low_confidence_task_clarifies(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_nlu("task", topic="invoices",
                                  confidence=0.2)), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question("invoices??")
        self.assertEqual(out["route"], "clarify")


class TroubleshootTest(unittest.TestCase):
    def test_error_text_goes_down_code_path(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_nlu("troubleshoot", confidence=0.85)), \
                mock.patch.object(
                    orchestrator.explain, "locate_and_explain",
                    return_value={"located": True,
                                  "explanation": "it's in `f.py`",
                                  "sources": [{"path": "f.py",
                                               "line_start": 1,
                                               "line_end": 2}],
                                  "search_terms": ["ValidationError"],
                                  "total_hits": 3}):
            out = orchestrator.handle_question(
                "My Sales Invoice won't submit. Traceback ValidationError")
        self.assertEqual(out["route"], "code")
        self.assertIn("f.py", out["answer"])

    def test_vague_trouble_asks_for_error_text(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_nlu("troubleshoot", confidence=0.7)), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question(
                "My Sales Invoice won't submit.")
        self.assertEqual(out["route"], "clarify")
        self.assertIn("error", out["answer"].lower())


class DegradedNluTest(unittest.TestCase):
    def test_nlu_failure_with_strong_signal_still_routes_task(self) -> None:
        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=RuntimeError("llm down")), \
                mock.patch.object(
                    orchestrator.explain, "locate_and_explain",
                    return_value={"located": True, "explanation": "x",
                                  "sources": [], "search_terms": [],
                                  "total_hits": 0}):
            out = orchestrator.handle_question(
                "in this repo, where is it implemented — the pathsafe check")
        self.assertEqual(out["route"], "code")
        self.assertEqual(out["route_how"], "degraded")

    def test_nlu_failure_without_signal_clarifies(self) -> None:
        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=RuntimeError("llm down")), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question("invoices")
        self.assertEqual(out["route"], "clarify")
        self.assertEqual(out["route_how"], "degraded")

    def test_malformed_nlu_then_valid_recovers(self) -> None:
        calls = {"n": 0}

        def fake(messages, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return "not json at all"
            return json.dumps({"kind": "out_of_scope", "subtype": None,
                               "topic": None, "context_dependency": "none",
                               "confidence": 0.9})

        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=fake), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question("tell me a joke")
        self.assertEqual(out["route"], "out_of_scope")
        self.assertEqual(calls["n"], 2)


class TopicContinuationCondenseTest(unittest.TestCase):
    HIST = [{"role": "user",
             "content": "How do I create a Sales Invoice?"},
            {"role": "assistant", "content": "Open ... [1]."}]

    def _run(self, text, nlu, condensed):
        seen = {}

        def fake_retrieve(q, **k):
            seen["query"] = q
            return [{"title": "T", "section": "s", "url_or_path": "u",
                     "source_type": "public_doc", "score": 0.9,
                     "text": "x"}]

        with mock.patch.object(orchestrator, "_understand_with_llm",
                               return_value=nlu), \
                mock.patch.object(orchestrator.generator, "condense_followup",
                                  return_value=condensed) as m_cond, \
                mock.patch.object(orchestrator, "decide_route",
                                  return_value=("rag", "classifier")), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=fake_retrieve), \
                mock.patch.object(orchestrator.retriever,
                                  "classify_confidence",
                                  return_value="high"), \
                mock.patch.object(orchestrator.generator, "generate_answer",
                                  return_value="A [1]."), \
                mock.patch.object(orchestrator, "get_instance_versions",
                                  return_value={"status": "unavailable",
                                                "frappe": "?", "erpnext": "?"}):
            out = orchestrator.handle_question(text, history=list(self.HIST))
        return out, seen, m_cond

    def test_continuation_retrieves_on_condensed_question(self) -> None:
        out, seen, _ = self._run(
            "what about Purchase Invoices?",
            _nlu("task", topic="Purchase Invoices", confidence=0.9,
                 context_dependency="follows_topic"),
            "How do I create a Purchase Invoice?")
        self.assertEqual(out["route"], "rag")
        self.assertEqual(seen["query"], "How do I create a Purchase Invoice?")

    def test_condense_failure_falls_back_to_raw(self) -> None:
        _, seen, _ = self._run(
            "what about Purchase Invoices?",
            _nlu("task", topic="Purchase Invoices", confidence=0.9,
                 context_dependency="follows_topic"),
            None)
        self.assertEqual(seen["query"], "what about Purchase Invoices?")

    def test_self_contained_question_never_condenses(self) -> None:
        q = "How do I submit a Purchase Order?"
        with mock.patch.object(orchestrator.generator, "condense_followup",
                               side_effect=AssertionError("condense ran")):
            _, seen, m = self._run(
                q, _nlu("task", topic="purchase orders", confidence=0.9,
                        context_dependency="none"),
                "unused")
        self.assertEqual(seen["query"], q)
        m.assert_not_called()

    def test_greeting_after_topic_stays_greeting(self) -> None:
        with mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=_nlu("conversational", subtype="greeting",
                                  confidence=0.97)), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question("hey",
                                               history=list(self.HIST))
        self.assertEqual(out["route"], "smalltalk")


class NluTimeoutTest(unittest.TestCase):
    def test_nlu_uses_short_timeout_budget(self) -> None:
        import config
        seen = {}

        def fake_complete(messages, **kwargs):
            seen["timeout"] = kwargs.get("timeout")
            seen["retries"] = kwargs.get("num_retries")
            return json.dumps({"kind": "out_of_scope", "subtype": None,
                               "topic": None, "context_dependency": "none",
                               "confidence": 0.9})

        with mock.patch.object(orchestrator.generator, "_complete",
                               side_effect=fake_complete), \
                mock.patch.object(orchestrator.retriever, "retrieve",
                                  side_effect=AssertionError("RAG ran")):
            out = orchestrator.handle_question("tell me a joke")
        self.assertEqual(out["route"], "out_of_scope")
        self.assertEqual(seen["timeout"], config.NLU_TIMEOUT_SECONDS)
        self.assertLess(seen["timeout"], 120)
        # No transport-level retry: the corrective re-ask already serves
        # as the retry, so provider-down degrades after ~2x timeout, not 4x.
        self.assertEqual(seen["retries"], 0)


if __name__ == "__main__":
    unittest.main()
