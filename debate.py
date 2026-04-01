#!/usr/bin/env python3
"""debate-cli: Claude Code vs Codex debate orchestrator with Gemini moderator."""

import argparse, json, subprocess, sys, os, re, textwrap, time
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

# ─── Terminal rendering ───────────────────────────────────────────────────────

AGENT_COLORS = {"claude": "red", "codex": "blue", "gemini": "bright_yellow"}
AGENT_ICONS  = {"claude": "🟠", "codex": "🔵", "gemini": "🟡"}

AGENT_SPINNERS = {"claude": "dots", "codex": "bouncingBall", "gemini": "circle"}

try:
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.padding import Padding
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    console = Console()

    # ── Core display ──

    def print_agent(role, text, turn=None):
        color = AGENT_COLORS.get(role, "white")
        icon  = AGENT_ICONS.get(role, "⚪")
        bx    = box.HEAVY if role == "gemini" else box.ROUNDED
        subtitle = f"confidence {turn.confidence:.0%}" if turn and turn.confidence > 0 else ""
        console.print(Panel(
            Markdown(text),
            title=f"[bold {color}]{icon} {role.upper()}[/]",
            subtitle=f"[dim]{subtitle}[/]" if subtitle else None,
            border_style=color, box=bx, padding=(1, 2),
        ))

    def print_steel_man(role, steel_man_text):
        if not steel_man_text:
            return
        opponent = "Codex" if role == "claude" else "Claude"
        console.print(Panel(
            Markdown(steel_man_text),
            title=f"[dim]🤝 {role.upper()} steel-manning {opponent}[/]",
            border_style="dim", box=box.SIMPLE, padding=(0, 2),
        ))

    def print_status(msg):
        console.print(f"[dim]{msg}[/dim]")

    def print_header(msg):
        console.print()
        console.print(Align.center(f"[bold bright_white]{msg}[/]"))
        console.print()

    def ask_user(prompt_text, default=""):
        try:
            return Prompt.ask(f"[bold green]👤 YOU[/bold green] {prompt_text}", default=default)
        except (EOFError, KeyboardInterrupt):
            return default

    # ── Animated elements ──

    def print_turn_stats(turn):
        """Animate confidence bar filling from 0 → final value, then show stats."""
        target = int(turn.confidence * 100)
        try:
            with Live(refresh_per_second=30, transient=True, console=console) as live:
                for pct in range(0, target + 1, max(1, target // 15)):
                    bar_color = "green" if pct > 80 else "yellow" if pct > 50 else "red"
                    filled = pct // 5
                    bar = f"[{bar_color}]{'█' * filled}{'░' * (20 - filled)}[/] {pct}%"
                    grid = Table.grid(padding=(0, 2))
                    grid.add_column()
                    grid.add_column()
                    grid.add_column()
                    grid.add_row(bar, "", "")
                    live.update(Padding(grid, (0, 4)))
                    time.sleep(0.025)
        except Exception:
            pass  # fall through to static display

        # Final persistent stats
        bar_color = "green" if turn.confidence > 0.8 else "yellow" if turn.confidence > 0.5 else "red"
        bar = f"[{bar_color}]{'█' * (target // 5)}{'░' * (20 - target // 5)}[/] {target}%"
        stats = Table.grid(padding=(0, 2))
        stats.add_column()
        stats.add_column()
        stats.add_column()
        stats.add_row(
            bar,
            f"[green]✓ {len(turn.convergence)} agree[/]",
            f"[red]✗ {len(turn.divergence)} disagree[/]",
        )
        console.print(Padding(stats, (0, 4)))
        console.print()

    def print_convergence_meter(overlap_ratio):
        """Animated meter showing how close agents are to agreement."""
        target = int(overlap_ratio * 100)
        color = "green" if target > 60 else "yellow" if target > 30 else "red"
        label = "Converging!" if target > 60 else "Narrowing..." if target > 30 else "Divergent"
        try:
            with Live(refresh_per_second=20, transient=True, console=console) as live:
                for i in range(0, target + 1, max(1, target // 12)):
                    c = "green" if i > 60 else "yellow" if i > 30 else "red"
                    filled = i // 5
                    meter = Align.center(
                        f"[{c}]{'▰' * filled}{'▱' * (20 - filled)}[/]  [{c}]{i}%[/]"
                    )
                    live.update(meter)
                    time.sleep(0.025)
        except Exception:
            pass
        console.print(Align.center(
            f"[{color}]{'▰' * (target // 5)}{'▱' * (20 - target // 5)}[/]  "
            f"[bold {color}]{target}% {label}[/]"
        ))
        console.print()

    def print_round_comparison(claude_turn, codex_turn):
        agree = Table(
            title="[bold green]✓ Convergence[/]", box=box.SIMPLE,
            border_style="green", show_header=False, padding=(0, 1),
        )
        agree.add_column()
        for p in set(claude_turn.convergence + codex_turn.convergence) or ["(none yet)"]:
            agree.add_row(f"[green]•[/] {p}")

        disagree = Table(
            title="[bold red]✗ Divergence[/]", box=box.SIMPLE,
            border_style="red", show_header=False, padding=(0, 1),
        )
        disagree.add_column()
        for p in set(claude_turn.divergence + codex_turn.divergence) or ["(none yet)"]:
            disagree.add_row(f"[red]•[/] {p}")

        console.print(Columns([agree, disagree], equal=True, padding=(0, 2)))
        console.print()

    def print_round_transition():
        """Brief animated transition between rounds."""
        frames = ["·", "· ·", "· · ·", "· · · ·", "· · · · ·", "· · · ·", "· · ·"]
        try:
            with Live(refresh_per_second=10, transient=True, console=console) as live:
                for frame in frames:
                    live.update(Align.center(f"[dim]{frame}[/]"))
                    time.sleep(0.08)
        except Exception:
            pass

    def print_round_progress(current, total):
        filled = "[bright_white]●[/]" * current
        empty  = "[dim]○[/]" * (total - current)
        console.print()
        console.print(Align.center(f"{filled}{empty}  [bold]Round {current} of {total}[/]"))
        console.print()

    def print_banner(topic, max_rounds, allow_tools, context_count):
        """Animated banner reveal: swords → title → full details."""
        def _make_banner(*rows):
            grid = Table.grid(padding=0)
            grid.add_column(justify="center")
            for r in rows:
                grid.add_row(r)
            return Panel(grid, box=box.DOUBLE, border_style="bright_white", padding=(1, 2))

        title = "[bold bright_white]⚔️  STEEL MAN DEBATE  ⚔️[/]"
        topic_line = f"[italic]{topic}[/]"
        details = (
            f"[red]🟠 Claude[/]  vs  [blue]🔵 Codex[/]  ·  "
            f"[bright_yellow]🟡 Gemini[/] moderating  ·  "
            f"{max_rounds} rounds  ·  "
            f"tools [{'bold green' if allow_tools else 'dim'}]{'on' if allow_tools else 'off'}[/]  ·  "
            f"{context_count} context path(s)"
        )

        try:
            with Live(refresh_per_second=8, transient=True, console=console) as live:
                live.update(_make_banner("⚔️"))
                time.sleep(0.25)
                live.update(_make_banner(title))
                time.sleep(0.25)
                live.update(_make_banner(title, topic_line))
                time.sleep(0.25)
                live.update(_make_banner(title, topic_line, "", details))
                time.sleep(0.3)
        except Exception:
            pass
        console.print(_make_banner(title, topic_line, "", details))

    def print_convergence_reached():
        """Animated convergence celebration."""
        frames = [
            Align.center("[green]✅ Convergence...[/]"),
            Align.center("[bold green]✅ Convergence reached![/]"),
            Align.center("[bold bright_green]✅ ✅ CONVERGENCE REACHED! ✅ ✅[/]"),
        ]
        try:
            with Live(refresh_per_second=4, transient=True, console=console) as live:
                for frame in frames:
                    live.update(frame)
                    time.sleep(0.3)
        except Exception:
            pass
        console.print(Align.center("[bold bright_green]✅ CONVERGENCE REACHED![/]"))
        console.print()

    def print_actions_table(actions):
        table = Table(
            title="[bold]📋 Recommended Actions[/]", box=box.ROUNDED,
            border_style="bright_white", show_lines=True, padding=(0, 1),
        )
        table.add_column("#", style="bold", width=3, justify="center")
        table.add_column("Action", min_width=40)
        table.add_column("Agent", width=16, justify="center")
        table.add_column("Type", width=10, justify="center")

        type_styles = {"execute": "[bold green]execute[/]", "plan": "[bold yellow]plan[/]"}
        for i, a in enumerate(actions, 1):
            agent = a.get("agent", "?")
            icon = AGENT_ICONS.get(agent, "👤" if agent == "user" else "⚪")
            type_display = type_styles.get(a.get("type", ""), a.get("type", "plan"))
            table.add_row(str(i), a["action"], f"{icon} {agent}", type_display)
        console.print(table)

    def agent_spinner(role):
        """Context manager: themed animated spinner while an agent is thinking."""
        color   = AGENT_COLORS.get(role, "white")
        icon    = AGENT_ICONS.get(role, "⚪")
        spinner = AGENT_SPINNERS.get(role, "dots")
        return console.status(
            f"[bold {color}]{icon} {role.upper()} is thinking...[/]",
            spinner=spinner,
        )

except ImportError:
    # Fallback: no rich — static output, no animations
    def print_agent(role, text, turn=None):
        marker = AGENT_ICONS.get(role, "⚪")
        print(f"\n{marker} {role.upper()}\n{'─'*60}\n{text}\n")

    def print_steel_man(role, steel_man_text):
        if not steel_man_text:
            return
        opponent = "Codex" if role == "claude" else "Claude"
        print(f"  🤝 {role.upper()} steel-manning {opponent}:")
        print(f"     {steel_man_text}\n")

    def print_turn_stats(turn):
        conf_pct = int(turn.confidence * 100)
        bar = "█" * (conf_pct // 5) + "░" * (20 - conf_pct // 5)
        print(f"  {bar} {conf_pct}%  ✓{len(turn.convergence)} agree  ✗{len(turn.divergence)} disagree")

    def print_convergence_meter(overlap_ratio):
        pct = int(overlap_ratio * 100)
        label = "Converging!" if pct > 60 else "Narrowing..." if pct > 30 else "Divergent"
        filled = pct // 5
        print(f"  {'▰' * filled}{'▱' * (20 - filled)}  {pct}% {label}")

    def print_round_comparison(claude_turn, codex_turn):
        print("  Convergence:", "; ".join(set(claude_turn.convergence + codex_turn.convergence)) or "(none)")
        print("  Divergence:", "; ".join(set(claude_turn.divergence + codex_turn.divergence)) or "(none)")

    def print_round_transition():
        print("  · · · · ·")

    def print_convergence_reached():
        print("  ✅ CONVERGENCE REACHED!")

    def print_status(msg):
        print(f"  ⋯ {msg}")

    def print_header(msg):
        print(f"\n{'━'*60}\n  {msg}\n{'━'*60}")

    def print_round_progress(current, total):
        filled = "●" * current
        empty = "○" * (total - current)
        print(f"\n  {filled}{empty}  Round {current} of {total}\n")

    def print_banner(topic, max_rounds, allow_tools, context_count):
        print(f"\n{'═'*60}")
        print(f"  ⚔️  STEEL MAN DEBATE  ⚔️")
        print(f"  {topic}")
        print(f"  Claude vs Codex · Gemini moderating · {max_rounds} rounds")
        print(f"{'═'*60}\n")

    def print_actions_table(actions):
        print("\n📋 Recommended Actions:")
        for i, a in enumerate(actions, 1):
            icon = AGENT_ICONS.get(a.get("agent", ""), "⚪")
            print(f"  {i}. {icon} [{a.get('agent','?')}] {a['action']} ({a.get('type','plan')})")
        print()

    def ask_user(prompt_text, default=""):
        try:
            val = input(f"👤 YOU  {prompt_text} [{default}]: ").strip()
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            return default

    class _NoOpCtx:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def agent_spinner(role):
        print(f"  ⏳ {AGENT_ICONS.get(role, '⚪')} {role.upper()} is thinking...")
        return _NoOpCtx()


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class DebateTurn:
    agent: str
    round: int
    position: str
    convergence: list = field(default_factory=list)
    divergence: list = field(default_factory=list)
    steel_man: str = ""
    confidence: float = 0.5
    tool_outputs: list = field(default_factory=list)

@dataclass
class ModerationSummary:
    round: int
    summary: str
    focus_next: str
    raw: str = ""

@dataclass
class UserInput:
    round: int
    text: str


# ─── Prompts ──────────────────────────────────────────────────────────────────

# Hardcoded defaults (used when prompts.toml is missing or tomllib unavailable)
_DEFAULT_PROMPTS = {
    "debate": textwrap.dedent("""\
        You are {role} in a structured STEEL MAN debate with {opponent}.
        A moderator (Gemini) is overseeing this debate to help the user reach a better outcome.

        Topic: {topic}

        {context_block}

        ## Previous rounds:
        {history}

        {moderator_guidance}

        {user_input_block}

        ## Your instructions:
        1. If this is NOT the first round, you MUST first STEEL MAN your opponent's strongest
           argument from the previous round. Present it as charitably and accurately as possible
           — show that you truly understand their best case before you counter it.
        2. State your own position clearly and concisely.
        3. If useful, read files or run commands to gather evidence.
        4. Respond to the moderator's guidance and the user's input if provided.
        5. End your response with EXACTLY this structured block:

        STEEL MAN:
        [Your charitable restatement of opponent's strongest argument. Write "N/A" if first round.]

        CONVERGENCE:
        - [point you agree with opponent on]

        DIVERGENCE:
        - [point you disagree on]

        CONFIDENCE: [0.0 to 1.0]
    """),
    "moderator": textwrap.dedent("""\
        You are the MODERATOR of a structured STEEL MAN debate between Claude Code and Codex.
        Your role is to help the user get the best possible outcome.

        Topic: {topic}

        ## Round {round} debate:
        {round_turns}

        {user_input_block}

        ## Your tasks:
        1. **Summarize** this round: what each agent argued, where they agree, where they diverge.
        2. **Evaluate steel man quality**: Did each agent accurately and charitably represent their
           opponent's strongest argument? Call out any distortions, straw men, or weak steel mans.
        3. **Evaluate** the strength of each argument. Be critical — call out weak reasoning.
        4. **Steer** the next round: suggest what each agent should focus on or investigate.
           Be specific — "Claude should benchmark X" or "Codex should address the scalability concern".
        5. If the debate seems to be going in circles, say so.

        Format your response as:

        ## Summary
        [your summary]

        ## Steel Man Quality
        - Claude's steel man: [evaluation]
        - Codex's steel man: [evaluation]

        ## Focus for Next Round
        - Claude should: [specific guidance]
        - Codex should: [specific guidance]
    """),
    "final_summary": textwrap.dedent("""\
        You are the MODERATOR wrapping up a structured STEEL MAN debate between Claude Code and Codex.
        Your goal: give the user a clear, actionable outcome.

        Topic: {topic}

        ## Full debate history:
        {full_history}

        ## User inputs throughout:
        {user_inputs}

        ## Your tasks:
        1. Write a **final summary** of the debate outcome.
        2. Note how the steel man process affected the debate — did it lead to better understanding?
        3. List the **points of consensus** (what both agents agree on).
        4. List the **unresolved disagreements** and your recommendation on each.
        5. Produce a **numbered action list** — concrete next steps the user should take.
           For each action, suggest which agent (claude, codex, gemini, or user) is best suited.

        Format the action list EXACTLY like this (one per line, parseable):

        ## Actions
        ACTION 1: [description] | AGENT: [claude/codex/gemini/user] | TYPE: [execute/plan]
        ACTION 2: [description] | AGENT: [claude/codex/gemini/user] | TYPE: [execute/plan]
        ...
    """),
    "action_execution": textwrap.dedent("""\
        You have been assigned an action from a debate between Claude Code and Codex.

        Original topic: {topic}
        Debate conclusion summary: {summary}

        YOUR ACTION: {action}
        MODE: {mode}

        {context_block}

        {instruction}
    """),
}


def load_prompts(path: Path | None = None) -> dict[str, str]:
    """Load prompt templates from TOML file, falling back to built-in defaults."""
    prompts = dict(_DEFAULT_PROMPTS)

    if path is None:
        path = Path(__file__).parent / "prompts.toml"

    if path.exists() and tomllib is not None:
        with open(path, "rb") as f:
            custom = tomllib.load(f)
        for key in prompts:
            if key in custom and "template" in custom[key]:
                prompts[key] = custom[key]["template"]
    elif path.exists() and tomllib is None:
        print_status("  ⚠️  prompts.toml found but tomllib/tomli not available — using defaults")

    return prompts


# ─── Agent callers ────────────────────────────────────────────────────────────

def call_claude(prompt: str, allow_tools: bool = False) -> str:
    """Call claude CLI with --print flag."""
    cmd = ["claude", "--print"]
    if allow_tools:
        cmd.extend(["--allowedTools", "Bash,Read,Write,Edit", "--dangerously-skip-permissions"])
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr[:500]}")
    return result.stdout


def call_codex(prompt: str, allow_tools: bool = False) -> str:
    """Call codex CLI in non-interactive mode."""
    cmd = ["codex", "exec"]
    if allow_tools:
        cmd.append("--full-auto")
    cmd.append("-")
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"codex CLI error: {result.stderr[:500]}")
    return result.stdout


def call_gemini(prompt: str, allow_tools: bool = False) -> str:
    """Call gemini CLI in headless mode via stdin."""
    cmd = ["gemini", "-p", ""]  # -p "" enables headless mode, prompt via stdin
    if allow_tools:
        cmd.append("-y")  # yolo mode: auto-approve tool actions
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"gemini CLI error: {result.stderr[:500]}")
    if not result.stdout.strip() and result.stderr.strip():
        raise RuntimeError(f"gemini returned empty output. stderr: {result.stderr[:500]}")
    return result.stdout


AGENT_CALLERS = {
    "claude": call_claude,
    "codex": call_codex,
    "gemini": call_gemini,
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_context(paths: list[str]) -> str:
    chunks = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            try:
                chunks.append(f"### {path.name}\n```\n{path.read_text()[:8000]}\n```")
            except (UnicodeDecodeError, PermissionError):
                print_status(f"  ⚠️  Skipping {path} (unreadable)")
        elif path.is_dir():
            for f in sorted(path.rglob("*"))[:20]:
                if f.is_file() and f.suffix in ('.py', '.rs', '.ts', '.js', '.md', '.toml', '.yaml', '.json'):
                    try:
                        chunks.append(f"### {f.relative_to(path)}\n```\n{f.read_text()[:4000]}\n```")
                    except (UnicodeDecodeError, PermissionError):
                        pass
        else:
            print_status(f"  ⚠️  Context path not found: {p}")
    return "\n\n".join(chunks) if chunks else "(no context files)"


def format_history(turns: list[DebateTurn], moderations: list[ModerationSummary] = None,
                   user_inputs: list[UserInput] = None) -> str:
    if not turns:
        return "(first round — no history yet)"

    moderations = moderations or []
    user_inputs = user_inputs or []
    mod_by_round = {m.round: m for m in moderations}
    user_by_round = {u.round: u for u in user_inputs}

    lines = []
    rounds_seen = sorted(set(t.round for t in turns))
    for rnd in rounds_seen:
        round_turns = [t for t in turns if t.round == rnd]
        for t in round_turns:
            lines.append(f"### Round {t.round} — {t.agent.upper()}")
            lines.append(t.position[:2000])
            if t.steel_man:
                lines.append("Steel Man: " + t.steel_man[:500])
            if t.convergence:
                lines.append("Convergence: " + "; ".join(t.convergence))
            if t.divergence:
                lines.append("Divergence: " + "; ".join(t.divergence))

        if rnd in mod_by_round:
            lines.append(f"### Round {rnd} — MODERATOR (Gemini)")
            lines.append(mod_by_round[rnd].summary[:1500])

        if rnd in user_by_round and user_by_round[rnd].text:
            lines.append(f"### Round {rnd} — USER")
            lines.append(user_by_round[rnd].text)

    return "\n\n".join(lines)


def parse_structured(text: str) -> dict:
    """Extract STEEL MAN/CONVERGENCE/DIVERGENCE/CONFIDENCE from agent output."""
    result = {"steel_man": "", "convergence": [], "divergence": [], "confidence": 0.5}

    # Extract confidence
    conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", text)
    if conf_match:
        try:
            result["confidence"] = min(1.0, max(0.0, float(conf_match.group(1))))
        except ValueError:
            pass

    # Extract steel man (free text between STEEL MAN: and next section header)
    sm_match = re.search(
        r"STEEL MAN:\s*\n(.*?)(?=\n(?:CONVERGENCE|DIVERGENCE|CONFIDENCE):|\Z)",
        text, re.DOTALL,
    )
    if sm_match:
        steel_man = sm_match.group(1).strip()
        if steel_man.upper() != "N/A":
            result["steel_man"] = steel_man

    # Extract convergence/divergence bullet lists
    sections = re.split(r"(CONVERGENCE:|DIVERGENCE:)", text)
    current = None
    for s in sections:
        if "CONVERGENCE:" in s:
            current = "convergence"
        elif "DIVERGENCE:" in s:
            current = "divergence"
        elif current:
            points = [l.strip().removeprefix("- ") for l in s.split("\n")
                      if l.strip().startswith("- ")]
            result[current] = points
            current = None
    return result


def parse_actions(text: str) -> list[dict]:
    """Parse ACTION lines from moderator's final summary."""
    actions = []
    for line in text.split("\n"):
        match = re.match(
            r"ACTION\s+\d+:\s*(.+?)\s*\|\s*AGENT:\s*(\w+)\s*\|\s*TYPE:\s*(\w+)",
            line.strip(),
            re.IGNORECASE,
        )
        if match:
            actions.append({
                "action": match.group(1).strip(),
                "agent": match.group(2).strip().lower(),
                "type": match.group(3).strip().lower(),
            })
    return actions


# ─── Markdown report generation ───────────────────────────────────────────────

def generate_markdown_report(topic, history, moderations, user_inputs, final_raw, actions):
    """Generate a readable markdown transcript of the entire debate."""
    lines = [f"# Steel Man Debate: {topic}\n"]

    rounds_seen = sorted(set(t.round for t in history))
    mod_by_round = {m.round: m for m in moderations}
    user_by_round = {u.round: u for u in user_inputs}

    for rnd in rounds_seen:
        lines.append(f"## Round {rnd}\n")
        round_turns = [t for t in history if t.round == rnd]

        for t in round_turns:
            icon = AGENT_ICONS.get(t.agent, "⚪")
            lines.append(f"### {icon} {t.agent.upper()} (confidence: {t.confidence:.0%})\n")
            lines.append(t.position.strip())
            lines.append("")

            if t.steel_man:
                opponent = "Codex" if t.agent == "claude" else "Claude"
                lines.append(f"**Steel Man of {opponent}'s argument:**")
                for sm_line in t.steel_man.strip().split("\n"):
                    lines.append(f"> {sm_line}")
                lines.append("")

            if t.convergence:
                lines.append("**Convergence:** " + "; ".join(t.convergence))
            if t.divergence:
                lines.append("**Divergence:** " + "; ".join(t.divergence))
            lines.append("")

        if rnd in mod_by_round:
            lines.append(f"### 🟡 Moderator\n")
            lines.append(mod_by_round[rnd].summary.strip())
            lines.append("")

        if rnd in user_by_round and user_by_round[rnd].text:
            lines.append(f"### 👤 User\n")
            lines.append(user_by_round[rnd].text.strip())
            lines.append("")

        lines.append("---\n")

    lines.append("## Final Summary\n")
    lines.append(final_raw.strip())
    lines.append("")

    if actions:
        lines.append("## Recommended Actions\n")
        lines.append("| # | Action | Agent | Type |")
        lines.append("|---|--------|-------|------|")
        for i, a in enumerate(actions, 1):
            icon = AGENT_ICONS.get(a.get("agent", ""), "⚪")
            lines.append(f"| {i} | {a['action']} | {icon} {a.get('agent', '?')} | {a.get('type', 'plan')} |")
        lines.append("")

    return "\n".join(lines)


# ─── Preflight check ─────────────────────────────────────────────────────────

def run_preflight():
    """Run system and agent readiness checks with animated display."""
    results = []  # list of {"category", "name", "passed", "detail", "duration"}

    def _add(category, name, check_fn):
        start = time.time()
        try:
            passed, detail = check_fn()
        except Exception as e:
            passed, detail = False, str(e)[:80]
        elapsed = time.time() - start
        results.append({
            "category": category, "name": name,
            "passed": passed, "detail": detail, "duration": elapsed,
        })

    def _render(pending=None):
        """Build the preflight panel from current results + optional pending check."""
        grid = Table.grid(padding=(0, 2))
        grid.add_column(width=4)
        grid.add_column(min_width=44)
        grid.add_column(justify="right", width=8)

        current_cat = None
        for r in results:
            if r["category"] != current_cat:
                current_cat = r["category"]
                grid.add_row("", f"[bold bright_white]{current_cat}[/]", "")
            icon = "[green]✅[/]" if r["passed"] else "[red]❌[/]"
            grid.add_row(f" {icon}", r["detail"], f"[dim]{r['duration']:.1f}s[/]")

        if pending:
            cat, name, icon = pending
            if cat != current_cat:
                grid.add_row("", f"[bold bright_white]{cat}[/]", "")
            grid.add_row(f" {icon}", f"[dim]{name}...[/]", "")

        return Panel(grid, title="[bold]🔍 PREFLIGHT CHECK[/]",
                     box=box.ROUNDED, border_style="bright_white", padding=(1, 2))

    # ── Define checks ──

    def check_python():
        v = sys.version_info
        detail = f"Python {v.major}.{v.minor}.{v.micro}"
        if v < (3, 11):
            detail += " [dim](tomli fallback)[/]"
        return v >= (3, 9), detail

    def check_rich():
        try:
            from importlib.metadata import version as pkg_version
            ver = pkg_version("rich")
            return True, f"Rich {ver}"
        except Exception:
            return False, "Rich not installed [dim](pip install rich)[/]"

    def check_toml():
        if tomllib is not None:
            mod = getattr(tomllib, "__name__", "tomli")
            return True, f"TOML support ({mod})"
        return False, "No TOML support [dim](pip install tomli)[/]"

    def check_prompts():
        p = load_prompts()
        return True, f"prompts.toml ({len(p)} templates)"

    def check_cli(name, cmd):
        def _check():
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                ver = (r.stdout.strip() or r.stderr.strip()).split("\n")[0][:60]
                return r.returncode == 0, f"{name} — {ver}" if ver else name
            except FileNotFoundError:
                return False, f"{name} — not found in PATH"
            except subprocess.TimeoutExpired:
                return False, f"{name} — timed out"
        return _check

    def check_agent(name, caller):
        def _check():
            start = time.time()
            result = caller("Respond with exactly one word: READY", allow_tools=False)
            elapsed = time.time() - start
            icon = AGENT_ICONS.get(name, "⚪")
            if "READY" in result.upper():
                return True, f"{icon} {name.capitalize()} responded [dim]({elapsed:.1f}s)[/]"
            return False, f"{icon} {name.capitalize()} responded but no READY [dim]({elapsed:.1f}s)[/]"
        return _check

    checks = [
        ("System", "Python version", check_python),
        ("System", "Rich library", check_rich),
        ("System", "TOML support", check_toml),
        ("System", "Prompt templates", check_prompts),
        ("CLI Tools", "claude", check_cli("claude", ["claude", "--version"])),
        ("CLI Tools", "codex", check_cli("codex", ["codex", "--version"])),
        ("CLI Tools", "gemini", check_cli("gemini", ["gemini", "--version"])),
        ("Agent Liveness", "Claude", check_agent("claude", call_claude)),
        ("Agent Liveness", "Codex", check_agent("codex", call_codex)),
        ("Agent Liveness", "Gemini", check_agent("gemini", call_gemini)),
    ]

    # ── Run checks with animation ──

    try:
        from rich.live import Live as _Live

        with _Live(_render(), refresh_per_second=8, console=console) as live:
            for cat, name, fn in checks:
                agent_icon = AGENT_ICONS.get(name.lower(), "⏳")
                live.update(_render(pending=(cat, name, agent_icon)))
                _add(cat, name, fn)
                live.update(_render())
                time.sleep(0.05)

        # Final summary
        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        if passed == total:
            print_convergence_reached.__wrapped__ if hasattr(print_convergence_reached, '__wrapped__') else None
            console.print()
            console.print(Align.center(
                f"[bold bright_green]✅ All {total} checks passed — ready to debate![/]"
            ))
        else:
            console.print()
            console.print(Align.center(
                f"[bold yellow]⚠️  {passed}/{total} passed, {total - passed} failed — see above[/]"
            ))
        console.print()

    except ImportError:
        # No rich — plain text
        for cat, name, fn in checks:
            _add(cat, name, fn)

        current_cat = None
        for r in results:
            if r["category"] != current_cat:
                current_cat = r["category"]
                print(f"\n  {current_cat}")
            icon = "✅" if r["passed"] else "❌"
            print(f"  {icon} {r['detail']:<50} {r['duration']:.1f}s")

        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        if passed == total:
            print(f"\n  ✅ All {total} checks passed — ready to debate!\n")
        else:
            print(f"\n  ⚠️  {passed}/{total} passed, {total - passed} failed\n")

    return all(r["passed"] for r in results)


# ─── Main debate loop ─────────────────────────────────────────────────────────

def run_debate(topic, context_paths, max_rounds=3, allow_tools=False, output=None,
               prompts_path=None):
    prompts = load_prompts(prompts_path)
    context = load_context(context_paths)
    context_block = f"## Context:\n{context}" if context != "(no context files)" else ""

    history: list[DebateTurn] = []
    moderations: list[ModerationSummary] = []
    user_inputs: list[UserInput] = []

    print_banner(topic, max_rounds, allow_tools, len(context_paths))

    for rnd in range(1, max_rounds + 1):
        if rnd > 1:
            print_round_transition()
        print_round_progress(rnd, max_rounds)

        # ── Get the moderator's guidance from previous round ──
        last_mod = next((m for m in moderations if m.round == rnd - 1), None)
        moderator_guidance = ""
        if last_mod and last_mod.focus_next:
            moderator_guidance = f"## Moderator guidance for this round:\n{last_mod.focus_next}"

        # ── Get user input from previous round ──
        last_user = next((u for u in user_inputs if u.round == rnd - 1), None)
        user_input_text = ""
        if last_user and last_user.text:
            user_input_text = f"## User's direction:\n{last_user.text}"

        # ── Debaters take turns ──
        for role, opponent in [("claude", "Codex"), ("codex", "Claude Code")]:
            prompt = prompts["debate"].format(
                role=f"{role.upper()} (Agent {'A' if role == 'claude' else 'B'})",
                opponent=opponent,
                topic=topic,
                context_block=context_block,
                history=format_history(history, moderations, user_inputs),
                moderator_guidance=moderator_guidance,
                user_input_block=user_input_text,
            )

            errored = False
            with agent_spinner(role):
                try:
                    raw = AGENT_CALLERS[role](prompt, allow_tools)
                except Exception as e:
                    raw = f"[ERROR] Agent {role} failed: {e}"
                    errored = True

            if errored:
                print_status(f"  ⚠️  {role} failed")
                turn = DebateTurn(
                    agent=role, round=rnd, position=raw,
                    confidence=0.0,
                )
            else:
                parsed = parse_structured(raw)
                turn = DebateTurn(
                    agent=role, round=rnd, position=raw,
                    steel_man=parsed["steel_man"],
                    convergence=parsed["convergence"],
                    divergence=parsed["divergence"],
                    confidence=parsed["confidence"],
                )
            history.append(turn)
            print_steel_man(role, turn.steel_man)
            print_agent(role, raw, turn)
            print_turn_stats(turn)

        # ── Moderator summarizes the round ──
        round_turns = [t for t in history if t.round == rnd]
        round_turns_text = "\n\n".join(
            f"### {t.agent.upper()}:\n{t.position[:3000]}" for t in round_turns
        )
        last_user_text = ""
        if last_user and last_user.text:
            last_user_text = f"## User said after previous round:\n{last_user.text}"

        mod_prompt = prompts["moderator"].format(
            topic=topic,
            round=rnd,
            round_turns=round_turns_text,
            user_input_block=last_user_text,
        )

        with agent_spinner("gemini"):
            try:
                mod_raw = call_gemini(mod_prompt, allow_tools=False)
            except Exception as e:
                mod_raw = f"[Moderator error: {e}]"
                print_status(f"  ⚠️  Gemini moderator failed: {e}")

        # Extract focus section
        focus_match = re.search(
            r"## Focus for Next Round\s*\n(.*?)(?:\n##|\Z)", mod_raw, re.DOTALL
        )
        focus_next = focus_match.group(1).strip() if focus_match else ""

        mod_summary = ModerationSummary(
            round=rnd, summary=mod_raw, focus_next=focus_next, raw=mod_raw
        )
        moderations.append(mod_summary)
        print_agent("gemini", mod_raw)

        # ── Round comparison ──
        claude_t = next((t for t in history if t.round == rnd and t.agent == "claude"), None)
        codex_t = next((t for t in history if t.round == rnd and t.agent == "codex"), None)
        if claude_t and codex_t:
            print_round_comparison(claude_t, codex_t)

        # ── Check convergence ──
        def _words(points):
            return set(w.lower() for p in points for w in p.split())

        if claude_t and codex_t:
            a_words = _words(claude_t.convergence)
            b_words = _words(codex_t.convergence)
            union = a_words | b_words
            overlap = len(a_words & b_words) / max(len(union), 1)
            print_convergence_meter(overlap)

            if claude_t.confidence > 0.8 and codex_t.confidence > 0.8 and overlap > 0.4:
                print_convergence_reached()
                break

        # ── User input (empty = skip) ──
        if rnd < max_rounds:
            print()
            user_text = ask_user(
                "Your thoughts? (steer the debate, add constraints, or Enter to skip)",
                default="",
            )
            user_inputs.append(UserInput(round=rnd, text=user_text))
            if user_text:
                print_status(f"  ✓ Your input will be fed into round {rnd + 1}\n")
            else:
                print_status("  ↩ Skipped — agents will continue on their own\n")

    # ──────────────────────────────────────────────────────────────────────────
    # FINAL SUMMARY + ACTION LIST
    # ──────────────────────────────────────────────────────────────────────────

    print_header("⚖️  FINAL SUMMARY")

    user_inputs_text = "\n".join(
        f"Round {u.round}: {u.text}" for u in user_inputs if u.text
    ) or "(user did not provide input)"

    final_prompt = prompts["final_summary"].format(
        topic=topic,
        full_history=format_history(history, moderations, user_inputs),
        user_inputs=user_inputs_text,
    )

    with agent_spinner("gemini"):
        try:
            final_raw = call_gemini(final_prompt, allow_tools=False)
        except Exception as e:
            final_raw = f"[Final summary error: {e}]"
            print_status(f"  ⚠️  Final summary failed: {e}")

    print_agent("gemini", final_raw)

    # Parse actions
    actions = parse_actions(final_raw)

    if actions:
        print_actions_table(actions)

        # ── Let user assign / modify / execute actions ──
        print()
        print_status("For each action, choose: (e)xecute, (p)lan, (s)kip, or reassign agent")
        print_status("Format: just press Enter to accept defaults, or type e/p/s or agent:e/agent:p")
        print_status("Example: 'claude:e' = assign to claude + execute, 'p' = plan with suggested agent\n")

        for i, action in enumerate(actions):
            choice = ask_user(
                f"Action {i+1}: {action['action']}\n"
                f"  [{action['agent']}:{action['type']}]",
                default=f"{action['agent']}:{action['type']}"
            )

            # Parse user's choice
            parts = choice.lower().strip().split(":")
            if len(parts) == 2:
                agent_choice, mode_choice = parts[0].strip(), parts[1].strip()
            elif choice.lower().strip() in ("e", "execute"):
                agent_choice, mode_choice = action["agent"], "execute"
            elif choice.lower().strip() in ("p", "plan"):
                agent_choice, mode_choice = action["agent"], "plan"
            elif choice.lower().strip() in ("s", "skip"):
                print_status(f"  ⏭ Skipping action {i+1}")
                continue
            else:
                agent_choice, mode_choice = action["agent"], action["type"]

            # Validate agent
            if agent_choice not in AGENT_CALLERS and agent_choice != "user":
                print_status(f"  ⚠️  Unknown agent '{agent_choice}', falling back to {action['agent']}")
                agent_choice = action["agent"]

            if agent_choice == "user":
                print_status(f"  📝 Action {i+1} assigned to you — skipping AI execution")
                continue

            # Execute or plan
            instruction = (
                "Execute this action now. Make changes, write files, run commands as needed."
                if mode_choice == "execute"
                else "Produce a detailed plan for this action. Do NOT execute — just plan."
            )
            exec_prompt = prompts["action_execution"].format(
                topic=topic,
                summary=final_raw[:3000],
                action=action["action"],
                mode=mode_choice,
                context_block=context_block,
                instruction=instruction,
            )

            with agent_spinner(agent_choice):
                try:
                    exec_result = AGENT_CALLERS[agent_choice](exec_prompt, allow_tools=(mode_choice == "execute"))
                except Exception as e:
                    print_status(f"  ⚠️  Action {i+1} failed: {e}")
                    continue
            print_agent(agent_choice, exec_result)
    else:
        print_status("  ℹ️  No structured actions parsed — review the summary above.")

    # ── Save log ──
    if output:
        out_path = Path(output)
        ext = out_path.suffix.lower()

        md_report = generate_markdown_report(
            topic, history, moderations, user_inputs, final_raw, actions
        )

        if ext == ".md":
            out_path.write_text(md_report, encoding="utf-8")
            print_status(f"\n💾 Markdown report saved to {out_path}")
        elif ext == ".json":
            log = {
                "topic": topic, "rounds": max_rounds,
                "turns": [asdict(t) for t in history],
                "moderations": [asdict(m) for m in moderations],
                "user_inputs": [asdict(u) for u in user_inputs],
                "final_summary": final_raw, "actions": actions,
            }
            out_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
            print_status(f"\n💾 JSON log saved to {out_path}")
        else:
            # No extension or unknown → write both
            json_path = out_path.with_suffix(".json")
            md_path = out_path.with_suffix(".md")
            log = {
                "topic": topic, "rounds": max_rounds,
                "turns": [asdict(t) for t in history],
                "moderations": [asdict(m) for m in moderations],
                "user_inputs": [asdict(u) for u in user_inputs],
                "final_summary": final_raw, "actions": actions,
            }
            json_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
            md_path.write_text(md_report, encoding="utf-8")
            print_status(f"\n💾 Saved: {json_path} + {md_path}")

    return history


# ─── CLI entry ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Claude Code vs Codex debate with Gemini moderator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s "Should we use microservices or monolith?"
              %(prog)s "Review this codebase" --context ./src --tools --rounds 4
              %(prog)s "Improve error handling" --context ./src/api -o debate.json
        """),
    )
    parser.add_argument("topic", nargs="?", help="The debate topic or question")
    parser.add_argument("--context", nargs="*", default=[], help="Files/dirs for context")
    parser.add_argument("--rounds", type=int, default=3, help="Max debate rounds (default: 3)")
    parser.add_argument("--tools", action="store_true", help="Allow agents to use tools (file I/O, shell)")
    parser.add_argument("--output", "-o", help="Save debate log (.json, .md, or both if no extension)")
    parser.add_argument("--prompts", type=Path, help="Custom prompts TOML file (default: prompts.toml)")
    parser.add_argument("--test", action="store_true", help="Run preflight checks on all agents and exit")
    args = parser.parse_args()

    if args.test:
        success = run_preflight()
        sys.exit(0 if success else 1)

    if not args.topic:
        parser.error("topic is required (use --test to check system readiness)")

    try:
        run_debate(args.topic, args.context, args.rounds, args.tools, args.output, args.prompts)
    except KeyboardInterrupt:
        print_status("\n\n⛔ Debate interrupted by user")
        sys.exit(1)