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
        icons = self._icons()
        suffix = output_path.suffix.lower()

        # ── Single-format output (explicit extension) ──
        if suffix == ".md":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(generate_markdown_report(result, icons), encoding="utf-8")
            return [output_path]

        if suffix == ".json":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(serialize_result(result), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return [output_path]

        if suffix == ".html":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            from debate_cli.infrastructure.pdf_report import render_html_report
            output_path.write_text(render_html_report(result, icons), encoding="utf-8")
            return [output_path]

        if suffix == ".pdf":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                from debate_cli.infrastructure.pdf_report import render_pdf_report
                return [render_pdf_report(result, icons, output_path)]
            except (ImportError, OSError):
                md_path = output_path.with_suffix(".md")
                md_path.write_text(generate_markdown_report(result, icons), encoding="utf-8")
                return [md_path]

        # ── Directory output (no extension) — write all formats as report.* ──
        output_path.mkdir(parents=True, exist_ok=True)
        return self._write_all_formats(result, icons, output_path)

    def _write_all_formats(
        self, result: DebateResult, icons: dict[str, str], directory: Path,
    ) -> list[Path]:
        """Write all available formats into a directory."""
        created: list[Path] = []

        json_path = directory / "report.json"
        json_path.write_text(
            json.dumps(serialize_result(result), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        created.append(json_path)

        md_path = directory / "report.md"
        md_path.write_text(generate_markdown_report(result, icons), encoding="utf-8")
        created.append(md_path)

        try:
            from debate_cli.infrastructure.pdf_report import render_html_report
            html_path = directory / "report.html"
            html_path.write_text(render_html_report(result, icons), encoding="utf-8")
            created.append(html_path)
        except (ImportError, OSError):
            pass

        try:
            from debate_cli.infrastructure.pdf_report import render_pdf_report
            pdf_path = directory / "report.pdf"
            render_pdf_report(result, icons, pdf_path)
            created.append(pdf_path)
        except (ImportError, OSError):
            pass

        return created
