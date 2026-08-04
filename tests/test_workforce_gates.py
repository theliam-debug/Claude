"""Tests for accountability gates."""

import pytest

from lsto_workforce.charter import default_charter
from lsto_workforce.gates import (
    CalibrationGate,
    ConflictOfInterestGate,
    EthicsGate,
    EvidenceSufficiencyGate,
    FreshnessGate,
    GateContext,
    HumanApprovalGate,
    ProvenanceGate,
    RedTeamGate,
    RoleCoverageGate,
)
from lsto_workforce.models import (
    Assessment,
    DecisionRecord,
    Dissent,
    DissentSeverity,
    Evidence,
    Forecast,
    GateStatus,
    ImpactTier,
    RoleType,
    SourceTier,
    new_id,
    utc_now_iso,
)

AS_OF = "2026-07-23"


def make_record(impact=ImpactTier.LOW, category="general") -> DecisionRecord:
    return DecisionRecord(
        decision_id=new_id("dec"),
        question="Test question?",
        impact=impact,
        category=category,
        requested_by="liam",
        opened_at=utc_now_iso(),
        as_of=AS_OF,
    )


def make_evidence(source="US Treasury", tier=SourceTier.PRIMARY, as_of="2026-07-20"):
    return Evidence.create(
        claim="claim", source_name=source, source_tier=tier, as_of=as_of,
    )


def ctx(record) -> GateContext:
    return GateContext(record=record, charter=default_charter())


class TestProvenanceGate:
    def test_registered_sources_pass(self):
        record = make_record()
        record.evidence.append(make_evidence())
        assert ProvenanceGate().evaluate(ctx(record)).status == GateStatus.PASS

    def test_unregistered_source_blocks(self):
        record = make_record()
        record.evidence.append(make_evidence(source="some blog"))
        result = ProvenanceGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        assert "unregistered source" in result.details["problems"][0]


class TestEvidenceSufficiencyGate:
    def test_low_tier_needs_one_item(self):
        record = make_record(ImpactTier.LOW)
        assert EvidenceSufficiencyGate().evaluate(ctx(record)).status == GateStatus.BLOCK
        record.evidence.append(make_evidence(tier=SourceTier.PRIMARY))
        assert EvidenceSufficiencyGate().evaluate(ctx(record)).status == GateStatus.PASS

    def test_high_tier_needs_primary_quota(self):
        record = make_record(ImpactTier.HIGH)
        for _ in range(3):
            record.evidence.append(
                make_evidence(source="MT Newswires", tier=SourceTier.SECONDARY)
            )
        result = EvidenceSufficiencyGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        assert "primary/internal" in result.message

    def test_model_estimates_never_fill_quota(self):
        record = make_record(ImpactTier.MEDIUM)  # needs 2 items, 1 primary/internal
        record.evidence.append(
            make_evidence(source="analyst_judgment", tier=SourceTier.MODEL_ESTIMATE)
        )
        record.evidence.append(
            make_evidence(source="analyst_judgment", tier=SourceTier.MODEL_ESTIMATE)
        )
        assert EvidenceSufficiencyGate().evaluate(ctx(record)).status == GateStatus.BLOCK


class TestFreshnessGate:
    def test_fresh_evidence_passes(self):
        record = make_record(ImpactTier.HIGH)
        record.evidence.append(make_evidence(as_of="2026-07-01"))
        assert FreshnessGate().evaluate(ctx(record)).status == GateStatus.PASS

    def test_stale_evidence_blocks_high_tier(self):
        record = make_record(ImpactTier.HIGH)  # max 90 days
        record.evidence.append(make_evidence(as_of="2026-01-01"))
        result = FreshnessGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK

    def test_same_staleness_ok_at_low_tier(self):
        record = make_record(ImpactTier.LOW)  # max 365 days
        record.evidence.append(make_evidence(as_of="2026-01-01"))
        assert FreshnessGate().evaluate(ctx(record)).status == GateStatus.PASS


class TestRoleCoverageGate:
    def test_missing_roles_block(self):
        record = make_record(ImpactTier.MEDIUM)
        record.assessments.append(
            Assessment.create(RoleType.RESEARCH_ANALYST, "s", 0.5)
        )
        result = RoleCoverageGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        assert "risk_officer" in result.message

    def test_sensitive_category_requires_ethics_reviewer(self):
        record = make_record(ImpactTier.LOW, category="hiring")
        record.assessments.append(
            Assessment.create(RoleType.RESEARCH_ANALYST, "s", 0.5)
        )
        result = RoleCoverageGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        assert "ethics_reviewer" in result.message


class TestRedTeamGate:
    def test_high_tier_requires_red_team(self):
        record = make_record(ImpactTier.HIGH)
        assert RedTeamGate().evaluate(ctx(record)).status == GateStatus.BLOCK

    def test_unresolved_material_dissent_blocks(self):
        record = make_record(ImpactTier.LOW)
        record.dissents.append(
            Dissent.create(RoleType.RED_TEAM, "objection", DissentSeverity.MATERIAL)
        )
        result = RedTeamGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        assert result.override_allowed  # material may be overridden

    def test_unresolved_fatal_dissent_not_overridable(self):
        record = make_record(ImpactTier.LOW)
        record.dissents.append(
            Dissent.create(RoleType.RED_TEAM, "objection", DissentSeverity.FATAL)
        )
        result = RedTeamGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        assert not result.override_allowed

    def test_note_dissent_does_not_block(self):
        record = make_record(ImpactTier.LOW)
        record.dissents.append(
            Dissent.create(RoleType.RED_TEAM, "fyi", DissentSeverity.NOTE)
        )
        assert RedTeamGate().evaluate(ctx(record)).status == GateStatus.PASS


class TestEthicsGate:
    def test_prohibited_content_blocks_without_override(self):
        record = make_record()
        record.question = "Can we trade on insider information from the call?"
        result = EthicsGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        assert not result.override_allowed

    def test_sensitive_category_needs_reviewer(self):
        record = make_record(ImpactTier.LOW, category="lending")
        result = EthicsGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        record.assessments.append(
            Assessment.create(RoleType.ETHICS_REVIEWER, "reviewed", 0.9)
        )
        assert EthicsGate().evaluate(ctx(record)).status == GateStatus.PASS

    def test_clean_low_tier_passes(self):
        record = make_record(ImpactTier.LOW)
        assert EthicsGate().evaluate(ctx(record)).status == GateStatus.PASS


class TestConflictOfInterestGate:
    def test_no_conflicts_pass(self):
        record = make_record()
        assert ConflictOfInterestGate().evaluate(ctx(record)).status == GateStatus.PASS

    def test_conflict_warns_at_low_tier(self):
        record = make_record(ImpactTier.LOW)
        record.assessments.append(Assessment.create(
            RoleType.RESEARCH_ANALYST, "s", 0.5,
            declared_conflicts=["holds the position personally"],
        ))
        assert ConflictOfInterestGate().evaluate(ctx(record)).status == GateStatus.WARN

    def test_conflict_blocks_at_high_tier(self):
        record = make_record(ImpactTier.HIGH)
        record.assessments.append(Assessment.create(
            RoleType.RESEARCH_ANALYST, "s", 0.5,
            declared_conflicts=["holds the position personally"],
        ))
        assert ConflictOfInterestGate().evaluate(ctx(record)).status == GateStatus.BLOCK


class TestCalibrationGate:
    def test_missing_confidence_warns(self):
        record = make_record()
        result = CalibrationGate().evaluate(ctx(record))
        assert result.status == GateStatus.WARN
        assert "no confidence stated" in result.message

    def test_overconfidence_flagged_at_high_impact(self):
        record = make_record(ImpactTier.HIGH)
        record.confidence = 0.99
        record.forecast = Forecast("x", 0.9, "2026-12-31")
        record.what_would_change_our_mind = ["new data"]
        result = CalibrationGate().evaluate(ctx(record))
        assert result.status == GateStatus.WARN
        assert "above 0.95" in result.message

    def test_complete_calibration_passes(self):
        record = make_record(ImpactTier.HIGH)
        record.confidence = 0.7
        record.forecast = Forecast("x", 0.7, "2026-12-31")
        record.what_would_change_our_mind = ["new data"]
        assert CalibrationGate().evaluate(ctx(record)).status == GateStatus.PASS

    def test_low_impact_needs_no_forecast(self):
        record = make_record(ImpactTier.LOW)
        record.confidence = 0.6
        record.what_would_change_our_mind = ["new data"]
        assert CalibrationGate().evaluate(ctx(record)).status == GateStatus.PASS


class TestHumanApprovalGate:
    def test_low_tier_needs_no_approval(self):
        record = make_record(ImpactTier.LOW)
        assert HumanApprovalGate().evaluate(ctx(record)).status == GateStatus.PASS

    def test_high_tier_blocks_without_approval(self):
        record = make_record(ImpactTier.HIGH)
        result = HumanApprovalGate().evaluate(ctx(record))
        assert result.status == GateStatus.BLOCK
        assert not result.override_allowed  # never overridable

    def test_high_tier_passes_with_named_approver(self):
        record = make_record(ImpactTier.HIGH)
        record.approved_by = "liam"
        assert HumanApprovalGate().evaluate(ctx(record)).status == GateStatus.PASS
