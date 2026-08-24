"""Unit tests for tools.search + tools.explain (Phase 2 Task 2).

Run: .venv/bin/python -m unittest discover -s tests -v

Uses a throwaway git repo so .gitignore behavior is exercised against real
git, and mocks the single LLM call site for explain-path tests.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from tools import explain, search


class GitRepoTestBase(unittest.TestCase):
    """A temp dir that is a real git repo with committed + ignored files."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._git("init", "-q")
        self._write("app/worker.py",
                    "def run_job():\n    raise ValidationError('bad')\n")
        self._write("app/util.py", "def helper():\n    return 42\n")
        self._write(".gitignore", "secret.txt\ndata/\n")
        self._write("secret.txt", "token = 'abc123'\n")
        self._write("data/cache.json", "{}\n")

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, capture_output=True)

    def _write(self, rel: str, content: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


class TestSearchProject(GitRepoTestBase):
    def search(self, query: str, **kw) -> dict:
        with mock.patch("config.PROJECT_ROOT", self.root):
            return search.search_project(query, **kw)

    def test_finds_matches_with_line_numbers(self) -> None:
        result = self.search("ValidationError")
        paths = {m["path"] for m in result["matches"]}
        self.assertEqual(paths, {"app/worker.py"})
        hit = result["matches"][0]
        self.assertEqual(hit["line_number"], 2)
        self.assertIn("raise ValidationError", hit["line"])

    def test_gitignored_files_excluded_from_results(self) -> None:
        result = self.search("abc123")          # only in secret.txt
        self.assertEqual(result["matches"], [])
        result = self.search("cache")           # only under data/
        self.assertNotIn(
            "data/cache.json", [m["path"] for m in result["matches"]])

    def test_untracked_but_not_ignored_files_included(self) -> None:
        # worker.py etc. were never git-added; ls-files --others covers them.
        result = self.search("helper")
        self.assertEqual(len(result["matches"]), 1)

    def test_invalid_regex_degrades_to_literal(self) -> None:
        result = self.search("run_job(")
        self.assertTrue(result["literal_fallback"])
        self.assertEqual(result["matches"][0]["path"], "app/worker.py")

    def test_ignore_case_flag(self) -> None:
        self.assertEqual(self.search("validationerror")["total_matches"], 0)
        self.assertEqual(
            self.search("validationerror", ignore_case=True)["total_matches"],
            1,
        )

    def test_case_sensitive_by_default(self) -> None:
        self.assertEqual(self.search("validationerror")["total_matches"], 0)


class TestExtractSearchTerms(unittest.TestCase):
    def test_quoted_and_identifiers_ranked(self) -> None:
        terms = explain.extract_search_terms(
            "KeyError 'project_root' when calling resolve_in_project "
            "during startup"
        )
        self.assertEqual(terms[0], "project_root")
        self.assertIn("resolve_in_project", terms)
        self.assertLessEqual(len(terms), config.EXPLAIN_MAX_SEARCH_TERMS)

    def test_noise_words_dropped(self) -> None:
        terms = explain.extract_search_terms("the error fails unexpectedly")
        self.assertEqual(terms, [])

    def test_longer_identifiers_win(self) -> None:
        terms = explain.extract_search_terms(
            "bug in do_thing when _handle_small_thing_name runs"
        )
        self.assertEqual(terms[0], "_handle_small_thing_name")


class TestLocateAndExplain(GitRepoTestBase):
    def test_no_terms_is_honest_without_llm(self) -> None:
        with mock.patch("config.PROJECT_ROOT", self.root), \
                mock.patch("tools.explain._complete") as fake:
            result = explain.locate_and_explain("the error fails badly")
            fake.assert_not_called()
        self.assertFalse(result["located"])

    def test_no_hits_declines_without_llm(self) -> None:
        with mock.patch("config.PROJECT_ROOT", self.root), \
                mock.patch("tools.explain._complete") as fake:
            result = explain.locate_and_explain("quantum_flux_capacitor")
            fake.assert_not_called()
        self.assertFalse(result["located"])

    def test_locates_code_and_passes_excerpts_to_llm(self) -> None:
        captured = {}

        def fake_complete(messages):
            captured["messages"] = messages
            return ("Cause is in `app/worker.py` line 2: raises "
                    "ValidationError.")

        with mock.patch("config.PROJECT_ROOT", self.root), \
                mock.patch("tools.explain._complete",
                           side_effect=fake_complete):
            result = explain.locate_and_explain(
                "ValidationError raised when calling run_job"
            )

        self.assertTrue(result["located"])
        self.assertIn("app/worker.py",
                      [s["path"] for s in result["sources"]])
        user_msg = captured["messages"][1]["content"]
        self.assertIn("raise ValidationError", user_msg)
        self.assertIn("Problem description:", user_msg)

    def test_ungrounded_answer_triggers_one_retry(self) -> None:
        calls = []

        def fake_complete(messages):
            calls.append(messages)
            if len(calls) == 1:
                return "See `totally_made_up_symbol` for details."
            return "It is `run_job` in the excerpt."

        with mock.patch("config.PROJECT_ROOT", self.root), \
                mock.patch("tools.explain._complete",
                           side_effect=fake_complete):
            result = explain.locate_and_explain(
                "run_job misbehaves with ValidationError"
            )

        self.assertEqual(len(calls), 2)
        self.assertIn("totally_made_up_symbol", calls[1][-1]["content"])
        self.assertIn("`run_job`", result["explanation"])


    def test_specific_identifier_beats_generic_decoy(self) -> None:
        # A big file full of generic words must not outrank the file that
        # actually contains the specific identifier from the description.
        self._write("app/noise.py", "\n".join(
            f"# response client parse note {i}" for i in range(40)
        ) + "\n")
        captured = {}

        def fake_complete(messages):
            captured["user"] = messages[1]["content"]
            return "It is `run_job` in `app/worker.py`."

        with mock.patch("config.PROJECT_ROOT", self.root), \
                mock.patch("tools.explain._complete",
                           side_effect=fake_complete):
            result = explain.locate_and_explain(
                "run_job raises ValidationError"
            )

        top_path = result["sources"][0]["path"]
        self.assertEqual(top_path, "app/worker.py")
        self.assertIn("raise ValidationError", captured["user"])

    def test_sources_report_true_excerpt_span(self) -> None:
        long_file = "app/long_module.py"
        lines = [f"line_{i} = {i}" for i in range(1, 400)]
        lines.append("def run_job():\n    pass")
        self._write(long_file, "\n".join(lines) + "\n")

        def fake_complete(messages):
            return "`run_job` is defined near the end."

        with mock.patch("config.PROJECT_ROOT", self.root), \
                mock.patch("tools.explain._complete",
                           side_effect=fake_complete):
            result = explain.locate_and_explain(
                "where does run_job get defined in long_module"
            )

        src = next(s for s in result["sources"]
                   if s["path"] == long_file)
        real_length = len((self.root / long_file).read_text().splitlines())
        self.assertLessEqual(src["line_end"], real_length)
        self.assertGreaterEqual(src["line_start"], 1)
        self.assertLess(src["line_start"], src["line_end"])


if __name__ == "__main__":
    unittest.main()
