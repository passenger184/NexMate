"""Unit tests for citation-markdown discipline (bug: [[1]text](url))
and condenser version-echo scrubbing (bug: refined query inherits
"in ERPNext 16.31.0 and 16.32.3" from version authority).

Run: .venv/bin/python -m unittest discover -s tests -v

The UI renders the structured sources list as pills and never parses
citations out of prose — so the generator must emit bare [n] markers
only. These tests pin the prompt contract and the deterministic net
that backs it up.

The condenser rewrites follow-ups for keyword search; version echoes
from earlier assistant answers poison BM25 (digits read as rare
discriminating terms). Scrubbing is deterministic at both the context
and the output, because small models copy the phrase even when the
prompt forbids it.
"""

import unittest
from unittest import mock

from rag import generator


class CitationPromptContractTest(unittest.TestCase):
    def test_developer_prompt_forbids_markdown_link_citations(self) -> None:
        prompt = generator.SYSTEM_PROMPT
        self.assertIn("[n]", prompt)
        self.assertIn("markdown", prompt.lower())
        self.assertIn("Bare [n]", prompt)

    def test_employee_prompt_forbids_markdown_link_citations(self) -> None:
        prompt = generator.EMPLOYEE_SYSTEM_PROMPT
        self.assertIn("[n]", prompt)
        self.assertIn("markdown", prompt.lower())
        self.assertIn("Bare [n]", prompt)


class CitationLinkRegexTest(unittest.TestCase):
    def test_malformed_double_bracket_shape_detected(self) -> None:
        self.assertTrue(generator._CITATION_LINK_RE.search(
            "as shown in [[1]Sales Invoice](http://x/y) today"))

    def test_plain_markdown_link_detected(self) -> None:
        self.assertTrue(generator._CITATION_LINK_RE.search(
            "see [the docs](https://example.com/a) for details"))

    def test_bare_markers_not_flagged(self) -> None:
        self.assertIsNone(generator._CITATION_LINK_RE.search(
            "Open the order [1] and click Create [2][3]."))

    def test_plain_prose_not_flagged(self) -> None:
        self.assertIsNone(generator._CITATION_LINK_RE.search(
            "There is no confident answer in the knowledge base."))


class VersionEchoScrubTest(unittest.TestCase):
    def test_full_version_authority_echo_removed(self) -> None:
        self.assertEqual(
            generator._scrub_version_echoes(
                "How do I create a Purchase Invoice in ERPNext "
                "16.31.0 and 16.32.3?"),
            "How do I create a Purchase Invoice in ERPNext?")

    def test_bare_version_pair_removed(self) -> None:
        self.assertEqual(
            generator._scrub_version_echoes("Do X ERPNext 16.32.3 now"),
            "Do X ERPNext now")

    def test_plain_prose_untouched(self) -> None:
        text = "How do I create a Purchase Invoice in ERPNext?"
        self.assertEqual(generator._scrub_version_echoes(text), text)

    def test_assistant_history_scrubbed_user_history_kept(self) -> None:
        hist = [
            {"role": "user",
             "content": "how do I create a Sales Invoice?"},
            {"role": "assistant",
             "content": "To create a Sales Invoice in ERPNext 16.31.0 "
                        "and 16.32.3, follow these steps: [1]."},
        ]
        cleaned = generator._scrub_history_for_condense(hist)
        self.assertEqual(cleaned[0]["content"],
                         "how do I create a Sales Invoice?")
        self.assertNotIn("16.31.0", cleaned[1]["content"])
        self.assertIn("[1]", cleaned[1]["content"])

    def test_condense_output_version_echo_stripped(self) -> None:
        with mock.patch.object(
                generator, "_complete",
                return_value="How do I create a Purchase Invoice "
                             "in ERPNext 16.31.0 and 16.32.3?"):
            out = generator.condense_followup(
                [{"role": "user", "content": "How do I make X?"},
                 {"role": "assistant", "content": "Like this [1]."}],
                "what about Purchase Invoices?")
        self.assertEqual(out,
                         "How do I create a Purchase Invoice in ERPNext?")

    def test_condense_context_hides_version_echo_from_model(self) -> None:
        seen = {}

        def fake_complete(messages, **kwargs):
            seen["user"] = messages[1]["content"]
            return "How do I create a Purchase Invoice?"

        hist = [
            {"role": "user",
             "content": "how do I create a Sales Invoice?"},
            {"role": "assistant",
             "content": "To create a Sales Invoice in ERPNext 16.31.0 "
                        "and 16.32.3, follow these steps: [1]."},
        ]
        with mock.patch.object(generator, "_complete",
                               side_effect=fake_complete):
            generator.condense_followup(hist, "what about Purchase Invoices?")
        self.assertNotIn("16.31.0", seen["user"])
        self.assertNotIn("16.32.3", seen["user"])


if __name__ == "__main__":
    unittest.main()
