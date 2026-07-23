"""
Workforce scorecard: process and calibration metrics computed from decision
records and the audit ledger. Accountability is measurable or it is theater.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from lsto_workforce.models import (
    DecisionRecord,
    DecisionStatus,
    GateStatus,
    SourceTier,
)


@dataclass
class Scorecard:
    """Aggregate workforce performance metrics."""
    decisions_total: int = 0
    by_status: dict = field(default_factory=dict)
    by_impact: dict = field(default_factory=dict)
    gate_pass: int = 0
    gate_warn: int = 0
    gate_block: int = 0
    overrides: int = 0
    avg_evidence_per_decision: float = 0.0
    primary_or_internal_share: float = 0.0
    model_estimate_share: float = 0.0
    dissents_total: int = 0
    dissents_resolved: int = 0
    forecasts_total: int = 0
    forecasts_resolved: int = 0
    brier_score: Optional[float] = None      # lower is better; 0.25 = coin flip
    avg_confidence: Optional[float] = None
    hit_rate: Optional[float] = None         # share of resolved forecasts correct

    def to_dict(self) -> dict:
        return {
            "decisions_total": self.decisions_total,
            "by_status": dict(self.by_status),
            "by_impact": dict(self.by_impact),
            "gates": {
                "pass": self.gate_pass,
                "warn": self.gate_warn,
                "block": self.gate_block,
                "overrides": self.overrides,
            },
            "evidence": {
                "avg_per_decision": round(self.avg_evidence_per_decision, 2),
                "primary_or_internal_share": round(self.primary_or_internal_share, 4),
                "model_estimate_share": round(self.model_estimate_share, 4),
            },
            "dissent": {
                "total": self.dissents_total,
                "resolved": self.dissents_resolved,
            },
            "calibration": {
                "forecasts_total": self.forecasts_total,
                "forecasts_resolved": self.forecasts_resolved,
                "brier_score": (
                    round(self.brier_score, 4) if self.brier_score is not None else None
                ),
                "hit_rate": (
                    round(self.hit_rate, 4) if self.hit_rate is not None else None
                ),
                "avg_confidence": (
                    round(self.avg_confidence, 4) if self.avg_confidence is not None else None
                ),
            },
        }


def brier_score(forecasts: list) -> Optional[float]:
    """
    Mean squared error of probability vs outcome over resolved forecasts.
    0.0 is perfect, 0.25 matches always saying 50%, 1.0 is perfectly wrong.
    """
    resolved = [f for f in forecasts if f.resolved is not None]
    if not resolved:
        return None
    total = 0.0
    for f in resolved:
        outcome = 1.0 if f.resolved else 0.0
        total += (f.probability - outcome) ** 2
    return total / len(resolved)


def compute_scorecard(records: list) -> Scorecard:
    """Compute the scorecard over a set of DecisionRecords."""
    card = Scorecard()
    card.decisions_total = len(records)

    evidence_total = 0
    strong_total = 0
    estimate_total = 0
    confidences = []
    forecasts = []

    for record in records:
        card.by_status[record.status.value] = (
            card.by_status.get(record.status.value, 0) + 1
        )
        card.by_impact[record.impact.value] = (
            card.by_impact.get(record.impact.value, 0) + 1
        )
        evidence_total += len(record.evidence)
        for ev in record.evidence:
            if ev.source_tier in (SourceTier.PRIMARY, SourceTier.INTERNAL):
                strong_total += 1
            elif ev.source_tier == SourceTier.MODEL_ESTIMATE:
                estimate_total += 1
        for g in record.gate_results:
            if g.status == GateStatus.PASS:
                card.gate_pass += 1
            elif g.status == GateStatus.WARN:
                card.gate_warn += 1
            else:
                card.gate_block += 1
        card.overrides += len(record.overrides)
        card.dissents_total += len(record.dissents)
        card.dissents_resolved += sum(1 for d in record.dissents if d.resolved)
        if record.confidence is not None:
            confidences.append(record.confidence)
        if record.forecast is not None:
            forecasts.append(record.forecast)

    if records:
        card.avg_evidence_per_decision = evidence_total / len(records)
    if evidence_total:
        card.primary_or_internal_share = strong_total / evidence_total
        card.model_estimate_share = estimate_total / evidence_total
    if confidences:
        card.avg_confidence = sum(confidences) / len(confidences)

    card.forecasts_total = len(forecasts)
    resolved = [f for f in forecasts if f.resolved is not None]
    card.forecasts_resolved = len(resolved)
    card.brier_score = brier_score(forecasts)
    if resolved:
        correct = sum(
            1 for f in resolved
            if (f.probability >= 0.5) == bool(f.resolved)
        )
        card.hit_rate = correct / len(resolved)

    return card


def render_scorecard(card: Scorecard) -> str:
    """Render the scorecard as markdown."""
    lines = []
    add = lines.append
    add("# LsTo Workforce Scorecard")
    add("")
    add(f"**Decisions:** {card.decisions_total}")
    if card.by_status:
        add("")
        add("| Status | Count |")
        add("|---|---|")
        for status, count in sorted(card.by_status.items()):
            add(f"| {status} | {count} |")
    add("")
    add("## Process integrity")
    add("")
    add(f"- Gate results: {card.gate_pass} pass / {card.gate_warn} warn / "
        f"{card.gate_block} block; {card.overrides} override(s)")
    add(f"- Evidence per decision: {card.avg_evidence_per_decision:.1f} avg; "
        f"{card.primary_or_internal_share:.0%} primary/internal; "
        f"{card.model_estimate_share:.0%} model estimates")
    add(f"- Dissents: {card.dissents_total} raised, {card.dissents_resolved} resolved")
    add("")
    add("## Calibration")
    add("")
    if card.brier_score is not None:
        add(f"- Brier score over {card.forecasts_resolved} resolved forecast(s): "
            f"**{card.brier_score:.3f}** (0 = perfect, 0.25 = coin flip)")
        add(f"- Hit rate: {card.hit_rate:.0%}")
    else:
        add(f"- {card.forecasts_total} forecast(s) attached, none resolved yet — "
            "resolve forecasts as their judge-by dates pass to build a track record")
    if card.avg_confidence is not None:
        add(f"- Average stated confidence: {card.avg_confidence:.0%}")
    add("")
    return "\n".join(lines)
