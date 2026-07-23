"""
Accountability gates for workforce decisions.

Same pattern as derivatives_strategies policy gates: each gate evaluates one
standard and returns PASS / WARN / BLOCK. Hard gates block finalization
unless overridden by a named human (where the tier allows overrides at all).

These gates enforce process integrity — they do not adjudicate substance.
The EthicsGate in particular is a screen that routes decisions to human
ethics review; it never certifies a decision as "ethical".
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from lsto_workforce.charter import Charter, TierRequirements
from lsto_workforce.models import (
    DecisionRecord,
    DissentSeverity,
    GateResult,
    GateStatus,
    RoleType,
    SourceTier,
)


@dataclass
class GateContext:
    """Everything a gate needs to evaluate a decision record."""
    record: DecisionRecord
    charter: Charter

    @property
    def requirements(self) -> TierRequirements:
        return self.charter.requirements_for(self.record.impact)


class Gate(ABC):
    """Abstract base class for accountability gates."""

    def __init__(self, name: str, hard: bool = True, override_allowed: bool = True):
        self.name = name
        self.hard = hard
        self.override_allowed = override_allowed

    @abstractmethod
    def evaluate(self, context: GateContext) -> GateResult:
        """Evaluate the gate against a decision record."""

    def _make_result(
        self,
        passed: bool,
        message: str,
        details: Optional[dict] = None,
        override_allowed: Optional[bool] = None,
    ) -> GateResult:
        if passed:
            status = GateStatus.PASS
        elif self.hard:
            status = GateStatus.BLOCK
        else:
            status = GateStatus.WARN
        return GateResult(
            gate_name=self.name,
            status=status,
            message=message,
            details=details or {},
            override_allowed=(
                self.override_allowed if override_allowed is None else override_allowed
            ),
        )


class ProvenanceGate(Gate):
    """
    Every evidence item must cite a registered source and carry retrieval
    metadata. Unsourced claims are the root failure mode of an agent
    workforce — this gate is always hard.
    """

    def __init__(self):
        super().__init__(name="ProvenanceGate", hard=True)

    def evaluate(self, context: GateContext) -> GateResult:
        problems = []
        for ev in context.record.evidence:
            if context.charter.source_by_name(ev.source_name) is None:
                problems.append(f"{ev.evidence_id}: unregistered source '{ev.source_name}'")
            if not ev.retrieved_at:
                problems.append(f"{ev.evidence_id}: missing retrieved_at")
            if not ev.as_of:
                problems.append(f"{ev.evidence_id}: missing as_of date")
        if problems:
            return self._make_result(
                False,
                f"{len(problems)} evidence item(s) fail provenance checks",
                details={"problems": problems},
            )
        return self._make_result(
            True, f"All {len(context.record.evidence)} evidence items have valid provenance"
        )


class EvidenceSufficiencyGate(Gate):
    """
    The decision must rest on enough evidence, with enough of it from
    PRIMARY or INTERNAL sources, per the impact tier's requirements.
    MODEL_ESTIMATE items never count toward the primary/internal quota.
    """

    def __init__(self):
        super().__init__(name="EvidenceSufficiencyGate", hard=True)

    def evaluate(self, context: GateContext) -> GateResult:
        req = context.requirements
        evidence = context.record.evidence
        strong = [
            e for e in evidence
            if e.source_tier in (SourceTier.PRIMARY, SourceTier.INTERNAL)
        ]
        details = {
            "evidence_count": len(evidence),
            "min_evidence": req.min_evidence,
            "primary_or_internal_count": len(strong),
            "min_primary_or_internal": req.min_primary_or_internal,
        }
        if len(evidence) < req.min_evidence:
            return self._make_result(
                False,
                f"Only {len(evidence)} evidence item(s); tier '{req.tier.value}' requires {req.min_evidence}",
                details=details,
            )
        if len(strong) < req.min_primary_or_internal:
            return self._make_result(
                False,
                f"Only {len(strong)} primary/internal item(s); tier '{req.tier.value}' requires {req.min_primary_or_internal}",
                details=details,
            )
        return self._make_result(True, "Evidence base meets tier requirements", details=details)


class FreshnessGate(Gate):
    """
    Evidence must be recent enough for the tier. Stale data warns on LOW /
    MEDIUM tiers and blocks on HIGH / CRITICAL via tier config — implemented
    here as hard, since the tier's max age already scales with stakes.
    """

    def __init__(self):
        super().__init__(name="FreshnessGate", hard=True)

    def evaluate(self, context: GateContext) -> GateResult:
        req = context.requirements
        as_of = context.record.as_of
        stale = []
        for ev in context.record.evidence:
            try:
                age = ev.age_days(as_of)
            except ValueError:
                stale.append(f"{ev.evidence_id}: unparseable as_of '{ev.as_of}'")
                continue
            if age > req.max_evidence_age_days:
                stale.append(
                    f"{ev.evidence_id}: {age}d old (max {req.max_evidence_age_days}d)"
                )
        if stale:
            return self._make_result(
                False,
                f"{len(stale)} evidence item(s) too stale for tier '{req.tier.value}'",
                details={"stale": stale},
            )
        return self._make_result(True, "All evidence within freshness window")


class RoleCoverageGate(Gate):
    """All roles required by the impact tier must have filed an assessment."""

    def __init__(self):
        super().__init__(name="RoleCoverageGate", hard=True)

    def evaluate(self, context: GateContext) -> GateResult:
        req = context.requirements
        present = context.record.roles_present()
        required = set(req.required_roles)
        if req.ethics_review_required or (
            context.record.category.lower() in
            {c.lower() for c in context.charter.sensitive_categories}
        ):
            required.add(RoleType.ETHICS_REVIEWER)
        missing = required - present
        if missing:
            return self._make_result(
                False,
                f"Missing required role assessment(s): {sorted(r.value for r in missing)}",
                details={
                    "required": sorted(r.value for r in required),
                    "present": sorted(r.value for r in present),
                },
            )
        return self._make_result(True, "All required roles have filed assessments")


class RedTeamGate(Gate):
    """
    High-stakes decisions require an adversarial review, and MATERIAL/FATAL
    dissents must carry a written resolution before finalization.
    """

    def __init__(self):
        super().__init__(name="RedTeamGate", hard=True)

    def evaluate(self, context: GateContext) -> GateResult:
        req = context.requirements
        record = context.record
        if req.red_team_required and RoleType.RED_TEAM not in record.roles_present():
            return self._make_result(
                False, f"Tier '{req.tier.value}' requires a red-team assessment"
            )
        unresolved = [
            d for d in record.unresolved_dissents()
            if d.severity in (DissentSeverity.MATERIAL, DissentSeverity.FATAL)
        ]
        if unresolved:
            return self._make_result(
                False,
                f"{len(unresolved)} material/fatal dissent(s) lack a written resolution",
                details={"unresolved": [d.dissent_id for d in unresolved]},
                # A fatal dissent cannot be overridden away — it must be resolved.
                override_allowed=not any(
                    d.severity == DissentSeverity.FATAL for d in unresolved
                ),
            )
        return self._make_result(True, "Adversarial review complete; dissents resolved")


class EthicsGate(Gate):
    """
    Screen — not verdict. Blocks outright on prohibited request content
    (no override), and requires an ethics-reviewer assessment for sensitive
    categories or when the tier demands it.
    """

    def __init__(self):
        super().__init__(name="EthicsGate", hard=True)

    def evaluate(self, context: GateContext) -> GateResult:
        record = context.record
        text = " ".join([
            record.question.lower(),
            record.recommendation.lower(),
        ])
        hits = [t for t in context.charter.prohibited_terms if t.lower() in text]
        if hits:
            return self._make_result(
                False,
                f"Prohibited content detected: {hits}",
                details={"prohibited_terms": hits},
                override_allowed=False,
            )
        sensitive = record.category.lower() in {
            c.lower() for c in context.charter.sensitive_categories
        }
        needs_review = sensitive or context.requirements.ethics_review_required
        if needs_review and RoleType.ETHICS_REVIEWER not in record.roles_present():
            reason = "sensitive category" if sensitive else "impact tier"
            return self._make_result(
                False,
                f"Ethics review required ({reason}: '{record.category or record.impact.value}') "
                "but no ethics_reviewer assessment filed",
            )
        return self._make_result(
            True,
            "No prohibited content; ethics review present where required",
            details={"sensitive_category": sensitive},
        )


class ConflictOfInterestGate(Gate):
    """Declared conflicts warn always and block at HIGH/CRITICAL impact."""

    def __init__(self):
        super().__init__(name="ConflictOfInterestGate", hard=True)

    def evaluate(self, context: GateContext) -> GateResult:
        conflicts = {
            a.role.value: list(a.declared_conflicts)
            for a in context.record.assessments
            if a.declared_conflicts
        }
        if not conflicts:
            return self._make_result(True, "No conflicts of interest declared")
        high_stakes = context.requirements.human_approval_required
        if high_stakes:
            return self._make_result(
                False,
                "Declared conflicts require the decision owner to reassign or "
                "explicitly accept them via override",
                details={"conflicts": conflicts},
            )
        return GateResult(
            gate_name=self.name,
            status=GateStatus.WARN,
            message="Conflicts declared; acceptable at this impact tier but recorded",
            details={"conflicts": conflicts},
            override_allowed=self.override_allowed,
        )


class CalibrationGate(Gate):
    """
    Recommendations must state a usable confidence. HIGH/CRITICAL decisions
    must attach a falsifiable forecast so calibration can be scored later.
    Soft gate: it warns rather than blocks, but the warning is permanent
    in the record.
    """

    def __init__(self):
        super().__init__(name="CalibrationGate", hard=False)

    def evaluate(self, context: GateContext) -> GateResult:
        record = context.record
        problems = []
        if record.confidence is None:
            problems.append("no confidence stated")
        elif not (0.0 <= record.confidence <= 1.0):
            problems.append(f"confidence {record.confidence} outside [0, 1]")
        elif record.confidence > 0.95 and record.impact.rank >= 2:
            problems.append(
                f"confidence {record.confidence:.2f} above 0.95 on a "
                f"{record.impact.value}-impact decision — justify or temper"
            )
        if record.impact.rank >= 2:
            if record.forecast is None:
                problems.append("no falsifiable forecast attached (required habit at HIGH/CRITICAL)")
            elif not record.forecast.resolve_by:
                problems.append("forecast has no resolve_by date")
        if not record.what_would_change_our_mind:
            problems.append("no 'what would change our mind' conditions listed")
        if problems:
            return self._make_result(
                False, "; ".join(problems), details={"problems": problems}
            )
        return self._make_result(True, "Confidence stated and forecast attached where required")


class HumanApprovalGate(Gate):
    """
    Decision rights: tiers configured to require human approval cannot
    finalize as APPROVED without a named approver. Never overridable —
    removing the human from the loop is not a gate override, it is a
    charter change.
    """

    def __init__(self):
        super().__init__(name="HumanApprovalGate", hard=True, override_allowed=False)

    def evaluate(self, context: GateContext) -> GateResult:
        req = context.requirements
        record = context.record
        if not req.human_approval_required:
            return self._make_result(True, "Human approval not required at this tier")
        if record.approved_by:
            return self._make_result(
                True, f"Approved by named human: {record.approved_by}"
            )
        return self._make_result(
            False,
            f"Tier '{req.tier.value}' requires a named human approver before finalization",
        )


def default_gates() -> list:
    """The standard gate stack, in evaluation order."""
    return [
        ProvenanceGate(),
        EvidenceSufficiencyGate(),
        FreshnessGate(),
        RoleCoverageGate(),
        RedTeamGate(),
        EthicsGate(),
        ConflictOfInterestGate(),
        CalibrationGate(),
        HumanApprovalGate(),
    ]
