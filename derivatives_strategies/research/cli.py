"""
Command-line interface for the Lsto research tools.

Usage:
    python -m derivatives_strategies research equity --symbol AAPL
    python -m derivatives_strategies research futures --root /ES
    python -m derivatives_strategies research tools [--asset-class futures]

By default this uses the offline ``SampleResearchSource`` (no network). To run
against live data, an orchestrator constructs an ``MCPResearchSource`` with an
injected ``call_tool`` callable - see ``research.sources``.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

from derivatives_strategies.research import registry
from derivatives_strategies.research.sources import (
    ResearchDataSource,
    SampleResearchSource,
)
from derivatives_strategies.research.equity import analyze_equity
from derivatives_strategies.research.futures import analyze_futures


def _today() -> str:
    return date.today().isoformat()


def cmd_equity(args, source: ResearchDataSource) -> int:
    symbol = args.symbol
    quote = source.get_equity_quote(symbol)
    if quote is None:
        print(f"No equity quote available for {symbol}")
        return 1
    series = source.get_price_series(symbol)
    short_interest = source.get_short_interest(symbol)
    vol_regime = source.get_vol_regime()

    brief = analyze_equity(
        quote=quote,
        series=series,
        short_interest=short_interest,
        vol_regime=vol_regime,
        as_of=args.as_of or _today(),
    )
    _emit(brief.to_markdown(), brief.to_dict(), args, default_stub=f"equity_{symbol}")
    return 0


def cmd_futures(args, source: ResearchDataSource) -> int:
    root = args.root
    quotes = []
    if hasattr(source, "futures_curve"):
        quotes = source.futures_curve(root)  # type: ignore[attr-defined]
    if not quotes and args.symbols:
        for sym in args.symbols:
            q = source.get_futures_quote(sym)
            if q is not None:
                quotes.append(q)
    if not quotes:
        print(f"No futures quotes available for {root}. "
              f"Pass explicit contracts with --symbols.")
        return 1

    vol_regime = source.get_vol_regime()
    brief = analyze_futures(quotes, vol_regime=vol_regime, as_of=args.as_of or _today())
    _emit(brief.to_markdown(), brief.to_dict(),
          args, default_stub=f"futures_{root.lstrip('/')}")
    return 0


def cmd_tools(args, source: ResearchDataSource) -> int:
    tools = registry.RESEARCH_TOOLS
    if args.asset_class:
        tools = registry.tools_for_asset_class(args.asset_class)
    if args.category:
        tools = [t for t in tools if t.category == args.category]

    if args.json:
        print(json.dumps([t.to_dict() for t in tools], indent=2))
        return 0

    print(f"Research MCP tools ({len(tools)}):\n")
    for t in tools:
        classes = ",".join(t.asset_classes)
        print(f"  [{t.category:<12}] {t.label}/{t.tool}  ({classes})")
        print(f"      {t.description}")
    return 0


def _emit(markdown: str, data: dict, args, default_stub: str) -> None:
    """Print markdown (or JSON) and optionally write files to --out."""
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(markdown)

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{default_stub}.md").write_text(markdown)
        (out_dir / f"{default_stub}.json").write_text(json.dumps(data, indent=2))
        print(f"\nWritten to {out_dir}/{default_stub}.{{md,json}}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="derivatives_strategies research",
        description="Lsto equity & futures research tools",
    )
    sub = parser.add_subparsers(dest="research_command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", "-o", default=None, help="Write brief to directory")
    common.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    common.add_argument("--as-of", default=None, help="As-of date (ISO); defaults to today")

    p_eq = sub.add_parser("equity", parents=[common], help="Equity research brief")
    p_eq.add_argument("--symbol", "-s", required=True, help="Ticker, e.g. AAPL")

    p_fut = sub.add_parser("futures", parents=[common], help="Futures research brief")
    p_fut.add_argument("--root", "-r", default="/ES", help="Root symbol, e.g. /ES")
    p_fut.add_argument("--symbols", nargs="*", default=None,
                       help="Explicit contracts, e.g. /ESM26 /ESU26 /ESZ26")

    p_tools = sub.add_parser("tools", help="List catalogued research MCP tools")
    p_tools.add_argument("--asset-class", choices=["equity", "futures", "macro", "cross_asset"])
    p_tools.add_argument("--category", default=None)
    p_tools.add_argument("--json", action="store_true")

    return parser


def main(argv: Optional[Sequence[str]] = None, source: Optional[ResearchDataSource] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source = source or SampleResearchSource()

    if args.research_command == "equity":
        return cmd_equity(args, source)
    if args.research_command == "futures":
        return cmd_futures(args, source)
    if args.research_command == "tools":
        return cmd_tools(args, source)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
