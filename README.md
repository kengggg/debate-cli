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
- Python 3.11+ (for `tomllib`; 3.9+ works with `pip install tomli`)

Optional: `pip install rich` for animated panels, spinners, and confidence bars.

### Verify setup

```bash
python debate.py --test
```

Runs a preflight check: Python version, Rich, TOML support, prompt templates, CLI availability, and agent liveness (sends a test prompt to each agent).

## Usage

```bash
python debate.py "Should we use microservices or monolith?"

python debate.py "Review this codebase" --context ./src --tools --rounds 4

python debate.py "Improve error handling" --context ./src/api -o debate.json
```

| Flag | Description |
|------|-------------|
| `--context PATH...` | Files and/or directories to include as context |
| `--rounds N` | Max debate rounds (default: 3) |
| `--tools` | Allow agents to read/write files and run commands |
| `-o FILE` | Save debate log (`.json`, `.md`, or both if no extension) |
| `--prompts FILE` | Custom prompts TOML file (default: `prompts.toml`) |
| `--test` | Run preflight checks on all agents and exit |

### Context paths

`--context` accepts both individual files and directories:

```bash
# Single file
python debate.py "Review this" --context ./src/main.py

# Directory (recursively includes .py, .rs, .ts, .js, .md, .toml, .yaml, .json)
python debate.py "Review this" --context ./src

# Mix of both
python debate.py "Review this" --context ./src/main.py ./docs ./config.toml
```

## During the debate

After each round you can type guidance to steer the next round, or press Enter to skip. After the final summary, Gemini proposes actions you can assign:

- `e` / `p` / `s` — execute, plan, or skip with the suggested agent
- `claude:e` — reassign to Claude and execute
- `codex:p` — reassign to Codex and plan
- Enter — accept the default

### Output formats

```bash
python debate.py "topic" -o debate.json   # JSON log only
python debate.py "topic" -o debate.md     # Markdown report only
python debate.py "topic" -o debate        # Both debate.json + debate.md
```

The markdown report includes full debate transcript with steel mans as blockquotes, confidence percentages, moderator summaries, and an actions table.

## Customizing prompts

Edit `prompts.toml` to change agent behavior. Four sections:

| Section | Controls |
|---------|----------|
| `[debate]` | Agent debate prompt (steel man instructions, structured output format) |
| `[moderator]` | Gemini's round-by-round moderation prompt |
| `[final_summary]` | Final summary and action list generation |
| `[action_execution]` | Prompt for executing individual actions |

Each has a `template` key with `{placeholder}` variables. Missing sections fall back to built-in defaults. Use `--prompts custom.toml` to load a different file.
