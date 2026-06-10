"""Bootstrap CLI for the one-time OAuth authorisation step.

Usage:

    python -m mcp_schwab.cli authorize

Schwab's authorisation flow is interactive: open the printed URL in a
browser, complete the consent screen, copy the full callback URL you are
redirected to, and paste it back. The CLI extracts the `code` query
parameter, exchanges it for tokens, and writes them to disk.
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import parse_qs, urlparse

from mcp_schwab import auth


def _read_env() -> tuple[str, str, str]:
    client_id = os.environ.get("SCHWAB_APP_KEY")
    client_secret = os.environ.get("SCHWAB_APP_SECRET")
    redirect_uri = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
    if not client_id or not client_secret:
        print(
            "ERROR: SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in "
            "the environment.",
            file=sys.stderr,
        )
        sys.exit(2)
    return client_id, client_secret, redirect_uri


def cmd_authorize(_args: argparse.Namespace) -> int:
    client_id, client_secret, redirect_uri = _read_env()
    url = auth.authorize_url(client_id=client_id, redirect_uri=redirect_uri)
    print("Open this URL in a browser and complete the Schwab consent:\n")
    print(url)
    print(
        "\nAfter approval Schwab will redirect to a URL starting with\n  "
        f"{redirect_uri}\nthat contains a ?code=... query parameter. "
        "Paste that full URL below."
    )
    callback = input("\nPaste callback URL: ").strip()
    parsed = urlparse(callback)
    code_values = parse_qs(parsed.query).get("code")
    if not code_values:
        print("ERROR: no ?code= query parameter found in the URL.", file=sys.stderr)
        return 2
    tokens = auth.exchange_code(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        code=code_values[0],
    )
    auth.save_tokens(tokens)
    print("\nTokens saved. Access expires in ~30 minutes; refresh in 7 days.")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    tokens = auth.load_tokens()
    if tokens is None:
        print("No tokens on disk. Run `authorize` first.")
        return 1
    print(
        "Tokens present. "
        f"Access expires {'(expired)' if tokens.is_expired() else 'in future'}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcp_schwab.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("authorize", help="One-time browser-based OAuth setup")
    sub.add_parser("status", help="Show whether tokens are on disk")
    args = parser.parse_args(argv)
    if args.cmd == "authorize":
        return cmd_authorize(args)
    if args.cmd == "status":
        return cmd_status(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
