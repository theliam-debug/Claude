"""
Risk report generation.

Creates human-readable markdown reports explaining recommendations
and gate decisions.
"""

from datetime import datetime
from typing import Optional
from derivatives_strategies.data.models import (
    Recommendation,
    GateResult,
    GateStatus,
    Position,
    ActionType,
)


class RiskReportGenerator:
    """
    Generates markdown risk reports.

    Reports include:
    - Run summary
    - Position analysis
    - Gate results with explanations
    - Recommendations with rationale
    """

    def __init__(self, run_id: str, as_of: str, policy_name: str):
        """
        Initialize report generator.

        Args:
            run_id: Run identifier
            as_of: As-of date
            policy_name: Policy name
        """
        self.run_id = run_id
        self.as_of = as_of
        self.policy_name = policy_name

    def generate(
        self,
        recommendations: list[Recommendation],
        positions: list[Position],
        portfolio_value: Optional[float] = None,
    ) -> str:
        """
        Generate complete risk report.

        Args:
            recommendations: List of recommendations
            positions: List of positions
            portfolio_value: Total portfolio value

        Returns:
            Markdown formatted report
        """
        sections = [
            self._header(),
            self._summary(recommendations, positions, portfolio_value),
            self._recommendations_section(recommendations),
            self._blocked_actions_section(recommendations),
            self._warnings_section(recommendations),
            self._gate_summary(recommendations),
            self._footer(),
        ]

        return '\n\n'.join(section for section in sections if section)

    def _header(self) -> str:
        """Generate report header."""
        return f"""# Risk Report

**Run ID:** `{self.run_id}`
**As Of:** {self.as_of}
**Policy:** {self.policy_name}
**Generated:** {datetime.utcnow().isoformat()}Z"""

    def _summary(
        self,
        recommendations: list[Recommendation],
        positions: list[Position],
        portfolio_value: Optional[float],
    ) -> str:
        """Generate summary section."""
        approved = [r for r in recommendations if r.approved]
        blocked = [r for r in recommendations if r.blocked_by]
        warnings = [r for r in recommendations if r.warnings]

        # Count by action type
        action_counts = {}
        for r in approved:
            action = r.action.value
            action_counts[action] = action_counts.get(action, 0) + 1

        summary = f"""## Summary

| Metric | Value |
|--------|-------|
| Positions Analyzed | {len(positions)} |
| Recommendations | {len(recommendations)} |
| Approved | {len(approved)} |
| Blocked | {len(blocked)} |
| With Warnings | {len(warnings)} |"""

        if portfolio_value:
            summary += f"\n| Portfolio Value | ${portfolio_value:,.2f} |"

        if action_counts:
            summary += "\n\n### Actions by Type\n"
            for action, count in sorted(action_counts.items()):
                summary += f"- **{action.title()}:** {count}\n"

        return summary

    def _recommendations_section(
        self,
        recommendations: list[Recommendation]
    ) -> str:
        """Generate approved recommendations section."""
        approved = [r for r in recommendations if r.approved]

        if not approved:
            return "## Approved Recommendations\n\n*No recommendations approved in this run.*"

        lines = ["## Approved Recommendations"]

        for rec in approved:
            lines.append(self._format_recommendation(rec))

        return '\n\n'.join(lines)

    def _blocked_actions_section(
        self,
        recommendations: list[Recommendation]
    ) -> str:
        """Generate blocked actions section."""
        blocked = [r for r in recommendations if r.blocked_by]

        if not blocked:
            return ""

        lines = ["## Blocked Actions"]

        for rec in blocked:
            pos = rec.position
            lines.append(f"""### {pos.symbol} - {rec.action.value.upper()} BLOCKED

**Position:** {pos.quantity} {pos.position_type}
{f"**Strike:** ${pos.strike:.2f}" if pos.strike else ""}
{f"**Expiry:** {pos.expiry}" if pos.expiry else ""}

**Blocked By:** `{rec.blocked_by}`

**Reason:** {rec.reason}

**Gate Details:**""")

            for gate in rec.gate_results:
                if gate.status == GateStatus.BLOCK:
                    lines.append(f"""
- **{gate.gate_name}:** {gate.message}
  - Threshold: {gate.threshold}
  - Actual: {gate.actual_value}""")

        return '\n'.join(lines)

    def _warnings_section(
        self,
        recommendations: list[Recommendation]
    ) -> str:
        """Generate warnings section."""
        with_warnings = [r for r in recommendations if r.warnings and r.approved]

        if not with_warnings:
            return ""

        lines = ["## Warnings"]

        for rec in with_warnings:
            pos = rec.position
            lines.append(f"### {pos.symbol}")

            for warning in rec.warnings:
                lines.append(f"- ⚠️ {warning}")

        return '\n\n'.join(lines)

    def _gate_summary(
        self,
        recommendations: list[Recommendation]
    ) -> str:
        """Generate gate summary section."""
        all_gates: dict[str, dict] = {}

        for rec in recommendations:
            for gate in rec.gate_results:
                if gate.gate_name not in all_gates:
                    all_gates[gate.gate_name] = {
                        'pass': 0,
                        'warn': 0,
                        'block': 0,
                    }
                all_gates[gate.gate_name][gate.status.value] += 1

        if not all_gates:
            return ""

        lines = ["## Gate Summary", "", "| Gate | Pass | Warn | Block |", "|------|------|------|-------|"]

        for gate_name, counts in sorted(all_gates.items()):
            lines.append(
                f"| {gate_name} | {counts['pass']} | {counts['warn']} | {counts['block']} |"
            )

        return '\n'.join(lines)

    def _format_recommendation(self, rec: Recommendation) -> str:
        """Format a single recommendation."""
        pos = rec.position
        action = rec.action.value.upper()

        header = f"### {pos.symbol} - {action}"

        position_info = f"""**Current Position:** {pos.quantity} {pos.position_type}"""

        if pos.strike:
            position_info += f" @ ${pos.strike:.2f}"
        if pos.expiry:
            position_info += f" exp {pos.expiry}"

        target_info = ""
        if rec.target_strike or rec.target_expiry:
            target_info = "\n**Target:**"
            if rec.target_strike:
                target_info += f" ${rec.target_strike:.2f}"
            if rec.target_expiry:
                target_info += f" exp {rec.target_expiry}"
            if rec.target_quantity:
                target_info += f" x{rec.target_quantity}"

        economics_info = ""
        if rec.economics:
            eco = rec.economics
            economics_info = f"""
**Economics:**
| Metric | Value |
|--------|-------|
| Gross Premium | ${eco.gross_premium:.2f} |
| Transaction Costs | ${eco.transaction_costs.total:.2f} |
| Net Premium | ${eco.net_premium:.2f} |
| Max Profit | ${eco.max_profit:.2f} |
| Max Loss | ${eco.max_loss:.2f} |"""

            if eco.annualized_return:
                economics_info += f"\n| Annualized Return | {eco.annualized_return:.1%} |"

        greeks_info = ""
        if rec.greeks:
            g = rec.greeks
            greeks_info = f"""
**Greeks:**
| Greek | Value |
|-------|-------|
| Delta | {g.delta:.4f} |
| Gamma | {g.gamma:.6f} |
| Theta | ${g.theta:.2f}/day |
| Vega | ${g.vega:.2f}/1% |"""

        reason_info = f"\n**Rationale:** {rec.reason}" if rec.reason else ""

        warnings_info = ""
        if rec.warnings:
            warnings_info = "\n**Warnings:**\n"
            for w in rec.warnings:
                warnings_info += f"- ⚠️ {w}\n"

        return f"""{header}

{position_info}{target_info}
{economics_info}
{greeks_info}
{reason_info}
{warnings_info}"""

    def _footer(self) -> str:
        """Generate report footer."""
        return f"""---

*This report was generated automatically by derivatives_strategies v3.*
*All recommendations should be reviewed before execution.*
*Run ID: {self.run_id}*"""


def generate_risk_report(
    run_id: str,
    as_of: str,
    policy_name: str,
    recommendations: list[Recommendation],
    positions: list[Position],
    portfolio_value: Optional[float] = None,
) -> str:
    """
    Convenience function to generate a risk report.

    Args:
        run_id: Run identifier
        as_of: As-of date
        policy_name: Policy name
        recommendations: List of recommendations
        positions: List of positions
        portfolio_value: Total portfolio value

    Returns:
        Markdown formatted report
    """
    generator = RiskReportGenerator(run_id, as_of, policy_name)
    return generator.generate(recommendations, positions, portfolio_value)
