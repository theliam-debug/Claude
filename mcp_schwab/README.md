# mcp_schwab — Schwab market-data MCP (read-only)

A minimal, audit-friendly MCP server that exposes Charles Schwab Market Data
Production API endpoints as tools, so an agent can pull live quotes, option
chains, expirations, price history, market hours, and instrument metadata
directly in-loop.

## Read-only by construction

This package will not place, cancel, or modify an order, by design:

- The HTTP client (`client.py`) hard-codes the base URL to
  `https://api.schwabapi.com/marketdata/v1`. Any path argument containing
  `/trader/`, `/accounts/`, `/orders`, or `/transactions` raises
  `ScopeViolation` before a request leaves the process.
- Only `GET` is exposed. There is no `post`, `put`, `patch`, or `delete`.
- The Trader API surface is never imported. The test suite checks this.

If you ever want order entry, build a separate package. Keeping the scope
split at the module boundary makes the guarantee auditable in seconds.

## Setup (one time)

1. Register a Schwab developer application at
   <https://developer.schwab.com>. Choose Market Data only. Note your app
   key, app secret, and callback URL.
2. Export the credentials:

   ```bash
   export SCHWAB_APP_KEY="…"
   export SCHWAB_APP_SECRET="…"
   export SCHWAB_CALLBACK_URL="https://127.0.0.1"
   ```

3. Run the OAuth bootstrap once:

   ```bash
   pip install -e ".[schwab]"
   python -m mcp_schwab.cli authorize
   ```

   Open the printed URL, complete Schwab consent, paste the full callback
   URL back. Tokens are stored at
   `${XDG_CONFIG_HOME:-$HOME/.config}/schwab-mcp/tokens.json` mode 0600.

4. Verify with `python -m mcp_schwab.cli status`.

## Register with Claude Code

A repo-root `.mcp.json` is included:

```json
{
  "mcpServers": {
    "schwab-marketdata": {
      "command": "python",
      "args": ["-m", "mcp_schwab"]
    }
  }
}
```

Claude Code picks this up on project load.

## Tools exposed

| Tool | Endpoint | Purpose |
| --- | --- | --- |
| `schwab_quotes` | `GET /quotes` | Level-1 quotes for equities, options, indices, futures, forex |
| `schwab_option_chain` | `GET /chains` | Full chain with Greeks, IV, OI, volume |
| `schwab_option_expirations` | `GET /expirationchain` | Expiry ladder only |
| `schwab_price_history` | `GET /pricehistory` | OHLCV bars |
| `schwab_market_hours` | `GET /markets` | Session hours |
| `schwab_instrument_search` | `GET /instruments` | Symbol/CUSIP/description search |

## Token lifecycle

Access tokens are 30 minutes; the client refreshes 5 minutes early and
again on any 401. Refresh tokens are 7 days; expect to re-run
`authorize` weekly. The lifecycle is in `auth.py`.
