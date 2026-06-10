"""Smoke + safety tests for the Schwab MCP shim.

No live network: every test uses fakes. The point of this suite is to make
the read-only guarantee a test, not a comment — and to prove the package
imports cleanly without the optional `mcp` runtime dependency.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
from pathlib import Path

import pytest


# ---------- safety: scope guard ----------------------------------------------


def test_client_rejects_trader_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHWAB_APP_KEY", "k")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "s")
    from mcp_schwab.client import ScopeViolation, _validate_path

    for bad in [
        "/trader/v1/accounts",
        "/accounts/123/orders",
        "/orders",
        "/transactions",
        "https://example.com/marketdata/v1/quotes",
    ]:
        with pytest.raises(ScopeViolation):
            _validate_path(bad)


def test_client_accepts_marketdata_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHWAB_APP_KEY", "k")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "s")
    from mcp_schwab.client import _validate_path

    assert _validate_path("/quotes") == "/quotes"
    assert _validate_path("chains") == "/chains"
    assert _validate_path("/expirationchain") == "/expirationchain"


def test_no_module_references_trader_scope() -> None:
    """Static guarantee: no executable code under mcp_schwab/ references the
    Trader API surface. Docstrings and comments are allowed to mention the
    excluded scope so the read-only contract can be documented in-source.
    """
    import ast
    import tokenize

    package_dir = Path(__file__).parent.parent / "mcp_schwab"
    forbidden_tokens = ("/trader/v1", "PlaceOrder", "cancel_order")

    def _docstring_node_ids(tree: ast.AST) -> set[int]:
        ids: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            body = getattr(node, "body", None) or []
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    ids.add(id(first.value))
        return ids

    for py_file in package_dir.rglob("*.py"):
        source = py_file.read_text()
        tree = ast.parse(source)
        doc_ids = _docstring_node_ids(tree)
        # Check every string constant that is NOT a docstring.
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in doc_ids:
                    continue
                for forbidden in forbidden_tokens:
                    assert forbidden not in node.value, (
                        f"{py_file}: executable string contains forbidden "
                        f"trader-scope token {forbidden!r}: {node.value!r}"
                    )
            if isinstance(node, ast.Name):
                for forbidden in forbidden_tokens:
                    assert forbidden not in node.id, (
                        f"{py_file}: identifier contains forbidden "
                        f"trader-scope token {forbidden!r}: {node.id}"
                    )
        # Belt-and-braces: also verify the tokenizer sees no NAME tokens that
        # reference forbidden identifiers (catches odd cases like attribute
        # access strings constructed by string addition).
        with open(py_file, "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type == tokenize.NAME:
                    for forbidden in ("PlaceOrder", "cancel_order"):
                        assert forbidden not in tok.string, (
                            f"{py_file}: token {tok.string!r} references "
                            f"forbidden symbol {forbidden!r}"
                        )


def test_client_exposes_only_get(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHWAB_APP_KEY", "k")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "s")
    from mcp_schwab.client import SchwabMarketDataClient

    public = {
        name
        for name, member in inspect.getmembers(SchwabMarketDataClient)
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    }
    # The only async public method that performs HTTP work should be `get`.
    # `aclose` is sync-callable; everything else is sync.
    assert "get" in public
    assert public.isdisjoint({"post", "put", "patch", "delete"})


# ---------- auth: token round-trip + refresh path ----------------------------


def test_tokens_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from mcp_schwab import auth

    importlib.reload(auth)  # pick up XDG override
    tokens = auth.TokenSet(
        access_token="a", refresh_token="r", expires_at=9.99e9
    )
    auth.save_tokens(tokens)

    loaded = auth.load_tokens()
    assert loaded is not None
    assert loaded.access_token == "a"
    assert loaded.refresh_token == "r"
    assert not loaded.is_expired()

    saved_path = Path(tmp_path) / "schwab-mcp" / "tokens.json"
    assert saved_path.exists()
    assert (saved_path.stat().st_mode & 0o777) == 0o600
    data = json.loads(saved_path.read_text())
    assert set(data) == {"access_token", "refresh_token", "expires_at"}


def test_expired_token_detection() -> None:
    from mcp_schwab.auth import TokenSet

    fresh = TokenSet(access_token="a", refresh_token="r", expires_at=9.99e9)
    expired = TokenSet(access_token="a", refresh_token="r", expires_at=1.0)
    assert not fresh.is_expired()
    assert expired.is_expired()


# ---------- client: full GET flow with httpx mock -----------------------------


def test_client_get_uses_bearer_and_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setenv("SCHWAB_APP_KEY", "k")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "s")
    from mcp_schwab import auth
    from mcp_schwab.client import SchwabMarketDataClient, SCHWAB_MARKETDATA_BASE

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)

    tokens = auth.TokenSet(access_token="tok", refresh_token="r", expires_at=9.99e9)
    client = SchwabMarketDataClient(tokens=tokens, http=http)

    import asyncio

    result = asyncio.get_event_loop().run_until_complete(
        client.get("/quotes", params={"symbols": "VG"})
    )
    assert result == {"ok": True}
    assert captured["auth"] == "Bearer tok"
    assert captured["url"].startswith(SCHWAB_MARKETDATA_BASE + "/quotes")


# ---------- cli surface -----------------------------------------------------


def test_cli_status_no_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # Force a clean re-import so XDG override takes effect for the module-
    # level token-path resolver.
    for mod in list(sys.modules):
        if mod.startswith("mcp_schwab"):
            sys.modules.pop(mod)
    from mcp_schwab.cli import main

    rc = main(["status"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "No tokens" in out
