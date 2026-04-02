"""Preflight readiness checks."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable

from debate_cli.application.contracts import AgentRegistry, PromptRepository
from debate_cli.domain.models import PreflightCheckResult


@dataclass(frozen=True)
class PreflightCheck:
    """One executable preflight check."""

    category: str
    name: str
    runner: Callable[[], tuple[bool, str]]


class PreflightService:
    """Run non-mutating readiness checks."""

    def __init__(self, prompt_repository: PromptRepository, agent_registry: AgentRegistry):
        self._prompt_repository = prompt_repository
        self._agent_registry = agent_registry

    def build_checks(self) -> list[PreflightCheck]:
        """Build all preflight checks."""
        return [
            PreflightCheck("System", "Python version", self._check_python),
            PreflightCheck("System", "Rich library", self._check_rich),
            PreflightCheck("System", "Prompt templates", self._check_prompts),
            PreflightCheck("Export Libraries", "Jinja2", self._check_jinja2),
            PreflightCheck("Export Libraries", "WeasyPrint", self._check_weasyprint),
            PreflightCheck("Export Libraries", "Pango (system)", self._check_pango),
            PreflightCheck("CLI Tools", "claude", self._check_cli("claude", ["claude", "--version"])),
            PreflightCheck("CLI Tools", "codex", self._check_cli("codex", ["codex", "--version"])),
            PreflightCheck("CLI Tools", "gemini", self._check_cli("gemini", ["gemini", "--version"])),
            PreflightCheck("Agent Liveness", "Claude", self._check_agent("claude")),
            PreflightCheck("Agent Liveness", "Codex", self._check_agent("codex")),
            PreflightCheck("Agent Liveness", "Gemini", self._check_agent("gemini")),
        ]

    def run(self) -> list[PreflightCheckResult]:
        """Execute all checks and return results."""
        results = []
        for check in self.build_checks():
            start = time.time()
            try:
                passed, detail = check.runner()
            except Exception as exc:
                passed, detail = False, str(exc)[:120]
            results.append(
                PreflightCheckResult(
                    category=check.category,
                    name=check.name,
                    passed=passed,
                    detail=detail,
                    duration=time.time() - start,
                )
            )
        return results

    def _check_python(self) -> tuple[bool, str]:
        version = sys.version_info
        detail = f"Python {version.major}.{version.minor}.{version.micro}"
        if version < (3, 11):
            detail += " (tomli fallback)"
        return version >= (3, 9), detail

    def _check_rich(self) -> tuple[bool, str]:
        try:
            from importlib.metadata import version as pkg_version

            version = pkg_version("rich")
            return True, f"Rich {version}"
        except Exception:
            return False, "Rich not installed (pip install 'debate-cli[rich]')"

    def _check_prompts(self) -> tuple[bool, str]:
        prompts = self._prompt_repository.load()
        return True, f"Packaged prompts ({len(prompts.as_mapping())} templates)"

    def _check_jinja2(self) -> tuple[bool, str]:
        try:
            from importlib.metadata import version as pkg_version
            ver = pkg_version("jinja2")
            return True, f"Jinja2 {ver} (HTML/PDF templates)"
        except Exception:
            return False, "Jinja2 not installed (pip install 'debate-cli[pdf]')"

    def _check_weasyprint(self) -> tuple[bool, str]:
        try:
            from importlib.metadata import version as pkg_version
            ver = pkg_version("weasyprint")
            return True, f"WeasyPrint {ver} (PDF rendering)"
        except Exception:
            return False, "WeasyPrint not installed (pip install 'debate-cli[pdf]')"

    def _check_pango(self) -> tuple[bool, str]:
        try:
            from weasyprint.text.ffi import pango  # noqa: F401
            return True, "Pango available (PDF text layout)"
        except ImportError:
            return False, "WeasyPrint not installed - skipping Pango check"
        except OSError:
            # Pango may be installed but not on library path
            hint = "brew install pango / apt install libpango1.0-dev"
            if sys.platform == "darwin":
                import shutil
                if shutil.which("brew"):
                    hint = (
                        "Pango may be installed but not found by Python. "
                        "The CLI auto-sets DYLD_FALLBACK_LIBRARY_PATH at startup; "
                        "if this persists, try: export DYLD_FALLBACK_LIBRARY_PATH=$(brew --prefix)/lib"
                    )
            return False, hint

    def _check_cli(self, name: str, cmd: list[str]) -> Callable[[], tuple[bool, str]]:
        def _runner() -> tuple[bool, str]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            except FileNotFoundError:
                return False, f"{name} - not found in PATH"
            except subprocess.TimeoutExpired:
                return False, f"{name} - timed out"

            version = (result.stdout.strip() or result.stderr.strip()).splitlines()
            summary = version[0][:60] if version else name
            return result.returncode == 0, f"{name} - {summary}" if summary else name

        return _runner

    def _check_agent(self, name: str) -> Callable[[], tuple[bool, str]]:
        def _runner() -> tuple[bool, str]:
            start = time.time()
            client = self._agent_registry.get_client(name)
            metadata = self._agent_registry.get_metadata(name)
            response = client.run("Respond with exactly one word: READY", allow_tools=False)
            elapsed = time.time() - start
            if "READY" in response.upper():
                return True, f"{metadata.icon} {metadata.display_name} responded ({elapsed:.1f}s)"
            return False, f"{metadata.icon} {metadata.display_name} responded but no READY ({elapsed:.1f}s)"

        return _runner
