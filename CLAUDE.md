# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable mode)
pip install -e .
pip install -e ".[rich]"    # with Rich UI

# Run tests
python -m unittest tests/test_debate.py

# Run a single test
python -m unittest tests.test_debate.ParseStructuredTests.test_parses_confidence

# Preflight check (verifies all CLIs + agent liveness)
debate-cli --test

# Run a debate
debate-cli "topic" --context ./src --tools --rounds 3 -o result
```

There is no linter or formatter configured.

## Architecture

Three-layer design with dependency injection:

```
cli.py → bootstrap.build_application() → DebateService.run(DebateConfig)

domain/models.py          Pure dataclasses (DebateConfig, DebateTurn, DebateAction, etc.)
application/contracts.py  Protocol interfaces (AgentRegistry, Renderer, ContextLoader, etc.)
application/debate_service.py  Core debate loop orchestration
infrastructure/           Concrete implementations (subprocess agents, Rich renderer, TOML prompts)
```

**Bootstrap** (`bootstrap.py`) is the single DI wiring point. It constructs all services and passes them to `DebateService`. The renderer is auto-selected: `RichRenderer` if Rich is available, `PlainRenderer` otherwise.

**Entry points**: `debate-cli` console script (pyproject.toml) → `cli.py:main()`. Also `python -m debate_cli` and `python debate.py` (compatibility shim).

## Agent subprocess invocation

Each agent is called via `subprocess.run()` with prompt on stdin and 300s timeout. Tool permission flags differ per CLI:

- **Claude**: `claude --print [--allowedTools Bash,Read,Write,Edit --dangerously-skip-permissions]`
- **Codex**: `codex exec [--full-auto] -` (the `-` stdin marker must always be last)
- **Gemini**: `gemini -p "" [-y]` (prompt via stdin, `-p ""` triggers headless mode)

Defined in `infrastructure/agents.py`. The `BuiltinAgentRegistry` maps agent names to metadata (icon, color, spinner style) and `CommandAgentClient` instances.

## Debate flow

1. Each round: Claude argues → Codex argues → Gemini moderates → user steers
2. Steel man format: agents must restate opponent's strongest argument before countering
3. Structured output parsed via regex: `STEEL MAN:`, `CONVERGENCE:`, `DIVERGENCE:`, `CONFIDENCE:` sections
4. Early stop: both agents >0.8 confidence AND >40% word overlap on convergence points
5. Final: Gemini produces summary + `ACTION N: desc | AGENT: x | TYPE: execute/plan` lines
6. User assigns each action → agent executes or plans

Parsing logic in `application/parsing.py`. Convergence overlap uses Jaccard similarity on lowercased words (not semantic matching).

## Testing

Tests use **fake implementations** (not `mock.patch`) for service boundaries:

- `FakeAgentRegistry` — returns pre-canned responses from a list
- `FakeRenderer` — captures output calls, implements full `Renderer` protocol
- `FakePromptRepository`, `FakeContextLoader` — minimal stubs

Exception: `AgentClientTests` and `PreflightTests` use `@mock.patch("subprocess.run")` to verify CLI command construction.

All fakes are defined at the top of `tests/test_debate.py`.

## Prompt templates

Packaged at `src/debate_cli/resources/default_prompts.toml`, loaded via `importlib.resources`. Four sections: `[debate]`, `[moderator]`, `[final_summary]`, `[action_execution]`. Each has a `template` key using Python `.format()` placeholders. Override with `--prompts custom.toml`.
