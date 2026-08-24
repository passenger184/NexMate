"""Unit tests for Phase 4: session continuity + resolved-issue memory.

Run: .venv/bin/python -m unittest discover -s tests -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from service import session_store
from tools.memory import build_resolution_document, read_commit  # noqa: F401


class SessionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._patcher = mock.patch.object(config, "SESSIONS_DIR",
                                          self.root / "sessions")
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_roundtrip_and_order(self) -> None:
        session_store.append_turn("s1", "user", "What gates /ask?")
        session_store.append_turn("s1", "assistant", "Cosine bands do.")
        history = session_store.load_history("s1")
        self.assertEqual([t["role"] for t in history],
                         ["user", "assistant"])
        self.assertIn("gates", history[0]["content"])

    def test_missing_session_is_empty(self) -> None:
        self.assertEqual(session_store.load_history("nope"), [])

    def test_delete_clears_but_knowledge_untouched(self) -> None:
        session_store.append_turn("s2", "user", "hi")
        self.assertTrue(session_store.delete_session("s2"))
        self.assertFalse(session_store.delete_session("s2"))  # idempotent
        self.assertEqual(session_store.load_history("s2"), [])

    def test_invalid_session_ids_never_touch_disk(self) -> None:
        for bad in ("../evil", "", "a" * 65, "has space", "slash/"):
            with self.assertRaises(session_store.InvalidSessionId):
                session_store.validate_session_id(bad)

    def test_history_budget_trims_to_recent(self) -> None:
        for i in range(12):
            session_store.append_turn("s3", "user", f"q{i}" * 50)
            session_store.append_turn("s3", "assistant", f"a{i}" * 50)
        history = session_store.load_history("s3")
        self.assertLessEqual(len(history), config.SESSION_MAX_TURNS)
        # most recent content survives
        self.assertIn("a11", history[-1]["content"][:200])


class BuildResolutionTest(unittest.TestCase):
    def test_document_shape_and_unique_url(self) -> None:
        text1, meta1 = build_resolution_document(
            "README.md", "abc1234", "docs: fix chunk count",
            context="Index count drifted from README.",
            diff="--- a/README.md\n+++ b/README.md\n@@ ...")
        text2, meta2 = build_resolution_document(
            "README.md", "def5678", "docs: another fix",
            context="Other reason.", diff="diff")
        self.assertIn("Resolved issue in README.md (commit abc1234)", text1)
        self.assertIn("Why it came up:", text1)
        self.assertIn("docs: fix chunk count", text1)
        self.assertNotEqual(meta1["url_or_path"], meta2["url_or_path"])
        self.assertEqual(meta1["source_type"], "resolved_issue")

    def test_diff_budget_truncates_long_diffs(self) -> None:
        text, _ = build_resolution_document(
            "f.py", "aaa1111", "m: msg here",
            context="ctx", diff="x" * 10_000)
        self.assertLess(len(text), config.RESPLIT_THRESHOLD_CHARS + 200)
        self.assertIn("[diff truncated]", text)


class BackfillReadCommitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        import subprocess

        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=self.root,
                                  capture_output=True, text=True).stdout
        self._git = git
        git("init", "-q")
        git("config", "user.email", "t@e.com")
        git("config", "user.name", "T")
        (self.root / "f.txt").write_text("one\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-m", "first: baseline")

    def test_read_commit_parses_real_repo(self) -> None:
        with mock.patch("config.PROJECT_ROOT", self.root):
            info = read_commit("HEAD")
        self.assertTrue(info["hash"])
        self.assertEqual(info["message"], "first: baseline")
        self.assertEqual(info["files"], ["f.txt"])
        self.assertIn("+one", info["diff"])


if __name__ == "__main__":
    unittest.main()
