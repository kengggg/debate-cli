"""Debate orchestration service."""

from __future__ import annotations

import random
from pathlib import Path

from debate_cli.application.contracts import AgentRegistry, ContextLoader, PromptRepository, Renderer, ReportWriter
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
    ActionResult,
    ActionSelection,
    ActionStatus,
    DebateAction,
    DebateConfig,
    DebateResult,
    DebateTurn,
    ModerationSummary,
    UserInput,
)

# ── Round-aware instruction blocks ──────────────────────────────────────────

OPENING_ROUND_INSTRUCTIONS = """\
## Your instructions (Opening Round):
This is the OPENING ROUND. State your initial position clearly and concisely.
There is no opponent argument yet, so do NOT produce STEEL MAN, CONVERGENCE,
or DIVERGENCE sections.

If useful, read files or run commands to gather evidence for your position.

End your response with ONLY:

CONFIDENCE: [0.0 to 1.0]
"""

STANDARD_ROUND_INSTRUCTIONS = """\
## Your instructions:
1. You MUST first STEEL MAN your opponent's strongest argument from the previous
   round. Present it as charitably and accurately as possible — show that you
   truly understand their best case before you counter it.
2. State your own position clearly and concisely.
3. If useful, read files or run commands to gather evidence.
4. Respond to the moderator's guidance and the user's input if provided.
5. End your response with EXACTLY this structured block:

STEEL MAN:
[Your charitable restatement of opponent's strongest argument.]

CONVERGENCE:
- [point you agree with opponent on]

DIVERGENCE:
- [point you disagree on]

CONFIDENCE: [0.0 to 1.0]
"""

OPENING_MODERATOR_INSTRUCTIONS = """\
## Your tasks (Opening Round):
This is the opening round. The agents are stating their initial positions.
1. **Summarize** each agent's opening position and initial stance.
2. **Evaluate** the strength and clarity of each opening argument.
3. **Steer** the next round: suggest what each agent should address or investigate.
   Be specific — "Claude should benchmark X" or "Codex should address the scalability concern".

Do NOT expect convergence, divergence, or steel mans yet — this is the first exchange.

Format your response as:

## Summary
[your summary of opening positions]

## Focus for Next Round
- Claude should: [specific guidance]
- Codex should: [specific guidance]
"""

STANDARD_MODERATOR_INSTRUCTIONS = """\
## Your tasks:
1. **Summarize** this round: what each agent argued, where they agree, where they diverge.
2. **Evaluate steel man quality**: Did each agent accurately and charitably represent their
   opponent's strongest argument? Call out any distortions, straw men, or weak steel mans.
3. **Evaluate** the strength of each argument. Be critical - call out weak reasoning.
4. **Steer** the next round: suggest what each agent should focus on or investigate.
   Be specific - "Claude should benchmark X" or "Codex should address the scalability concern".
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
"""


class DebateService:
    """Run the full debate workflow."""

    def __init__(
        self,
        prompt_repository: PromptRepository,
        context_loader: ContextLoader,
        renderer: Renderer,
        agent_registry: AgentRegistry,
        report_writer: ReportWriter | None = None,
    ):
        self._prompt_repository = prompt_repository
        self._context_loader = context_loader
        self._renderer = renderer
        self._agent_registry = agent_registry
        self._report_writer = report_writer

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

            # Randomize who speaks first each round
            round_pairs = list(debate_pairs)
            random.shuffle(round_pairs)
            first_speaker = round_pairs[0][0]
            self._renderer.print_status(f"  {first_speaker.capitalize()} opens this round")

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

            round_instructions = (
                OPENING_ROUND_INSTRUCTIONS if round_number == 1 else STANDARD_ROUND_INSTRUCTIONS
            )

            for role, opponent in round_pairs:
                prompt = prompts.render(
                    "debate",
                    role=f"{role.upper()} (Agent {'A' if role == 'claude' else 'B'})",
                    opponent=opponent,
                    topic=config.topic,
                    context_block=context_block,
                    history=format_history(result.turns, result.moderations, result.user_inputs),
                    moderator_guidance=moderator_guidance,
                    user_input_block=user_input_block,
                    round_instructions=round_instructions,
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

            moderator_round_instructions = (
                OPENING_MODERATOR_INSTRUCTIONS if round_number == 1
                else STANDARD_MODERATOR_INSTRUCTIONS
            )
            moderator_prompt = prompts.render(
                "moderator",
                topic=config.topic,
                round=round_number,
                round_turns=round_turns_text,
                user_input_block=last_user_text,
                moderator_round_instructions=moderator_round_instructions,
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

            # Convergence check — skip opening round (no structured output yet)
            if round_number > 1:
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
                if config.autopilot:
                    self._renderer.print_status("  🤖 Autopilot — agents continue autonomously\n")
                    result.user_inputs.append(UserInput(round=round_number, text=""))
                else:
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

        content_actions = [a for a in result.actions if a.mode != ActionMode.EXPORT]
        export_actions = [a for a in result.actions if a.mode == ActionMode.EXPORT]

        if content_actions:
            # ── Phase 1: Content actions (everything except export) ──
            self._renderer.print_actions_table(content_actions)
            self._renderer.print_status(
                "For each action: (e)xecute, (p)lan, (c)ontinue, (s)kip, or reassign"
            )
            self._renderer.print_status(
                "Format: press Enter for defaults, or type e/p/c/s or agent:e/agent:p\n"
            )

            for index, action in enumerate(content_actions, start=1):
                ar = self._prompt_and_execute_action(
                    index, action, config, result, prompts, context_block, final_raw,
                )
                result.action_results.append(ar)
        elif not result.actions:
            self._renderer.print_status("  ℹ️  No structured actions parsed - review the summary above.")

        # ── Phase 2: Export (runs last, includes action results) ──
        self._handle_export_phase(result, config, export_requested=bool(export_actions))

        return result

    def _prompt_and_execute_action(
        self,
        index: int,
        action: DebateAction,
        config: DebateConfig,
        result: DebateResult,
        prompts,
        context_block: str,
        final_raw: str,
    ) -> ActionResult:
        """Prompt user for action choice and execute. Returns ActionResult."""
        default_agent = action.agent if (
            self._agent_registry.has(action.agent) or action.agent == "system"
        ) else "user"
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
                allowed_agents=self._agent_registry.names() | {"user", "system"},
            )
        except ValueError as exc:
            self._renderer.print_status(
                f"  ⚠️  {exc}; falling back to {default_agent}:{default_mode.value}"
            )
            selection = ActionSelection(agent=default_agent, mode=default_mode)

        if selection is None:
            self._renderer.print_status(f"  ⏭ Skipping action {index}")
            return ActionResult(action=action, status=ActionStatus.SKIPPED)

        return self._execute_action(
            index, action, selection, config, result, prompts, context_block, final_raw,
        )

    def _execute_action(
        self,
        index: int,
        action: DebateAction,
        selection: ActionSelection,
        config: DebateConfig,
        result: DebateResult,
        prompts,
        context_block: str,
        final_raw: str,
    ) -> ActionResult:
        """Execute a single action and return the result."""
        # ── Meta-actions ──
        if selection.mode == ActionMode.CONTINUE:
            self._renderer.print_status(
                "  💡 To continue this debate, re-run with more rounds:\n"
                f'     debate-cli "{config.topic}" --rounds N'
            )
            return ActionResult(
                action=action, status=ActionStatus.COMPLETED,
                agent_used="system", mode_used=ActionMode.CONTINUE,
                output=f'Re-run with: debate-cli "{config.topic}" --rounds N',
            )

        # ── Agent-based routing ──
        if selection.agent in ("user", "system"):
            self._renderer.print_status(
                f"  📝 Action {index} assigned to you - skipping AI execution"
            )
            return ActionResult(
                action=action, status=ActionStatus.SKIPPED,
                agent_used=selection.agent, mode_used=selection.mode,
            )

        # ── AI agent execution (EXECUTE / PLAN) ──
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
                exec_output = self._agent_registry.get_client(selection.agent).run(
                    exec_prompt,
                    allow_tools=(config.allow_tools and selection.mode == ActionMode.EXECUTE),
                )
            except Exception as exc:
                self._renderer.print_status(f"  ⚠️  Action {index} failed: {exc}")
                return ActionResult(
                    action=action, status=ActionStatus.FAILED,
                    agent_used=selection.agent, mode_used=selection.mode,
                    error=str(exc),
                )
        self._renderer.print_agent(selection.agent, exec_output)
        return ActionResult(
            action=action, status=ActionStatus.COMPLETED,
            agent_used=selection.agent, mode_used=selection.mode,
            output=exec_output,
        )

    def _safe_export(self, result: DebateResult, output_path: Path) -> None:
        """Export with error handling — never crash, never lose debate data."""
        try:
            self._do_export(result, output_path)
        except Exception as exc:
            self._renderer.print_status(f"  ⚠️  Export failed: {exc}")
            self._renderer.print_status("  ℹ️  Your debate data is preserved in the session.")

    def _handle_export_phase(
        self,
        result: DebateResult,
        config: DebateConfig,
        export_requested: bool,
    ) -> None:
        """Offer or perform export once, after all other actions finish."""
        self._renderer.print_header("💾 Export")

        if config.output:
            self._safe_export(result, config.output)
            return

        if export_requested:
            self._renderer.print_status("  ℹ️  Moderator recommended exporting this debate.")

        export_choice = self._renderer.ask_user(
            "Export report? (includes debate + action results)\n"
            "  Enter path (e.g., report.pdf), or (s)kip:",
            default="debate-report",
        )
        if export_choice.strip().lower() in ("s", "skip"):
            self._renderer.print_status("  ⏭ Export skipped")
            return

        chosen_path = Path(export_choice.strip()) if export_choice.strip() else Path("debate-report")
        self._safe_export(result, chosen_path)

    def _do_export(self, result: DebateResult, output_path: Path) -> None:
        """Export the report including action results."""
        if self._report_writer:
            paths = self._report_writer.write(result, output_path)
            self._renderer.print_status(
                f"  💾 Exported: {', '.join(str(p) for p in paths)}"
            )
        else:
            self._renderer.print_status(
                "  💾 Report writer not available. Use -o <path> at startup."
            )
