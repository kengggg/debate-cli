#!/usr/bin/env python3
"""debate-cli: Claude Code vs Codex debate orchestrator with Gemini moderator."""

import argparse, json, subprocess, sys, os, re, textwrap
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ─── Terminal rendering ───────────────────────────────────────────────────────

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.rule import Rule
    console = Console()

    def print_agent(role, text):
        colors = {"claude": "red", "codex": "blue", "gemini": "yellow"}
        icons  = {"claude": "🟠", "codex": "🔵", "gemini": "🟡"}
        color = colors.get(role, "white")
        icon  = icons.get(role, "⚪")
        console.print(Panel(
            Markdown(text),
            title=f"[bold {color}]{icon} {role.upper()}[/]",
            border_style=color,
            padding=(1, 2),
        ))

    def print_status(msg):
        console.print(f"[dim]{msg}[/dim]")

    def print_header(msg):
        console.print(Rule(f"[bold]{msg}[/bold]", style="bright_white"))

    def print_actions_table(actions):
        table = Table(title="📋 Suggested Actions", show_lines=True, border_style="bright_white")
        table.add_column("#", style="bold", width=3)
        table.add_column("Action", style="white", min_width=40)
        table.add_column("Suggested Agent", style="cyan", width=16)
        table.add_column("Type", style="dim", width=10)
        for i, a in enumerate(actions, 1):
            table.add_row(str(i), a["action"], a.get("agent", "?"), a.get("type", "plan"))
        console.print(table)

    def ask_user(prompt_text, default=""):
        try:
            return Prompt.ask(f"[bold green]👤 YOU[/bold green] {prompt_text}", default=default)
        except (EOFError, KeyboardInterrupt):
            return default

except ImportError:
    # Fallback: no rich
    def print_agent(role, text):
        icons = {"claude": "🟠", "codex": "🔵", "gemini": "🟡"}
        marker = icons.get(role, "⚪")
        print(f"\n{marker} {role.upper()}\n{'─'*60}\n{text}\n")

    def print_status(msg):
        print(f"  ⋯ {msg}")

    def print_header(msg):
        print(f"\n{'━'*60}\n  {msg}\n{'━'*60}")

    def print_actions_table(actions):
        print("\n📋 Suggested Actions:")
        for i, a in enumerate(actions, 1):
            print(f"  {i}. [{a.get('agent','?')}] {a['action']} ({a.get('type','plan')})")
        print()

    def ask_user(prompt_text, default=""):
        try:
            val = input(f"👤 YOU  {prompt_text} [{default}]: ").strip()
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            return default


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class DebateTurn:
    agent: str
    round: int
    position: str
    convergence: list = field(default_factory=list)
    divergence: list = field(default_factory=list)
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

DEBATE_PROMPT = textwrap.dedent("""\
    You are {role} in a structured debate with {opponent}.
    A moderator (Gemini) is overseeing this debate to help the user reach a better outcome.

    Topic: {topic}

    {context_block}

    ## Previous rounds:
    {history}

    {moderator_guidance}

    {user_input_block}

    ## Your instructions:
    1. State your position clearly and concisely.
    2. If useful, read files or run commands to gather evidence.
    3. Respond to the moderator's guidance and the user's input if provided.
    4. End your response with EXACTLY this structured block:

    CONVERGENCE:
    - [point you agree with opponent on]

    DIVERGENCE:
    - [point you disagree on]

    CONFIDENCE: [0.0 to 1.0]
""")

MODERATOR_PROMPT = textwrap.dedent("""\
    You are the MODERATOR of a structured debate between Claude Code and Codex.
    Your role is to help the user get the best possible outcome.

    Topic: {topic}

    ## Round {round} debate:
    {round_turns}

    {user_input_block}

    ## Your tasks:
    1. **Summarize** this round: what each agent argued, where they agree, where they diverge.
    2. **Evaluate** the strength of each argument. Be critical — call out weak reasoning.
    3. **Steer** the next round: suggest what each agent should focus on or investigate.
       Be specific — "Claude should benchmark X" or "Codex should address the scalability concern".
    4. If the debate seems to be going in circles, say so.

    Format your response as:

    ## Summary
    [your summary]

    ## Focus for Next Round
    - Claude should: [specific guidance]
    - Codex should: [specific guidance]
""")

FINAL_SUMMARY_PROMPT = textwrap.dedent("""\
    You are the MODERATOR wrapping up a structured debate between Claude Code and Codex.
    Your goal: give the user a clear, actionable outcome.

    Topic: {topic}

    ## Full debate history:
    {full_history}

    ## User inputs throughout:
    {user_inputs}

    ## Your tasks:
    1. Write a **final summary** of the debate outcome.
    2. List the **points of consensus** (what both agents agree on).
    3. List the **unresolved disagreements** and your recommendation on each.
    4. Produce a **numbered action list** — concrete next steps the user should take.
       For each action, suggest which agent (claude, codex, gemini, or user) is best suited.

    Format the action list EXACTLY like this (one per line, parseable):

    ## Actions
    ACTION 1: [description] | AGENT: [claude/codex/gemini/user] | TYPE: [execute/plan]
    ACTION 2: [description] | AGENT: [claude/codex/gemini/user] | TYPE: [execute/plan]
    ...
""")

ACTION_EXECUTION_PROMPT = textwrap.dedent("""\
    You have been assigned an action from a debate between Claude Code and Codex.

    Original topic: {topic}
    Debate conclusion summary: {summary}

    YOUR ACTION: {action}
    MODE: {mode}

    {context_block}

    {"Execute this action now. Make changes, write files, run commands as needed." if mode == "execute" else "Produce a detailed plan for this action. Do NOT execute — just plan."}
""")


# ─── Agent callers ────────────────────────────────────────────────────────────

def call_claude(prompt: str, allow_tools: bool = False) -> str:
    """Call claude CLI with --print flag."""
    cmd = ["claude", "--print"]
    if allow_tools:
        cmd.extend(["--allowedTools", "Bash,Read,Write"])
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
        cmd.extend(["-c", 'sandbox_permissions=["disk-full-read-access"]'])
    cmd.append("-")
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"codex CLI error: {result.stderr[:500]}")
    return result.stdout


def call_gemini(prompt: str, allow_tools: bool = False) -> str:
    """Call gemini CLI in headless mode."""
    cmd = ["gemini"]
    if allow_tools:
        cmd.append("-y")  # yolo mode: auto-approve tool actions
    cmd.extend(["-p", prompt])
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"gemini CLI error: {result.stderr[:500]}")
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
            chunks.append(f"### {path.name}\n```\n{path.read_text()[:8000]}\n```")
        elif path.is_dir():
            for f in sorted(path.rglob("*"))[:20]:
                if f.is_file() and f.suffix in ('.py', '.rs', '.ts', '.js', '.md', '.toml', '.yaml', '.json'):
                    try:
                        chunks.append(f"### {f.relative_to(path)}\n```\n{f.read_text()[:4000]}\n```")
                    except (UnicodeDecodeError, PermissionError):
                        pass
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
    """Extract CONVERGENCE/DIVERGENCE/CONFIDENCE from agent output."""
    result = {"convergence": [], "divergence": [], "confidence": 0.5}
    conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", text)
    if conf_match:
        try:
            result["confidence"] = min(1.0, max(0.0, float(conf_match.group(1))))
        except ValueError:
            pass

    sections = re.split(r"(CONVERGENCE:|DIVERGENCE:)", text)
    current = None
    for s in sections:
        if "CONVERGENCE:" in s:
            current = "convergence"
        elif "DIVERGENCE:" in s:
            current = "divergence"
        elif current:
            points = [l.strip().lstrip("- ") for l in s.split("\n")
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


# ─── Main debate loop ─────────────────────────────────────────────────────────

def run_debate(topic, context_paths, max_rounds=3, allow_tools=False, output=None):
    context = load_context(context_paths)
    context_block = f"## Context:\n{context}" if context != "(no context files)" else ""

    history: list[DebateTurn] = []
    moderations: list[ModerationSummary] = []
    user_inputs: list[UserInput] = []

    print_header(f"DEBATE: {topic}")
    print_status(f"Agents: Claude Code vs Codex  |  Moderator: Gemini  |  Rounds: {max_rounds}")
    print_status(f"Tools: {'enabled' if allow_tools else 'disabled'}  |  Context: {len(context_paths)} path(s)\n")

    for rnd in range(1, max_rounds + 1):
        print_header(f"Round {rnd} of {max_rounds}")

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
            prompt = DEBATE_PROMPT.format(
                role=f"{role.upper()} (Agent {'A' if role == 'claude' else 'B'})",
                opponent=opponent,
                topic=topic,
                context_block=context_block,
                history=format_history(history, moderations, user_inputs),
                moderator_guidance=moderator_guidance,
                user_input_block=user_input_text,
            )

            print_status(f"  ⏳ Waiting for {role}...")
            try:
                raw = AGENT_CALLERS[role](prompt, allow_tools)
            except Exception as e:
                raw = f"[Agent error: {e}]"
                print_status(f"  ⚠️  {role} failed: {e}")

            parsed = parse_structured(raw)
            turn = DebateTurn(
                agent=role, round=rnd, position=raw,
                convergence=parsed["convergence"],
                divergence=parsed["divergence"],
                confidence=parsed["confidence"],
            )
            history.append(turn)
            print_agent(role, raw)

        # ── Moderator summarizes the round ──
        print_status("  ⏳ Moderator (Gemini) is reviewing the round...")
        round_turns = [t for t in history if t.round == rnd]
        round_turns_text = "\n\n".join(
            f"### {t.agent.upper()}:\n{t.position[:3000]}" for t in round_turns
        )
        last_user_text = ""
        if last_user and last_user.text:
            last_user_text = f"## User said after previous round:\n{last_user.text}"

        mod_prompt = MODERATOR_PROMPT.format(
            topic=topic,
            round=rnd,
            round_turns=round_turns_text,
            user_input_block=last_user_text,
        )

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

        # ── Check convergence ──
        a = next((t for t in history if t.round == rnd and t.agent == "claude"), None)
        b = next((t for t in history if t.round == rnd and t.agent == "codex"), None)
        if a and b and a.confidence > 0.8 and b.confidence > 0.8:
            def _words(points):
                return set(w.lower() for p in points for w in p.split())
            a_words, b_words = _words(a.convergence), _words(b.convergence)
            union = a_words | b_words
            overlap = len(a_words & b_words) / max(len(union), 1)
            if overlap > 0.4:
                print_status("✅ Convergence reached early!")
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

    print_header("FINAL SUMMARY")
    print_status("  ⏳ Moderator is producing final summary and action list...")

    user_inputs_text = "\n".join(
        f"Round {u.round}: {u.text}" for u in user_inputs if u.text
    ) or "(user did not provide input)"

    final_prompt = FINAL_SUMMARY_PROMPT.format(
        topic=topic,
        full_history=format_history(history, moderations, user_inputs),
        user_inputs=user_inputs_text,
    )

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
            print_status(f"  ⏳ {agent_choice} is {'executing' if mode_choice == 'execute' else 'planning'} action {i+1}...")

            exec_prompt = ACTION_EXECUTION_PROMPT.format(
                topic=topic,
                summary=final_raw[:3000],
                action=action["action"],
                mode=mode_choice,
                context_block=context_block,
            )
            # Fix the conditional in the prompt
            exec_prompt = exec_prompt.replace(
                '{"Execute this action now. Make changes, write files, run commands as needed." if mode == "execute" else "Produce a detailed plan for this action. Do NOT execute — just plan."}',
                "Execute this action now. Make changes, write files, run commands as needed."
                if mode_choice == "execute"
                else "Produce a detailed plan for this action. Do NOT execute — just plan."
            )

            try:
                exec_result = AGENT_CALLERS[agent_choice](exec_prompt, allow_tools=(mode_choice == "execute"))
                print_agent(agent_choice, exec_result)
            except Exception as e:
                print_status(f"  ⚠️  Action {i+1} failed: {e}")
    else:
        print_status("  ℹ️  No structured actions parsed — review the summary above.")

    # ── Save log ──
    if output:
        log = {
            "topic": topic,
            "rounds": max_rounds,
            "turns": [asdict(t) for t in history],
            "moderations": [asdict(m) for m in moderations],
            "user_inputs": [asdict(u) for u in user_inputs],
            "final_summary": final_raw,
            "actions": actions,
        }
        Path(output).write_text(json.dumps(log, indent=2, ensure_ascii=False))
        print_status(f"\n💾 Full debate log saved to {output}")

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
    parser.add_argument("topic", help="The debate topic or question")
    parser.add_argument("--context", nargs="*", default=[], help="Files/dirs for context")
    parser.add_argument("--rounds", type=int, default=3, help="Max debate rounds (default: 3)")
    parser.add_argument("--tools", action="store_true", help="Allow agents to use tools (file I/O, shell)")
    parser.add_argument("--output", "-o", help="Save full debate log to JSON file")
    args = parser.parse_args()

    try:
        run_debate(args.topic, args.context, args.rounds, args.tools, args.output)
    except KeyboardInterrupt:
        print_status("\n\n⛔ Debate interrupted by user")
        sys.exit(1)