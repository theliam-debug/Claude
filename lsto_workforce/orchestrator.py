"""
Workforce orchestrator: routes a decision through evidence gathering,
role assessments, dissent, gates, and approval — writing every step to the
hash-chained ledger and persisting the final record to disk.

The orchestrator is the governance harness. It does not call models itself;
agent sessions (or humans) act through it, and it enforces that no step can
be skipped, back-dated, or silently dropped.
"""

import json
from pathlib import Path
from typing import Optional
from lsto_workforce.charter import Charter, default_charter
from lsto_workforce.gates import Gate, GateContext, default_gates
from lsto_workforce.ledger import HashChainLedger
from lsto_workforce.models import (
    Assessment,
    DecisionRecord,
    DecisionStatus,
    Dissent,
    Evidence,
    Forecast,
    GateStatus,
    ImpactTier,
    Override,
    new_id,
    utc_now_iso,
)


class WorkforceError(Exception):
    """Raised when an action violates the workforce's operating rules."""


class Workforce:
    """
    The LsTo agent workforce operating around a shared charter, gate stack,
    and audit ledger.
    """

    def __init__(
        self,
        charter: Optional[Charter] = None,
        gates: Optional[list] = None,
        ledger_path: str = "out/workforce_ledger.jsonl",
        records_dir: str = "out/decisions",
    ):
        self.charter = charter or default_charter()
        self.gates: list[Gate] = gates if gates is not None else default_gates()
        self.ledger = HashChainLedger(ledger_path)
        self.records_dir = Path(records_dir)
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, DecisionRecord] = {}

    # -- lifecycle --------------------------------------------------------------

    def open_request(
        self,
        question: str,
        impact: ImpactTier,
        category: str,
        requested_by: str,
        as_of: str,
    ) -> DecisionRecord:
        """Open a decision request. requested_by must be a named human."""
        if not question.strip():
            raise WorkforceError("question must not be empty")
        if not requested_by.strip():
            raise WorkforceError(
                "requested_by must name the accountable human decision owner"
            )
        record = DecisionRecord(
            decision_id=new_id("dec"),
            question=question.strip(),
            impact=impact,
            category=category.strip().lower(),
            requested_by=requested_by.strip(),
            opened_at=utc_now_iso(),
            as_of=as_of,
            charter_hash=self.charter.charter_hash(),
        )
        self._records[record.decision_id] = record
        self.ledger.append(
            actor=record.requested_by,
            action="request_opened",
            decision_id=record.decision_id,
            payload={
                "question": record.question,
                "impact": record.impact.value,
                "category": record.category,
                "as_of": record.as_of,
                "charter_hash": record.charter_hash,
            },
        )
        return record

    def get(self, decision_id: str) -> DecisionRecord:
        record = self._records.get(decision_id)
        if record is None:
            record = self._load(decision_id)
        if record is None:
            raise WorkforceError(f"unknown decision '{decision_id}'")
        return record

    def _require_open(self, decision_id: str) -> DecisionRecord:
        """Terminal states (approved/blocked/withdrawn) accept no further edits.
        PENDING_APPROVAL stays editable because finalize() always re-runs the
        full gate stack, so nothing added late can dodge review."""
        record = self.get(decision_id)
        if record.status not in (
            DecisionStatus.OPEN,
            DecisionStatus.RECOMMENDED,
            DecisionStatus.PENDING_APPROVAL,
        ):
            raise WorkforceError(
                f"decision '{decision_id}' is {record.status.value}; no further edits allowed"
            )
        return record

    # -- contributions ----------------------------------------------------------

    def add_evidence(self, decision_id: str, evidence: Evidence) -> Evidence:
        """Attach evidence. The source must be registered in the charter."""
        record = self._require_open(decision_id)
        source = self.charter.source_by_name(evidence.source_name)
        if source is None:
            raise WorkforceError(
                f"source '{evidence.source_name}' is not registered in the charter; "
                "register it (with an honest tier) before citing it"
            )
        if source.tier != evidence.source_tier:
            raise WorkforceError(
                f"evidence tier '{evidence.source_tier.value}' does not match "
                f"registered tier '{source.tier.value}' for '{evidence.source_name}'"
            )
        record.evidence.append(evidence)
        self.ledger.append(
            actor=evidence.added_by.value,
            action="evidence_added",
            decision_id=decision_id,
            payload=evidence.to_dict(),
        )
        return evidence

    def add_assessment(self, decision_id: str, assessment: Assessment) -> Assessment:
        """File a role assessment. Evidence references must exist."""
        record = self._require_open(decision_id)
        if not (0.0 <= assessment.confidence <= 1.0):
            raise WorkforceError("assessment confidence must be within [0, 1]")
        known = {e.evidence_id for e in record.evidence}
        missing = [eid for eid in assessment.evidence_ids if eid not in known]
        if missing:
            raise WorkforceError(
                f"assessment cites unknown evidence ids: {missing}"
            )
        record.assessments.append(assessment)
        self.ledger.append(
            actor=assessment.role.value,
            action="assessment_added",
            decision_id=decision_id,
            payload=assessment.to_dict(),
        )
        return assessment

    def raise_dissent(self, decision_id: str, dissent: Dissent) -> Dissent:
        record = self._require_open(decision_id)
        record.dissents.append(dissent)
        self.ledger.append(
            actor=dissent.role.value,
            action="dissent_raised",
            decision_id=decision_id,
            payload=dissent.to_dict(),
        )
        return dissent

    def resolve_dissent(
        self, decision_id: str, dissent_id: str, resolution: str, resolved_by: str
    ) -> Dissent:
        """Resolve a dissent with a written response. Never deletes it."""
        record = self._require_open(decision_id)
        if not resolution.strip():
            raise WorkforceError("a dissent resolution must be a written response")
        for dissent in record.dissents:
            if dissent.dissent_id == dissent_id:
                dissent.resolution = resolution.strip()
                dissent.resolved_at = utc_now_iso()
                dissent.resolved_by = resolved_by
                self.ledger.append(
                    actor=resolved_by,
                    action="dissent_resolved",
                    decision_id=decision_id,
                    payload=dissent.to_dict(),
                )
                return dissent
        raise WorkforceError(f"unknown dissent '{dissent_id}'")

    def set_recommendation(
        self,
        decision_id: str,
        recommendation: str,
        confidence: float,
        alternatives_considered: Optional[list] = None,
        what_would_change_our_mind: Optional[list] = None,
        forecast: Optional[Forecast] = None,
    ) -> DecisionRecord:
        record = self._require_open(decision_id)
        if not recommendation.strip():
            raise WorkforceError("recommendation must not be empty")
        record.recommendation = recommendation.strip()
        record.confidence = confidence
        record.alternatives_considered = list(alternatives_considered or [])
        record.what_would_change_our_mind = list(what_would_change_our_mind or [])
        record.forecast = forecast
        record.status = DecisionStatus.RECOMMENDED
        self.ledger.append(
            actor="synthesizer",
            action="recommendation_set",
            decision_id=decision_id,
            payload={
                "recommendation": record.recommendation,
                "confidence": record.confidence,
                "alternatives_considered": record.alternatives_considered,
                "what_would_change_our_mind": record.what_would_change_our_mind,
                "forecast": forecast.to_dict() if forecast else None,
            },
        )
        return record

    def override_gate(
        self, decision_id: str, gate_name: str, reason: str, authorized_by: str
    ) -> Override:
        """
        Override a blocking gate. Requires the tier to allow overrides, the
        gate to be overridable, and a named human with a written reason.
        """
        record = self._require_open(decision_id)
        requirements = self.charter.requirements_for(record.impact)
        if not requirements.overrides_allowed:
            raise WorkforceError(
                f"tier '{record.impact.value}' does not allow gate overrides"
            )
        if not reason.strip() or not authorized_by.strip():
            raise WorkforceError("overrides require a written reason and a named human")
        gate = next((g for g in self.gates if g.name == gate_name), None)
        if gate is None:
            raise WorkforceError(f"unknown gate '{gate_name}'")
        if not gate.override_allowed:
            raise WorkforceError(f"gate '{gate_name}' can never be overridden")
        override = Override(
            gate_name=gate_name,
            reason=reason.strip(),
            authorized_by=authorized_by.strip(),
            at=utc_now_iso(),
        )
        record.overrides.append(override)
        self.ledger.append(
            actor=override.authorized_by,
            action="gate_overridden",
            decision_id=decision_id,
            payload=override.to_dict(),
        )
        return override

    # -- finalization -----------------------------------------------------------

    def run_gates(self, decision_id: str) -> list:
        """Evaluate the full gate stack and record results (idempotent)."""
        record = self.get(decision_id)
        context = GateContext(record=record, charter=self.charter)
        results = [gate.evaluate(context) for gate in self.gates]
        record.gate_results = results
        for result in results:
            self.ledger.append(
                actor="system",
                action="gate_result",
                decision_id=decision_id,
                payload=result.to_dict(),
            )
        return results

    def approve(self, decision_id: str, approved_by: str) -> DecisionRecord:
        """Record the named human approval (does not finalize by itself)."""
        record = self._require_open(decision_id)
        if not approved_by.strip():
            raise WorkforceError("approved_by must be a named human")
        record.approved_by = approved_by.strip()
        self.ledger.append(
            actor=record.approved_by,
            action="human_approved",
            decision_id=decision_id,
            payload={"approved_by": record.approved_by},
        )
        return record

    def finalize(self, decision_id: str) -> DecisionRecord:
        """
        Run gates and close the decision:
        - any unoverridden BLOCK -> BLOCKED
        - human approval required but absent -> PENDING_APPROVAL (re-finalize
          after approve())
        - otherwise -> APPROVED
        The record is persisted and its hash is anchored in the ledger.
        """
        record = self.get(decision_id)
        if record.status not in (DecisionStatus.RECOMMENDED,
                                 DecisionStatus.PENDING_APPROVAL):
            raise WorkforceError(
                "finalize requires a recommendation first "
                f"(status is '{record.status.value}')"
            )
        self.run_gates(decision_id)

        # HumanApprovalGate blocking solely for a not-yet-granted approval is
        # the PENDING_APPROVAL state, not a terminal block. Any other
        # unoverridden block is terminal.
        blocking = record.blocking_results()
        other_blocks = [g for g in blocking if g.gate_name != "HumanApprovalGate"]
        requirements = self.charter.requirements_for(record.impact)
        if other_blocks:
            record.status = DecisionStatus.BLOCKED
        elif requirements.human_approval_required and not record.approved_by:
            record.status = DecisionStatus.PENDING_APPROVAL
        else:
            record.status = DecisionStatus.APPROVED

        if record.status != DecisionStatus.PENDING_APPROVAL:
            record.finalized_at = utc_now_iso()

        self._persist(record)
        self.ledger.append(
            actor="system",
            action="finalized",
            decision_id=decision_id,
            payload={
                "status": record.status.value,
                "blocking_gates": [g.gate_name for g in blocking],
                "record_hash": record.record_hash(),
            },
        )
        return record

    def withdraw(self, decision_id: str, reason: str, by: str) -> DecisionRecord:
        """Close a decision without deciding. The record is kept, not deleted."""
        record = self._require_open(decision_id)
        record.status = DecisionStatus.WITHDRAWN
        record.finalized_at = utc_now_iso()
        self._persist(record)
        self.ledger.append(
            actor=by,
            action="withdrawn",
            decision_id=decision_id,
            payload={"reason": reason, "record_hash": record.record_hash()},
        )
        return record

    # -- persistence ------------------------------------------------------------

    def _persist(self, record: DecisionRecord) -> Path:
        path = self.records_dir / f"{record.decision_id}.json"
        with open(path, "w") as f:
            json.dump(record.to_dict(), f, indent=2, sort_keys=True)
        return path

    def _load(self, decision_id: str) -> Optional[DecisionRecord]:
        path = self.records_dir / f"{decision_id}.json"
        if not path.exists():
            return None
        with open(path, "r") as f:
            record = DecisionRecord.from_dict(json.load(f))
        self._records[decision_id] = record
        return record

    def load_all_records(self) -> list:
        """Load every persisted decision record (for metrics/audit)."""
        records = []
        for path in sorted(self.records_dir.glob("dec-*.json")):
            with open(path, "r") as f:
                records.append(DecisionRecord.from_dict(json.load(f)))
        return records
