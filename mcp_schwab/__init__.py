"""Schwab market-data MCP shim — read-only by construction.

This package exposes Charles Schwab Market Data Production API endpoints
as MCP tools. The Trader API (`/trader/v1/`) is deliberately not imported
and the HTTP client refuses to construct any URL outside `/marketdata/v1/`.
There is no path through this package that places, cancels, or modifies an
order.
"""

from mcp_schwab._version import __version__

__all__ = ["__version__"]
