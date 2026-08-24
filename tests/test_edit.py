"""Integration tests for tools.edit (Phase 2 Task 3).

Run: .venv/bin/python -m unittest discover -s tests -v

Uses a REAL throwaway git repo (commits included) so the clean-tree gate,
tracked/ignored checks, and atomic-commit behavior are exercised against
actual git, not mocks. Only the LLM-adjacent layers are mocked elsewhere;
nothing is mocked here because there's nothing to mock.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import edit
from tools.pathsafe import PathOutsideRootError


class EditFlowTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.write("app/service.py",
                   "def handler():\n    return 1\n\n\ndef other():\n"
                   "    return 2\n")
        self.write(".gitignore", ".env\ncache/\n")
        self.write("cache/artifact.txt", "junk\n")
        self.commit_all("initial")

    def git(self, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=self.root,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssertionError(f"git {args} failed: {proc.stderr}")
        return proc.stdout

    def write(self, rel: str, content: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def commit_all(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-m", message)

    def head_count(self) -> int:
        return len(self.git("rev-list", "HEAD").splitlines())

    def propose(self, path: str, find: str, replace: str,
                message: str = "update service handler docstring") -> dict:
        with mock.patch("config.PROJECT_ROOT", self.root), \
                mock.patch("config.EDIT_PROPOSAL_TTL_MINUTES", 15):
            return edit.propose_edit(path, find, replace, message)

    def apply(self, proposal_id: str, confirmed: bool) -> dict:
        with mock.patch("config.PROJECT_ROOT", self.root):
            return edit.apply_edit(proposal_id, confirmed)


class TestProposeGates(EditFlowTestBase):
    def test_dirty_tree_refused_with_guidance(self) -> None:
        self.write("uncommitted.py", "x = 1\n")  # untracked -> dirty
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.propose("app/service.py", "return 1", "return 11")
        self.assertEqual(ctx.exception.category, "dirty_tree")
        self.assertIn("Commit or stash", ctx.exception.detail)

    def test_outside_root_refused(self) -> None:
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.propose("../../outside.txt", "a", "b")
        self.assertEqual(ctx.exception.category, "outside_root")

    def test_ignored_file_refused_distinctly(self) -> None:
        self.write(".env", "SECRET=1\n")  # ignored via .gitignore
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.propose(".env", "SECRET=1", "SECRET=2")
        self.assertEqual(ctx.exception.category, "ignored_file")

    def test_untracked_file_refused_distinctly(self) -> None:
        self.write("newfile.py", "v = 1\n")  # not ignored, not tracked
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.propose("newfile.py", "v = 1", "v = 2")
        self.assertEqual(ctx.exception.category, "untracked_file")
        self.assertIn("git add", ctx.exception.detail)

    def test_missing_file_refused(self) -> None:
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.propose("app/ghost.py", "a", "b")
        self.assertEqual(ctx.exception.category, "not_found")

    def test_zero_and_multiple_matches_refused_with_counts(self) -> None:
        with self.assertRaises(edit.EditRefusal) as zero:
            self.propose("app/service.py", "not present", "x")
        self.assertIn("0 times", zero.exception.detail)
        with self.assertRaises(edit.EditRefusal) as multi:
            self.propose("app/service.py", "return", "yield")
        self.assertIn("2 times", multi.exception.detail)

    def test_no_op_refused(self) -> None:
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.propose("app/service.py", "return 1", "return 1")
        self.assertEqual(ctx.exception.category, "no_op")

    def test_short_message_refused(self) -> None:
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.propose("app/service.py", "return 1", "return 11", "fix")
        self.assertEqual(ctx.exception.category, "bad_message")


class TestProposeAndApply(EditFlowTestBase):
    def test_proposal_returns_diff_without_touching_disk(self) -> None:
        before = (self.root / "app/service.py").read_text()
        proposal = self.propose("app/service.py",
                                "def handler():",
                                '"""Handle it."""\ndef handler():')
        after = (self.root / "app/service.py").read_text()
        self.assertEqual(before, after)          # nothing applied yet
        self.assertIn("--- a/app/service.py", proposal["diff"])
        self.assertIn('+++ b/app/service.py', proposal["diff"])
        self.assertIn('+"""Handle it."""', proposal["diff"])
        self.assertTrue(proposal["proposal_id"])

    def test_apply_requires_explicit_confirmation(self) -> None:
        proposal = self.propose("app/service.py",
                                "return 1", "return 11")
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.apply(proposal["proposal_id"], confirmed=False)
        self.assertEqual(ctx.exception.category, "confirmation_required")
        self.assertIn("return 1", (self.root / "app/service.py").read_text())

    def test_full_edit_cycle_is_one_atomic_commit(self) -> None:
        commits_before = self.head_count()
        proposal = self.propose(
            "app/service.py", "return 1", "return 11",
            message="service: bump handler result for retry logic",
        )
        result = self.apply(proposal["proposal_id"], confirmed=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["path"], "app/service.py")
        self.assertEqual(result["message"],
                         "service: bump handler result for retry logic")
        content = (self.root / "app/service.py").read_text()
        self.assertIn("return 11", content)
        # exactly one new commit, touching exactly one file
        self.assertEqual(self.head_count(), commits_before + 1)
        last = self.git("show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(last, ["app/service.py"])
        self.assertEqual(result["commit_hash"],
                         self.git("rev-parse", "--short", "HEAD").strip())
        # proposal is one-shot
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.apply(proposal["proposal_id"], confirmed=True)
        self.assertEqual(ctx.exception.category, "unknown_proposal")

    def test_stale_proposal_refused_when_file_changed(self) -> None:
        proposal = self.propose("app/service.py",
                                "return 1", "return 11")
        # someone edits the file behind the tool's back
        p = self.root / "app/service.py"
        p.write_text(p.read_text() + "\n# stray comment\n", encoding="utf-8")
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.apply(proposal["proposal_id"], confirmed=True)
        self.assertEqual(ctx.exception.category, "stale_proposal")
        # nothing was written by the refused apply
        self.assertIn("# stray comment", p.read_text())
        self.assertNotIn("return 11", p.read_text())

    def test_stale_proposal_refused_when_tree_dirtied(self) -> None:
        proposal = self.propose("app/service.py",
                                "return 1", "return 11")
        self.write("other_dirty.py", "q = 1\n")  # dirties the tree
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.apply(proposal["proposal_id"], confirmed=True)
        self.assertEqual(ctx.exception.category, "dirty_tree")

    def test_unknown_proposal_is_loud(self) -> None:
        with self.assertRaises(edit.EditRefusal) as ctx:
            self.apply("deadbeef0000", confirmed=True)
        self.assertEqual(ctx.exception.category, "unknown_proposal")


if __name__ == "__main__":
    unittest.main()
