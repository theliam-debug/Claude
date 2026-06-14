"""
CLI entry point for derivatives_strategies.

Usage:
    # Options overlay engine
    python -m derivatives_strategies run --policy policy.yml --positions positions.json --out ./out
    ds3 run --policy policy.yml --positions positions.json --out ./out

    # Equity & futures research tools
    python -m derivatives_strategies research equity --symbol AAPL
    python -m derivatives_strategies research futures --root /ES
    python -m derivatives_strategies research tools
"""

import sys

from derivatives_strategies.engine.runner import run_cli


def main() -> None:
    # Route the `research` subcommand to the research CLI; everything else
    # falls through to the existing options-overlay engine CLI.
    if len(sys.argv) > 1 and sys.argv[1] == "research":
        from derivatives_strategies.research.cli import main as research_main
        raise SystemExit(research_main(sys.argv[2:]))
    run_cli()


if __name__ == "__main__":
    main()
