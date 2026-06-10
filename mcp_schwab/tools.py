"""Read-only Schwab market-data tools surfaced as MCP entry points.

Each function here is a thin wrapper over `SchwabMarketDataClient.get` that
documents the call and shapes parameters into Schwab's expected query form.
"""

from __future__ import annotations

from typing import Any

from mcp_schwab.client import SchwabMarketDataClient


async def quotes(
    client: SchwabMarketDataClient,
    *,
    symbols: list[str],
    fields: str | None = None,
    indicative: bool | None = None,
) -> dict[str, Any]:
    """Fetch level-1 quotes for one or more symbols.

    Symbols may include equities (e.g. "VG"), options
    (e.g. "VG   280121C00015000" — Schwab OSI format with spaces preserved),
    indices (e.g. "$SPX"), futures (e.g. "/ES"), and forex.
    """
    params: dict[str, Any] = {"symbols": ",".join(symbols)}
    if fields:
        params["fields"] = fields
    if indicative is not None:
        params["indicative"] = "true" if indicative else "false"
    return await client.get("/quotes", params=params)


async def option_chain(
    client: SchwabMarketDataClient,
    *,
    symbol: str,
    contract_type: str = "ALL",
    strike_count: int | None = None,
    include_underlying_quote: bool = True,
    strategy: str = "SINGLE",
    interval: float | None = None,
    strike: float | None = None,
    range: str | None = None,  # noqa: A002 - Schwab API field name
    from_date: str | None = None,
    to_date: str | None = None,
    exp_month: str | None = None,
    option_type: str | None = None,
    entitlement: str | None = None,
) -> dict[str, Any]:
    """Fetch the option chain for an underlying.

    Args:
        symbol: Underlying ticker (e.g. "VG").
        contract_type: CALL, PUT, or ALL.
        strike_count: Number of strikes above and below ATM.
        include_underlying_quote: Include underlying's level-1 quote.
        strategy: SINGLE, ANALYTICAL, COVERED, VERTICAL, CALENDAR, STRANGLE,
            STRADDLE, BUTTERFLY, CONDOR, DIAGONAL, COLLAR, ROLL.
        from_date, to_date: ISO dates bounding expirations.
        range: ITM, NTM, OTM, SAK, SBK, SNK, ALL.
        exp_month: JAN..DEC or ALL.
    """
    params: dict[str, Any] = {
        "symbol": symbol,
        "contractType": contract_type,
        "includeUnderlyingQuote": "true" if include_underlying_quote else "false",
        "strategy": strategy,
    }
    if strike_count is not None:
        params["strikeCount"] = strike_count
    if interval is not None:
        params["interval"] = interval
    if strike is not None:
        params["strike"] = strike
    if range:
        params["range"] = range
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date
    if exp_month:
        params["expMonth"] = exp_month
    if option_type:
        params["optionType"] = option_type
    if entitlement:
        params["entitlement"] = entitlement
    return await client.get("/chains", params=params)


async def option_expirations(
    client: SchwabMarketDataClient,
    *,
    symbol: str,
) -> dict[str, Any]:
    """List all option expirations available for an underlying."""
    return await client.get("/expirationchain", params={"symbol": symbol})


async def price_history(
    client: SchwabMarketDataClient,
    *,
    symbol: str,
    period_type: str | None = None,  # day, month, year, ytd
    period: int | None = None,
    frequency_type: str | None = None,  # minute, daily, weekly, monthly
    frequency: int | None = None,
    start_date: int | None = None,  # epoch ms
    end_date: int | None = None,  # epoch ms
    need_extended_hours_data: bool | None = None,
    need_previous_close: bool | None = None,
) -> dict[str, Any]:
    """OHLCV bars for an underlying. Epoch values are milliseconds."""
    params: dict[str, Any] = {"symbol": symbol}
    if period_type:
        params["periodType"] = period_type
    if period is not None:
        params["period"] = period
    if frequency_type:
        params["frequencyType"] = frequency_type
    if frequency is not None:
        params["frequency"] = frequency
    if start_date is not None:
        params["startDate"] = start_date
    if end_date is not None:
        params["endDate"] = end_date
    if need_extended_hours_data is not None:
        params["needExtendedHoursData"] = "true" if need_extended_hours_data else "false"
    if need_previous_close is not None:
        params["needPreviousClose"] = "true" if need_previous_close else "false"
    return await client.get("/pricehistory", params=params)


async def market_hours(
    client: SchwabMarketDataClient,
    *,
    markets: list[str],
    date: str | None = None,
) -> dict[str, Any]:
    """Market session hours.

    Markets: equity, option, bond, future, forex.
    Date: YYYY-MM-DD; defaults to today.
    """
    params: dict[str, Any] = {"markets": ",".join(markets)}
    if date:
        params["date"] = date
    return await client.get("/markets", params=params)


async def instrument_search(
    client: SchwabMarketDataClient,
    *,
    symbol: str,
    projection: str = "symbol-search",
) -> dict[str, Any]:
    """Search the instrument universe.

    Projection: symbol-search, symbol-regex, desc-search, desc-regex,
    search, fundamental.
    """
    return await client.get(
        "/instruments",
        params={"symbol": symbol, "projection": projection},
    )
