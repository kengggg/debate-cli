import argparse
import tempfile
import unittest
from pathlib import Path

import debate


class ParseStructuredTests(unittest.TestCase):
    def test_parse_structured_accepts_markdown_headers_and_percent_confidence(self):
        text = """
        ## STEEL MAN:
        The strongest case is that a monolith keeps changes coordinated.

        ## CONVERGENCE:
        - Shared schemas matter
        * Operational simplicity is valuable

        ## DIVERGENCE:
        - Deployment isolation is worth the overhead

        ## CONFIDENCE: 85%
        """

        parsed = debate.parse_structured(text)

        self.assertEqual(
            parsed["steel_man"],
            "The strongest case is that a monolith keeps changes coordinated.",
        )
        self.assertEqual(
            parsed["convergence"],
            ["Shared schemas matter", "Operational simplicity is valuable"],
        )
        self.assertEqual(
            parsed["divergence"],
            ["Deployment isolation is worth the overhead"],
        )
        self.assertEqual(parsed["confidence"], 0.85)

    def test_parse_actions_accepts_bulleted_action_lines(self):
        text = """
        - ACTION 1: Tighten parser | AGENT: Codex | TYPE: Execute
        * ACTION 2: Review rollout plan | AGENT: user | TYPE: plan
        """

        actions = debate.parse_actions(text)

        self.assertEqual(
            actions,
            [
                {"action": "Tighten parser", "agent": "codex", "type": "execute"},
                {"action": "Review rollout plan", "agent": "user", "type": "plan"},
            ],
        )


class ContextLoadingTests(unittest.TestCase):
    def test_load_context_filters_before_limiting_directory_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(25):
                (root / f"{index:02d}_dir").mkdir()
            target = root / "zz_target.py"
            target.write_text("print('included')\n", encoding="utf-8")

            context = debate.load_context([str(root)])

        self.assertIn("zz_target.py", context)
        self.assertIn("print('included')", context)

    def test_load_context_deduplicates_direct_files_and_directory_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "app.py"
            target.write_text("print('once')\n", encoding="utf-8")

            context = debate.load_context([str(target), str(root)])

        self.assertEqual(context.count("print('once')"), 1)


class PromptLoadingTests(unittest.TestCase):
    def test_load_prompts_raises_for_missing_explicit_file(self):
        missing = Path("/tmp/does-not-exist-prompts.toml")
        with self.assertRaises(FileNotFoundError):
            debate.load_prompts(missing)


class ValidationTests(unittest.TestCase):
    def test_positive_int_rejects_zero(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            debate.positive_int("0")

    def test_normalize_action_choice_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            debate.normalize_action_choice("codex:shipit", "codex", "plan")


if __name__ == "__main__":
    unittest.main()
