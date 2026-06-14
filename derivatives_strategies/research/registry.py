"""
Catalog of MCP data sources relevant to equity & futures research.

This is the "find the relevant tools" half of the task, made machine-readable.
Each entry maps a research need to a concrete MCP tool, tagged by asset class
and category so callers (and the CLI) can discover what is available.

Notes:
- ``server`` holds the MCP server id as exposed in this workspace. Server ids
  are assigned per session/workspace, so treat them as a hint and resolve the
  live ids from the running MCP host when wiring an ``MCPResearchSource``.
- ``label`` is the stable, human-meaningful name for the upstream source.
- Only read-only research tools are catalogued here. Order entry, streaming,
  and authentication tools are intentionally excluded.
"""

from dataclasses import dataclass


# Asset-class tags
EQUITY = "equity"
FUTURES = "futures"
MACRO = "macro"           # rates / economy; context for both equities & futures
CROSS = "cross_asset"     # volatility, credit, FX that inform both


@dataclass(frozen=True)
class MCPTool:
    """A single external research tool exposed over MCP."""
    label: str            # stable upstream name, e.g. "schwab-market-data"
    server: str           # MCP server id in this workspace (session-scoped)
    tool: str             # tool name to invoke
    category: str         # e.g. "quotes", "fundamentals", "positioning"
    asset_classes: tuple  # which asset classes this informs
    description: str

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "server": self.server,
            "tool": self.tool,
            "category": self.category,
            "asset_classes": list(self.asset_classes),
            "description": self.description,
        }


# Server ids observed in this workspace (session-scoped; resolve live at wire time).
_MARKET_DATA = "11015bd8-b1a8-4751-a24e-86c60d8b22e3"   # Schwab-style market data
_SEC = "707d543c-dbc6-4ed4-8a4b-73da215263b9"            # SEC EDGAR / XBRL
_FINRA = "d8e9b504-4d1c-4e74-a5d6-01d2727ab6a4"          # FINRA
_COMMOD_VOL = "7fbc7477-436c-429f-bf2d-6e72ea512c98"     # Commodities & volatility
_MACRO = "a9ecf119-64b6-4b62-9ffb-eed5842af7ec"          # FRED / Fed macro
_TREASURY = "d9175574-ce83-405e-8163-07dc8c077f5e"       # US Treasury / rates


RESEARCH_TOOLS: list[MCPTool] = [
    # --- Market data: prices, fundamentals, options (equities + futures) ---
    MCPTool(
        "schwab-market-data", _MARKET_DATA, "get_quotes", "quotes",
        (EQUITY, FUTURES),
        "Real-time quotes for stocks, ETFs, indices, options, and futures "
        "(price, bid/ask, mark, volume, 52w range, PE, dividend yield).",
    ),
    MCPTool(
        "schwab-market-data", _MARKET_DATA, "get_price_history", "prices",
        (EQUITY, FUTURES),
        "Historical OHLCV candles (minute to monthly) for momentum, "
        "volatility, and drawdown analysis.",
    ),
    MCPTool(
        "schwab-market-data", _MARKET_DATA, "get_options_chain", "options",
        (EQUITY, FUTURES),
        "Full options chains with greeks and implied volatility, used to feed "
        "the surface builder and overlay engine.",
    ),
    MCPTool(
        "schwab-market-data", _MARKET_DATA, "get_expiration_chain", "options",
        (EQUITY, FUTURES),
        "Expiration ladders for an underlying, used to enumerate futures and "
        "options expiries for term-structure work.",
    ),
    MCPTool(
        "schwab-market-data", _MARKET_DATA, "get_fundamentals", "fundamentals",
        (EQUITY,),
        "Fundamental projections (valuation, margins, growth) for equities.",
    ),
    MCPTool(
        "schwab-market-data", _MARKET_DATA, "get_movers", "screening",
        (EQUITY,),
        "Index movers (gainers/losers/most active) for idea generation.",
    ),
    MCPTool(
        "schwab-market-data", _MARKET_DATA, "get_market_hours", "reference",
        (EQUITY, FUTURES),
        "Session hours / market status for scheduling research runs.",
    ),

    # --- SEC EDGAR: fundamentals, ownership, insiders ---
    MCPTool(
        "sec-edgar", _SEC, "sec_financials", "fundamentals", (EQUITY,),
        "Structured XBRL financials (revenue, net income, EPS, cash flow) "
        "from 10-K/10-Q filings.",
    ),
    MCPTool(
        "sec-edgar", _SEC, "sec_financial_comparison", "fundamentals", (EQUITY,),
        "Side-by-side financial comparison across companies/periods.",
    ),
    MCPTool(
        "sec-edgar", _SEC, "sec_screen_by_metric", "screening", (EQUITY,),
        "Screen the universe by fundamental metrics.",
    ),
    MCPTool(
        "sec-edgar", _SEC, "sec_insider_trades", "positioning", (EQUITY,),
        "Form 4 insider buy/sell activity for sentiment and positioning.",
    ),
    MCPTool(
        "sec-edgar", _SEC, "sec_institutional_holders", "positioning", (EQUITY,),
        "13F institutional ownership and changes.",
    ),
    MCPTool(
        "sec-edgar", _SEC, "sec_company_events", "events", (EQUITY,),
        "Material events / 8-K calendar for event-risk awareness.",
    ),

    # --- FINRA: short positioning ---
    MCPTool(
        "finra", _FINRA, "finra_short_interest", "positioning", (EQUITY,),
        "Bi-monthly consolidated short interest and days-to-cover for "
        "squeeze and crowding analysis.",
    ),
    MCPTool(
        "finra", _FINRA, "finra_short_volume", "positioning", (EQUITY,),
        "Daily short volume as a share of total volume.",
    ),
    MCPTool(
        "finra", _FINRA, "finra_regsho_daily", "positioning", (EQUITY,),
        "Reg SHO threshold / fails-to-deliver signals.",
    ),

    # --- Commodities & volatility (core for futures research) ---
    MCPTool(
        "markets-commodities-vol", _COMMOD_VOL, "energy_prices", "commodities",
        (FUTURES,),
        "WTI/Brent crude, Henry Hub natural gas, heating oil spot prices.",
    ),
    MCPTool(
        "markets-commodities-vol", _COMMOD_VOL, "metals_prices", "commodities",
        (FUTURES,),
        "Industrial and precious metals (copper, aluminum, platinum, etc.).",
    ),
    MCPTool(
        "markets-commodities-vol", _COMMOD_VOL, "agriculture_prices", "commodities",
        (FUTURES,),
        "Grains and softs (wheat, corn, soybeans, sugar, coffee, cotton).",
    ),
    MCPTool(
        "markets-commodities-vol", _COMMOD_VOL, "vix_term_structure", "volatility",
        (EQUITY, FUTURES, CROSS),
        "VIX complex term structure (VIX9D/VIX/VIX3M/VXN/VXD) for "
        "contango/backwardation reads.",
    ),
    MCPTool(
        "markets-commodities-vol", _COMMOD_VOL, "vol_regime", "volatility",
        (EQUITY, FUTURES, CROSS),
        "Volatility regime classification (low/normal/elevated/crisis) with "
        "VIX percentile and term-structure slope.",
    ),
    MCPTool(
        "markets-commodities-vol", _COMMOD_VOL, "skew_tail_risk", "volatility",
        (EQUITY, CROSS),
        "CBOE SKEW and tail-risk indicators.",
    ),
    MCPTool(
        "markets-commodities-vol", _COMMOD_VOL, "dollar_index", "fx",
        (FUTURES, CROSS),
        "US dollar index level/trend (drives commodity and FX futures).",
    ),

    # --- Macro / rates (discounting & futures fair value context) ---
    MCPTool(
        "fred-macro", _MACRO, "fed_yield_curve", "rates", (MACRO, FUTURES),
        "Treasury yield curve across tenors; rates input for cost-of-carry.",
    ),
    MCPTool(
        "fred-macro", _MACRO, "fed_policy_rates", "rates", (MACRO, FUTURES),
        "Policy rates (fed funds, IORB, SOFR) for short-rate context.",
    ),
    MCPTool(
        "us-treasury", _TREASURY, "treasury_rates", "rates", (MACRO, FUTURES),
        "Daily Treasury par yields used as the risk-free input for carry "
        "and discounting.",
    ),
]


def tools_for_asset_class(asset_class: str) -> list[MCPTool]:
    """Return tools tagged for a given asset class (equity/futures/etc.)."""
    return [t for t in RESEARCH_TOOLS if asset_class in t.asset_classes]


def tools_by_category(category: str) -> list[MCPTool]:
    """Return tools in a given category (quotes, fundamentals, ...)."""
    return [t for t in RESEARCH_TOOLS if t.category == category]


def categories() -> list[str]:
    """Sorted, de-duplicated list of catalogued categories."""
    return sorted({t.category for t in RESEARCH_TOOLS})


def find(query: str) -> list[MCPTool]:
    """Case-insensitive substring search across tool name and description."""
    q = query.lower()
    return [
        t for t in RESEARCH_TOOLS
        if q in t.tool.lower() or q in t.description.lower() or q in t.label.lower()
    ]
