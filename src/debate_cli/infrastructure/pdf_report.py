"""HTML and PDF report rendering via Jinja2 + WeasyPrint."""

from __future__ import annotations

import html
import importlib.resources
from datetime import date
from pathlib import Path

from debate_cli.application.parsing import calculate_convergence_overlap
from debate_cli.domain.models import DebateResult


def _confidence_class(value: float) -> str:
    if value > 0.8:
        return "high"
    if value > 0.5:
        return "mid"
    return "low"


def _md_to_html(text: str) -> str:
    """Convert markdown text to HTML for report rendering."""
    try:
        import markdown
        return markdown.markdown(
            text.strip(),
            extensions=["tables", "fenced_code", "nl2br"],
        )
    except ImportError:
        # Fallback: basic paragraph splitting
        escaped = html.escape(text.strip())
        paragraphs = escaped.split("\n\n")
        return "\n".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())


def _build_convergence_svg(
    data: list[dict[str, float | int]],
    width: int = 440,
    height: int = 140,
) -> str:
    """Generate an inline SVG line chart showing convergence % across rounds."""
    if not data:
        return ""

    pad_left, pad_right, pad_top, pad_bottom = 40, 20, 15, 30
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    n = len(data)
    if n == 1:
        xs = [pad_left + plot_w // 2]
    else:
        xs = [pad_left + int(i * plot_w / (n - 1)) for i in range(n)]
    ys = [pad_top + int((1 - d["overlap"]) * plot_h) for d in data]

    # Build SVG
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" style="font-family: Helvetica Neue, Arial, sans-serif;">',
        # Background
        f'<rect width="{width}" height="{height}" fill="#f8fafc" rx="6"/>',
        # Grid lines
    ]
    for pct in (0, 25, 50, 75, 100):
        y = pad_top + int((1 - pct / 100) * plot_h)
        lines.append(f'<line x1="{pad_left}" y1="{y}" x2="{width - pad_right}" y2="{y}" '
                     f'stroke="#e2e8f0" stroke-width="1"/>')
        lines.append(f'<text x="{pad_left - 6}" y="{y + 3}" text-anchor="end" '
                     f'fill="#94a3b8" font-size="8">{pct}%</text>')

    # X-axis labels
    for i, d in enumerate(data):
        lines.append(f'<text x="{xs[i]}" y="{height - 8}" text-anchor="middle" '
                     f'fill="#94a3b8" font-size="8">R{d["round"]}</text>')

    # Area fill
    if n > 1:
        area_points = " ".join(f"{xs[i]},{ys[i]}" for i in range(n))
        area_points = f"{xs[0]},{pad_top + plot_h} {area_points} {xs[-1]},{pad_top + plot_h}"
        lines.append(f'<polygon points="{area_points}" fill="#16a34a" opacity="0.1"/>')

    # Line
    if n > 1:
        points = " ".join(f"{xs[i]},{ys[i]}" for i in range(n))
        lines.append(f'<polyline points="{points}" fill="none" stroke="#16a34a" '
                     f'stroke-width="2.5" stroke-linejoin="round"/>')

    # Data points
    for i, d in enumerate(data):
        color = "#16a34a" if d["overlap"] > 0.6 else "#ca8a04" if d["overlap"] > 0.3 else "#dc2626"
        lines.append(f'<circle cx="{xs[i]}" cy="{ys[i]}" r="4" fill="{color}" stroke="white" stroke-width="1.5"/>')
        pct_label = f'{int(d["overlap"] * 100)}%'
        lines.append(f'<text x="{xs[i]}" y="{ys[i] - 8}" text-anchor="middle" '
                     f'fill="{color}" font-size="8" font-weight="600">{pct_label}</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def _build_template_context(result: DebateResult, agent_icons: dict[str, str]) -> dict:
    """Build the Jinja2 template context from a DebateResult."""
    rounds_seen = sorted({t.round for t in result.turns})
    mod_by_round = {m.round: m for m in result.moderations}
    user_by_round = {u.round: u for u in result.user_inputs}

    # Convergence data across rounds
    convergence_data = []
    rounds_ctx = []

    for rnd in rounds_seen:
        round_turns = [t for t in result.turns if t.round == rnd]
        claude_t = next((t for t in round_turns if t.agent == "claude"), None)
        codex_t = next((t for t in round_turns if t.agent == "codex"), None)

        overlap = None
        if claude_t and codex_t:
            overlap = calculate_convergence_overlap(claude_t.convergence, codex_t.convergence)
            convergence_data.append({"round": rnd, "overlap": overlap})

        turns_ctx = []
        for t in round_turns:
            pct = int(t.confidence * 100)
            turns_ctx.append({
                "agent": t.agent,
                "agent_upper": t.agent.upper(),
                "icon": agent_icons.get(t.agent, ""),
                "opponent": "Codex" if t.agent == "claude" else "Claude",
                "confidence_pct": pct,
                "confidence_class": _confidence_class(t.confidence),
                "steel_man": _md_to_html(t.steel_man) if t.steel_man else "",
                "position_html": _md_to_html(t.position),
                "convergence": t.convergence,
                "divergence": t.divergence,
            })

        mod = mod_by_round.get(rnd)
        user = user_by_round.get(rnd)

        overlap_pct = int(overlap * 100) if overlap is not None else None
        rounds_ctx.append({
            "number": rnd,
            "turns": turns_ctx,
            "moderation": mod.summary if mod else "",
            "moderation_html": _md_to_html(mod.summary) if mod else "",
            "user_input": user.text if user and user.text else "",
            "overlap": overlap,
            "overlap_pct": overlap_pct,
            "overlap_class": _confidence_class(overlap) if overlap is not None else "",
        })

    # Last round consensus/disagreements
    last_round_turns = [t for t in result.turns if t.round == (rounds_seen[-1] if rounds_seen else 0)]
    consensus = set()
    disagreements = set()
    for t in last_round_turns:
        consensus.update(t.convergence)
        disagreements.update(t.divergence)

    # Actions
    actions_ctx = []
    for a in result.actions:
        actions_ctx.append({
            "action": a.action,
            "agent": a.agent,
            "icon": agent_icons.get(a.agent, ""),
            "mode": a.mode.value,
        })

    # Action results
    action_results_ctx = []
    for ar in result.action_results:
        action_results_ctx.append({
            "action_desc": ar.action.action,
            "agent_used": ar.agent_used,
            "icon": agent_icons.get(ar.agent_used, "⚪"),
            "mode": ar.mode_used.value,
            "status": ar.status.value,
            "output_html": _md_to_html(ar.output) if ar.output else "",
            "error": ar.error,
        })

    return {
        "topic": result.config.topic,
        "date": date.today().isoformat(),
        "completed_rounds": result.completed_rounds,
        "final_summary_html": _md_to_html(result.final_summary) if result.final_summary else "<em>No summary</em>",
        "consensus_points": sorted(consensus),
        "disagreement_points": sorted(disagreements),
        "actions": actions_ctx,
        "action_results": action_results_ctx,
        "convergence_data": convergence_data,
        "convergence_svg": _build_convergence_svg(convergence_data),
        "rounds": rounds_ctx,
    }


def render_html_report(result: DebateResult, agent_icons: dict[str, str]) -> str:
    """Render a DebateResult to a styled HTML string."""
    try:
        from jinja2 import Environment, BaseLoader
    except ImportError:
        raise ImportError(
            "HTML/PDF export requires jinja2. Install with: pip install -e '.[pdf]'"
        )

    # Load template from package resources
    resources = importlib.resources.files("debate_cli.resources")
    template_text = (resources / "report_template.html").read_text(encoding="utf-8")

    env = Environment(loader=BaseLoader(), autoescape=False)
    template = env.from_string(template_text)
    context = _build_template_context(result, agent_icons)
    return template.render(**context)


def render_pdf_report(
    result: DebateResult,
    agent_icons: dict[str, str],
    output_path: Path,
) -> Path:
    """Render a DebateResult to a PDF file."""
    html_content = render_html_report(result, agent_icons)

    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise ImportError(
            f"PDF export requires weasyprint + system libraries (pango). "
            f"Install with: pip install -e '.[pdf]' and brew install pango. "
            f"Original error: {exc}"
        ) from exc

    HTML(string=html_content).write_pdf(str(output_path))
    return output_path
