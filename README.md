# debate-cli

Steel man debates between Claude Code and Codex, moderated by Gemini. You steer.

## How it works

```
Round N:  Claude argues → Codex argues → Gemini moderates → You steer
Final:    Gemini summarizes → Action list → You assign → Agents execute
```

Each round, agents must **steel man** their opponent's strongest argument before countering it. The moderator evaluates steel man quality alongside argument strength. Agents track convergence/divergence with confidence scores; the debate stops early if both converge (>0.8 confidence, >40% word overlap).

## Prerequisites

- [Claude Code](https://github.com/anthropics/claude-code) (`claude`)
- [Codex CLI](https://github.com/openai/codex) (`codex`)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`gemini`)
- Python 3.9+

Install the package in editable mode:

```bash
pip install -e .
```

The package metadata, runtime dependencies, and `debate-cli` console entrypoint are defined in `pyproject.toml`.
`requirements.txt` is intentionally minimal and kept only as a local editable-install convenience wrapper.

Optional rich UI:

```bash
pip install -e ".[rich]"
```

### Verify setup

```bash
debate-cli --test
```

Runs a preflight check: Python version, Rich availability, packaged prompt templates, CLI availability, and agent liveness.

## Project structure

- `src/debate_cli/` contains the packaged application code
- `src/debate_cli/resources/default_prompts.toml` contains the built-in prompt defaults
- `pyproject.toml` defines dependencies and the `debate-cli` entrypoint
- `debate.py` remains as a compatibility shim to the packaged CLI

## Usage

```bash
debate-cli "Should we use microservices or monolith?"

debate-cli "Review this codebase" --context ./src --tools --rounds 4

debate-cli "Improve error handling" --context ./src/api -o debate.json
```

`python debate.py ...` still works as a compatibility shim.

| Flag | Description |
|------|-------------|
| `--context PATH...` | Files and/or directories to include as context |
| `--rounds N` | Max debate rounds (default: 3) |
| `--tools` | Allow agents to read/write files and run commands |
| `-o FILE` | Save debate log (`.json`, `.md`, or both if no extension) |
| `--prompts FILE` | Custom prompts TOML file override |
| `--test` | Run preflight checks on all agents and exit |

### Context paths

`--context` accepts both individual files and directories:

```bash
# Single file
debate-cli "Review this" --context ./src/main.py

# Directory (recursively includes .py, .rs, .ts, .js, .md, .toml, .yaml, .json)
debate-cli "Review this" --context ./src

# Mix of both
debate-cli "Review this" --context ./src/main.py ./docs ./config.toml
```

## During the debate

After each round you can type guidance to steer the next round, or press Enter to skip. After the final summary, Gemini proposes actions you can assign:

- `e` / `p` / `s` — execute, plan, or skip with the suggested agent
- `claude:e` — reassign to Claude and execute
- `codex:p` — reassign to Codex and plan
- Enter — accept the default

### Output formats

```bash
debate-cli "topic" -o debate.json   # JSON log only
debate-cli "topic" -o debate.md     # Markdown report only
debate-cli "topic" -o debate        # Both debate.json + debate.md
```

The markdown report includes full debate transcript with steel mans as blockquotes, confidence percentages, moderator summaries, and an actions table.

## Customizing prompts

The built-in defaults now live in the package at `src/debate_cli/resources/default_prompts.toml`.
Use `--prompts custom.toml` to override them. Four sections:

| Section | Controls |
|---------|----------|
| `[debate]` | Agent debate prompt (steel man instructions, structured output format) |
| `[moderator]` | Gemini's round-by-round moderation prompt |
| `[final_summary]` | Final summary and action list generation |
| `[action_execution]` | Prompt for executing individual actions |

Each has a `template` key with `{placeholder}` variables. Missing sections fall back to the packaged defaults.
