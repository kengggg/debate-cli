"""Parsing and normalization helpers."""

from __future__ import annotations

import argparse
import re
from collections.abc import Collection

from debate_cli.domain.models import ActionMode, ActionSelection, DebateAction, StructuredDebateResponse

STRUCTURED_SECTION_NAMES = ("STEEL MAN", "CONVERGENCE", "DIVERGENCE", "CONFIDENCE")
STRUCTURED_SECTION_PATTERN = "|".join(re.escape(name) for name in STRUCTURED_SECTION_NAMES)
MODE_ALIASES = {
    "e": ActionMode.EXECUTE,
    "execute": ActionMode.EXECUTE,
    "p": ActionMode.PLAN,
    "plan": ActionMode.PLAN,
    "c": ActionMode.CONTINUE,
    "continue": ActionMode.CONTINUE,
    "x": ActionMode.EXPORT,
    "export": ActionMode.EXPORT,
}
SKIP_ALIASES = {"s", "skip"}


def parse_structured(text: str) -> StructuredDebateResponse:
    """Extract structured debate sections from agent output."""
    result = StructuredDebateResponse()

    def _extract_section_body(section_name: str) -> str:
        match = re.search(
            rf"(?ims)^\s*(?:#+\s*)?{re.escape(section_name)}\s*:\s*(.*?)(?=^\s*(?:#+\s*)?"
            rf"(?:{STRUCTURED_SECTION_PATTERN})\s*:|\Z)",
            text,
        )
        return match.group(1).strip() if match else ""

    def _extract_bullets(section_name: str) -> list[str]:
        body = _extract_section_body(section_name)
        if not body:
            return []
        points = []
        for line in body.splitlines():
            match = re.match(r"^\s*[-*]\s+(.*\S)\s*$", line)
            if match:
                points.append(match.group(1).strip())
        return points

    conf_match = re.search(
        r"(?im)^\s*(?:#+\s*)?CONFIDENCE\s*:\s*([0-9]+(?:\.[0-9]+)?)(%?)\b",
        text,
    )
    if conf_match:
        try:
            confidence = float(conf_match.group(1))
            if conf_match.group(2) or confidence > 1.0:
                confidence /= 100.0
            result.confidence = min(1.0, max(0.0, confidence))
        except ValueError:
            pass

    steel_man = _extract_section_body("STEEL MAN")
    if steel_man and steel_man.upper() != "N/A":
        result.steel_man = steel_man

    result.convergence = _extract_bullets("CONVERGENCE")
    result.divergence = _extract_bullets("DIVERGENCE")
    return result


def parse_actions(text: str) -> list[DebateAction]:
    """Parse structured action lines from the moderator's final summary."""
    actions = []
    for line in text.splitlines():
        match = re.match(
            r"^\s*(?:[-*]\s*)?ACTION\s+\d+\s*:\s*(.+?)\s*\|\s*AGENT\s*:\s*(\w+)\s*\|\s*"
            r"TYPE\s*:\s*(\w+)\s*$",
            line.strip(),
            re.IGNORECASE,
        )
        if not match:
            continue

        raw_mode = match.group(3).strip().lower()
        mode = MODE_ALIASES.get(raw_mode, ActionMode.PLAN)
        actions.append(
            DebateAction(
                action=match.group(1).strip(),
                agent=match.group(2).strip().lower(),
                mode=mode,
            )
        )
    return actions


def normalize_action_choice(
    choice: str,
    default_agent: str,
    default_mode: ActionMode,
    allowed_agents: Collection[str],
) -> ActionSelection | None:
    """Normalize interactive action choices and reject invalid modes early."""
    raw = choice.strip().lower()
    if not raw:
        return ActionSelection(agent=default_agent, mode=default_mode)

    if raw in MODE_ALIASES:
        return ActionSelection(agent=default_agent, mode=MODE_ALIASES[raw])
    if raw in SKIP_ALIASES:
        return None
    if raw in allowed_agents:
        return ActionSelection(agent=raw, mode=default_mode)

    parts = [part.strip() for part in raw.split(":", 1)]
    if len(parts) == 2:
        agent_choice, mode_choice = parts
        if mode_choice in SKIP_ALIASES:
            return None
        mode = MODE_ALIASES.get(mode_choice)
        if mode is None:
            raise ValueError(f"Unknown action mode '{mode_choice}'")
        if agent_choice not in allowed_agents:
            raise ValueError(f"Unknown agent '{agent_choice}'")
        return ActionSelection(agent=agent_choice, mode=mode)

    raise ValueError(f"Unrecognized action choice '{choice}'")


def positive_int(value: str) -> int:
    """argparse type that rejects non-positive integers."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("rounds must be at least 1")
    return parsed


def extract_focus_next_round(text: str) -> str:
    """Extract the moderator's next-round guidance section."""
    match = re.search(r"## Focus for Next Round\s*\n(.*?)(?:\n##|\Z)", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def calculate_convergence_overlap(points_a: list[str], points_b: list[str]) -> float:
    """Approximate convergence overlap using shared normalized words."""
    def _words(points: list[str]) -> set[str]:
        return {word.lower() for point in points for word in point.split()}

    a_words = _words(points_a)
    b_words = _words(points_b)
    union = a_words | b_words
    return len(a_words & b_words) / max(len(union), 1)
