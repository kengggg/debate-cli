"""Filesystem report writer."""

from __future__ import annotations

import json
from pathlib import Path

from debate_cli.application.contracts import AgentRegistry, ReportWriter
from debate_cli.application.reporting import generate_markdown_report, serialize_result
from debate_cli.domain.models import DebateResult


class FileReportWriter(ReportWriter):
    """Write markdown/json/html/pdf reports to disk."""

    def __init__(self, agent_registry: AgentRegistry):
        self._agent_registry = agent_registry

    def _icons(self) -> dict[str, str]:
        return {
            name: self._agent_registry.get_metadata(name).icon
            for name in self._agent_registry.names()
        }

    def write(self, result: DebateResult, output_path: Path) -> list[Path]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        icons = self._icons()

        suffix = output_path.suffix.lower()

        if suffix == ".md":
            output_path.write_text(generate_markdown_report(result, icons), encoding="utf-8")
            return [output_path]

        if suffix == ".json":
            output_path.write_text(
                json.dumps(serialize_result(result), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return [output_path]

        if suffix == ".html":
            from debate_cli.infrastructure.pdf_report import render_html_report
            output_path.write_text(render_html_report(result, icons), encoding="utf-8")
            return [output_path]

        if suffix == ".pdf":
            from debate_cli.infrastructure.pdf_report import render_pdf_report
            return [render_pdf_report(result, icons, output_path)]

        # No extension → write json + md + pdf (if weasyprint available)
        created: list[Path] = []

        json_path = output_path.with_suffix(".json")
        json_path.write_text(
            json.dumps(serialize_result(result), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        created.append(json_path)

        md_path = output_path.with_suffix(".md")
        md_path.write_text(generate_markdown_report(result, icons), encoding="utf-8")
        created.append(md_path)

        try:
            from debate_cli.infrastructure.pdf_report import render_pdf_report
            pdf_path = output_path.with_suffix(".pdf")
            render_pdf_report(result, icons, pdf_path)
            created.append(pdf_path)
        except ImportError:
            pass  # weasyprint not installed — skip PDF

        return created
