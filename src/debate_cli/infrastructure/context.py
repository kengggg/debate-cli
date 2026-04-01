"""Filesystem context loader."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from debate_cli.application.contracts import ContextLoader

CONTEXT_FILE_EXTENSIONS = {
    ".json",
    ".js",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
MAX_CONTEXT_FILES_PER_DIR = 20
MAX_DIRECT_FILE_CONTEXT_CHARS = 8000
MAX_DIR_FILE_CONTEXT_CHARS = 4000


class FilesystemContextLoader(ContextLoader):
    """Load prompt context from explicit files and directories."""

    def load(
        self,
        paths: Sequence[str],
        status_callback: Callable[[str], None] | None = None,
    ) -> str:
        chunks = []
        seen_paths: set[str] = set()
        for raw_path in paths:
            path = Path(raw_path)
            if path.is_file():
                key = self._dedupe_key(path)
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                text = self._read_context_file(path, MAX_DIRECT_FILE_CONTEXT_CHARS, status_callback)
                if text is not None:
                    chunks.append(f"### {path}\n```\n{text}\n```")
                continue

            if path.is_dir():
                for child in self._iter_directory_context_files(path, status_callback):
                    key = self._dedupe_key(child)
                    if key in seen_paths:
                        continue
                    seen_paths.add(key)
                    text = self._read_context_file(child, MAX_DIR_FILE_CONTEXT_CHARS, status_callback)
                    if text is not None:
                        chunks.append(f"### {child.relative_to(path)}\n```\n{text}\n```")
                continue

            if status_callback:
                status_callback(f"  ⚠️  Context path not found: {raw_path}")

        return "\n\n".join(chunks) if chunks else "(no context files)"

    def _dedupe_key(self, path: Path) -> str:
        try:
            return str(path.resolve(strict=False))
        except OSError:
            return str(path.absolute())

    def _read_context_file(
        self,
        path: Path,
        max_chars: int,
        status_callback: Callable[[str], None] | None,
    ) -> str | None:
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            if status_callback:
                status_callback(f"  ⚠️  Skipping {path} (unreadable)")
            return None

        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n... [truncated]"
        return text

    def _iter_directory_context_files(
        self,
        directory: Path,
        status_callback: Callable[[str], None] | None,
    ) -> list[Path]:
        files = []
        try:
            for candidate in directory.rglob("*"):
                try:
                    if candidate.is_file() and candidate.suffix.lower() in CONTEXT_FILE_EXTENSIONS:
                        files.append(candidate)
                except OSError:
                    continue
        except OSError as exc:
            if status_callback:
                status_callback(f"  ⚠️  Skipping {directory} ({exc})")
            return []

        return sorted(files)[:MAX_CONTEXT_FILES_PER_DIR]
