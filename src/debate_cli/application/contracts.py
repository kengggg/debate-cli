"""Application-layer contracts."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Callable, Protocol, Sequence

from debate_cli.domain.models import (
    AgentDefinition,
    DebateAction,
    DebateResult,
    DebateTurn,
    PreflightCheckResult,
    PromptTemplates,
)


class AgentClient(Protocol):
    """Client capable of executing a prompt against an agent backend."""

    def run(self, prompt: str, allow_tools: bool = False) -> str:
        """Execute a prompt and return raw stdout."""


class AgentRegistry(Protocol):
    """Registry for installed agent implementations."""

    def names(self) -> set[str]:
        """Return all registered agent names."""

    def has(self, name: str) -> bool:
        """Return whether an agent is registered."""

    def get_metadata(self, name: str) -> AgentDefinition:
        """Return presentation metadata for one agent."""

    def get_client(self, name: str) -> AgentClient:
        """Return the runnable client for one agent."""


class PromptRepository(Protocol):
    """Repository that loads packaged defaults plus optional overrides."""

    def load(self, override_path: Path | None = None) -> PromptTemplates:
        """Load prompt templates."""


class ContextLoader(Protocol):
    """Loader that turns context paths into prompt-safe text."""

    def load(
        self,
        paths: Sequence[str],
        status_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Load context from files and directories."""


class Renderer(Protocol):
    """User-facing rendering interface."""

    def print_agent(self, role: str, text: str, turn: DebateTurn | None = None) -> None:
        """Render one agent output block."""

    def print_steel_man(self, role: str, steel_man_text: str) -> None:
        """Render a steel-man summary."""

    def print_status(self, msg: str) -> None:
        """Render a status message."""

    def print_header(self, msg: str) -> None:
        """Render a section header."""

    def ask_user(self, prompt_text: str, default: str = "") -> str:
        """Prompt the user for input."""

    def print_turn_stats(self, turn: DebateTurn) -> None:
        """Render per-turn confidence/convergence stats."""

    def print_convergence_meter(self, overlap_ratio: float) -> None:
        """Render convergence progress."""

    def print_round_comparison(self, claude_turn: DebateTurn, codex_turn: DebateTurn) -> None:
        """Render round comparison output."""

    def print_round_transition(self) -> None:
        """Render round transition output."""

    def print_round_progress(self, current: int, total: int) -> None:
        """Render round progress."""

    def print_banner(
        self,
        topic: str,
        max_rounds: int,
        allow_tools: bool,
        context_count: int,
    ) -> None:
        """Render the session banner."""

    def print_convergence_reached(self) -> None:
        """Render convergence completion."""

    def print_actions_table(self, actions: Sequence[DebateAction]) -> None:
        """Render structured actions."""

    def render_preflight_results(self, results: Sequence[PreflightCheckResult]) -> None:
        """Render preflight results."""

    def agent_spinner(self, role: str) -> AbstractContextManager[object]:
        """Return a context manager shown while an agent is working."""


class ReportWriter(Protocol):
    """Writer for generated reports/logs."""

    def write(self, result: DebateResult, output_path: Path) -> list[Path]:
        """Write report artifacts and return the created paths."""
