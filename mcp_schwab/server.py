"""FastMCP server that exposes the read-only Schwab market-data tools.

Run with: `python -m mcp_schwab` (uses stdio transport). For Claude Code
register via the project `.mcp.json` at the repo root.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_schwab import tools
from mcp_schwab.client import SchwabMarketDataClient

mcp = FastMCP("schwab-marketdata")

# A single shared client lives for the server's lifetime. The httpx async
# client is happy to be reused and pools connections.
_client: SchwabMarketDataClient | None = None


def _get_client() -> SchwabMarketDataClient:
    global _client
    if _client is None:
        _client = SchwabMarketDataClient()
    return _client


@mcp.tool(
    description=(
        "Get live level-1 quotes for one or more Schwab symbols (equities, "
        "options, indices, futures, forex). Returns last/bid/ask/volume and, "
        "for options, full Greeks and IV. READ-ONLY."
    )
)
async def schwab_quotes(
    symbols: list[str],
    fields: str | None = None,
) -> dict[str, Any]:
    return await tools.quotes(_get_client(), symbols=symbols, fields=fields)


@mcp.tool(
    description=(
        "Get the option chain for an underlying. Supports filtering by "
        "expiration window (from_date/to_date as YYYY-MM-DD), strike count "
        "around ATM, contract type (CALL/PUT/ALL), and strategy "
        "(SINGLE/VERTICAL/CALENDAR/etc). Returns full Greeks, IV, OI and "
        "volume per contract. READ-ONLY."
    )
)
async def schwab_option_chain(
    symbol: str,
    contract_type: str = "ALL",
    strike_count: int | None = None,
    strategy: str = "SINGLE",
    from_date: str | None = None,
    to_date: str | None = None,
    range: str | None = None,
    strike: float | None = None,
    include_underlying_quote: bool = True,
) -> dict[str, Any]:
    return await tools.option_chain(
        _get_client(),
        symbol=symbol,
        contract_type=contract_type,
        strike_count=strike_count,
        strategy=strategy,
        from_date=from_date,
        to_date=to_date,
        range=range,
        strike=strike,
        include_underlying_quote=include_underlying_quote,
    )


@mcp.tool(
    description=(
        "List all option expiration dates available for an underlying. "
        "Cheaper than a full chain when only scoping the expiry ladder. "
        "READ-ONLY."
    )
)
async def schwab_option_expirations(symbol: str) -> dict[str, Any]:
    return await tools.option_expirations(_get_client(), symbol=symbol)


@mcp.tool(
    description=(
        "OHLCV price-history bars for an underlying. Period_type one of "
        "day/month/year/ytd, frequency_type one of minute/daily/weekly/"
        "monthly. Epoch start_date/end_date are milliseconds. READ-ONLY."
    )
)
async def schwab_price_history(
    symbol: str,
    period_type: str | None = None,
    period: int | None = None,
    frequency_type: str | None = None,
    frequency: int | None = None,
    start_date: int | None = None,
    end_date: int | None = None,
    need_extended_hours_data: bool | None = None,
) -> dict[str, Any]:
    return await tools.price_history(
        _get_client(),
        symbol=symbol,
        period_type=period_type,
        period=period,
        frequency_type=frequency_type,
        frequency=frequency,
        start_date=start_date,
        end_date=end_date,
        need_extended_hours_data=need_extended_hours_data,
    )


@mcp.tool(
    description=(
        "Market session hours for one or more markets on a given date "
        "(YYYY-MM-DD). Markets: equity, option, bond, future, forex. "
        "READ-ONLY."
    )
)
async def schwab_market_hours(
    markets: list[str],
    date: str | None = None,
) -> dict[str, Any]:
    return await tools.market_hours(_get_client(), markets=markets, date=date)


@mcp.tool(
    description=(
        "Search Schwab's instrument universe by symbol or description. "
        "Projection one of symbol-search/symbol-regex/desc-search/"
        "desc-regex/search/fundamental. READ-ONLY."
    )
)
async def schwab_instrument_search(
    symbol: str,
    projection: str = "symbol-search",
) -> dict[str, Any]:
    return await tools.instrument_search(
        _get_client(), symbol=symbol, projection=projection
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
