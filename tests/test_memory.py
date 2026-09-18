"""Unit tests for Phase 4: session continuity + resolved-issue memory.

Run: .venv/bin/python -m unittest discover -s tests -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from service import main
from tools.memory import build_resolution_document, read_commit  # noqa: F401


class LegacyRetirementTest(unittest.TestCase):
    """The JSON session store is deleted: continuity lives in Frappe-owned
    records. These tests pin the removal (no module, no routes, no config)."""

    def test_session_store_module_is_gone(self) -> None:
        self.assertFalse(hasattr(main, "session_store"))
        with self.assertRaises(ImportError):
            import service.session_store  # noqa: F401

    def test_no_session_routes_remain(self) -> None:
        paths = {route.path for route in main.app.routes}
        self.assertNotIn("/tools/session/reset", paths)

    def test_no_session_config_remains(self) -> None:
        self.assertFalse(hasattr(config, "SESSIONS_DIR"))
        self.assertFalse(hasattr(config, "SESSION_ID_PATTERN"))


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
