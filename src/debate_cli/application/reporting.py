"""Pure report and transcript formatting."""

from __future__ import annotations

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
    """Generate a markdown transcript from the canonical result."""
    def _cell(value: str) -> str:
        return str(value).replace("|", r"\|").replace("\n", " ").strip()

    lines = [f"# Steel Man Debate: {result.config.topic}\n"]
    mod_by_round = {moderation.round: moderation for moderation in result.moderations}
    user_by_round = {user_input.round: user_input for user_input in result.user_inputs}

    for round_number in sorted({turn.round for turn in result.turns}):
        lines.append(f"## Round {round_number}\n")
        round_turns = [turn for turn in result.turns if turn.round == round_number]

        for turn in round_turns:
            icon = agent_icons.get(turn.agent, "⚪")
            lines.append(f"### {icon} {turn.agent.upper()} (confidence: {turn.confidence:.0%})\n")
            lines.append(turn.position.strip())
            lines.append("")

            if turn.steel_man:
                opponent = "Codex" if turn.agent == "claude" else "Claude"
                lines.append(f"**Steel Man of {opponent}'s argument:**")
                for steel_man_line in turn.steel_man.strip().splitlines():
                    lines.append(f"> {steel_man_line}")
                lines.append("")

            if turn.convergence:
                lines.append("**Convergence:** " + "; ".join(turn.convergence))
            if turn.divergence:
                lines.append("**Divergence:** " + "; ".join(turn.divergence))
            lines.append("")

        if round_number in mod_by_round:
            lines.append("### 🟡 Moderator\n")
            lines.append(mod_by_round[round_number].summary.strip())
            lines.append("")

        if round_number in user_by_round and user_by_round[round_number].text:
            lines.append("### 👤 User\n")
            lines.append(user_by_round[round_number].text.strip())
            lines.append("")

        lines.append("---\n")

    lines.append("## Final Summary\n")
    lines.append(result.final_summary.strip())
    lines.append("")

    if result.actions:
        lines.append("## Recommended Actions\n")
        lines.append("| # | Action | Agent | Type |")
        lines.append("|---|--------|-------|------|")
        for index, action in enumerate(result.actions, start=1):
            icon = agent_icons.get(action.agent, "👤" if action.agent == "user" else "⚪")
            agent_label = f"{icon} {action.agent}"
            lines.append(
                f"| {index} | {_cell(action.action)} | {_cell(agent_label)} | "
                f"{_cell(action.mode.value)} |"
            )
        lines.append("")

    return "\n".join(lines)


def serialize_result(result: DebateResult) -> dict[str, object]:
    """Expose the canonical result in JSON-safe form."""
    return result_to_dict(result)
