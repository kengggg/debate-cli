"""Package entrypoint for ``python -m debate_cli``."""

from debate_cli.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
