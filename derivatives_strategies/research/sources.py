"""
Research data sources.

``ResearchDataSource`` is the interface the research analytics depend on. Two
implementations are provided:

- ``SampleResearchSource``: deterministic, offline data so the CLI and tests
  run with no network and no credentials. Mirrors the package's existing
  "no network calls" guarantee (see DemoProvider).

- ``MCPResearchSource``: an adapter that turns the catalogued MCP tools into
  normalized models. It never opens a socket itself; the host injects a
  ``call_tool(server, tool, params) -> dict`` callable that performs the actual
  MCP invocation. This keeps the package network-free while letting an
  orchestrator wire in live data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from derivatives_strategies.research.models import (
    EquityQuote,
    FuturesQuote,
    PriceSeries,
    ShortInterest,
    VolRegime,
)
from derivatives_strategies.research import registry


class ResearchDataSource(ABC):
    """Abstract source of normalized equity & futures research data."""

    @abstractmethod
    def get_equity_quote(self, symbol: str) -> Optional[EquityQuote]:
        ...

    @abstractmethod
    def get_futures_quote(self, symbol: str) -> Optional[FuturesQuote]:
        ...

    @abstractmethod
    def get_price_series(self, symbol: str) -> Optional[PriceSeries]:
        ...

    def get_short_interest(self, symbol: str) -> Optional[ShortInterest]:
        return None

    def get_vol_regime(self) -> Optional[VolRegime]:
        return None


# Type of the injected MCP caller: (server_id, tool_name, params) -> json dict
CallTool = Callable[[str, str, dict], dict]


class MCPResearchSource(ResearchDataSource):
    """
    Live research source backed by MCP tools.

    Parameters
    ----------
    call_tool:
        Callable supplied by the host that invokes an MCP tool and returns its
        parsed JSON result. Signature: ``call_tool(server, tool, params)``.
    server_overrides:
        Optional map of catalog label -> live server id, for when session
        server ids differ from those recorded in the registry.
    """

    def __init__(
        self,
        call_tool: CallTool,
        server_overrides: Optional[dict] = None,
    ):
        self._call = call_tool
        self._overrides = server_overrides or {}

    def _server(self, label: str, default: str) -> str:
        return self._overrides.get(label, default)

    def _tool(self, label: str, tool: str):
        """Resolve the catalog entry and return (server_id, tool_name)."""
        for entry in registry.RESEARCH_TOOLS:
            if entry.label == label and entry.tool == tool:
                return self._server(label, entry.server), entry.tool
        raise KeyError(f"Unknown research tool: {label}/{tool}")

    def get_equity_quote(self, symbol: str) -> Optional[EquityQuote]:
        server, tool = self._tool("schwab-market-data", "get_quotes")
        payload = self._call(server, tool, {
            "symbols": [symbol],
            "fields": "quote,fundamental,reference",
        })
        data = payload.get(symbol) or payload.get(symbol.upper())
        return EquityQuote.from_quote_payload(symbol, data) if data else None

    def get_futures_quote(self, symbol: str) -> Optional[FuturesQuote]:
        server, tool = self._tool("schwab-market-data", "get_quotes")
        payload = self._call(server, tool, {"symbols": [symbol]})
        data = payload.get(symbol) or payload.get(symbol.upper())
        return FuturesQuote.from_quote_payload(symbol, data) if data else None

    def get_price_series(self, symbol: str) -> Optional[PriceSeries]:
        server, tool = self._tool("schwab-market-data", "get_price_history")
        payload = self._call(server, tool, {
            "symbol": symbol,
            "periodType": "year",
            "period": 1,
            "frequencyType": "daily",
            "frequency": 1,
        })
        return PriceSeries.from_price_history_payload(symbol, payload) if payload else None

    def get_short_interest(self, symbol: str) -> Optional[ShortInterest]:
        server, tool = self._tool("finra", "finra_short_interest")
        payload = self._call(server, tool, {"ticker": symbol, "limit": 1})
        records = payload.get("records", payload.get("data", payload)) if isinstance(payload, dict) else payload
        if isinstance(records, list) and records:
            return ShortInterest.from_finra_payload(symbol, records[0])
        if isinstance(records, dict):
            return ShortInterest.from_finra_payload(symbol, records)
        return None

    def get_vol_regime(self) -> Optional[VolRegime]:
        server, tool = self._tool("markets-commodities-vol", "vol_regime")
        payload = self._call(server, tool, {"lookback_days": 252})
        return VolRegime.from_payload(payload) if payload else None


class SampleResearchSource(ResearchDataSource):
    """Deterministic offline data for demos and tests (no network)."""

    def __init__(self):
        self._equities = {
            "AAPL": {
                "symbol": "AAPL", "description": "APPLE INC",
                "lastPrice": 291.58, "mark": 291.13, "bid": 291.52, "ask": 291.58,
                "change": -4.05, "changePct": -1.37, "volume": 38784789,
                "52wHigh": 317.40, "52wLow": 195.07,
                "peRatio": 35.29, "eps": 7.46,
                "divYield": 0.37, "divAmount": 1.08, "divExDate": "2026-05-11T00:00:00Z",
                "isShortable": True, "isHardToBorrow": False,
            },
        }
        self._futures = {
            "/ESM26": {
                "symbol": "/ESM26", "description": "E-mini S&P 500 Jun-2026",
                "lastPrice": 7436.25, "mark": 7436.25, "bid": 7436.25, "ask": 7436.75,
                "change": 40.25, "close": 7396.0, "volume": 0, "exchange": "XCME",
            },
            "/ESU26": {
                "symbol": "/ESU26", "description": "E-mini S&P 500 Sep-2026",
                "lastPrice": 7472.00, "mark": 7472.00, "bid": 7471.50, "ask": 7472.50,
                "change": 41.0, "close": 7431.0, "volume": 0, "exchange": "XCME",
            },
            "/ESZ26": {
                "symbol": "/ESZ26", "description": "E-mini S&P 500 Dec-2026",
                "lastPrice": 7509.50, "mark": 7509.50, "bid": 7509.0, "ask": 7510.0,
                "change": 42.0, "close": 7468.0, "volume": 0, "exchange": "XCME",
            },
        }
        self._short_interest = {
            "AAPL": {
                "symbolCode": "AAPL", "settlementDate": "2026-05-30",
                "currentShortPositionQuantity": 110_000_000,
                "daysToCoverQuantity": 1.4, "changePercent": -3.2,
                "averageDailyVolumeQuantity": 78_000_000,
            },
        }
        self._vol_regime = {
            "current_vix": 19.44, "percentile_rank": 77, "average": 18.09,
            "min": 13.47, "max": 31.05, "vix3m": 21.42,
            "term_structure_ratio": 1.102, "regime": "normal",
        }

    def get_equity_quote(self, symbol: str) -> Optional[EquityQuote]:
        data = self._equities.get(symbol.upper())
        return EquityQuote.from_quote_payload(symbol, data) if data else None

    def get_futures_quote(self, symbol: str) -> Optional[FuturesQuote]:
        data = self._futures.get(symbol.upper())
        return FuturesQuote.from_quote_payload(symbol, data) if data else None

    def futures_curve(self, root: str) -> list[FuturesQuote]:
        """All sample futures contracts for a root symbol (e.g. '/ES')."""
        root = root.upper().rstrip("0123456789")
        out = []
        for sym, data in self._futures.items():
            base = "".join(ch for ch in sym if not ch.isdigit())[:-1]  # drop month code
            if sym.upper().startswith(root) or base.upper() == root:
                out.append(FuturesQuote.from_quote_payload(sym, data))
        return out

    def get_price_series(self, symbol: str) -> Optional[PriceSeries]:
        # Deterministic synthetic uptrend with mild noise, 120 daily bars.
        base = 250.0
        candles = []
        price = base
        for i in range(120):
            drift = 0.0008
            wiggle = 0.012 * ((i * 7919) % 11 - 5) / 5.0  # deterministic pseudo-noise
            price = price * (1.0 + drift + wiggle)
            candles.append({
                "datetime": (1_700_000_000 + i * 86_400) * 1000,
                "open": round(price * 0.999, 4),
                "high": round(price * 1.008, 4),
                "low": round(price * 0.992, 4),
                "close": round(price, 4),
                "volume": 1_000_000 + i * 1000,
            })
        return PriceSeries.from_price_history_payload(symbol, {"symbol": symbol, "candles": candles})

    def get_short_interest(self, symbol: str) -> Optional[ShortInterest]:
        data = self._short_interest.get(symbol.upper())
        return ShortInterest.from_finra_payload(symbol, data) if data else None

    def get_vol_regime(self) -> Optional[VolRegime]:
        return VolRegime.from_payload(self._vol_regime)
