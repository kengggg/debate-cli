"""Prompt repository backed by packaged TOML files."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from debate_cli.application.contracts import PromptRepository
from debate_cli.domain.models import PromptTemplates

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


class TomlPromptRepository(PromptRepository):
    """Load packaged prompt defaults with optional file overrides."""

    def load(self, override_path: Path | None = None) -> PromptTemplates:
        if tomllib is None:
            raise RuntimeError("TOML support requires Python 3.11+ or tomli")

        default_data = self._load_toml_resource()
        if override_path is None:
            return self._build_templates(default_data)

        if not override_path.exists():
            raise FileNotFoundError(f"Prompts file not found: {override_path}")

        try:
            with override_path.open("rb") as handle:
                override_data = tomllib.load(handle)
        except Exception as exc:
            raise ValueError(f"Failed to parse prompts file {override_path}: {exc}") from exc

        merged = dict(default_data)
        for key in ("debate", "moderator", "final_summary", "action_execution"):
            default_section = merged.get(key, {})
            override_section = override_data.get(key, {})
            if isinstance(default_section, dict) and isinstance(override_section, dict):
                merged[key] = {**default_section, **override_section}

        return self._build_templates(merged)

    def _load_toml_resource(self) -> dict[str, Any]:
        resource = files("debate_cli.resources").joinpath("default_prompts.toml")
        with resource.open("rb") as handle:
            return tomllib.load(handle)

    def _build_templates(self, data: dict[str, Any]) -> PromptTemplates:
        templates = {}
        for key in ("debate", "moderator", "final_summary", "action_execution"):
            section = data.get(key)
            if not isinstance(section, dict) or not isinstance(section.get("template"), str):
                raise ValueError(f"Prompt template '{key}' is missing or invalid")
            templates[key] = section["template"]

        return PromptTemplates(
            debate=templates["debate"],
            moderator=templates["moderator"],
            final_summary=templates["final_summary"],
            action_execution=templates["action_execution"],
        )
