"""
Decision brief rendering.

The brief is the product the decision maker actually reads: recommendation
up front, then evidence with sources and age, dissent verbatim, gate
outcomes, and the accountability line. Everything in it is reconstructable
from the decision record — the brief adds no facts of its own.
"""

from lsto_workforce.models import (
    DecisionRecord,
    DecisionStatus,
    GateStatus,
)

_STATUS_LABELS = {
    DecisionStatus.OPEN: "OPEN — evidence gathering",
    DecisionStatus.RECOMMENDED: "RECOMMENDED — not yet finalized",
    DecisionStatus.APPROVED: "APPROVED",
    DecisionStatus.BLOCKED: "BLOCKED by accountability gates",
    DecisionStatus.PENDING_APPROVAL: "PENDING HUMAN APPROVAL",
    DecisionStatus.WITHDRAWN: "WITHDRAWN",
}

_GATE_ICONS = {
    GateStatus.PASS: "PASS ",
    GateStatus.WARN: "WARN ",
    GateStatus.BLOCK: "BLOCK",
}


def render_brief(record: DecisionRecord) -> str:
    """Render a decision record as a markdown decision brief."""
    lines: list[str] = []
    add = lines.append

    add(f"# Decision Brief: {record.question}")
    add("")
    add(f"- **Decision ID:** `{record.decision_id}`")
    add(f"- **Status:** {_STATUS_LABELS[record.status]}")
    add(f"- **Impact tier:** {record.impact.value.upper()}  |  **Category:** {record.category or 'general'}")
    add(f"- **Decision owner:** {record.requested_by}"
        + (f"  |  **Approved by:** {record.approved_by}" if record.approved_by else ""))
    add(f"- **As of:** {record.as_of}  |  **Opened:** {record.opened_at}"
        + (f"  |  **Finalized:** {record.finalized_at}" if record.finalized_at else ""))
    add(f"- **Charter hash:** `{record.charter_hash[:16]}…`" if record.charter_hash else "")
    add("")

    add("## Recommendation")
    add("")
    if record.recommendation:
        add(record.recommendation)
        if record.confidence is not None:
            add("")
            add(f"**Confidence:** {record.confidence:.0%}")
    else:
        add("_No recommendation yet._")
    add("")

    if record.forecast:
        add("## Falsifiable forecast")
        add("")
        f = record.forecast
        resolved = (
            "unresolved" if f.resolved is None
            else ("came true" if f.resolved else "did not come true")
        )
        add(f"> {f.statement}")
        add("")
        add(f"Probability: {f.probability:.0%} — judge by {f.resolve_by} ({resolved}).")
        add("")

    if record.alternatives_considered:
        add("## Alternatives considered")
        add("")
        for alt in record.alternatives_considered:
            add(f"- {alt}")
        add("")

    if record.what_would_change_our_mind:
        add("## What would change our mind")
        add("")
        for cond in record.what_would_change_our_mind:
            add(f"- {cond}")
        add("")

    add("## Evidence")
    add("")
    if record.evidence:
        add("| Claim | Source | Tier | Data as-of | Age (d) | Ref |")
        add("|---|---|---|---|---|---|")
        for ev in record.evidence:
            try:
                age = str(ev.age_days(record.as_of))
            except ValueError:
                age = "?"
            claim = ev.claim.replace("|", "\\|")
            ref = ev.ref.replace("|", "\\|") if ev.ref else "—"
            add(f"| {claim} | {ev.source_name} | {ev.source_tier.value} "
                f"| {ev.as_of} | {age} | {ref} |")
    else:
        add("_No evidence attached._")
    add("")

    add("## Role assessments")
    add("")
    if record.assessments:
        for a in record.assessments:
            conflict = (
                f" — **declared conflicts:** {', '.join(a.declared_conflicts)}"
                if a.declared_conflicts else ""
            )
            add(f"- **{a.role.value}** (confidence {a.confidence:.0%}): {a.summary}{conflict}")
    else:
        add("_No assessments filed._")
    add("")

    add("## Dissent")
    add("")
    if record.dissents:
        for d in record.dissents:
            add(f"- **[{d.severity.value.upper()}] {d.role.value}:** {d.objection}")
            if d.resolved:
                add(f"  - _Resolved by {d.resolved_by}:_ {d.resolution}")
            else:
                add("  - _UNRESOLVED_")
    else:
        add("_No dissents raised._")
    add("")

    add("## Accountability gates")
    add("")
    if record.gate_results:
        overridden = {o.gate_name: o for o in record.overrides}
        add("| Gate | Result | Detail |")
        add("|---|---|---|")
        for g in record.gate_results:
            note = g.message.replace("|", "\\|")
            if g.gate_name in overridden:
                o = overridden[g.gate_name]
                note += (f" — **OVERRIDDEN** by {o.authorized_by}: "
                         f"{o.reason}".replace("|", "\\|"))
            add(f"| {g.gate_name} | {_GATE_ICONS[g.status]} | {note} |")
    else:
        add("_Gates not yet evaluated._")
    add("")

    add("---")
    add(f"_Record hash: `{record.record_hash()}` — verify against the workforce ledger._")
    add("")
    return "\n".join(lines)
