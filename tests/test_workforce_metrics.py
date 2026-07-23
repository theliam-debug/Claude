"""Tests for metrics, calibration scoring, charter loading, and the demo."""

import pytest

from lsto_workforce.charter import default_charter, load_charter
from lsto_workforce.demo import run_demo
from lsto_workforce.ledger import HashChainLedger
from lsto_workforce.metrics import brier_score, compute_scorecard, render_scorecard
from lsto_workforce.models import (
    DecisionRecord,
    DecisionStatus,
    Forecast,
    ImpactTier,
    SourceTier,
    new_id,
    utc_now_iso,
)


class TestBrierScore:
    def test_no_resolved_forecasts_returns_none(self):
        assert brier_score([Forecast("x", 0.7, "2026-01-01")]) is None

    def test_perfect_forecast_scores_zero(self):
        assert brier_score([Forecast("x", 1.0, "d", resolved=True)]) == 0.0

    def test_coin_flip_scores_quarter(self):
        forecasts = [
            Forecast("a", 0.5, "d", resolved=True),
            Forecast("b", 0.5, "d", resolved=False),
        ]
        assert brier_score(forecasts) == pytest.approx(0.25)

    def test_confident_wrong_scores_high(self):
        assert brier_score(
            [Forecast("x", 0.9, "d", resolved=False)]
        ) == pytest.approx(0.81)


class TestScorecard:
    def _record(self, status, forecast=None):
        record = DecisionRecord(
            decision_id=new_id("dec"), question="q", impact=ImpactTier.LOW,
            category="general", requested_by="liam",
            opened_at=utc_now_iso(), as_of="2026-07-23",
        )
        record.status = status
        record.confidence = 0.7
        record.forecast = forecast
        return record

    def test_aggregates_statuses_and_calibration(self):
        records = [
            self._record(DecisionStatus.APPROVED,
                         Forecast("a", 0.8, "d", resolved=True)),
            self._record(DecisionStatus.BLOCKED,
                         Forecast("b", 0.6, "d", resolved=False)),
        ]
        card = compute_scorecard(records)
        assert card.decisions_total == 2
        assert card.by_status == {"approved": 1, "blocked": 1}
        assert card.forecasts_resolved == 2
        # Brier: ((0.8-1)^2 + (0.6-0)^2) / 2 = (0.04 + 0.36) / 2 = 0.2
        assert card.brier_score == pytest.approx(0.2)
        assert card.hit_rate == pytest.approx(0.5)
        markdown = render_scorecard(card)
        assert "Brier score" in markdown

    def test_empty_records(self):
        card = compute_scorecard([])
        assert card.decisions_total == 0
        assert card.brier_score is None
        assert "Decisions:** 0" in render_scorecard(card)


class TestCharter:
    def test_charter_hash_is_stable(self):
        assert default_charter().charter_hash() == default_charter().charter_hash()

    def test_yaml_override(self, tmp_path):
        charter_yaml = tmp_path / "charter.yml"
        charter_yaml.write_text(
            "name: Custom Charter\n"
            "sensitive_categories:\n"
            "  - vendor_selection\n"
            "sources:\n"
            "  - name: Internal CRM\n"
            "    tier: internal\n"
            "tier_requirements:\n"
            "  high:\n"
            "    min_evidence: 7\n"
        )
        charter = load_charter(str(charter_yaml))
        assert charter.name == "Custom Charter"
        assert "vendor_selection" in charter.sensitive_categories
        assert charter.source_by_name("Internal CRM").tier == SourceTier.INTERNAL
        assert charter.requirements_for(ImpactTier.HIGH).min_evidence == 7
        # Untouched tiers keep defaults.
        assert charter.requirements_for(ImpactTier.LOW).min_evidence == 1
        # Overrides change the hash.
        assert charter.charter_hash() != default_charter().charter_hash()


class TestDemo:
    def test_demo_runs_end_to_end(self, tmp_path):
        paths = run_demo(out_dir=str(tmp_path / "wf"))
        ledger = HashChainLedger(paths["ledger"])
        assert ledger.verify().valid
        brief = open(paths["decision_brief"]).read()
        assert "APPROVED" in brief
        assert "Dissent" in brief
        assert "Record hash" in brief
