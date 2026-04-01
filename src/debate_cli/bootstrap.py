"""Runtime wiring for the CLI application."""

from __future__ import annotations

from dataclasses import dataclass

from debate_cli.application.contracts import Renderer
from debate_cli.application.debate_service import DebateService
from debate_cli.application.preflight import PreflightService
from debate_cli.infrastructure.agents import BuiltinAgentRegistry, build_builtin_agent_registry
from debate_cli.infrastructure.context import FilesystemContextLoader
from debate_cli.infrastructure.prompts import TomlPromptRepository
from debate_cli.infrastructure.renderers import build_renderer
from debate_cli.infrastructure.reports import FileReportWriter


@dataclass
class ApplicationServices:
    """Wired application dependencies."""

    agent_registry: BuiltinAgentRegistry
    prompt_repository: TomlPromptRepository
    context_loader: FilesystemContextLoader
    renderer: Renderer
    report_writer: FileReportWriter
    debate_service: DebateService
    preflight_service: PreflightService


def build_application() -> ApplicationServices:
    """Create the default application service graph."""
    agent_registry = build_builtin_agent_registry()
    prompt_repository = TomlPromptRepository()
    context_loader = FilesystemContextLoader()
    renderer = build_renderer(agent_registry)
    report_writer = FileReportWriter(agent_registry)
    debate_service = DebateService(prompt_repository, context_loader, renderer, agent_registry, report_writer)
    preflight_service = PreflightService(prompt_repository, agent_registry)
    return ApplicationServices(
        agent_registry=agent_registry,
        prompt_repository=prompt_repository,
        context_loader=context_loader,
        renderer=renderer,
        report_writer=report_writer,
        debate_service=debate_service,
        preflight_service=preflight_service,
    )
