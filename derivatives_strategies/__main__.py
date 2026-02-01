"""
CLI entry point for derivatives_strategies.

Usage:
    python -m derivatives_strategies run --policy policy.yml --positions positions.json --out ./out
    ds3 run --policy policy.yml --positions positions.json --out ./out
"""

from derivatives_strategies.engine.runner import run_cli

if __name__ == "__main__":
    run_cli()
