"""Pure report and transcript formatting."""

from __future__ import annotations

from datetime import date

from debate_cli.domain.models import DebateResult, DebateTurn, ModerationSummary, UserInput, result_to_dict


def format_history(
    turns: list[DebateTurn],
    moderations: list[ModerationSummary] | None = None,
    user_inputs: list[UserInput] | None = None,
) -> str:
    """Format debate history for prompt reuse."""
    if not turns:
        return "(first round - no history yet)"

    moderations = moderations or []
    user_inputs = user_inputs or []
    mod_by_round = {moderation.round: moderation for moderation in moderations}
    user_by_round = {user_input.round: user_input for user_input in user_inputs}

    lines = []
    rounds_seen = sorted({turn.round for turn in turns})
    for round_number in rounds_seen:
        round_turns = [turn for turn in turns if turn.round == round_number]
        for turn in round_turns:
            lines.append(f"### Round {turn.round} - {turn.agent.upper()}")
            lines.append(turn.position[:2000])
            if turn.steel_man:
                lines.append("Steel Man: " + turn.steel_man[:500])
            if turn.convergence:
                lines.append("Convergence: " + "; ".join(turn.convergence))
            if turn.divergence:
                lines.append("Divergence: " + "; ".join(turn.divergence))

        if round_number in mod_by_round:
            lines.append(f"### Round {round_number} - MODERATOR (Gemini)")
            lines.append(mod_by_round[round_number].summary[:1500])

        if round_number in user_by_round and user_by_round[round_number].text:
            lines.append(f"### Round {round_number} - USER")
            lines.append(user_by_round[round_number].text)

    return "\n\n".join(lines)


def generate_markdown_report(result: DebateResult, agent_icons: dict[str, str]) -> str:
    """Generate a professional markdown report with executive summary + full transcript."""
    from debate_cli.application.parsing import calculate_convergence_overlap

    def _cell(value: str) -> str:
        return str(value).replace("|", r"\|").replace("\n", " ").strip()

    lines: list[str] = []
    mod_by_round = {m.round: m for m in result.moderations}
    user_by_round = {u.round: u for u in result.user_inputs}
    rounds_seen = sorted({t.round for t in result.turns})

    # ── Header ──
    lines.append(f"# Steel Man Debate Report\n")
    lines.append(f"**Topic:** {result.config.topic}  ")
    lines.append(f"**Date:** {date.today().isoformat()}  ")
    lines.append(
        f"**Rounds:** {result.completed_rounds} | "
        f"**Agents:** Claude vs Codex | **Moderator:** Gemini"
    )
    lines.append("\n---\n")

    # ── Executive Summary ──
    lines.append("## Executive Summary\n")
    if result.final_summary:
        lines.append(result.final_summary.strip())
    else:
        lines.append("*(No final summary produced)*")
    lines.append("")

    # Consensus + disagreements from last round
    last_round = rounds_seen[-1] if rounds_seen else 0
    last_claude = next((t for t in result.turns if t.round == last_round and t.agent == "claude"), None)
    last_codex = next((t for t in result.turns if t.round == last_round and t.agent == "codex"), None)

    all_convergence = set()
    all_divergence = set()
    if last_claude:
        all_convergence.update(last_claude.convergence)
        all_divergence.update(last_claude.divergence)
    if last_codex:
        all_convergence.update(last_codex.convergence)
        all_divergence.update(last_codex.divergence)

    if all_convergence:
        lines.append("### Consensus Points\n")
        for point in all_convergence:
            lines.append(f"- {point}")
        lines.append("")

    if all_divergence:
        lines.append("### Unresolved Disagreements\n")
        for point in all_divergence:
            lines.append(f"- {point}")
        lines.append("")

    if result.actions:
        lines.append("### Recommended Actions\n")
        lines.append("| # | Action | Agent | Type |")
        lines.append("|---|--------|-------|------|")
        for i, action in enumerate(result.actions, 1):
            icon = agent_icons.get(action.agent, "👤" if action.agent == "user" else "⚪")
            lines.append(
                f"| {i} | {_cell(action.action)} | {_cell(f'{icon} {action.agent}')} | "
                f"{_cell(action.mode.value)} |"
            )
        lines.append("")

    lines.append("\n---\n")

    # ── Debate Transcript ──
    lines.append("## Debate Transcript\n")

    for round_number in rounds_seen:
        lines.append(f"### Round {round_number}\n")
        round_turns = [t for t in result.turns if t.round == round_number]

        for turn in round_turns:
            icon = agent_icons.get(turn.agent, "⚪")
            lines.append(f"#### {icon} {turn.agent.upper()} (confidence: {turn.confidence:.0%})\n")

            if turn.steel_man:
                opponent = "Codex" if turn.agent == "claude" else "Claude"
                lines.append(f"**Steel Man of {opponent}'s argument:**")
                for sm_line in turn.steel_man.strip().splitlines():
                    lines.append(f"> {sm_line}")
                lines.append("")

            lines.append(turn.position.strip())
            lines.append("")

            if turn.convergence:
                lines.append("**Agrees on:** " + "; ".join(turn.convergence))
            if turn.divergence:
                lines.append("**Disagrees on:** " + "; ".join(turn.divergence))
            lines.append("")

        if round_number in mod_by_round:
            lines.append("#### 🟡 Moderator Assessment\n")
            lines.append(mod_by_round[round_number].summary.strip())
            lines.append("")

        if round_number in user_by_round and user_by_round[round_number].text:
            lines.append("#### 👤 User Steering\n")
            lines.append(user_by_round[round_number].text.strip())
            lines.append("")

        # Convergence meter for this round
        claude_t = next((t for t in round_turns if t.agent == "claude"), None)
        codex_t = next((t for t in round_turns if t.agent == "codex"), None)
        if claude_t and codex_t:
            overlap = calculate_convergence_overlap(claude_t.convergence, codex_t.convergence)
            pct = int(overlap * 100)
            filled = pct // 5
            bar = "▰" * filled + "▱" * (20 - filled)
            lines.append(f"**Convergence: {pct}%** {bar}")
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)


def serialize_result(result: DebateResult) -> dict[str, object]:
    """Expose the canonical result in JSON-safe form."""
    return result_to_dict(result)
