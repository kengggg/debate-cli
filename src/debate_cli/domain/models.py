"""Core models for debate-cli."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ActionMode(StrEnum):
    """Supported action execution modes."""

    EXECUTE = "execute"
    PLAN = "plan"


@dataclass(frozen=True)
class AgentDefinition:
    """Presentation metadata for a registered agent."""

    name: str
    display_name: str
    icon: str
    color: str
    spinner: str


@dataclass(frozen=True)
class PromptTemplates:
    """Concrete prompt templates available to the application."""

    debate: str
    moderator: str
    final_summary: str
    action_execution: str

    def as_mapping(self) -> dict[str, str]:
        """Return templates as a plain mapping."""
        return {
            "debate": self.debate,
            "moderator": self.moderator,
            "final_summary": self.final_summary,
            "action_execution": self.action_execution,
        }

    def render(self, prompt_name: str, **values: Any) -> str:
        """Render one template with a clearer error on bad placeholders."""
        try:
            template = self.as_mapping()[prompt_name]
        except KeyError as exc:
            raise ValueError(f"Prompt template '{prompt_name}' is missing") from exc

        try:
            return template.format(**values)
        except KeyError as exc:
            missing = exc.args[0]
            raise ValueError(
                f"Prompt template '{prompt_name}' references unknown placeholder '{missing}'"
            ) from exc
        except ValueError as exc:
            raise ValueError(f"Prompt template '{prompt_name}' is invalid: {exc}") from exc


@dataclass
class StructuredDebateResponse:
    """Parsed structured response produced by a debating agent."""

    steel_man: str = ""
    convergence: list[str] = field(default_factory=list)
    divergence: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class DebateTurn:
    """One debating agent's turn."""

    agent: str
    round: int
    position: str
    convergence: list[str] = field(default_factory=list)
    divergence: list[str] = field(default_factory=list)
    steel_man: str = ""
    confidence: float = 0.5
    tool_outputs: list[str] = field(default_factory=list)


@dataclass
class ModerationSummary:
    """Moderator output for one round."""

    round: int
    summary: str
    focus_next: str
    raw: str = ""


@dataclass
class UserInput:
    """User steering captured between rounds."""

    round: int
    text: str


@dataclass(frozen=True)
class ActionSelection:
    """Validated action routing choice."""

    agent: str
    mode: ActionMode


@dataclass
class DebateAction:
    """Structured action extracted from the final summary."""

    action: str
    agent: str
    mode: ActionMode


@dataclass(frozen=True)
class DebateConfig:
    """Runtime configuration for a debate session."""

    topic: str
    context_paths: list[str] = field(default_factory=list)
    max_rounds: int = 3
    allow_tools: bool = False
    output: Path | None = None
    prompts_path: Path | None = None


@dataclass
class DebateResult:
    """Canonical result of a debate run."""

    config: DebateConfig
    turns: list[DebateTurn] = field(default_factory=list)
    moderations: list[ModerationSummary] = field(default_factory=list)
    user_inputs: list[UserInput] = field(default_factory=list)
    final_summary: str = ""
    actions: list[DebateAction] = field(default_factory=list)

    @property
    def completed_rounds(self) -> int:
        """Return the number of completed rounds."""
        return max((turn.round for turn in self.turns), default=0)


@dataclass(frozen=True)
class PreflightCheckResult:
    """Result of one preflight validation."""

    category: str
    name: str
    passed: bool
    detail: str
    duration: float


def result_to_dict(result: DebateResult) -> dict[str, Any]:
    """Serialize a debate result into JSON-safe primitives."""
    return {
        "topic": result.config.topic,
        "rounds": result.config.max_rounds,
        "completed_rounds": result.completed_rounds,
        "turns": [asdict(turn) for turn in result.turns],
        "moderations": [asdict(moderation) for moderation in result.moderations],
        "user_inputs": [asdict(user_input) for user_input in result.user_inputs],
        "final_summary": result.final_summary,
        "actions": [
            {
                "action": action.action,
                "agent": action.agent,
                "type": action.mode.value,
            }
            for action in result.actions
        ],
    }
