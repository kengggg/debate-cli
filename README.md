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

For PDF export, you also need the Pango system library:

```bash
brew install pango          # macOS
apt install libpango1.0-dev # Linux
```

### Verify setup

```bash
debate-cli --test
```

Checks: Python, Rich, export libraries (Jinja2, WeasyPrint, Pango), prompt templates, CLI tools, and agent liveness.

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
| `--autopilot` | Run without user interaction (agents debate autonomously) |
| `--test` | Run preflight checks on all agents and exit |

### Context paths

`--context` accepts both individual files and directories:

```bash
debate-cli "Review this" --context ./src/main.py           # Single file
debate-cli "Review this" --context ./src                    # Directory (recursive)
debate-cli "Review this" --context ./src/main.py ./docs     # Mix of both
```

Directories are filtered to common code/config extensions (.py, .rs, .ts, .js, .md, .toml, .yaml, .json).

### Autopilot mode

Let agents debate autonomously without steering — you only interact at the action phase:

```bash
debate-cli "Should we rewrite in Rust?" --context ./src --rounds 4 --autopilot -o report
```

Autopilot skips user steering between rounds (agents follow moderator guidance on their own). The action phase at the end still prompts you — you always decide what to execute, plan, export, or skip.

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

### Actions (two-phase)

**Phase 1 — Content actions** are presented first (execute, plan, continue). Agent outputs are captured for the report.

- `e` / `p` / `c` / `s` — execute, plan, continue, or skip
- `claude:e` — reassign to Claude and execute
- `codex:p` — reassign to Codex and plan
- Enter — accept the default

**Phase 2 — Export** runs automatically after all content actions. Reports are saved to `./outputs/` by default.

Without `--tools`, agents cannot write files or run commands — even for execute-type actions.

## Output

Every debate auto-saves to a timestamped folder in `./outputs/`:

```
./outputs/
  2026-04-02T10-13_microservices-vs-monolith/
    report.json
    report.md
    report.html   (if jinja2 installed)
    report.pdf    (if weasyprint + pango installed)
```

Override with `-o`:

```bash
debate-cli "topic" -o custom.json    # Single format to specific file
debate-cli "topic" -o custom.pdf     # PDF only
debate-cli "topic" -o ./my-reports/debate  # All formats into custom directory
```

Reports include an executive summary (consensus, disagreements, actions table), the full debate transcript with steel mans and convergence meters, and **action results** — any plans or outputs generated during the action phase.

The HTML/PDF report adds color-coded agent sections, confidence bars, convergence trend chart (SVG), status badges for action results, and page-aware layout. Requires `pip install -e ".[pdf]"` + pango.

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
