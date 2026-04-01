"""Terminal renderers."""

from __future__ import annotations

import time
from contextlib import AbstractContextManager
from typing import Sequence

from debate_cli.application.contracts import AgentRegistry, Renderer
from debate_cli.domain.models import DebateAction, DebateTurn, PreflightCheckResult

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

    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


class PlainRenderer(Renderer):
    """Fallback renderer when Rich is unavailable."""

    def __init__(self, agent_registry: AgentRegistry):
        self._agent_registry = agent_registry

    def _icon(self, role: str) -> str:
        if role == "user":
            return "👤"
        if self._agent_registry.has(role):
            return self._agent_registry.get_metadata(role).icon
        return "⚪"

    def print_agent(self, role: str, text: str, turn: DebateTurn | None = None) -> None:
        print(f"\n{self._icon(role)} {role.upper()}\n{'─' * 60}\n{text}\n")

    def print_steel_man(self, role: str, steel_man_text: str) -> None:
        if not steel_man_text:
            return
        opponent = "Codex" if role == "claude" else "Claude"
        print(f"  🤝 {role.upper()} steel-manning {opponent}:")
        print(f"     {steel_man_text}\n")

    def print_status(self, msg: str) -> None:
        print(f"  ⋯ {msg}")

    def print_header(self, msg: str) -> None:
        print(f"\n{'━' * 60}\n  {msg}\n{'━' * 60}")

    def ask_user(self, prompt_text: str, default: str = "") -> str:
        try:
            value = input(f"👤 YOU  {prompt_text} [{default}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return default
        return value if value else default

    def print_turn_stats(self, turn: DebateTurn) -> None:
        confidence_pct = int(turn.confidence * 100)
        bar = "█" * (confidence_pct // 5) + "░" * (20 - confidence_pct // 5)
        print(
            f"  {bar} {confidence_pct}%  ✓{len(turn.convergence)} agree  ✗{len(turn.divergence)} disagree"
        )

    def print_convergence_meter(self, overlap_ratio: float) -> None:
        percent = int(overlap_ratio * 100)
        label = "Converging!" if percent > 60 else "Narrowing..." if percent > 30 else "Divergent"
        filled = percent // 5
        print(f"  {'▰' * filled}{'▱' * (20 - filled)}  {percent}% {label}")

    def print_round_comparison(self, claude_turn: DebateTurn, codex_turn: DebateTurn) -> None:
        convergence = "; ".join(set(claude_turn.convergence + codex_turn.convergence)) or "(none)"
        divergence = "; ".join(set(claude_turn.divergence + codex_turn.divergence)) or "(none)"
        print("  Convergence:", convergence)
        print("  Divergence:", divergence)

    def print_round_transition(self) -> None:
        print("  · · · · ·")

    def print_round_progress(self, current: int, total: int) -> None:
        filled = "●" * current
        empty = "○" * (total - current)
        print(f"\n  {filled}{empty}  Round {current} of {total}\n")

    def print_banner(self, topic: str, max_rounds: int, allow_tools: bool, context_count: int) -> None:
        print(f"\n{'═' * 60}")
        print("  ⚔️  STEEL MAN DEBATE  ⚔️")
        print(f"  {topic}")
        print(f"  Claude vs Codex · Gemini moderating · {max_rounds} rounds")
        print(f"  tools {'on' if allow_tools else 'off'} · {context_count} context path(s)")
        print(f"{'═' * 60}\n")

    def print_convergence_reached(self) -> None:
        print("  ✅ CONVERGENCE REACHED!")

    def print_actions_table(self, actions: Sequence[DebateAction]) -> None:
        print("\n📋 Recommended Actions:")
        for index, action in enumerate(actions, start=1):
            print(
                f"  {index}. {self._icon(action.agent)} [{action.agent}] "
                f"{action.action} ({action.mode.value})"
            )
        print()

    def render_preflight_results(self, results: Sequence[PreflightCheckResult]) -> None:
        current_category = None
        for result in results:
            if result.category != current_category:
                current_category = result.category
                print(f"\n  {current_category}")
            icon = "✅" if result.passed else "❌"
            print(f"  {icon} {result.detail:<50} {result.duration:.1f}s")

        passed = sum(1 for result in results if result.passed)
        total = len(results)
        if passed == total:
            print(f"\n  ✅ All {total} checks passed - ready to debate!\n")
        else:
            print(f"\n  ⚠️  {passed}/{total} passed, {total - passed} failed\n")

    class _NoOpContext(AbstractContextManager[object]):
        def __enter__(self) -> object:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def agent_spinner(self, role: str) -> AbstractContextManager[object]:
        print(f"  ⏳ {self._icon(role)} {role.upper()} is thinking...")
        return self._NoOpContext()


if _RICH_AVAILABLE:
    class RichRenderer(Renderer):
        """Rich renderer with panels and animations."""

        def __init__(self, agent_registry: AgentRegistry):
            self._agent_registry = agent_registry
            self._console = Console()

        def _metadata(self, role: str) -> tuple[str, str, str]:
            if self._agent_registry.has(role):
                metadata = self._agent_registry.get_metadata(role)
                return metadata.icon, metadata.color, metadata.spinner
            if role == "user":
                return "👤", "green", "dots"
            return "⚪", "white", "dots"

        def print_agent(self, role: str, text: str, turn: DebateTurn | None = None) -> None:
            icon, color, _spinner = self._metadata(role)
            border = box.HEAVY if role == "gemini" else box.ROUNDED
            subtitle = f"confidence {turn.confidence:.0%}" if turn and turn.confidence > 0 else ""
            self._console.print(
                Panel(
                    Markdown(text),
                    title=f"[bold {color}]{icon} {role.upper()}[/]",
                    subtitle=f"[dim]{subtitle}[/]" if subtitle else None,
                    border_style=color,
                    box=border,
                    padding=(1, 2),
                )
            )

        def print_steel_man(self, role: str, steel_man_text: str) -> None:
            if not steel_man_text:
                return
            opponent = "Codex" if role == "claude" else "Claude"
            self._console.print(
                Panel(
                    Markdown(steel_man_text),
                    title=f"[dim]🤝 {role.upper()} steel-manning {opponent}[/]",
                    border_style="dim",
                    box=box.SIMPLE,
                    padding=(0, 2),
                )
            )

        def print_status(self, msg: str) -> None:
            self._console.print(f"[dim]{msg}[/dim]")

        def print_header(self, msg: str) -> None:
            self._console.print()
            self._console.print(Align.center(f"[bold bright_white]{msg}[/]"))
            self._console.print()

        def ask_user(self, prompt_text: str, default: str = "") -> str:
            try:
                return Prompt.ask(f"[bold green]👤 YOU[/bold green] {prompt_text}", default=default)
            except (EOFError, KeyboardInterrupt):
                return default

        def print_turn_stats(self, turn: DebateTurn) -> None:
            target = int(turn.confidence * 100)
            try:
                with Live(refresh_per_second=30, transient=True, console=self._console) as live:
                    for percent in range(0, target + 1, max(1, target // 15)):
                        bar_color = "green" if percent > 80 else "yellow" if percent > 50 else "red"
                        filled = percent // 5
                        bar = f"[{bar_color}]{'█' * filled}{'░' * (20 - filled)}[/] {percent}%"
                        grid = Table.grid(padding=(0, 2))
                        grid.add_column()
                        grid.add_column()
                        grid.add_column()
                        grid.add_row(bar, "", "")
                        live.update(Padding(grid, (0, 4)))
                        time.sleep(0.025)
            except Exception:
                pass

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
            self._console.print(Padding(stats, (0, 4)))
            self._console.print()

        def print_convergence_meter(self, overlap_ratio: float) -> None:
            target = int(overlap_ratio * 100)
            color = "green" if target > 60 else "yellow" if target > 30 else "red"
            label = "Converging!" if target > 60 else "Narrowing..." if target > 30 else "Divergent"
            try:
                with Live(refresh_per_second=20, transient=True, console=self._console) as live:
                    for percent in range(0, target + 1, max(1, target // 12)):
                        current_color = "green" if percent > 60 else "yellow" if percent > 30 else "red"
                        filled = percent // 5
                        meter = Align.center(
                            f"[{current_color}]{'▰' * filled}{'▱' * (20 - filled)}[/]  "
                            f"[{current_color}]{percent}%[/]"
                        )
                        live.update(meter)
                        time.sleep(0.025)
            except Exception:
                pass

            self._console.print(
                Align.center(
                    f"[{color}]{'▰' * (target // 5)}{'▱' * (20 - target // 5)}[/]  "
                    f"[bold {color}]{target}% {label}[/]"
                )
            )
            self._console.print()

        def print_round_comparison(self, claude_turn: DebateTurn, codex_turn: DebateTurn) -> None:
            agree = Table(
                title="[bold green]✓ Convergence[/]",
                box=box.SIMPLE,
                border_style="green",
                show_header=False,
                padding=(0, 1),
            )
            agree.add_column()
            for point in set(claude_turn.convergence + codex_turn.convergence) or ["(none yet)"]:
                agree.add_row(f"[green]•[/] {point}")

            disagree = Table(
                title="[bold red]✗ Divergence[/]",
                box=box.SIMPLE,
                border_style="red",
                show_header=False,
                padding=(0, 1),
            )
            disagree.add_column()
            for point in set(claude_turn.divergence + codex_turn.divergence) or ["(none yet)"]:
                disagree.add_row(f"[red]•[/] {point}")

            self._console.print(Columns([agree, disagree], equal=True, padding=(0, 2)))
            self._console.print()

        def print_round_transition(self) -> None:
            frames = ["·", "· ·", "· · ·", "· · · ·", "· · · · ·", "· · · ·", "· · ·"]
            try:
                with Live(refresh_per_second=10, transient=True, console=self._console) as live:
                    for frame in frames:
                        live.update(Align.center(f"[dim]{frame}[/]"))
                        time.sleep(0.08)
            except Exception:
                pass

        def print_round_progress(self, current: int, total: int) -> None:
            filled = "[bright_white]●[/]" * current
            empty = "[dim]○[/]" * (total - current)
            self._console.print()
            self._console.print(Align.center(f"{filled}{empty}  [bold]Round {current} of {total}[/]"))
            self._console.print()

        def print_banner(self, topic: str, max_rounds: int, allow_tools: bool, context_count: int) -> None:
            def _make_banner(*rows: str) -> Panel:
                grid = Table.grid(padding=0)
                grid.add_column(justify="center")
                for row in rows:
                    grid.add_row(row)
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
                with Live(refresh_per_second=8, transient=True, console=self._console) as live:
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
            self._console.print(_make_banner(title, topic_line, "", details))

        def print_convergence_reached(self) -> None:
            frames = [
                Align.center("[green]✅ Convergence...[/]"),
                Align.center("[bold green]✅ Convergence reached![/]"),
                Align.center("[bold bright_green]✅ ✅ CONVERGENCE REACHED! ✅ ✅[/]"),
            ]
            try:
                with Live(refresh_per_second=4, transient=True, console=self._console) as live:
                    for frame in frames:
                        live.update(frame)
                        time.sleep(0.3)
            except Exception:
                pass
            self._console.print(Align.center("[bold bright_green]✅ CONVERGENCE REACHED![/]"))
            self._console.print()

        def print_actions_table(self, actions: Sequence[DebateAction]) -> None:
            table = Table(
                title="[bold]📋 Recommended Actions[/]",
                box=box.ROUNDED,
                border_style="bright_white",
                show_lines=True,
                padding=(0, 1),
            )
            table.add_column("#", style="bold", width=3, justify="center")
            table.add_column("Action", min_width=40)
            table.add_column("Agent", width=16, justify="center")
            table.add_column("Type", width=10, justify="center")

            type_styles = {
                "execute": "[bold green]execute[/]",
                "plan": "[bold yellow]plan[/]",
            }
            for index, action in enumerate(actions, start=1):
                icon, _color, _spinner = self._metadata(action.agent)
                type_display = type_styles.get(action.mode.value, action.mode.value)
                table.add_row(str(index), action.action, f"{icon} {action.agent}", type_display)
            self._console.print(table)

        def render_preflight_results(self, results: Sequence[PreflightCheckResult]) -> None:
            grid = Table.grid(padding=(0, 2))
            grid.add_column(width=4)
            grid.add_column(min_width=44)
            grid.add_column(justify="right", width=8)

            current_category = None
            for result in results:
                if result.category != current_category:
                    current_category = result.category
                    grid.add_row("", f"[bold bright_white]{current_category}[/]", "")
                icon = "[green]✅[/]" if result.passed else "[red]❌[/]"
                grid.add_row(f" {icon}", result.detail, f"[dim]{result.duration:.1f}s[/]")

            self._console.print(
                Panel(
                    grid,
                    title="[bold]🔍 PREFLIGHT CHECK[/]",
                    box=box.ROUNDED,
                    border_style="bright_white",
                    padding=(1, 2),
                )
            )

            passed = sum(1 for result in results if result.passed)
            total = len(results)
            self._console.print()
            if passed == total:
                self._console.print(
                    Align.center(f"[bold bright_green]✅ All {total} checks passed - ready to debate![/]")
                )
            else:
                self._console.print(
                    Align.center(
                        f"[bold yellow]⚠️  {passed}/{total} passed, {total - passed} failed - see above[/]"
                    )
                )
            self._console.print()

        def agent_spinner(self, role: str) -> AbstractContextManager[object]:
            icon, color, spinner = self._metadata(role)
            return self._console.status(
                f"[bold {color}]{icon} {role.upper()} is thinking...[/]",
                spinner=spinner,
            )


def build_renderer(agent_registry: AgentRegistry) -> Renderer:
    """Create the best available renderer for the current environment."""
    if _RICH_AVAILABLE:
        return RichRenderer(agent_registry)
    return PlainRenderer(agent_registry)
