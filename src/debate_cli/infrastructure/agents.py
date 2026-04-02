"""Subprocess-backed agent implementations and registry."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from debate_cli.application.contracts import AgentClient, AgentRegistry
from debate_cli.domain.models import AgentDefinition


@dataclass
class CommandAgentClient(AgentClient):
    """Thin subprocess adapter for one CLI backend."""

    name: str
    command_prefix: list[str]
    tool_flags: list[str]
    prompt_argument: list[str] = field(default_factory=list)
    prompt_via_stdin: bool = True
    command_suffix: list[str] = field(default_factory=list)

    def run(self, prompt: str, allow_tools: bool = False) -> str:
        cmd = list(self.command_prefix)
        if allow_tools:
            cmd.extend(self.tool_flags)
        if self.prompt_argument:
            cmd.extend(self.prompt_argument)
            cmd.append(prompt)
        cmd.extend(self.command_suffix)
        stdin_input = prompt if self.prompt_via_stdin else None
        result = subprocess.run(cmd, input=stdin_input, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"{self.name} CLI error: {result.stderr[:500]}")
        if self.name == "gemini" and not result.stdout.strip() and result.stderr.strip():
            raise RuntimeError(f"gemini returned empty output. stderr: {result.stderr[:500]}")
        return result.stdout


@dataclass(frozen=True)
class RegisteredAgent:
    """Concrete agent registration."""

    metadata: AgentDefinition
    client: AgentClient


class BuiltinAgentRegistry(AgentRegistry):
    """Registry for the built-in agent adapters."""

    def __init__(self, agents: list[RegisteredAgent]):
        self._agents = {agent.metadata.name: agent for agent in agents}

    def names(self) -> set[str]:
        return set(self._agents)

    def has(self, name: str) -> bool:
        return name in self._agents

    def get_metadata(self, name: str) -> AgentDefinition:
        try:
            return self._agents[name].metadata
        except KeyError as exc:
            raise KeyError(f"Unknown agent '{name}'") from exc

    def get_client(self, name: str) -> AgentClient:
        try:
            return self._agents[name].client
        except KeyError as exc:
            raise KeyError(f"Unknown agent '{name}'") from exc


def build_builtin_agent_registry() -> BuiltinAgentRegistry:
    """Build the default agent registry."""
    return BuiltinAgentRegistry(
        [
            RegisteredAgent(
                metadata=AgentDefinition(
                    name="claude",
                    display_name="Claude",
                    icon="🟠",
                    color="red",
                    spinner="dots",
                ),
                client=CommandAgentClient(
                    name="claude",
                    command_prefix=["claude", "--print"],
                    tool_flags=["--allowedTools", "Bash,Read,Write,Edit", "--dangerously-skip-permissions"],
                ),
            ),
            RegisteredAgent(
                metadata=AgentDefinition(
                    name="codex",
                    display_name="Codex",
                    icon="🔵",
                    color="blue",
                    spinner="bouncingBall",
                ),
                client=CommandAgentClient(
                    name="codex",
                    command_prefix=["codex", "exec"],
                    tool_flags=["--full-auto"],
                    command_suffix=["-"],
                ),
            ),
            RegisteredAgent(
                metadata=AgentDefinition(
                    name="gemini",
                    display_name="Gemini",
                    icon="🟡",
                    color="bright_yellow",
                    spinner="circle",
                ),
                client=CommandAgentClient(
                    name="gemini",
                    command_prefix=["gemini"],
                    tool_flags=["-y"],
                    prompt_argument=["-p"],
                    prompt_via_stdin=False,
                ),
            ),
        ]
    )
