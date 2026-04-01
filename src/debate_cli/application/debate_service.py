"""Debate orchestration service."""

from __future__ import annotations

from debate_cli.application.contracts import AgentRegistry, ContextLoader, PromptRepository, Renderer
from debate_cli.application.parsing import (
    calculate_convergence_overlap,
    extract_focus_next_round,
    normalize_action_choice,
    parse_actions,
    parse_structured,
)
from debate_cli.application.reporting import format_history
from debate_cli.domain.models import (
    ActionMode,
    ActionSelection,
    DebateConfig,
    DebateResult,
    DebateTurn,
    ModerationSummary,
    UserInput,
)


class DebateService:
    """Run the full debate workflow."""

    def __init__(
        self,
        prompt_repository: PromptRepository,
        context_loader: ContextLoader,
        renderer: Renderer,
        agent_registry: AgentRegistry,
    ):
        self._prompt_repository = prompt_repository
        self._context_loader = context_loader
        self._renderer = renderer
        self._agent_registry = agent_registry

    def run(self, config: DebateConfig) -> DebateResult:
        """Run a debate session and return the canonical result."""
        if config.max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")

        prompts = self._prompt_repository.load(config.prompts_path)
        context = self._context_loader.load(config.context_paths, self._renderer.print_status)
        context_block = f"## Context:\n{context}" if context != "(no context files)" else ""

        result = DebateResult(config=config)
        self._renderer.print_banner(
            config.topic,
            config.max_rounds,
            config.allow_tools,
            len(config.context_paths),
        )

        debate_pairs = [("claude", "Codex"), ("codex", "Claude Code")]
        for round_number in range(1, config.max_rounds + 1):
            if round_number > 1:
                self._renderer.print_round_transition()
            self._renderer.print_round_progress(round_number, config.max_rounds)

            last_moderation = next(
                (moderation for moderation in result.moderations if moderation.round == round_number - 1),
                None,
            )
            moderator_guidance = ""
            if last_moderation and last_moderation.focus_next:
                moderator_guidance = (
                    "## Moderator guidance for this round:\n" + last_moderation.focus_next
                )

            last_user_input = next(
                (user_input for user_input in result.user_inputs if user_input.round == round_number - 1),
                None,
            )
            user_input_block = ""
            if last_user_input and last_user_input.text:
                user_input_block = "## User's direction:\n" + last_user_input.text

            for role, opponent in debate_pairs:
                prompt = prompts.render(
                    "debate",
                    role=f"{role.upper()} (Agent {'A' if role == 'claude' else 'B'})",
                    opponent=opponent,
                    topic=config.topic,
                    context_block=context_block,
                    history=format_history(result.turns, result.moderations, result.user_inputs),
                    moderator_guidance=moderator_guidance,
                    user_input_block=user_input_block,
                )

                errored = False
                with self._renderer.agent_spinner(role):
                    try:
                        raw = self._agent_registry.get_client(role).run(prompt, config.allow_tools)
                    except Exception as exc:
                        raw = f"[ERROR] Agent {role} failed: {exc}"
                        errored = True

                if errored:
                    self._renderer.print_status(f"  ⚠️  {role} failed")
                    turn = DebateTurn(agent=role, round=round_number, position=raw, confidence=0.0)
                else:
                    parsed = parse_structured(raw)
                    turn = DebateTurn(
                        agent=role,
                        round=round_number,
                        position=raw,
                        steel_man=parsed.steel_man,
                        convergence=parsed.convergence,
                        divergence=parsed.divergence,
                        confidence=parsed.confidence,
                    )

                result.turns.append(turn)
                self._renderer.print_steel_man(role, turn.steel_man)
                self._renderer.print_agent(role, raw, turn)
                self._renderer.print_turn_stats(turn)

            round_turns = [turn for turn in result.turns if turn.round == round_number]
            round_turns_text = "\n\n".join(
                f"### {turn.agent.upper()}:\n{turn.position[:3000]}" for turn in round_turns
            )
            last_user_text = ""
            if last_user_input and last_user_input.text:
                last_user_text = f"## User said after previous round:\n{last_user_input.text}"

            moderator_prompt = prompts.render(
                "moderator",
                topic=config.topic,
                round=round_number,
                round_turns=round_turns_text,
                user_input_block=last_user_text,
            )

            with self._renderer.agent_spinner("gemini"):
                try:
                    moderator_raw = self._agent_registry.get_client("gemini").run(
                        moderator_prompt,
                        allow_tools=False,
                    )
                except Exception as exc:
                    moderator_raw = f"[Moderator error: {exc}]"
                    self._renderer.print_status(f"  ⚠️  Gemini moderator failed: {exc}")

            moderation = ModerationSummary(
                round=round_number,
                summary=moderator_raw,
                focus_next=extract_focus_next_round(moderator_raw),
                raw=moderator_raw,
            )
            result.moderations.append(moderation)
            self._renderer.print_agent("gemini", moderator_raw)

            claude_turn = next(
                (turn for turn in result.turns if turn.round == round_number and turn.agent == "claude"),
                None,
            )
            codex_turn = next(
                (turn for turn in result.turns if turn.round == round_number and turn.agent == "codex"),
                None,
            )
            if claude_turn and codex_turn:
                self._renderer.print_round_comparison(claude_turn, codex_turn)
                overlap = calculate_convergence_overlap(
                    claude_turn.convergence,
                    codex_turn.convergence,
                )
                self._renderer.print_convergence_meter(overlap)
                if claude_turn.confidence > 0.8 and codex_turn.confidence > 0.8 and overlap > 0.4:
                    self._renderer.print_convergence_reached()
                    break

            if round_number < config.max_rounds:
                user_text = self._renderer.ask_user(
                    "Your thoughts? (steer the debate, add constraints, or Enter to skip)",
                    default="",
                )
                result.user_inputs.append(UserInput(round=round_number, text=user_text))
                if user_text:
                    self._renderer.print_status(
                        f"  ✓ Your input will be fed into round {round_number + 1}\n"
                    )
                else:
                    self._renderer.print_status("  ↩ Skipped - agents will continue on their own\n")

        self._renderer.print_header("⚖️  FINAL SUMMARY")
        user_inputs_text = "\n".join(
            f"Round {user_input.round}: {user_input.text}"
            for user_input in result.user_inputs
            if user_input.text
        ) or "(user did not provide input)"

        final_prompt = prompts.render(
            "final_summary",
            topic=config.topic,
            full_history=format_history(result.turns, result.moderations, result.user_inputs),
            user_inputs=user_inputs_text,
        )

        with self._renderer.agent_spinner("gemini"):
            try:
                final_raw = self._agent_registry.get_client("gemini").run(final_prompt, allow_tools=False)
            except Exception as exc:
                final_raw = f"[Final summary error: {exc}]"
                self._renderer.print_status(f"  ⚠️  Final summary failed: {exc}")

        result.final_summary = final_raw
        self._renderer.print_agent("gemini", final_raw)
        result.actions = parse_actions(final_raw)

        if result.actions:
            self._renderer.print_actions_table(result.actions)
            self._renderer.print_status(
                "For each action, choose: (e)xecute, (p)lan, (s)kip, or reassign agent"
            )
            self._renderer.print_status(
                "Format: press Enter for defaults, or type e/p/s or agent:e/agent:p"
            )
            self._renderer.print_status(
                "Example: 'claude:e' = assign to claude + execute, 'p' = plan with suggested agent\n"
            )

            for index, action in enumerate(result.actions, start=1):
                default_agent = action.agent if self._agent_registry.has(action.agent) else "user"
                default_mode = action.mode
                choice = self._renderer.ask_user(
                    f"Action {index}: {action.action}\n  [{default_agent}:{default_mode.value}]",
                    default=f"{default_agent}:{default_mode.value}",
                )

                try:
                    selection = normalize_action_choice(
                        choice,
                        default_agent=default_agent,
                        default_mode=default_mode,
                        allowed_agents=self._agent_registry.names() | {"user"},
                    )
                except ValueError as exc:
                    self._renderer.print_status(
                        f"  ⚠️  {exc}; falling back to {default_agent}:{default_mode.value}"
                    )
                    selection = ActionSelection(agent=default_agent, mode=default_mode)

                if selection is None:
                    self._renderer.print_status(f"  ⏭ Skipping action {index}")
                    continue

                if selection.agent == "user":
                    self._renderer.print_status(
                        f"  📝 Action {index} assigned to you - skipping AI execution"
                    )
                    continue

                instruction = (
                    "Execute this action now. Make changes, write files, run commands as needed."
                    if selection.mode == ActionMode.EXECUTE
                    else "Produce a detailed plan for this action. Do NOT execute - just plan."
                )
                exec_prompt = prompts.render(
                    "action_execution",
                    topic=config.topic,
                    summary=final_raw[:3000],
                    action=action.action,
                    mode=selection.mode.value,
                    context_block=context_block,
                    instruction=instruction,
                )

                with self._renderer.agent_spinner(selection.agent):
                    try:
                        exec_result = self._agent_registry.get_client(selection.agent).run(
                            exec_prompt,
                            allow_tools=(selection.mode == ActionMode.EXECUTE),
                        )
                    except Exception as exc:
                        self._renderer.print_status(f"  ⚠️  Action {index} failed: {exc}")
                        continue
                self._renderer.print_agent(selection.agent, exec_result)
        else:
            self._renderer.print_status("  ℹ️  No structured actions parsed - review the summary above.")

        return result
