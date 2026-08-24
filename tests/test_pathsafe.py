"""Unit tests for tools.pathsafe + tools.files (Phase 2 Task 1).

Run: .venv/bin/python -m unittest discover -s tests -v

Uses a temporary directory as the project root so the real repo is never
touched. Covers every rejection property PHASE_2_SPEC.md's DoD requires:
traversal, absolute-outside, symlink-out are REJECTED loudly; in-root
reads work, including via an in-root symlink.
"""

import os
import tempfile
import unittest
from pathlib import Path

from tools.files import (
    BinaryFileError,
    FileTooLargeError,
    NotAFileError,
    read_project_file,
)
from tools.pathsafe import PathOutsideRootError, resolve_in_project


class PathSafeTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text(
            "def hello():\n    return 'hi'\n", encoding="utf-8"
        )
        self.addCleanup(self._tmp.cleanup)


class TestResolveInProject(PathSafeTestBase):
    def test_relative_path_resolves_inside_root(self) -> None:
        resolved = resolve_in_project("src/main.py", root=self.root)
        self.assertEqual(resolved, self.root / "src" / "main.py")

    def test_absolute_path_inside_root_allowed(self) -> None:
        resolved = resolve_in_project(
            str(self.root / "src" / "main.py"), root=self.root
        )
        self.assertTrue(resolved.is_relative_to(self.root))

    def test_dotdot_traversal_rejected(self) -> None:
        with self.assertRaises(PathOutsideRootError):
            resolve_in_project("src/../../etc/passwd", root=self.root)

    def test_deep_traversal_rejected(self) -> None:
        with self.assertRaises(PathOutsideRootError):
            resolve_in_project("a/b/c/../../../../../../etc/passwd",
                               root=self.root)

    def test_absolute_outside_rejected(self) -> None:
        with self.assertRaises(PathOutsideRootError):
            resolve_in_project("/etc/passwd", root=self.root)

    def test_symlink_pointing_outside_rejected(self) -> None:
        link = self.root / "src" / "escape"
        os.symlink("/etc", link)
        with self.assertRaises(PathOutsideRootError):
            resolve_in_project("src/escape/passwd", root=self.root)

    def test_symlink_inside_root_allowed(self) -> None:
        target = self.root / "src" / "main.py"
        link = self.root / "link_to_main.py"
        os.symlink(target, link)
        resolved = resolve_in_project("link_to_main.py", root=self.root)
        self.assertEqual(resolved, target)

    def test_empty_path_rejected(self) -> None:
        with self.assertRaises(PathOutsideRootError):
            resolve_in_project("", root=self.root)

    def test_error_names_the_offending_paths(self) -> None:
        with self.assertRaises(PathOutsideRootError) as ctx:
            resolve_in_project("../outside.txt", root=self.root)
        msg = str(ctx.exception)
        self.assertIn("'../outside.txt'", msg)
        self.assertIn(str(self.root), msg)


class TestReadProjectFile(PathSafeTestBase):
    def test_reads_a_real_file(self) -> None:
        info = self._read("src/main.py")
        self.assertEqual(info["path"], "src/main.py")
        self.assertIn("hello", info["content"])
        self.assertEqual(info["line_count"], 2)
        self.assertEqual(info["size_bytes"], len(info["content"].encode()))

    def _read(self, raw: str) -> dict:
        # bind the project root for reader-level tests
        from unittest import mock

        with mock.patch("config.PROJECT_ROOT", self.root):
            return read_project_file(raw)

    def test_missing_file_is_loud(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self._read("src/nope.py")

    def test_directory_read_rejected(self) -> None:
        with self.assertRaises(NotAFileError):
            self._read("src")

    def test_traversal_rejected_at_reader_level(self) -> None:
        with self.assertRaises(PathOutsideRootError):
            self._read("../../etc/passwd")

    def test_oversized_file_refused_not_truncated(self) -> None:
        big = self.root / "big.bin.txt"
        big.write_text("x" * 2_000_001, encoding="utf-8")
        from unittest import mock

        with mock.patch("config.PROJECT_ROOT", self.root), \
                mock.patch("config.MAX_READ_FILE_BYTES", 1_000_000):
            with self.assertRaises(FileTooLargeError):
                read_project_file("big.bin.txt")

    def test_binary_file_refused_with_explanation(self) -> None:
        blob = self.root / "blob.bin"
        blob.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")
        with self.assertRaises(BinaryFileError):
            self._read("blob.bin")


if __name__ == "__main__":
    unittest.main()
