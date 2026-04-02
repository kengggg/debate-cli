import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from debate_cli.application.debate_service import DebateService
from debate_cli.application.parsing import normalize_action_choice, parse_actions, parse_structured
from debate_cli.application.preflight import PreflightService
from debate_cli.cli import positive_int
from debate_cli.domain.models import (
    ActionMode, ActionResult, ActionStatus, AgentDefinition,
    DebateAction, DebateConfig, DebateResult, PromptTemplates, result_to_dict,
)
from debate_cli.infrastructure.context import FilesystemContextLoader
from debate_cli.infrastructure.agents import CommandAgentClient
from debate_cli.infrastructure.prompts import TomlPromptRepository
from debate_cli.infrastructure.reports import FileReportWriter


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

        parsed = parse_structured(text)

        self.assertEqual(
            parsed.steel_man,
            "The strongest case is that a monolith keeps changes coordinated.",
        )
        self.assertEqual(
            parsed.convergence,
            ["Shared schemas matter", "Operational simplicity is valuable"],
        )
        self.assertEqual(parsed.divergence, ["Deployment isolation is worth the overhead"])
        self.assertEqual(parsed.confidence, 0.85)

    def test_parse_actions_accepts_bulleted_action_lines(self):
        text = """
        - ACTION 1: Tighten parser | AGENT: Codex | TYPE: Execute
        * ACTION 2: Review rollout plan | AGENT: user | TYPE: plan
        """

        actions = parse_actions(text)

        self.assertEqual(
            [(action.action, action.agent, action.mode) for action in actions],
            [
                ("Tighten parser", "codex", ActionMode.EXECUTE),
                ("Review rollout plan", "user", ActionMode.PLAN),
            ],
        )

    def test_parse_actions_ignores_unknown_action_types(self):
        text = """
        ACTION 1: Broken mode | AGENT: codex | TYPE: shipit
        ACTION 2: Valid plan | AGENT: user | TYPE: plan
        """

        actions = parse_actions(text)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, "Valid plan")
        self.assertEqual(actions[0].mode, ActionMode.PLAN)


class ContextLoadingTests(unittest.TestCase):
    def test_load_context_filters_before_limiting_directory_entries(self):
        loader = FilesystemContextLoader()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(25):
                (root / f"{index:02d}_dir").mkdir()
            target = root / "zz_target.py"
            target.write_text("print('included')\n", encoding="utf-8")

            context = loader.load([str(root)])

        self.assertIn("zz_target.py", context)
        self.assertIn("print('included')", context)

    def test_load_context_deduplicates_direct_files_and_directory_matches(self):
        loader = FilesystemContextLoader()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "app.py"
            target.write_text("print('once')\n", encoding="utf-8")

            context = loader.load([str(target), str(root)])

        self.assertEqual(context.count("print('once')"), 1)


class PromptLoadingTests(unittest.TestCase):
    def test_load_prompts_raises_for_missing_explicit_file(self):
        repository = TomlPromptRepository()
        missing = Path("/tmp/does-not-exist-prompts.toml")
        with self.assertRaises(FileNotFoundError):
            repository.load(missing)

    def test_load_prompts_reads_packaged_defaults(self):
        repository = TomlPromptRepository()
        prompts = repository.load()

        self.assertIn("You are {role}", prompts.debate)
        self.assertIn("## Actions", prompts.final_summary)


class ValidationTests(unittest.TestCase):
    def test_positive_int_rejects_zero(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")

    def test_normalize_action_choice_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            normalize_action_choice(
                "codex:shipit",
                default_agent="codex",
                default_mode=ActionMode.PLAN,
                allowed_agents={"claude", "codex", "gemini", "user"},
            )


class FakeAgentRegistry:
    def __init__(self, responses):
        self._responses = {name: list(values) for name, values in responses.items()}
        self._metadata = {
            "claude": AgentDefinition("claude", "Claude", "🟠", "red", "dots"),
            "codex": AgentDefinition("codex", "Codex", "🔵", "blue", "dots"),
            "gemini": AgentDefinition("gemini", "Gemini", "🟡", "yellow", "dots"),
        }

    def names(self):
        return set(self._responses)

    def has(self, name):
        return name in self._responses

    def get_metadata(self, name):
        return self._metadata[name]

    def get_client(self, name):
        registry = self

        class _Client:
            def run(self, prompt, allow_tools=False):
                return registry._responses[name].pop(0)

        return _Client()


class FakeRenderer:
    def __init__(self):
        self.status_messages = []
        self.convergence_reached = 0
        self.ask_user_calls = []

    def print_agent(self, role, text, turn=None):
        return None

    def print_steel_man(self, role, steel_man_text):
        return None

    def print_status(self, msg):
        self.status_messages.append(msg)

    def print_header(self, msg):
        return None

    def ask_user(self, prompt_text, default=""):
        self.ask_user_calls.append(prompt_text)
        return default

    def print_turn_stats(self, turn):
        return None

    def print_convergence_meter(self, overlap_ratio):
        return None

    def print_round_comparison(self, claude_turn, codex_turn):
        return None

    def print_round_transition(self):
        return None

    def print_round_progress(self, current, total):
        return None

    def print_banner(self, topic, max_rounds, allow_tools, context_count):
        return None

    def print_convergence_reached(self):
        self.convergence_reached += 1

    def print_actions_table(self, actions):
        return None

    def render_preflight_results(self, results):
        return None

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def agent_spinner(self, role):
        return self._Ctx()


class FakePromptRepository:
    def load(self, override_path=None):
        return PromptTemplates(
            debate=(
                "Topic: {topic}\n{context_block}\n{history}\n{moderator_guidance}\n{user_input_block}\n"
                "Role: {role}\nOpponent: {opponent}\n{round_instructions}"
            ),
            moderator="Moderator round {round}\n{round_turns}\n{user_input_block}\n{moderator_round_instructions}",
            final_summary="Final summary for {topic}\n## Actions",
            action_execution="Action {action} in {mode}",
        )


class FakeContextLoader:
    def load(self, paths, status_callback=None):
        return "(no context files)"


class DebateServiceTests(unittest.TestCase):
    def test_service_stops_early_on_convergence(self):
        responses = {
            "claude": [
                # Round 1: opening statement (no structured sections expected)
                "My opening position.\n\nCONFIDENCE: 0.6",
                # Round 2: converging
                "STEEL MAN:\nCodex is right about X.\n\nCONVERGENCE:\n- shared approach\n\nDIVERGENCE:\n- more speed\n\nCONFIDENCE: 0.9",
            ],
            "codex": [
                # Round 1: opening statement
                "My opening position.\n\nCONFIDENCE: 0.65",
                # Round 2: converging
                "STEEL MAN:\nClaude is right about Y.\n\nCONVERGENCE:\n- shared approach\n\nDIVERGENCE:\n- more safety\n\nCONFIDENCE: 0.95",
            ],
            "gemini": [
                # Round 1 moderation
                "## Summary\nOpening positions stated.\n\n## Focus for Next Round\n- Claude should: elaborate\n- Codex should: elaborate",
                # Round 2 moderation
                "## Summary\nLooks aligned.\n\n## Focus for Next Round\n- Claude should: none\n- Codex should: none",
                # Final summary
                "Final summary\n## Actions",
            ],
        }
        service = DebateService(
            prompt_repository=FakePromptRepository(),
            context_loader=FakeContextLoader(),
            renderer=FakeRenderer(),
            agent_registry=FakeAgentRegistry(responses),
        )

        result = service.run(DebateConfig(topic="test topic", max_rounds=3))

        self.assertEqual(result.completed_rounds, 2)
        self.assertEqual(len(result.turns), 4)  # 2 per round
        self.assertEqual(len(result.moderations), 2)
        self.assertEqual(result.actions, [])


class FakeReportWriter:
    def __init__(self):
        self.calls = []

    def write(self, result, output_path):
        self.calls.append((result, output_path))
        return [output_path]


class ReportWriterTests(unittest.TestCase):
    def test_writer_emits_both_files_for_extensionless_output(self):
        registry = FakeAgentRegistry({"claude": [], "codex": [], "gemini": []})
        writer = FileReportWriter(registry)
        service_result = DebateService(
            prompt_repository=FakePromptRepository(),
            context_loader=FakeContextLoader(),
            renderer=FakeRenderer(),
            agent_registry=FakeAgentRegistry(
                {
                    "claude": ["STEEL MAN:\nN/A\n\nCONVERGENCE:\n- one\n\nDIVERGENCE:\n- two\n\nCONFIDENCE: 0.5"],
                    "codex": ["STEEL MAN:\nN/A\n\nCONVERGENCE:\n- one\n\nDIVERGENCE:\n- two\n\nCONFIDENCE: 0.5"],
                    "gemini": ["## Summary\nx\n\n## Focus for Next Round\n- Claude should: x", "Final summary\n## Actions"],
                }
            ),
        ).run(DebateConfig(topic="topic", max_rounds=1))

        with tempfile.TemporaryDirectory() as tmp:
            written = writer.write(service_result, Path(tmp) / "debate")

        suffixes = {path.suffix for path in written}
        self.assertTrue({".json", ".md"}.issubset(suffixes))

    @mock.patch("debate_cli.infrastructure.pdf_report.render_pdf_report")
    @mock.patch("debate_cli.infrastructure.pdf_report.render_html_report")
    def test_writer_emits_html_for_extensionless_output(self, mock_render_html, mock_render_pdf):
        registry = FakeAgentRegistry({"claude": [], "codex": [], "gemini": []})
        writer = FileReportWriter(registry)
        result = DebateResult(config=DebateConfig(topic="topic"))

        mock_render_html.return_value = "<html>report</html>"

        def _write_pdf(_result, _icons, output_path):
            output_path.write_bytes(b"%PDF-1.4")
            return output_path

        mock_render_pdf.side_effect = _write_pdf

        with tempfile.TemporaryDirectory() as tmp:
            written = writer.write(result, Path(tmp) / "debate")

        suffixes = {path.suffix for path in written}
        self.assertEqual(suffixes, {".json", ".md", ".html", ".pdf"})


class PreflightTests(unittest.TestCase):
    @mock.patch("subprocess.run")
    def test_preflight_runs_packaged_prompts_check(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
        service = PreflightService(TomlPromptRepository(), FakeAgentRegistry({"claude": ["READY"], "codex": ["READY"], "gemini": ["READY"]}))

        results = service.run()

        self.assertTrue(any("Packaged prompts" in result.detail for result in results))


class AgentClientTests(unittest.TestCase):
    @mock.patch("subprocess.run")
    def test_codex_tool_flag_precedes_stdin_marker(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
        client = CommandAgentClient(
            name="codex",
            command_prefix=["codex", "exec"],
            tool_flags=["--full-auto"],
            command_suffix=["-"],
        )

        client.run("prompt", allow_tools=True)

        self.assertEqual(
            mock_run.call_args.args[0],
            ["codex", "exec", "--full-auto", "-"],
        )

    @mock.patch("subprocess.run")
    def test_gemini_prompt_is_passed_via_argument_not_stdin(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
        client = CommandAgentClient(
            name="gemini",
            command_prefix=["gemini"],
            tool_flags=["-y"],
            prompt_argument=["-p"],
            prompt_via_stdin=False,
        )

        client.run("prompt text", allow_tools=True)

        self.assertEqual(
            mock_run.call_args.args[0],
            ["gemini", "-y", "-p", "prompt text"],
        )
        self.assertIsNone(mock_run.call_args.kwargs["input"])


class ActionModeTests(unittest.TestCase):
    def test_normalize_accepts_continue_mode(self):
        sel = normalize_action_choice(
            "c", default_agent="system", default_mode=ActionMode.CONTINUE,
            allowed_agents={"claude", "codex", "gemini", "user", "system"},
        )
        self.assertEqual(sel.mode, ActionMode.CONTINUE)

    def test_normalize_accepts_export_mode(self):
        sel = normalize_action_choice(
            "x", default_agent="system", default_mode=ActionMode.EXPORT,
            allowed_agents={"claude", "codex", "gemini", "user", "system"},
        )
        self.assertEqual(sel.mode, ActionMode.EXPORT)

    def test_parse_actions_handles_continue_and_export_types(self):
        text = """
        ACTION 1: Continue debating with focus on costs | AGENT: system | TYPE: continue
        ACTION 2: Export report for team review | AGENT: system | TYPE: export
        """
        actions = parse_actions(text)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0].mode, ActionMode.CONTINUE)
        self.assertEqual(actions[0].agent, "system")
        self.assertEqual(actions[1].mode, ActionMode.EXPORT)


class ActionResultTests(unittest.TestCase):
    def test_result_to_dict_includes_action_results(self):
        action = DebateAction(action="Create plan", agent="claude", mode=ActionMode.PLAN)
        results = [
            ActionResult(
                action=action, status=ActionStatus.COMPLETED,
                agent_used="claude", mode_used=ActionMode.PLAN,
                output="Here is the plan...",
            ),
            ActionResult(
                action=DebateAction(action="User task", agent="user", mode=ActionMode.EXECUTE),
                status=ActionStatus.SKIPPED,
                agent_used="user",
            ),
            ActionResult(
                action=DebateAction(action="Broken", agent="codex", mode=ActionMode.EXECUTE),
                status=ActionStatus.FAILED,
                agent_used="codex", mode_used=ActionMode.EXECUTE,
                error="Timeout",
            ),
        ]
        config = DebateConfig(topic="test")
        debate_result = DebateResult(config=config, actions=[action], action_results=results)

        serialized = result_to_dict(debate_result)

        self.assertEqual(len(serialized["action_results"]), 3)
        self.assertEqual(serialized["action_results"][0]["status"], "completed")
        self.assertEqual(serialized["action_results"][0]["output"], "Here is the plan...")
        self.assertEqual(serialized["action_results"][1]["status"], "skipped")
        self.assertEqual(serialized["action_results"][2]["status"], "failed")
        self.assertEqual(serialized["action_results"][2]["error"], "Timeout")


class DebateServiceOpeningRoundTests(unittest.TestCase):
    def test_opening_round_skips_convergence_check(self):
        """Even with high confidence in round 1, convergence check is skipped."""
        responses = {
            "claude": ["Strong position.\n\nCONFIDENCE: 0.95"],
            "codex": ["Strong position.\n\nCONFIDENCE: 0.95"],
            "gemini": [
                "## Summary\nBoth agree.\n\n## Focus for Next Round\n- Claude should: x",
                "Final summary\n## Actions",
            ],
        }
        service = DebateService(
            prompt_repository=FakePromptRepository(),
            context_loader=FakeContextLoader(),
            renderer=FakeRenderer(),
            agent_registry=FakeAgentRegistry(responses),
        )

        result = service.run(DebateConfig(topic="test", max_rounds=1))

        # Should complete round 1 without early stop (convergence skipped for round 1)
        self.assertEqual(result.completed_rounds, 1)
        self.assertEqual(len(result.turns), 2)


class AutopilotTests(unittest.TestCase):
    def test_autopilot_skips_user_steering(self):
        """With autopilot=True, ask_user should not be called during debate rounds."""
        responses = {
            "claude": [
                "Opening.\n\nCONFIDENCE: 0.5",
                "STEEL MAN:\nX\n\nCONVERGENCE:\n- a\n\nDIVERGENCE:\n- b\n\nCONFIDENCE: 0.9",
            ],
            "codex": [
                "Opening.\n\nCONFIDENCE: 0.5",
                "STEEL MAN:\nY\n\nCONVERGENCE:\n- a\n\nDIVERGENCE:\n- c\n\nCONFIDENCE: 0.9",
            ],
            "gemini": [
                "## Summary\nRound 1.\n\n## Focus for Next Round\n- Claude should: x\n- Codex should: y",
                "## Summary\nRound 2.\n\n## Focus for Next Round\n- Claude should: x",
                "Final summary\n## Actions",
            ],
        }
        renderer = FakeRenderer()
        service = DebateService(
            prompt_repository=FakePromptRepository(),
            context_loader=FakeContextLoader(),
            renderer=renderer,
            agent_registry=FakeAgentRegistry(responses),
        )

        result = service.run(DebateConfig(topic="test", max_rounds=2, autopilot=True))

        # ask_user should only be called for the export prompt (Phase 2), not for steering
        steering_calls = [c for c in renderer.ask_user_calls if "Your thoughts" in c]
        self.assertEqual(len(steering_calls), 0)
        self.assertEqual(result.completed_rounds, 2)


class ExportFlowTests(unittest.TestCase):
    def test_service_exports_once_even_without_structured_actions_when_output_is_configured(self):
        responses = {
            "claude": ["Opening.\n\nCONFIDENCE: 0.5"],
            "codex": ["Opening.\n\nCONFIDENCE: 0.5"],
            "gemini": [
                "## Summary\nRound 1.\n\n## Focus for Next Round\n- Claude should: x",
                "Final summary without parseable action lines",
            ],
        }
        renderer = FakeRenderer()
        report_writer = FakeReportWriter()
        service = DebateService(
            prompt_repository=FakePromptRepository(),
            context_loader=FakeContextLoader(),
            renderer=renderer,
            agent_registry=FakeAgentRegistry(responses),
            report_writer=report_writer,
        )

        output_path = Path("report.md")
        result = service.run(DebateConfig(topic="test", max_rounds=1, output=output_path))

        self.assertEqual(result.actions, [])
        self.assertEqual(len(report_writer.calls), 1)
        self.assertEqual(report_writer.calls[0][1], output_path)
        self.assertEqual(renderer.ask_user_calls, [])

    def test_service_auto_exports_when_output_path_is_set(self):
        responses = {
            "claude": ["Opening.\n\nCONFIDENCE: 0.5"],
            "codex": ["Opening.\n\nCONFIDENCE: 0.5"],
            "gemini": [
                "## Summary\nRound 1.\n\n## Focus for Next Round\n- Claude should: x",
                "## Actions\nACTION 1: Broken | AGENT: codex | TYPE: shipit",
            ],
        }
        renderer = FakeRenderer()
        report_writer = FakeReportWriter()
        service = DebateService(
            prompt_repository=FakePromptRepository(),
            context_loader=FakeContextLoader(),
            renderer=renderer,
            agent_registry=FakeAgentRegistry(responses),
            report_writer=report_writer,
        )

        output_path = Path("outputs/test")
        service.run(DebateConfig(topic="test", max_rounds=1, output=output_path))

        # Auto-export happens without asking
        self.assertEqual(len(report_writer.calls), 1)
        self.assertEqual(report_writer.calls[0][1], output_path)


class PreflightExportLibsTests(unittest.TestCase):
    def test_preflight_checks_export_libraries(self):
        """Preflight should include checks for Jinja2, WeasyPrint, and Pango."""
        service = PreflightService(
            TomlPromptRepository(),
            FakeAgentRegistry({"claude": ["READY"], "codex": ["READY"], "gemini": ["READY"]}),
        )

        checks = service.build_checks()
        check_names = [c.name for c in checks]

        self.assertIn("Jinja2", check_names)
        self.assertIn("WeasyPrint", check_names)
        self.assertIn("Pango (system)", check_names)


if __name__ == "__main__":
    unittest.main()
