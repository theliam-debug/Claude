"""
Equity & futures research tooling for Lsto.

This subpackage adds a research layer on top of the derivatives_strategies
engine. It is organized in three parts:

1. ``registry`` - a curated catalog of the external MCP data sources that are
   relevant to equity and futures research (market data, SEC, FINRA,
   commodities/volatility, and macro/rates). This is the "which tools" map.

2. ``models`` - normalized, network-free data models with parsers that accept
   the raw JSON payloads returned by those MCP tools.

3. ``equity`` / ``futures`` - deterministic research analytics that turn the
   normalized data into a research brief (valuation, technicals, positioning,
   term structure, roll yield, volatility regime).

Following the same principle as the rest of the package, nothing here makes a
network call directly. An MCP-backed data source is wired in by injecting a
``call_tool`` callable (see ``research.sources.MCPResearchSource``); the
default ``SampleResearchSource`` provides deterministic offline data so the
CLI and tests run with no external dependencies.
"""

from derivatives_strategies.research.models import (
    EquityQuote,
    FuturesQuote,
    Bar,
    PriceSeries,
    ShortInterest,
    VolRegime,
)
from derivatives_strategies.research.equity import (
    EquityResearchBrief,
    analyze_equity,
)
from derivatives_strategies.research.futures import (
    FuturesResearchBrief,
    analyze_futures,
    parse_future_symbol,
)
from derivatives_strategies.research.registry import (
    MCPTool,
    RESEARCH_TOOLS,
    tools_for_asset_class,
    tools_by_category,
)

__all__ = [
    "EquityQuote",
    "FuturesQuote",
    "Bar",
    "PriceSeries",
    "ShortInterest",
    "VolRegime",
    "EquityResearchBrief",
    "analyze_equity",
    "FuturesResearchBrief",
    "analyze_futures",
    "parse_future_symbol",
    "MCPTool",
    "RESEARCH_TOOLS",
    "tools_for_asset_class",
    "tools_by_category",
]
