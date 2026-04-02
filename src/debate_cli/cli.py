"""CLI entrypoint for debate-cli."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from debate_cli.application.parsing import positive_int
from debate_cli.bootstrap import build_application
from debate_cli.domain.models import DebateConfig


def _ensure_homebrew_lib_path() -> None:
    """On macOS, add Homebrew's lib directory to DYLD_FALLBACK_LIBRARY_PATH.

    WeasyPrint needs pango/gobject shared libraries. Homebrew installs them
    in a non-default location that Python's ctypes.util.find_library misses.
    """
    if sys.platform != "darwin":
        return

    env_key = "DYLD_FALLBACK_LIBRARY_PATH"
    current = os.environ.get(env_key, "")

    # Try to find Homebrew prefix
    brew = shutil.which("brew")
    if not brew:
        return
    try:
        prefix = subprocess.run(
            [brew, "--prefix"], capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return

    lib_dir = os.path.join(prefix, "lib")
    if not os.path.isdir(lib_dir):
        return
    if lib_dir in current.split(os.pathsep):
        return

    os.environ[env_key] = f"{lib_dir}{os.pathsep}{current}" if current else lib_dir


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Claude Code vs Codex debate with Gemini moderator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              debate-cli "Should we use microservices or monolith?"
              debate-cli "Review this codebase" --context ./src --tools --rounds 4
              debate-cli "Improve error handling" --context ./src/api -o debate.json
            """
        ),
    )
    parser.add_argument("topic", nargs="?", help="The debate topic or question")
    parser.add_argument("--context", nargs="*", default=[], help="Files/dirs for context")
    parser.add_argument(
        "--rounds",
        type=positive_int,
        default=3,
        help="Max debate rounds (default: 3)",
    )
    parser.add_argument("--tools", action="store_true", help="Allow agents to use tools (file I/O, shell)")
    parser.add_argument("--output", "-o", help="Save debate log (.json, .md, or both if no extension)")
    parser.add_argument("--prompts", type=Path, help="Custom prompts TOML file")
    parser.add_argument("--autopilot", action="store_true",
                        help="Run without user interaction (agents debate autonomously)")
    parser.add_argument("--test", action="store_true", help="Run preflight checks on all agents and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    _ensure_homebrew_lib_path()
    parser = build_parser()
    args = parser.parse_args(argv)
    app = build_application()

    if args.test:
        results = app.preflight_service.run()
        app.renderer.render_preflight_results(results)
        return 0 if all(result.passed for result in results) else 1

    if not args.topic:
        parser.error("topic is required (use --test to check system readiness)")

    config = DebateConfig(
        topic=args.topic,
        context_paths=list(args.context),
        max_rounds=args.rounds,
        allow_tools=args.tools,
        autopilot=args.autopilot,
        output=Path(args.output) if args.output else None,
        prompts_path=args.prompts,
    )

    try:
        result = app.debate_service.run(config)
    except KeyboardInterrupt:
        app.renderer.print_status("\n\n⛔ Debate interrupted by user")
        return 1

    if config.output:
        written_paths = app.report_writer.write(result, config.output)
        if len(written_paths) == 1:
            app.renderer.print_status(f"\n💾 Saved: {written_paths[0]}")
        else:
            joined = " + ".join(str(path) for path in written_paths)
            app.renderer.print_status(f"\n💾 Saved: {joined}")

    return 0
