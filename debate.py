#!/usr/bin/env python3
"""debate-cli: Claude Code vs Codex debate orchestrator."""

import argparse, json, subprocess, sys, os
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    console = Console()
    def print_agent(role, text):
        color = "red" if role == "claude" else "blue"
        console.print(Panel(Markdown(text), title=f"[bold {color}]{role.upper()}[/]",
                           border_style=color))
    def print_status(msg):
        console.print(f"[dim]{msg}[/dim]")
except ImportError:
    # Fallback: no rich
    def print_agent(role, text):
        marker = "🟠" if role == "claude" else "🔵"
        print(f"\n{marker} {role.upper()}\n{'─'*50}\n{text}\n")
    def print_status(msg):
        print(f"  ⋯ {msg}")


@dataclass
class DebateTurn:
    agent: str
    round: int
    position: str
    convergence: list = field(default_factory=list)
    divergence: list = field(default_factory=list)
    confidence: float = 0.5
    tool_outputs: list = field(default_factory=list)


DEBATE_PROMPT = """You are {role} in a structured debate with {opponent}.
Topic: {topic}

{context_block}

## Previous rounds:
{history}

## Your instructions:
1. State your position clearly and concisely.
2. If useful, read files or run commands to gather evidence.
3. End your response with EXACTLY this structured block:

CONVERGENCE:
- [point you agree with opponent on]

DIVERGENCE:
- [point you disagree on]

CONFIDENCE: [0.0 to 1.0]
"""


def load_context(paths: list[str]) -> str:
    chunks = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            chunks.append(f"### {path.name}\n```\n{path.read_text()[:8000]}\n```")
        elif path.is_dir():
            for f in sorted(path.rglob("*"))[:20]:
                if f.is_file() and f.suffix in ('.py','.rs','.ts','.js','.md','.toml','.yaml'):
                    chunks.append(f"### {f.relative_to(path)}\n```\n{f.read_text()[:4000]}\n```")
    return "\n\n".join(chunks) if chunks else "(no context files)"


def format_history(turns: list[DebateTurn]) -> str:
    if not turns:
        return "(first round — no history yet)"
    lines = []
    for t in turns:
        lines.append(f"### Round {t.round} — {t.agent.upper()}")
        lines.append(t.position[:2000])
        if t.convergence:
            lines.append("Convergence: " + "; ".join(t.convergence))
        if t.divergence:
            lines.append("Divergence: " + "; ".join(t.divergence))
    return "\n\n".join(lines)


def call_claude(prompt: str, allow_tools: bool = False) -> str:
    """Call claude CLI with --print flag."""
    cmd = ["claude", "--print"]
    if allow_tools:
        cmd.append("--allowedTools")
        cmd.append("Bash,Read,Write")
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr[:500]}")
    return result.stdout


def call_codex(prompt: str, allow_tools: bool = False) -> str:
    """Call codex CLI."""
    cmd = ["codex", "--quiet"]
    if allow_tools:
        cmd.append("--approval-mode")
        cmd.append("full-auto")
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"codex CLI error: {result.stderr[:500]}")
    return result.stdout


def parse_structured(text: str) -> dict:
    """Extract CONVERGENCE/DIVERGENCE/CONFIDENCE from agent output."""
    result = {"convergence": [], "divergence": [], "confidence": 0.5}
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- ") and "convergence" in text[:text.index(line)].lower().split("DIVERGENCE")[0] if "DIVERGENCE" in text else "":
            pass  # simplified — real parsing below
    # Simple extraction
    import re
    conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", text)
    if conf_match:
        result["confidence"] = float(conf_match.group(1))

    sections = re.split(r"(CONVERGENCE:|DIVERGENCE:)", text)
    current = None
    for s in sections:
        if "CONVERGENCE:" in s: current = "convergence"
        elif "DIVERGENCE:" in s: current = "divergence"
        elif current:
            points = [l.strip().lstrip("- ") for l in s.split("\n")
                      if l.strip().startswith("- ")]
            result[current] = points
            current = None
    return result


def run_debate(topic, context_paths, max_rounds=3, allow_tools=False, output=None):
    context = load_context(context_paths)
    history: list[DebateTurn] = []

    for rnd in range(1, max_rounds + 1):
        print_status(f"━━━ Round {rnd}/{max_rounds} ━━━")

        for role, caller, opponent in [
            ("claude", call_claude, "Codex"),
            ("codex", call_codex, "Claude Code"),
        ]:
            prompt = DEBATE_PROMPT.format(
                role=f"{role.upper()} (Agent {'A' if role=='claude' else 'B'})",
                opponent=opponent,
                topic=topic,
                context_block=f"## Context:\n{context}" if context else "",
                history=format_history(history),
            )

            print_status(f"  Waiting for {role}...")
            raw = caller(prompt, allow_tools)
            parsed = parse_structured(raw)

            turn = DebateTurn(
                agent=role, round=rnd, position=raw,
                convergence=parsed["convergence"],
                divergence=parsed["divergence"],
                confidence=parsed["confidence"],
            )
            history.append(turn)
            print_agent(role, raw)

        # Check convergence
        a = [t for t in history if t.round == rnd and t.agent == "claude"][0]
        b = [t for t in history if t.round == rnd and t.agent == "codex"][0]
        if a.confidence > 0.8 and b.confidence > 0.8:
            overlap = set(a.convergence) & set(b.convergence)
            if len(overlap) / max(len(a.convergence), 1) > 0.6:
                print_status("✓ Convergence reached!")
                break

    # Save log
    if output:
        Path(output).write_text(json.dumps([asdict(t) for t in history], indent=2))
        print_status(f"Log saved to {output}")

    return history


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude vs Codex debate")
    parser.add_argument("topic", help="The debate topic or question")
    parser.add_argument("--context", nargs="*", default=[], help="Files/dirs for context")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--tools", action="store_true", help="Allow agents to use tools")
    parser.add_argument("--output", "-o", help="Save debate log to JSON file")
    args = parser.parse_args()

    run_debate(args.topic, args.context, args.rounds, args.tools, args.output)