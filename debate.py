#!/usr/bin/env python3
"""Compatibility shim for the packaged debate-cli application."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from debate_cli.application.parsing import normalize_action_choice, parse_actions, parse_structured, positive_int
from debate_cli.bootstrap import build_application
from debate_cli.cli import main
from debate_cli.domain.models import ActionMode, DebateConfig


def load_prompts(path: Path | None = None) -> dict[str, str]:
    """Compatibility wrapper returning prompt templates as a plain mapping."""
    return build_application().prompt_repository.load(path).as_mapping()


def load_context(paths: list[str]) -> str:
    """Compatibility wrapper around the packaged context loader."""
    return build_application().context_loader.load(paths)


def run_preflight() -> bool:
    """Compatibility wrapper for preflight checks."""
    app = build_application()
    results = app.preflight_service.run()
    app.renderer.render_preflight_results(results)
    return all(result.passed for result in results)


def run_debate(
    topic: str,
    context_paths: list[str],
    max_rounds: int = 3,
    allow_tools: bool = False,
    output: str | None = None,
    prompts_path: Path | None = None,
):
    """Compatibility wrapper returning the historical turn list."""
    app = build_application()
    config = DebateConfig(
        topic=topic,
        context_paths=list(context_paths),
        max_rounds=max_rounds,
        allow_tools=allow_tools,
        output=Path(output) if output else None,
        prompts_path=prompts_path,
    )
    result = app.debate_service.run(config)
    if config.output:
        app.report_writer.write(result, config.output)
    return result.turns


__all__ = [
    "ActionMode",
    "load_context",
    "load_prompts",
    "main",
    "normalize_action_choice",
    "parse_actions",
    "parse_structured",
    "positive_int",
    "run_debate",
    "run_preflight",
]


if __name__ == "__main__":
    raise SystemExit(main())
