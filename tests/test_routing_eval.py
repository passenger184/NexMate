"""Routing evaluation: dataset-driven behavior checks.

Run: .venv/bin/python -m unittest discover -s tests -v
Dataset: evaluation/routing_cases.json

Methodology (deliberate): the NLU decision is scripted per case, so this
suite measures ROUTING WIRING (right capability? right tools? honest
fallback?) deterministically and fast. Raw model classification quality
is verified separately by hand against the live service (manual A-J
matrix in progress/JOURNAL.md), where model output cannot be scripted.

Each case asserts: selected route, whether RAG ran, which tools ran,
whether clarification happened, and the fallback category.
"""

import json
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import orchestrator

CASES = json.loads(
    (Path(__file__).resolve().parent.parent
     / "evaluation" / "routing_cases.json").read_text())


def _fake_chunk():
    return {"title": "T", "section": "s", "url_or_path": "u",
            "source_type": "public_doc", "score": 0.9, "text": "x"}


class RoutingEvalTest(unittest.TestCase):
    def test_routing_dataset(self) -> None:
        for case in CASES["cases"]:
            with self.subTest(case=case["id"]):
                self._run_case(case)

    def _run_case(self, case: dict) -> None:
        expect = case["expect"]
        calls = {"rag": 0, "tools": []}

        def fake_retrieve(*a, **k):
            calls["rag"] += 1
            return [_fake_chunk()]

        def fake_tool(name):
            def inner(*a, **k):
                calls["tools"].append(name)
                if name == "code.explain":
                    return {"located": True, "explanation": "x `f.py` [1].",
                            "sources": [{"path": "f.py", "line_start": 1,
                                         "line_end": 2}],
                            "search_terms": [], "total_hits": 1}
                if name == "erpnext.schema":
                    return {"data": {"doctype": "D", "module": "M",
                                     "naming_rule": "N", "is_submittable": 0,
                                     "fields": []}}
                if name == "erpnext.document":
                    return {"data": {"name": "N"}}
                return {"doctype": "D", "count": 0, "rows": [], "limit": 20}
            return inner

        nlu = case.get("nlu")
        patches = [
            # None is the graceful-degradation value: _understand_with_llm
            # catches its own internal failures and returns None (never
            # raises), so the degraded path is scripted by returning None,
            # not by raising through the mock.
            mock.patch.object(
                orchestrator, "_understand_with_llm",
                return_value=nlu),
            mock.patch.object(orchestrator.retriever, "retrieve",
                              side_effect=fake_retrieve),
            mock.patch.object(orchestrator.retriever,
                              "classify_confidence", return_value="high"),
            mock.patch.object(orchestrator.generator, "generate_answer",
                              return_value="Canned grounded answer [1]."),
            # Payload-grounded answering (erpnext branch) and the short
            # conversational reply both legitimately use _complete; what
            # this suite measures is whether those branches RUN (via the
            # rag/tools counters), not what the model says.
            mock.patch.object(orchestrator.generator, "_complete",
                              return_value="Canned grounded answer [1]."),
            mock.patch.object(orchestrator.erpnext, "get_doctype_schema",
                              side_effect=fake_tool("erpnext.schema")),
            mock.patch.object(orchestrator.erpnext, "get_document",
                              side_effect=fake_tool("erpnext.document")),
            mock.patch.object(orchestrator.erpnext, "list_documents",
                              side_effect=fake_tool("erpnext.list")),
            mock.patch.object(orchestrator.explain, "locate_and_explain",
                              side_effect=fake_tool("code.explain")),
            mock.patch.object(orchestrator, "get_instance_versions",
                              return_value={"status": "unavailable",
                                            "frappe": "unknown",
                                            "erpnext": "unknown"}),
        ]
        if case.get("extraction") is not None:
            patches.append(mock.patch.object(
                orchestrator, "_extract_erpnext_request",
                return_value=case["extraction"]))
        else:
            patches.append(mock.patch.object(
                orchestrator, "_extract_erpnext_request",
                side_effect=AssertionError("unexpected extraction")))
        # The task-level router (heuristic + LLM classifier) is a second
        # understanding decision, scripted per case exactly like the NLU
        # verdict above. Cases without it exercise the real decide_route
        # (heuristic hits and the rag-by-default fallback).
        if case.get("task_route") is not None:
            patches.append(mock.patch.object(
                orchestrator, "decide_route",
                return_value=tuple(case["task_route"])))

        # Patches live ONLY for this case (ExitStack, not addCleanup:
        # addCleanup would stack every case's mocks until the end of the
        # whole dataset run, leaking e.g. a scripted decide_route from one
        # case into all later cases).
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)

            out = orchestrator.handle_question(
                case["message"], history=case.get("history") or None,
                mode=case.get("mode", "developer"))

        self.assertEqual(out["route"], expect["route"],
                         f"wrong route for {case['id']}")
        self.assertEqual(calls["rag"] > 0, expect["rag_called"],
                         f"rag_called mismatch for {case['id']}")
        self.assertEqual(sorted(calls["tools"]), sorted(expect["tools_called"]),
                         f"tools mismatch for {case['id']}")
        self.assertEqual(out["route"] == "clarify",
                         expect["clarification"],
                         f"clarification mismatch for {case['id']}")
        self.assertEqual(out.get("fallback"), expect["fallback"],
                         f"fallback mismatch for {case['id']}")


if __name__ == "__main__":
    unittest.main()
