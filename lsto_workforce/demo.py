"""
End-to-end demo: one HIGH-impact decision moved through the full workforce
process — evidence, role assessments, dissent, gates, human approval,
brief, ledger verification, and scorecard.

The demo is deterministic and offline (house rule: no network calls).
Evidence entries are samples that show the required provenance shape; in
live operation they come from the registered MCP data sources.
"""

from pathlib import Path

from lsto_workforce.brief import render_brief
from lsto_workforce.charter import Charter, default_charter
from lsto_workforce.metrics import compute_scorecard, render_scorecard
from lsto_workforce.models import (
    Assessment,
    Dissent,
    DissentSeverity,
    Evidence,
    Forecast,
    ImpactTier,
    RoleType,
    SourceTier,
)
from lsto_workforce.orchestrator import Workforce

DEMO_AS_OF = "2026-07-23"
DEMO_OWNER = "liam"


def run_demo(out_dir: str = "./out/workforce", charter: Charter = None) -> dict:
    """Run the demo decision. Returns a dict of output paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    workforce = Workforce(
        charter=charter or default_charter(),
        ledger_path=str(out / "workforce_ledger.jsonl"),
        records_dir=str(out / "decisions"),
    )

    record = workforce.open_request(
        question=(
            "Should we continue the covered-call overlay on the equity book "
            "for the August cycle?"
        ),
        impact=ImpactTier.HIGH,
        category="portfolio",
        requested_by=DEMO_OWNER,
        as_of=DEMO_AS_OF,
    )
    decision_id = record.decision_id

    # -- evidence (provenance-complete samples) --------------------------------
    ev_engine = workforce.add_evidence(decision_id, Evidence.create(
        claim=(
            "Latest derivatives_strategies run approved 2 of 3 roll candidates; "
            "1 blocked by DividendGate (early-assignment risk)."
        ),
        source_name="derivatives_strategies",
        source_tier=SourceTier.INTERNAL,
        as_of=DEMO_AS_OF,
        ref="out/run.json",
        method="analytics_run",
        raw_payload={"approved": 2, "blocked": 1, "blocking_gate": "DividendGate"},
        added_by=RoleType.RESEARCH_ANALYST,
    ))
    ev_rates = workforce.add_evidence(decision_id, Evidence.create(
        claim="3-month Treasury bill rate is 5.25% (sample figure for demo).",
        source_name="US Treasury",
        source_tier=SourceTier.PRIMARY,
        as_of="2026-07-22",
        ref="treasury_rates:DTB3",
        method="api",
        raw_payload={"series": "DTB3", "value": 5.25},
        added_by=RoleType.RESEARCH_ANALYST,
    ))
    ev_vol = workforce.add_evidence(decision_id, Evidence.create(
        claim="30-day implied volatility on the book's largest holding is in its 40th percentile of the trailing year (sample figure for demo).",
        source_name="FMP",
        source_tier=SourceTier.SECONDARY,
        as_of="2026-07-22",
        ref="fmp:iv_percentile",
        method="api",
        raw_payload={"iv_rank": 0.40},
        added_by=RoleType.RESEARCH_ANALYST,
    ))
    ev_earnings = workforce.add_evidence(decision_id, Evidence.create(
        claim="Next earnings date for the largest holding falls inside the proposed option tenor (sample: 2026-08-06).",
        source_name="SEC EDGAR",
        source_tier=SourceTier.PRIMARY,
        as_of="2026-07-21",
        ref="edgar:8-K-calendar",
        method="api",
        raw_payload={"earnings_date": "2026-08-06"},
        added_by=RoleType.DATA_STEWARD,
    ))

    # -- role assessments -------------------------------------------------------
    workforce.add_assessment(decision_id, Assessment.create(
        role=RoleType.RESEARCH_ANALYST,
        summary=(
            "Premium capture remains attractive on two of three positions; "
            "engine economics are positive net of modeled costs."
        ),
        confidence=0.72,
        evidence_ids=[ev_engine.evidence_id, ev_rates.evidence_id, ev_vol.evidence_id],
    ))
    workforce.add_assessment(decision_id, Assessment.create(
        role=RoleType.DATA_STEWARD,
        summary=(
            "All evidence is sourced, hashed, and within the 90-day freshness "
            "window; IV percentile is a secondary-source figure — treat as "
            "corroborating, not decisive."
        ),
        confidence=0.9,
        evidence_ids=[ev_earnings.evidence_id],
    ))
    workforce.add_assessment(decision_id, Assessment.create(
        role=RoleType.RISK_OFFICER,
        summary=(
            "Overlay caps upside through earnings; assignment risk on the "
            "dividend name is real but the engine already blocks that roll. "
            "Downside of continuing is bounded and reversible within one cycle."
        ),
        confidence=0.68,
        evidence_ids=[ev_engine.evidence_id, ev_earnings.evidence_id],
    ))
    workforce.add_assessment(decision_id, Assessment.create(
        role=RoleType.ETHICS_REVIEWER,
        summary=(
            "No ethics or compliance concerns: proprietary book, no client "
            "assets, no sensitive category. Standard market conduct applies."
        ),
        confidence=0.95,
    ))
    workforce.add_assessment(decision_id, Assessment.create(
        role=RoleType.SYNTHESIZER,
        summary=(
            "Continue the overlay on the two approved names; skip the "
            "dividend-blocked roll this cycle and revisit after ex-date."
        ),
        confidence=0.7,
        evidence_ids=[ev_engine.evidence_id],
    ))

    # -- adversarial review -----------------------------------------------------
    dissent = workforce.raise_dissent(decision_id, Dissent.create(
        role=RoleType.RED_TEAM,
        objection=(
            "IV in its 40th percentile means we are selling volatility below "
            "median richness while capping upside through an earnings event — "
            "the premium may not compensate for the skew of outcomes."
        ),
        severity=DissentSeverity.MATERIAL,
    ))
    workforce.add_assessment(decision_id, Assessment.create(
        role=RoleType.RED_TEAM,
        summary=(
            "Strongest case against: sub-median IV plus earnings inside tenor. "
            "If proceeding, strikes should sit above the earnings-move breakeven."
        ),
        confidence=0.6,
        evidence_ids=[ev_vol.evidence_id, ev_earnings.evidence_id],
    ))
    workforce.resolve_dissent(
        decision_id,
        dissent.dissent_id,
        resolution=(
            "Accepted in part: strike selection moved one notch further "
            "out-of-the-money on the earnings name, sacrificing ~15% of premium "
            "for materially more upside room. Documented in the recommendation."
        ),
        resolved_by=DEMO_OWNER,
    )

    # -- recommendation with falsifiable forecast --------------------------------
    workforce.set_recommendation(
        decision_id,
        recommendation=(
            "Continue the covered-call overlay for the August cycle on the two "
            "engine-approved names, with strikes one notch further OTM on the "
            "earnings name per red-team review. Skip the dividend-blocked roll; "
            "revisit after the ex-dividend date."
        ),
        confidence=0.7,
        alternatives_considered=[
            "Pause the overlay entirely for the earnings month (rejected: forgoes premium on non-earnings names with no offsetting risk reduction).",
            "Roll all three names including the dividend name (rejected: engine DividendGate flags early-assignment risk).",
            "Switch to cash-secured puts (rejected: changes the book's mandate, out of scope for a monthly cycle decision).",
        ],
        what_would_change_our_mind=[
            "IV percentile falling below the 25th percentile (premium too thin).",
            "Earnings date moving earlier such that no OTM strike clears the expected move.",
            "Margin utilization approaching the policy ceiling.",
        ],
        forecast=Forecast(
            statement=(
                "The August overlay cycle closes with positive net premium "
                "after costs and no early assignment."
            ),
            probability=0.7,
            resolve_by="2026-08-21",
        ),
    )

    # -- gates, approval, finalization -------------------------------------------
    workforce.finalize(decision_id)          # -> PENDING_APPROVAL (HIGH tier)
    workforce.approve(decision_id, approved_by=DEMO_OWNER)
    record = workforce.finalize(decision_id)  # -> APPROVED

    # -- outputs ------------------------------------------------------------------
    brief_path = out / f"{decision_id}_brief.md"
    brief_path.write_text(render_brief(record))

    verification = workforce.ledger.verify()
    verify_path = out / "ledger_verification.json"
    import json
    verify_path.write_text(json.dumps(verification.to_dict(), indent=2))

    anchor_path = out / "ledger_anchor.json"
    anchor_path.write_text(json.dumps(workforce.ledger.anchor(), indent=2))

    card = compute_scorecard(workforce.load_all_records())
    scorecard_path = out / "scorecard.md"
    scorecard_path.write_text(render_scorecard(card))

    return {
        "decision_record": str(out / "decisions" / f"{decision_id}.json"),
        "decision_brief": str(brief_path),
        "ledger": str(out / "workforce_ledger.jsonl"),
        "ledger_verification": str(verify_path),
        "ledger_anchor": str(anchor_path),
        "scorecard": str(scorecard_path),
    }
