"""Filesystem report writer."""

from __future__ import annotations

import json
from pathlib import Path

from debate_cli.application.contracts import AgentRegistry, ReportWriter
from debate_cli.application.reporting import generate_markdown_report, serialize_result
from debate_cli.domain.models import DebateResult


class FileReportWriter(ReportWriter):
    """Write markdown/json reports to disk."""

    def __init__(self, agent_registry: AgentRegistry):
        self._agent_registry = agent_registry

    def write(self, result: DebateResult, output_path: Path) -> list[Path]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        icons = {
            name: self._agent_registry.get_metadata(name).icon
            for name in self._agent_registry.names()
        }
        markdown_report = generate_markdown_report(result, icons)
        serialized = serialize_result(result)

        suffix = output_path.suffix.lower()
        if suffix == ".md":
            output_path.write_text(markdown_report, encoding="utf-8")
            return [output_path]
        if suffix == ".json":
            output_path.write_text(
                json.dumps(serialized, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return [output_path]

        json_path = output_path.with_suffix(".json")
        markdown_path = output_path.with_suffix(".md")
        json_path.write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8")
        markdown_path.write_text(markdown_report, encoding="utf-8")
        return [json_path, markdown_path]
