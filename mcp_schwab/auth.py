"""OAuth 2.0 helpers for Schwab market-data access.

Schwab uses the authorization-code flow with refresh tokens. Access tokens
expire after 30 minutes; refresh tokens are valid for 7 days. The token
store is a JSON file at $XDG_CONFIG_HOME/schwab-mcp/tokens.json (mode 0600).

This module never asks for or stores any scope beyond market data. The
authorisation URL is built with the bare `readonly` scope where Schwab
permits it; in practice Schwab grants a single combined scope per app, so
the read-only guarantee is enforced downstream in client.py by pinning the
base URL.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"

# Schwab access tokens are 30 minutes; refresh 5 minutes early.
ACCESS_TOKEN_SKEW_SECONDS = 300


def _token_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "schwab-mcp" / "tokens.json"


@dataclass(slots=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: float  # epoch seconds

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return now >= (self.expires_at - ACCESS_TOKEN_SKEW_SECONDS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenSet":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=float(data["expires_at"]),
        )


def load_tokens() -> TokenSet | None:
    path = _token_path()
    if not path.exists():
        return None
    return TokenSet.from_dict(json.loads(path.read_text()))


def save_tokens(tokens: TokenSet) -> None:
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tokens.to_dict()))
    os.chmod(path, 0o600)


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def exchange_code(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> TokenSet:
    """Initial authorization-code exchange. Called once at setup."""
    response = httpx.post(
        SCHWAB_TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    return TokenSet(
        access_token=payload["access_token"],
        refresh_token=payload["refresh_token"],
        expires_at=time.time() + float(payload["expires_in"]),
    )


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> TokenSet:
    """Refresh an expired access token. Refresh token unchanged on success."""
    response = httpx.post(
        SCHWAB_TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    return TokenSet(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token", refresh_token),
        expires_at=time.time() + float(payload["expires_in"]),
    )


def authorize_url(*, client_id: str, redirect_uri: str) -> str:
    """The URL the user opens once to grant the app market-data access."""
    from urllib.parse import urlencode

    return SCHWAB_AUTH_URL + "?" + urlencode(
        {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code"}
    )
