# debate-cli

Steel man debates between Claude Code and Codex, moderated by Gemini. You steer.

## How it works

```
Opening:  One agent states position → Other responds → Gemini evaluates
Round N:  Agent steel mans opponent → States position → Gemini moderates → You steer
Final:    Gemini summarizes → Suggests actions → You assign → Agents execute
```

The debate follows a **steel man** format: from round 2 onward, each agent must charitably restate their opponent's strongest argument before countering it. The moderator evaluates steel man quality alongside argument strength.

Who speaks first is **randomized each round** to prevent predictable first-mover framing.

Convergence is tracked automatically. The debate stops early if both agents reach >0.8 confidence with >40% word overlap on agreement points.

## Prerequisites

- [Claude Code](https://github.com/anthropics/claude-code) (`claude`)
- [Codex CLI](https://github.com/openai/codex) (`codex`)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`gemini`)
- Python 3.9+

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[rich]"    # Animated terminal UI (spinners, panels, confidence bars)
pip install -e ".[pdf]"     # HTML/PDF report export (WeasyPrint + Jinja2)
pip install -e ".[all]"     # Everything
```

### Verify setup

```bash
debate-cli --test
```

Runs preflight checks: Python, Rich, TOML support, prompt templates, CLI availability, and agent liveness.

## Usage

```bash
debate-cli "Should we use microservices or monolith?"

debate-cli "Review this codebase" --context ./src --tools --rounds 4

debate-cli "Will scrum die in the age of agentic AI coding?" --rounds 5 -o report
```

`python debate.py ...` also works as a compatibility shim.

| Flag | Description |
|------|-------------|
| `--context PATH...` | Files and/or directories to include as context |
| `--rounds N` | Max debate rounds (default: 3) |
| `--tools` | Allow agents to read/write files and run commands |
| `-o FILE` | Save report (`.json`, `.md`, `.html`, `.pdf`, or all if no extension) |
| `--prompts FILE` | Custom prompts TOML file override |
| `--test` | Run preflight checks on all agents and exit |

### Context paths

`--context` accepts both individual files and directories:

```bash
debate-cli "Review this" --context ./src/main.py           # Single file
debate-cli "Review this" --context ./src                    # Directory (recursive)
debate-cli "Review this" --context ./src/main.py ./docs     # Mix of both
```

Directories are filtered to common code/config extensions (.py, .rs, .ts, .js, .md, .toml, .yaml, .json).

## Debate flow

### Round 1 (Opening)

Agents state their initial positions. No steel man, convergence, or divergence is expected yet — just a clear argument and confidence score. The moderator evaluates opening positions and steers the next round.

### Round 2+ (Steel Man)

Each agent must first **steel man** their opponent's strongest argument from the previous round, then state their own position. The moderator evaluates steel man quality, argument strength, and suggests focus areas.

### After each round

You can type guidance to steer the next round, or press Enter to skip.

### Final summary

Gemini produces a synthesis with consensus points, unresolved disagreements, and an action list. The moderator considers what kind of debate this was:

- **Technical debates** get concrete actions (execute code, produce plans)
- **Philosophical/strategic debates** get reflective actions (continue debating, export report)

### Action assignment

For each suggested action:

- `e` / `p` / `c` / `x` / `s` — execute, plan, continue, export, or skip
- `claude:e` — reassign to Claude and execute
- `codex:p` — reassign to Codex and plan
- Enter — accept the default

**Continue** suggests re-running with more rounds. **Export** generates a report on the spot (prompts for path if `-o` wasn't specified).

## Output formats

```bash
debate-cli "topic" -o report.json    # JSON log
debate-cli "topic" -o report.md      # Markdown report (executive summary + transcript)
debate-cli "topic" -o report.html    # Styled HTML with confidence bars and charts
debate-cli "topic" -o report.pdf     # PDF with professional typography and visuals
debate-cli "topic" -o report         # All formats at once
```

The markdown report includes an executive summary (consensus, disagreements, actions table) followed by the full debate transcript with steel mans, convergence meters, and moderator assessments.

The HTML/PDF report adds color-coded agent sections, confidence bars, a convergence trend chart (SVG), and page-aware layout with headers and footers. Requires `pip install -e ".[pdf]"`.

## Project structure

- `src/debate_cli/` — packaged application (domain/application/infrastructure layers)
- `src/debate_cli/resources/default_prompts.toml` — built-in prompt templates
- `src/debate_cli/resources/report_template.html` — HTML/PDF report template
- `pyproject.toml` — dependencies, extras, and `debate-cli` entrypoint
- `debate.py` — compatibility shim

## Customizing prompts

Override built-in defaults with `--prompts custom.toml`. Four sections:

| Section | Controls |
|---------|----------|
| `[debate]` | Agent debate prompt with `{round_instructions}` for round-aware behavior |
| `[moderator]` | Per-round moderation with `{moderator_round_instructions}` |
| `[final_summary]` | Final summary, consensus, and intelligent action generation |
| `[action_execution]` | Prompt for executing individual actions |

Each has a `template` key with `{placeholder}` variables. Missing sections fall back to packaged defaults.
