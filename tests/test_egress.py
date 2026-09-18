"""Unit tests for the deny-by-default egress boundary (rag/egress.py).

Run: .venv/bin/python -m unittest discover -s tests -v

No real provider is ever contacted: grants are synthetic, payloads are
synthetic markers, and the no-switching guard is a static repository
check. Covers tasks 4.1–4.3 and the marker harness (task 6.5 unit part).
"""

import os
import unittest
from pathlib import Path
from unittest import mock

import config
from rag import egress


MARK = config.EGRESS_MARKER_PREFIX + "-SYNTHETIC-001"


class GrantTableTest(unittest.TestCase):
    def setUp(self) -> None:
        self._patcher = mock.patch.object(egress, "_grants", frozenset())
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_empty_table_denies_everything(self) -> None:
        for data_class in config.EGRESS_DATA_CLASSES:
            with self.assertRaises(egress.EgressDenied):
                egress.check(data_class, "ollama", "answer", "synthetic")
        self.assertEqual(egress.get_grants(), frozenset())

    def test_explicit_grant_permits_only_that_triple(self) -> None:
        egress.set_grants({("prompt", "ollama", "answer")})
        egress.check("prompt", "ollama", "answer", "synthetic")
        for triple in (("prompt", "ollama", "nlu"),
                       ("prompt", "openai", "answer"),
                       ("history", "ollama", "answer")):
            with self.assertRaises(egress.EgressDenied):
                egress.check(*triple, "synthetic")

    def test_revocation_without_restart(self) -> None:
        egress.set_grants({("prompt", "ollama", "answer")})
        egress.check("prompt", "ollama", "answer", "synthetic")
        egress.set_grants(frozenset())
        with self.assertRaises(egress.EgressDenied):
            egress.check("prompt", "ollama", "answer", "synthetic")

    def test_unknown_classes_and_purposes_denied(self) -> None:
        egress.set_grants({("prompt", "ollama", "answer")})
        with self.assertRaises(egress.EgressDenied):
            egress.check("nope", "ollama", "answer", "synthetic")
        with self.assertRaises(egress.EgressDenied):
            egress.check("prompt", "ollama", "nope", "synthetic")

    def test_guarded_call_runs_only_when_granted(self) -> None:
        ran = []
        with self.assertRaises(egress.EgressDenied):
            egress.guarded_call("prompt", "openai", "answer",
                                ran.append, "x", payload_text="synthetic")
        self.assertEqual(ran, [])
        egress.set_grants({("prompt", "openai", "answer")})
        self.assertEqual(
            egress.guarded_call("prompt", "openai", "answer",
                                lambda v: v, "x", payload_text="synthetic"),
            "x")


class SecretExclusionTest(unittest.TestCase):
    def test_configured_key_never_transmitted(self) -> None:
        with mock.patch.dict(os.environ,
                             {"NEXMATE_SERVICE_KEY": "s3cr3t-value-xyz"}):
            with self.assertRaises(egress.EgressDenied):
                egress.assert_no_secrets("call with s3cr3t-value-xyz inside")
            egress.assert_no_secrets("clean synthetic payload")

    def test_credential_shapes_and_headers_excluded(self) -> None:
        with self.assertRaises(egress.EgressDenied):
            egress.assert_no_secrets("key " + "a" * 64)
        with self.assertRaises(egress.EgressDenied):
            egress.assert_no_secrets("X-NexMate-Key: hidden")
        egress.assert_no_secrets("")

    def test_check_scans_payload_even_when_granted(self) -> None:
        egress.set_grants({("prompt", "ollama", "answer")})
        with mock.patch.dict(os.environ,
                             {"NEXMATE_SERVICE_KEY": "s3cr3t-value-xyz"}):
            with self.assertRaises(egress.EgressDenied):
                egress.check("prompt", "ollama", "answer",
                             "payload s3cr3t-value-xyz")


class NoSwitchingGuardTest(unittest.TestCase):
    def test_single_transmission_site(self) -> None:
        """litellm.completion is referenced only inside generator._complete;
        judges construct local clients only. A new direct call site fails."""
        import re
        root = Path(__file__).resolve().parents[1]
        hits = []
        for path in list((root / "rag").glob("*.py")) + [
                root / "orchestrator.py", root / "service" / "main.py"]:
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(r"(^|[^_.a-zA-Z])completion\s*\(", line):
                    hits.append(f"{path.name}:{i}")
        self.assertEqual(hits, ["generator.py:224"],
                         f"new direct provider call sites: {hits}")

    def test_judge_construction_is_local_only(self) -> None:
        text = (Path(__file__).resolve().parents[1]
                / "evaluation" / "ragas_eval.py").read_text(encoding="utf-8")
        self.assertIn("ChatOllama(", text)
        self.assertNotIn("ChatOpenAI(", text)
        self.assertNotIn("ChatAnthropic(", text)


class MarkerTest(unittest.TestCase):
    def test_marker_detection(self) -> None:
        self.assertTrue(egress.contains_marker(MARK))
        self.assertTrue(egress.contains_marker("prefix " + MARK + " suffix"))
        self.assertFalse(egress.contains_marker("ordinary synthetic text"))
        self.assertFalse(egress.contains_marker(None))

    def test_markers_prove_deny_grant_revoke_per_path(self) -> None:
        """Marker harness shape: each provider path demonstrates all three
        outcomes against synthetic markers without touching real providers."""
        paths = [
            ("prompt", "eval", "evaluate"),
            ("history", "eval", "evaluate"),
            ("company_content", "eval", "evaluate"),
        ]
        egress.set_grants(frozenset())
        for triple in paths:
            with self.assertRaises(egress.EgressDenied):  # deny
                egress.check(*triple, MARK)
        egress.set_grants(set(paths))
        for triple in paths:  # grant
            egress.check(*triple, MARK)
        egress.set_grants(frozenset())  # revoke
        for triple in paths:
            with self.assertRaises(egress.EgressDenied):
                egress.check(*triple, MARK)


class GuardedCompleteTest(unittest.TestCase):
    """Every generation call passes the boundary (task 4.1/6.5 unit part)."""

    def setUp(self) -> None:
        self._env = mock.patch.dict(
            os.environ, {"GENERATION_PROVIDER": "synthetic",
                         "GENERATION_MODEL": "m"})
        self._env.start()
        self.addCleanup(self._env.stop)
        self._grants = mock.patch.object(egress, "_grants", frozenset())
        self._grants.start()
        self.addCleanup(self._grants.stop)
        from rag import generator
        self._completion = mock.patch.object(
            generator, "completion", return_value=mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content="  ok  "))]))
        self._completion.start()
        self.addCleanup(self._completion.stop)
        self.generator = generator

    def test_ungranted_call_refused_before_transport(self) -> None:
        with self.assertRaises(egress.EgressDenied):
            self.generator._complete([{"role": "user", "content": "hi"}])
        self.generator.completion.assert_not_called()

    def test_granted_call_transmits_once(self) -> None:
        egress.set_grants({("prompt", "synthetic", "answer")})
        self.assertEqual(
            self.generator._complete([{"role": "user", "content": "hi"}]),
            "ok")
        self.generator.completion.assert_called_once()

    def test_secret_payload_refused_even_when_granted(self) -> None:
        egress.set_grants({("prompt", "synthetic", "answer")})
        with mock.patch.dict(os.environ,
                             {"NEXMATE_SERVICE_KEY": "s3cr3t-value-xyz"}):
            with self.assertRaises(egress.EgressDenied):
                self.generator._complete(
                    [{"role": "user", "content": "leak s3cr3t-value-xyz"}])
        self.generator.completion.assert_not_called()

    def test_purpose_is_enforced(self) -> None:
        egress.set_grants({("prompt", "synthetic", "answer")})
        with self.assertRaises(egress.EgressDenied):
            self.generator._complete([{"role": "user", "content": "hi"}],
                                     purpose="nlu")
        self.generator.completion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
