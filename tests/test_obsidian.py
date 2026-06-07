"""
Tests for the Obsidian vault exporter.
"""

import json


from derivatives_strategies.data.models import (
    Position,
    Recommendation,
    ActionType,
    Greeks,
    Economics,
    TransactionCosts,
    GateResult,
    GateStatus,
)
from derivatives_strategies.monitoring.obsidian import (
    export_vault,
    _slug,
    _merge_block,
)


def _make_rec(symbol="AAPL", action=ActionType.ROLL, approved=True, blocked_by=None):
    pos = Position(
        symbol=symbol,
        quantity=-1,
        position_type="call",
        strike=180.0,
        expiry="2025-02-21",
        cost_basis=2.5,
    )
    return Recommendation(
        run_id="run-123",
        timestamp="2025-01-15T10:00:00Z",
        position=pos,
        action=action,
        target_strike=185.0,
        target_expiry="2025-03-21",
        gate_results=[
            GateResult("LiquidityGate", GateStatus.PASS, "Liquid"),
            GateResult("DividendGate", GateStatus.BLOCK, "Assignment risk")
            if blocked_by else
            GateResult("DTEGate", GateStatus.WARN, "Short DTE"),
        ],
        economics=Economics(
            gross_premium=150.0,
            transaction_costs=TransactionCosts(2, 0.65, 0.08, 0.5, 3.23),
            net_premium=146.77,
            max_profit=500.0,
            max_loss=-100.0,
            annualized_return=0.18,
        ),
        greeks=Greeks(delta=0.28, gamma=0.015, theta=-0.08, vega=0.35),
        reason="Roll to capture additional premium",
        approved=approved,
        blocked_by=blocked_by,
        warnings=["Earnings within window"] if not blocked_by else [],
    )


class TestHelpers:
    def test_slug_sanitizes(self):
        assert _slug("AAPL 2025/02") == "AAPL-2025-02"
        assert _slug("  ") == "untitled"

    def test_merge_block_dedupes_and_sorts(self):
        text = "intro\n"
        out = _merge_block(text, "runs", ["[[b]]", "[[a]]"])
        out = _merge_block(out, "runs", ["[[a]]", "[[c]]"])
        assert out.count("[[a]]") == 1
        # sorted order
        assert out.index("[[a]]") < out.index("[[b]]") < out.index("[[c]]")


class TestExport:
    def test_creates_vault_structure(self, tmp_path):
        rec = _make_rec()
        export_vault(
            vault_dir=str(tmp_path / "vault"),
            run_id="run-123",
            timestamp="2025-01-15T10:00:00Z",
            as_of="2025-01-15",
            policy_name="covered_call",
            recommendations=[rec],
            positions=[rec.position],
            portfolio_value=100000.0,
        )
        vault = tmp_path / "vault"
        assert (vault / "Dashboard.md").exists()
        assert (vault / "Runs").is_dir()
        assert (vault / "Symbols" / "AAPL.md").exists()
        assert list((vault / "Recommendations").glob("*.md"))
        # gitignore present
        assert (vault / ".gitignore").exists()

    def test_obsidian_git_preconfigured(self, tmp_path):
        rec = _make_rec()
        export_vault(
            vault_dir=str(tmp_path / "vault"),
            run_id="run-123",
            timestamp="2025-01-15T10:00:00Z",
            as_of="2025-01-15",
            policy_name="covered_call",
            recommendations=[rec],
            positions=[rec.position],
        )
        cfg = tmp_path / "vault" / ".obsidian"
        community = json.loads((cfg / "community-plugins.json").read_text())
        assert "obsidian-git" in community
        data = json.loads((cfg / "plugins" / "obsidian-git" / "data.json").read_text())
        assert data["autoPushInterval"] == 10
        assert data["pullBeforePush"] is True

    def test_recommendation_note_has_frontmatter_and_links(self, tmp_path):
        rec = _make_rec()
        export_vault(
            vault_dir=str(tmp_path / "vault"),
            run_id="run-123",
            timestamp="2025-01-15T10:00:00Z",
            as_of="2025-01-15",
            policy_name="covered_call",
            recommendations=[rec],
            positions=[rec.position],
        )
        note = next((tmp_path / "vault" / "Recommendations").glob("*.md"))
        content = note.read_text()
        assert content.startswith("---")
        assert "type: recommendation" in content
        assert "#recommendation" not in content  # tags live in frontmatter list
        assert "tags:" in content
        assert "[[AAPL|AAPL]]" in content
        assert "## Economics" in content
        assert "## Greeks" in content
        assert "Delta | 0.2800" in content

    def test_runs_accumulate_in_symbol_note(self, tmp_path):
        vault = str(tmp_path / "vault")
        rec1 = _make_rec()
        export_vault(
            vault_dir=vault, run_id="run-aaaaaa", timestamp="t1",
            as_of="2025-01-15", policy_name="p",
            recommendations=[rec1], positions=[rec1.position],
        )
        rec2 = _make_rec()
        export_vault(
            vault_dir=vault, run_id="run-bbbbbb", timestamp="t2",
            as_of="2025-01-16", policy_name="p",
            recommendations=[rec2], positions=[rec2.position],
        )
        symbol_note = (tmp_path / "vault" / "Symbols" / "AAPL.md").read_text()
        assert "[[run-aaaaaa]]" in symbol_note
        assert "[[run-bbbbbb]]" in symbol_note
        # Dashboard lists both runs
        dashboard = (tmp_path / "vault" / "Dashboard.md").read_text()
        assert "[[run-aaaaaa]]" in dashboard
        assert "[[run-bbbbbb]]" in dashboard

    def test_blocked_recommendation_status(self, tmp_path):
        rec = _make_rec(approved=False, blocked_by="DividendGate")
        export_vault(
            vault_dir=str(tmp_path / "vault"),
            run_id="run-123", timestamp="t", as_of="2025-01-15",
            policy_name="p", recommendations=[rec], positions=[rec.position],
        )
        note = next((tmp_path / "vault" / "Recommendations").glob("*.md"))
        content = note.read_text()
        assert "blocked_by: DividendGate" in content
        assert "status/blocked" in content

    def test_user_edits_outside_blocks_preserved(self, tmp_path):
        vault = tmp_path / "vault"
        rec = _make_rec()
        export_vault(
            vault_dir=str(vault), run_id="run-aaaaaa", timestamp="t1",
            as_of="2025-01-15", policy_name="p",
            recommendations=[rec], positions=[rec.position],
        )
        symbol_path = vault / "Symbols" / "AAPL.md"
        edited = symbol_path.read_text() + "\n## My Notes\n\nWatch earnings.\n"
        symbol_path.write_text(edited)

        export_vault(
            vault_dir=str(vault), run_id="run-bbbbbb", timestamp="t2",
            as_of="2025-01-16", policy_name="p",
            recommendations=[rec], positions=[rec.position],
        )
        after = symbol_path.read_text()
        assert "## My Notes" in after
        assert "Watch earnings." in after
