"""Tests for the workforce orchestrator: workflow enforcement end to end."""

import pytest

from lsto_workforce.charter import default_charter
from lsto_workforce.models import (
    Assessment,
    DecisionRecord,
    DecisionStatus,
    Dissent,
    DissentSeverity,
    Evidence,
    Forecast,
    ImpactTier,
    RoleType,
    SourceTier,
)
from lsto_workforce.orchestrator import Workforce, WorkforceError

AS_OF = "2026-07-23"


@pytest.fixture
def workforce(tmp_path):
    return Workforce(
        ledger_path=str(tmp_path / "ledger.jsonl"),
        records_dir=str(tmp_path / "decisions"),
    )


def open_low(workforce, **kwargs) -> str:
    defaults = dict(
        question="Proceed?", impact=ImpactTier.LOW, category="general",
        requested_by="liam", as_of=AS_OF,
    )
    defaults.update(kwargs)
    return workforce.open_request(**defaults).decision_id


def add_min_low_content(workforce, decision_id):
    ev = workforce.add_evidence(decision_id, Evidence.create(
        claim="rate is 5.25%", source_name="US Treasury",
        source_tier=SourceTier.PRIMARY, as_of="2026-07-22",
    ))
    workforce.add_assessment(decision_id, Assessment.create(
        RoleType.RESEARCH_ANALYST, "looks fine", 0.6, [ev.evidence_id],
    ))
    workforce.set_recommendation(
        decision_id, "Proceed.", 0.6,
        what_would_change_our_mind=["contrary data"],
    )


class TestRequestValidation:
    def test_empty_question_rejected(self, workforce):
        with pytest.raises(WorkforceError, match="question"):
            workforce.open_request("  ", ImpactTier.LOW, "g", "liam", AS_OF)

    def test_unnamed_owner_rejected(self, workforce):
        with pytest.raises(WorkforceError, match="accountable human"):
            workforce.open_request("Q?", ImpactTier.LOW, "g", "", AS_OF)

    def test_charter_hash_stamped(self, workforce):
        decision_id = open_low(workforce)
        record = workforce.get(decision_id)
        assert record.charter_hash == default_charter().charter_hash()


class TestEvidenceRules:
    def test_unregistered_source_rejected(self, workforce):
        decision_id = open_low(workforce)
        with pytest.raises(WorkforceError, match="not registered"):
            workforce.add_evidence(decision_id, Evidence.create(
                claim="c", source_name="random blog",
                source_tier=SourceTier.PRIMARY, as_of=AS_OF,
            ))

    def test_tier_mismatch_rejected(self, workforce):
        # Cannot launder a secondary source as primary.
        decision_id = open_low(workforce)
        with pytest.raises(WorkforceError, match="does not match registered tier"):
            workforce.add_evidence(decision_id, Evidence.create(
                claim="c", source_name="FMP",
                source_tier=SourceTier.PRIMARY, as_of=AS_OF,
            ))

    def test_assessment_citing_unknown_evidence_rejected(self, workforce):
        decision_id = open_low(workforce)
        with pytest.raises(WorkforceError, match="unknown evidence"):
            workforce.add_assessment(decision_id, Assessment.create(
                RoleType.RESEARCH_ANALYST, "s", 0.5, ["ev-nonexistent"],
            ))

    def test_confidence_out_of_range_rejected(self, workforce):
        decision_id = open_low(workforce)
        with pytest.raises(WorkforceError, match="confidence"):
            workforce.add_assessment(decision_id, Assessment.create(
                RoleType.RESEARCH_ANALYST, "s", 1.5,
            ))


class TestLowTierFlow:
    def test_low_tier_approves_without_human(self, workforce):
        decision_id = open_low(workforce)
        add_min_low_content(workforce, decision_id)
        record = workforce.finalize(decision_id)
        assert record.status == DecisionStatus.APPROVED
        assert record.finalized_at

    def test_finalize_without_recommendation_rejected(self, workforce):
        decision_id = open_low(workforce)
        with pytest.raises(WorkforceError, match="recommendation"):
            workforce.finalize(decision_id)

    def test_terminal_record_rejects_edits(self, workforce):
        decision_id = open_low(workforce)
        add_min_low_content(workforce, decision_id)
        workforce.finalize(decision_id)
        with pytest.raises(WorkforceError, match="no further edits"):
            workforce.set_recommendation(decision_id, "Change it.", 0.9)


class TestHighTierFlow:
    def _build_high(self, workforce) -> str:
        decision_id = workforce.open_request(
            "Big move?", ImpactTier.HIGH, "portfolio", "liam", AS_OF,
        ).decision_id
        evidence_ids = []
        for source, tier in [
            ("US Treasury", SourceTier.PRIMARY),
            ("SEC EDGAR", SourceTier.PRIMARY),
            ("derivatives_strategies", SourceTier.INTERNAL),
        ]:
            ev = workforce.add_evidence(decision_id, Evidence.create(
                claim=f"claim from {source}", source_name=source,
                source_tier=tier, as_of="2026-07-20",
            ))
            evidence_ids.append(ev.evidence_id)
        for role in [
            RoleType.RESEARCH_ANALYST, RoleType.DATA_STEWARD,
            RoleType.RISK_OFFICER, RoleType.ETHICS_REVIEWER,
            RoleType.RED_TEAM, RoleType.SYNTHESIZER,
        ]:
            workforce.add_assessment(decision_id, Assessment.create(
                role, f"{role.value} view", 0.7, [evidence_ids[0]],
            ))
        workforce.set_recommendation(
            decision_id, "Do the move.", 0.7,
            alternatives_considered=["do nothing"],
            what_would_change_our_mind=["contrary data"],
            forecast=Forecast("it works out", 0.7, "2026-09-01"),
        )
        return decision_id

    def test_pending_until_named_human_approves(self, workforce):
        decision_id = self._build_high(workforce)
        record = workforce.finalize(decision_id)
        assert record.status == DecisionStatus.PENDING_APPROVAL
        assert not record.finalized_at

        workforce.approve(decision_id, "liam")
        record = workforce.finalize(decision_id)
        assert record.status == DecisionStatus.APPROVED
        assert record.approved_by == "liam"

    def test_missing_red_team_blocks(self, workforce):
        decision_id = workforce.open_request(
            "Big move?", ImpactTier.HIGH, "portfolio", "liam", AS_OF,
        ).decision_id
        for source, tier in [
            ("US Treasury", SourceTier.PRIMARY),
            ("SEC EDGAR", SourceTier.PRIMARY),
            ("derivatives_strategies", SourceTier.INTERNAL),
        ]:
            workforce.add_evidence(decision_id, Evidence.create(
                claim="c", source_name=source, source_tier=tier, as_of="2026-07-20",
            ))
        for role in [
            RoleType.RESEARCH_ANALYST, RoleType.DATA_STEWARD,
            RoleType.RISK_OFFICER, RoleType.ETHICS_REVIEWER, RoleType.SYNTHESIZER,
        ]:
            workforce.add_assessment(
                decision_id, Assessment.create(role, "view", 0.7)
            )
        workforce.set_recommendation(
            decision_id, "Do it.", 0.7,
            what_would_change_our_mind=["x"],
            forecast=Forecast("ok", 0.7, "2026-09-01"),
        )
        record = workforce.finalize(decision_id)
        assert record.status == DecisionStatus.BLOCKED
        blocked_gates = {g.gate_name for g in record.blocking_results()}
        assert "RoleCoverageGate" in blocked_gates
        assert "RedTeamGate" in blocked_gates

    def test_unresolved_material_dissent_blocks_then_resolution_unblocks(self, workforce):
        decision_id = self._build_high(workforce)
        dissent = workforce.raise_dissent(decision_id, Dissent.create(
            RoleType.RED_TEAM, "too risky", DissentSeverity.MATERIAL,
        ))
        workforce.approve(decision_id, "liam")
        record = workforce.finalize(decision_id)
        assert record.status == DecisionStatus.BLOCKED

        # Blocked is terminal — a new request is the retry path.
        with pytest.raises(WorkforceError, match="no further edits"):
            workforce.resolve_dissent(decision_id, dissent.dissent_id, "fixed", "liam")

        retry_id = self._build_high(workforce)
        dissent2 = workforce.raise_dissent(retry_id, Dissent.create(
            RoleType.RED_TEAM, "too risky", DissentSeverity.MATERIAL,
        ))
        workforce.resolve_dissent(
            retry_id, dissent2.dissent_id, "hedged the tail", "liam"
        )
        workforce.approve(retry_id, "liam")
        assert workforce.finalize(retry_id).status == DecisionStatus.APPROVED


class TestOverrides:
    def test_override_lets_medium_tier_past_soft_deficit(self, workforce, tmp_path):
        decision_id = workforce.open_request(
            "Medium?", ImpactTier.MEDIUM, "general", "liam", AS_OF,
        ).decision_id
        # Only one evidence item (tier needs 2) -> EvidenceSufficiencyGate blocks.
        ev = workforce.add_evidence(decision_id, Evidence.create(
            claim="c", source_name="US Treasury",
            source_tier=SourceTier.PRIMARY, as_of="2026-07-22",
        ))
        for role in (RoleType.RESEARCH_ANALYST, RoleType.RISK_OFFICER):
            workforce.add_assessment(decision_id, Assessment.create(
                role, "view", 0.6, [ev.evidence_id],
            ))
        workforce.set_recommendation(
            decision_id, "Proceed.", 0.6, what_would_change_our_mind=["x"],
        )
        assert workforce.finalize(decision_id).status == DecisionStatus.BLOCKED

        retry_id = workforce.open_request(
            "Medium retry?", ImpactTier.MEDIUM, "general", "liam", AS_OF,
        ).decision_id
        ev2 = workforce.add_evidence(retry_id, Evidence.create(
            claim="c", source_name="US Treasury",
            source_tier=SourceTier.PRIMARY, as_of="2026-07-22",
        ))
        for role in (RoleType.RESEARCH_ANALYST, RoleType.RISK_OFFICER):
            workforce.add_assessment(retry_id, Assessment.create(
                role, "view", 0.6, [ev2.evidence_id],
            ))
        workforce.set_recommendation(
            retry_id, "Proceed.", 0.6, what_would_change_our_mind=["x"],
        )
        workforce.override_gate(
            retry_id, "EvidenceSufficiencyGate",
            reason="time-critical; second source arrives tomorrow",
            authorized_by="liam",
        )
        record = workforce.finalize(retry_id)
        assert record.status == DecisionStatus.APPROVED
        assert record.overrides[0].authorized_by == "liam"

    def test_critical_tier_rejects_all_overrides(self, workforce):
        decision_id = workforce.open_request(
            "Irreversible?", ImpactTier.CRITICAL, "general", "liam", AS_OF,
        ).decision_id
        with pytest.raises(WorkforceError, match="does not allow gate overrides"):
            workforce.override_gate(decision_id, "FreshnessGate", "hurry", "liam")

    def test_override_requires_named_human_and_reason(self, workforce):
        decision_id = open_low(workforce)
        with pytest.raises(WorkforceError, match="written reason and a named human"):
            workforce.override_gate(decision_id, "FreshnessGate", "", "liam")
        with pytest.raises(WorkforceError, match="written reason and a named human"):
            workforce.override_gate(decision_id, "FreshnessGate", "reason", " ")

    def test_never_overridable_gate_rejected(self, workforce):
        decision_id = open_low(workforce)
        with pytest.raises(WorkforceError, match="can never be overridden"):
            workforce.override_gate(
                decision_id, "HumanApprovalGate", "skip the human", "liam"
            )


class TestPersistenceAndAudit:
    def test_record_roundtrip(self, workforce):
        decision_id = open_low(workforce)
        add_min_low_content(workforce, decision_id)
        record = workforce.finalize(decision_id)
        loaded = DecisionRecord.from_dict(record.to_dict())
        assert loaded.to_dict() == record.to_dict()
        assert loaded.record_hash() == record.record_hash()

    def test_every_step_ledgered_and_chain_valid(self, workforce):
        decision_id = open_low(workforce)
        add_min_low_content(workforce, decision_id)
        workforce.finalize(decision_id)
        actions = [e["action"] for e in workforce.ledger.read_by_decision(decision_id)]
        for expected in [
            "request_opened", "evidence_added", "assessment_added",
            "recommendation_set", "gate_result", "finalized",
        ]:
            assert expected in actions, f"missing ledger action {expected}"
        assert workforce.ledger.verify().valid

    def test_withdraw_persists_and_locks(self, workforce):
        decision_id = open_low(workforce)
        record = workforce.withdraw(decision_id, "superseded", "liam")
        assert record.status == DecisionStatus.WITHDRAWN
        with pytest.raises(WorkforceError, match="no further edits"):
            workforce.set_recommendation(decision_id, "r", 0.5)

    def test_load_all_records(self, workforce):
        for _ in range(2):
            decision_id = open_low(workforce)
            add_min_low_content(workforce, decision_id)
            workforce.finalize(decision_id)
        assert len(workforce.load_all_records()) == 2
