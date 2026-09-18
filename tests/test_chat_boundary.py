import itertools
import unittest
from contextlib import ExitStack
from unittest import mock

from fastapi.testclient import TestClient

import config
import orchestrator
from service import main
from tests.test_service_auth import KEY

ENVELOPE = {
    "question": "help", "user": "synthetic-user", "site": "synthetic-site",
    "mode": "employee", "execution_scope": "chat-only",
}
CONVERSATION = {
    "id": "NM-00001", "owner": "synthetic-user", "site": "synthetic-site",
    "turns": [{"role": "user", "content": "Prior synthetic question"},
              {"role": "assistant", "content": "Prior synthetic answer [1]."}],
}
NLU_TASK = {"kind": "task", "confidence": 1.0, "topic": None,
            "context_dependency": "none"}
CHUNK = {"title": "Synthetic manual", "section": "Steps", "url_or_path": "manual",
         "source_type": "public_doc", "text": "Synthetic reference text."}


class ChatBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(mock.patch.multiple(
            config, NEXMATE_SERVICE_KEY=KEY, NEXMATE_ENV="production",
            NEXMATE_DEV_UNAUTHENTICATED="0", NEXMATE_FRAPPE_SITE=ENVELOPE["site"]))
        self.forbidden = []
        for obj, names in (
            (main.retriever, ("get_index", "get_chroma_collection", "_get_embed_model")),
            (main.erpnext_tool, ("call_method", "get_document", "get_doctype_schema", "list_documents")),
            (main.files, ("read_project_file",)),
            (main.search_tool, ("search_project", "list_project_files")),
            (main.explain_tool, ("locate_and_explain",)),
            (main.edit_tool, ("propose_edit", "apply_edit")),
            (main.erpnext_write_tool, ("propose_write", "apply_write")),
            (orchestrator, ("get_instance_versions", "_extract_erpnext_request", "run_erpnext_branch")),
        ):
            for name in names:
                patched = self.stack.enter_context(mock.patch.object(
                    obj, name, side_effect=AssertionError("forbidden boundary call")))
                self.forbidden.append(patched)
        self.retrieve = self.stack.enter_context(mock.patch.object(
            main.retriever, "retrieve", return_value=[CHUNK]))
        self.confidence = self.stack.enter_context(mock.patch.object(
            main.retriever, "classify_confidence", return_value="high"))
        self.generate = self.stack.enter_context(mock.patch.object(
            main.generator, "generate_answer", return_value="Synthetic answer [1]."))
        self.complete = self.stack.enter_context(mock.patch.object(
            main.generator, "_complete", side_effect=AssertionError("unmocked model call")))
        self.condense = self.stack.enter_context(mock.patch.object(
            main.generator, "condense_followup", return_value=None))
        self.logs = self.stack.enter_context(mock.patch.object(main.logger, "info"))
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.assert_no_tools)

    def assert_no_tools(self) -> None:
        for patched in self.forbidden:
            patched.assert_not_called()

    def post(self, payload=None, credential=True):
        return self.client.post("/orchestrate", json=ENVELOPE if payload is None else payload,
                                headers={"X-NexMate-Key": KEY} if credential else {})

    def test_complete_envelope_both_personas_stateless_and_owned(self) -> None:
        for mode, conversation in itertools.product(
                ("employee", "developer"), (None, CONVERSATION)):
            payload = dict(ENVELOPE, mode=mode)
            if conversation is not None:
                payload["conversation"] = dict(
                    conversation, owner=ENVELOPE["user"], site=ENVELOPE["site"])
            response = self.post(payload)
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["mode"], mode)
            self.assertEqual(data["conversation_id"],
                             CONVERSATION["id"] if conversation else None)
            self.assertEqual(data["version_info"], orchestrator.unavailable_versions())
            self.assertEqual(data["route"], "capability")
            self.assertEqual(data["answer"], orchestrator.CHAT_ONLY_CAPABILITIES)
            if conversation is not None:
                self.assertEqual(data["turn_count"], 2)  # one prior pair + this turn
            else:
                self.assertIsNone(data["turn_count"])
        for marker in (KEY, ENVELOPE["user"], ENVELOPE["site"], "X-NexMate-Key"):
            self.assertNotIn(marker, str(self.logs.call_args_list))
        self.complete.assert_not_called()
        self.retrieve.assert_not_called()

    def test_owned_turns_flow_into_history(self) -> None:
        payload = dict(ENVELOPE, question="Explain this project",
                       conversation=dict(CONVERSATION))
        with mock.patch.object(orchestrator, "_understand_with_llm", return_value=NLU_TASK), \
                mock.patch.object(orchestrator, "decide_route", return_value=("rag", "classifier")):
            response = self.post(payload)
        self.assertEqual(response.status_code, 200, response.text)
        # Supplied owned turns reach generation as history; inference
        # persists nothing (no store exists to assert against).
        self.generate.assert_called_with(
            "Explain this project", [CHUNK], CONVERSATION["turns"],
            extra_system="", persona="employee")
        self.assertEqual(response.json()["conversation_id"], CONVERSATION["id"])
        self.assertFalse(hasattr(main, "session_store"))

    def test_legacy_session_id_refused_explicitly(self) -> None:
        # Retired caller-owned continuity fails loud, never silently stateless.
        for payload in ({"question": "help", "session_id": "Legacy_123-id"},
                        dict(ENVELOPE, session_id="Legacy_123-id")):
            response = self.post(payload)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json(), {"detail": "invalid_orchestrate_request"})
        self.retrieve.assert_not_called()
        self.complete.assert_not_called()
        self.logs.assert_not_called()

    def test_over_budget_conversation_refused(self) -> None:
        # Wire budget mirrors the prompt budget with headroom (auth.py);
        # Frappe enforces the tighter forward budget before sending.
        huge = "x" * (config.SESSION_MAX_CHARS * 4 + 1)
        cases = [
            dict(CONVERSATION, turns=[{"role": "user", "content": huge}]),
            dict(CONVERSATION, turns=[{"role": "user", "content": "q"}] * 200),
            dict(CONVERSATION, turns=[{"role": "note", "content": "q"}]),
            dict(CONVERSATION, turns=[{"role": "user"}]),
            dict(CONVERSATION, turns="not-a-list"),
            dict(CONVERSATION, owner="someone-else"),
            dict(CONVERSATION, site="wrong-site"),
            dict(CONVERSATION, id="../evil"),
            dict(CONVERSATION, id=""),
            {"id": "NM-1", "owner": "synthetic-user", "site": "synthetic-site"},
            dict(CONVERSATION, extra="field"),
        ]
        for conv in cases:
            with self.subTest(conv=str(conv)[:60]):
                response = self.post(dict(ENVELOPE, conversation=conv))
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json(), {"detail": "invalid_conversation_context"})
                self.assertNotIn(KEY, response.text)
                self.assertNotIn(ENVELOPE["user"], response.text)
        # Non-dict conversation values fail even earlier, at the schema.
        response = self.post(dict(ENVELOPE, conversation="not-a-dict"))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "invalid_orchestrate_request"})
        self.retrieve.assert_not_called()
        self.complete.assert_not_called()
        self.logs.assert_not_called()

    def test_reject_invalid_envelopes_before_any_work(self) -> None:
        cases = []
        for field in ("user", "site", "execution_scope", "mode"):
            payload = dict(ENVELOPE)
            del payload[field]
            cases.append(payload)
            for invalid in (None, "", 42, [], {}, True):
                cases.append(dict(ENVELOPE, **{field: invalid}))
        for field in ("user", "site"):
            for invalid in (" leading", "trailing ", "a\nb", "a\x00b", "a\x7fb",
                            "a\x85b", "a\u200bb", "x" * 256):
                cases.append(dict(ENVELOPE, **{field: invalid}))
        cases.extend([
            dict(ENVELOPE, user="Guest"), dict(ENVELOPE, execution_scope="tools"),
            dict(ENVELOPE, mode="admin"), dict(ENVELOPE, site="wrong-site"),
            dict(ENVELOPE, question=" "),
            dict(ENVELOPE, question="x" * 2001),
        ])
        for field in ("user", "site", "execution_scope"):
            cases.append({"question": "help", field: None})
        for operation in ("read", "search", "explain", "file", "edit", "create",
                          "update", "propose", "apply", "approve", "reject", "reset"):
            cases.append(dict(ENVELOPE, operation=operation))
        for payload in cases:
            with self.subTest(fields=list(payload)):
                response = self.post(payload)
                self.assertIn(response.status_code, (403, 422), response.text)
                self.assertNotIn(KEY, response.text)
                self.assertNotIn(ENVELOPE["user"], response.text)
        self.retrieve.assert_not_called()
        self.complete.assert_not_called()
        self.logs.assert_not_called()

    def test_expected_site_missing_or_invalid_refuses(self) -> None:
        for site in (None, "", " synthetic-site", "a\nb", "x" * 256, 42):
            with mock.patch.object(config, "NEXMATE_FRAPPE_SITE", site):
                response = self.post(dict(ENVELOPE))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"detail": "invalid_frappe_site_config"})

    def test_canonical_identifiers_are_not_repaired(self) -> None:
        for user in ("Administrator", "CaseSensitive", "not-an-email", "x" * 255):
            response = self.post(dict(ENVELOPE, user=user))
            self.assertEqual(response.status_code, 200)
        response = self.post(dict(ENVELOPE, site=ENVELOPE["site"].upper()))
        self.assertEqual(response.status_code, 403)

    def test_dev_bypass_never_authenticates_envelope(self) -> None:
        with mock.patch.multiple(config, NEXMATE_ENV="development", NEXMATE_DEV_UNAUTHENTICATED="1"):
            for key in (KEY, None):
                with mock.patch.object(config, "NEXMATE_SERVICE_KEY", key):
                    for payload in (ENVELOPE, {"question": "help", "user": None},
                                    dict(ENVELOPE, conversation=dict(CONVERSATION))):
                        response = self.post(payload, credential=False)
                        self.assertEqual(response.status_code, 401)
                        self.assertEqual(response.json(), {"detail": "gateway_credential_required"})
            self.assertEqual(self.post().status_code, 200)

    def test_forced_routes_in_both_personas(self) -> None:
        for mode, route, question in itertools.product(
                ("developer", "employee"), ("code", "erpnext"),
                ("List all invoices", "What files are in this project?",
                 "Read this file", "Approve the edit", "Reset my session")):
            with mock.patch.object(orchestrator, "_understand_with_llm", return_value=NLU_TASK), \
                    mock.patch.object(orchestrator, "decide_route", return_value=(route, "classifier")):
                response = self.post(dict(ENVELOPE, question=question, mode=mode))
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["answer"], orchestrator.CHAT_ONLY_UNAVAILABLE)
            self.assertEqual(data["route_how"], "classifier+chat-only-denied")
            self.assertEqual(data["confidence"], "low")
            self.assertEqual(data["sources"], [])
        self.retrieve.assert_not_called()
        self.generate.assert_not_called()

    def test_troubleshooting_and_degraded_routes_are_denied(self) -> None:
        for mode in ("employee", "developer"):
            cases = ((dict(NLU_TASK, kind="troubleshoot"), "Traceback: ValueError: failure"),
                     (None, "How many invoices are in our erpnext instance?"),
                     (None, "Where is it implemented in this project?"))
            for nlu, question in cases:
                with mock.patch.object(orchestrator, "_understand_with_llm", return_value=nlu):
                    response = self.post(dict(ENVELOPE, question=question, mode=mode))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["route_how"].endswith("+chat-only-denied"))
        self.retrieve.assert_not_called()

    def test_followup_rewrites_cannot_change_scope(self) -> None:
        history_payload = dict(ENVELOPE, question="What about that?",
                               conversation=dict(
                                   CONVERSATION,
                                   turns=[{"role": "user",
                                           "content": "Prior synthetic question"}]))
        with mock.patch.object(orchestrator, "_understand_with_llm", return_value=dict(
                NLU_TASK, context_dependency="follows_topic", topic="code", chat_only=False,
                execution_scope="tools")), \
                mock.patch.object(orchestrator, "decide_route", return_value=("code", "classifier")):
            response = self.post(history_payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["route_how"].endswith("+chat-only-denied"))
        self.assertGreaterEqual(self.condense.call_count, 2)
        self.retrieve.assert_not_called()

    def test_rag_keeps_citations_persona_filtering_and_no_version_calls(self) -> None:
        for mode in ("employee", "developer"):
            with mock.patch.object(orchestrator, "_understand_with_llm", return_value=NLU_TASK), \
                    mock.patch.object(orchestrator, "decide_route", return_value=("rag", "classifier")):
                response = self.post(dict(ENVELOPE, question="Explain this project", mode=mode))
            self.assertEqual(response.status_code, 200, response.text)
            self.retrieve.assert_called_with("Explain this project", include_company=mode == "developer")
            self.generate.assert_called_with("Explain this project", [CHUNK], [],
                                             extra_system="", persona=mode)
            self.assertEqual(response.json()["sources"][0]["url_or_path"], "manual")
        for marker in (KEY, ENVELOPE["user"], ENVELOPE["site"], "X-NexMate-Key"):
            self.assertNotIn(marker, str(self.generate.call_args_list))

    def test_all_conversational_paths_and_low_rag_skip_versions(self) -> None:
        for nlu in (dict(NLU_TASK, kind="conversational", subtype="greeting"),
                    dict(NLU_TASK, kind="capability"), dict(NLU_TASK, kind="clarify"),
                    dict(NLU_TASK, kind="out_of_scope"), dict(NLU_TASK, kind="troubleshoot"), None):
            with mock.patch.object(orchestrator, "_understand_with_llm", return_value=nlu):
                response = self.post(dict(ENVELOPE, question="Something vague"))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["version_info"], orchestrator.unavailable_versions())
        for confidence in ("low", "no_match"):
            self.confidence.return_value = confidence
            with mock.patch.object(orchestrator, "_understand_with_llm", return_value=NLU_TASK), \
                    mock.patch.object(orchestrator, "decide_route", return_value=("rag", "default")):
                response = self.post(dict(ENVELOPE, question="Explain a DocType"))
            self.assertEqual(response.json()["confidence"], confidence)
        self.generate.assert_not_called()

    def test_scope_aware_guidance_offers_only_documentation(self) -> None:
        topic = "live data and source code"
        cases = (
            (None, "clarify", "degraded",
             orchestrator.capabilities.render_clarification(None)),
            (dict(NLU_TASK, kind="clarify", topic=topic), "clarify", "classifier",
             orchestrator.capabilities.render_clarification(topic)),
            (dict(NLU_TASK, confidence=0.0, topic=topic), "clarify", "classifier",
             orchestrator.capabilities.render_clarification(topic)),
            (dict(NLU_TASK, kind="out_of_scope"), "out_of_scope", "classifier",
             orchestrator.capabilities.render_out_of_scope()),
            (dict(NLU_TASK, kind="troubleshoot"), "clarify", "classifier",
             orchestrator._TROUBLESHOOT_CLARIFY),
        )
        for mode, (nlu, route, how, legacy_answer) in itertools.product(
                ("employee", "developer"), cases):
            with self.subTest(mode=mode, kind=nlu, how=how), \
                    mock.patch.object(orchestrator, "_understand_with_llm", return_value=nlu):
                response = self.post(dict(ENVELOPE, question="Something vague", mode=mode))
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["route"], route)
                self.assertEqual(data["route_how"], how)
                self.assertEqual(data["confidence"], "low")
                self.assertEqual(data["sources"], [])
                answer = data["answer"].lower()
                self.assertIn("indexed documentation", answer)
                self.assertIn("erpnext/frappe", answer)
                for unsupported in ("live", "source code", "repository", "file",
                                    "connected instance", "look up", "lists", "statuses",
                                    "counts", "diagnose", "traceback", "approve", "reset"):
                    self.assertNotIn(unsupported, answer)
                legacy = orchestrator.handle_question("Something vague", mode=mode)
                self.assertEqual(legacy["answer"], legacy_answer)
                self.assertEqual(legacy["route"], route)
        self.complete.assert_not_called()
        self.retrieve.assert_not_called()
        self.generate.assert_not_called()

    def test_direct_stateless_mode_and_dispatch_remain_separate(self) -> None:
        with mock.patch.object(orchestrator, "handle_question", wraps=orchestrator.handle_question) as handle, \
                mock.patch.object(orchestrator, "get_instance_versions", return_value={"status": "legacy"}) as versions:
            response = self.post({"question": "help", "mode": "developer"})
            self.assertEqual(response.status_code, 200)
            handle.assert_called_once_with("help", None, [], mode="developer", chat_only=False)
            versions.assert_called_once_with()
        self.assertIn("Live ERPNext data lookups", response.json()["answer"])

    def test_legacy_direct_tool_retained_behind_gate(self) -> None:
        with mock.patch.object(main.search_tool, "search_project", return_value={
                "query": "synthetic", "regex_source": "synthetic", "literal_fallback": False,
                "ignore_case": False, "matches": [], "total_matches": 0, "truncated": False,
                "files_searched": 0, "skipped_binary": 0, "skipped_large": 0}) as search:
            for credential, status in ((False, 401), (True, 200)):
                response = self.client.post("/tools/search", json={"query": "synthetic"},
                    headers={"X-NexMate-Key": KEY} if credential else {})
                self.assertEqual(response.status_code, status)
            search.assert_called_once_with("synthetic", False)

    def test_route_inventory_and_outer_cors_gate(self) -> None:
        expected = {"/ask", "/orchestrate", "/health",
                    "/tools/read_file", "/tools/search", "/tools/explain",
                    "/tools/propose_edit", "/tools/apply_edit", "/tools/erpnext/schema",
                    "/tools/erpnext/document", "/tools/erpnext/list",
                    "/tools/erpnext_write/propose", "/tools/erpnext_write/apply",
                    "/ui", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
        self.assertEqual({route.path for route in main.app.routes}, expected)
        for path, method in itertools.product(expected - {"/health"} | {"/unknown", "/health/"},
                                              ("GET", "POST", "OPTIONS")):
            response = self.client.request(method, path, headers={
                "Origin": "http://localhost", "Access-Control-Request-Method": "POST"})
            self.assertEqual(response.status_code, 401, path)
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_invalid_request_body_is_not_reflected(self) -> None:
        response = self.client.post("/orchestrate", content='{"user":"' + KEY,
                                    headers={"X-NexMate-Key": KEY, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(KEY, response.text)
        response = self.post(dict(ENVELOPE, mode={"synthetic-secret": KEY}))
        self.assertEqual(response.json(), {"detail": "invalid_orchestrate_request"})
        self.logs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
