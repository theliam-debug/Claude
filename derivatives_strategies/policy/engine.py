"""
Policy engine for loading policies from YAML and evaluating gates.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from derivatives_strategies.data.models import GateResult, GateStatus
from derivatives_strategies.policy.gates import (
    Gate,
    GateContext,
    LiquidityGate,
    EventGate,
    DividendGate,
    MarginGate,
    RollCreditGate,
    ConcentrationGate,
    DTEGate,
    DeltaGate,
)


@dataclass
class PolicyOverride:
    """An override for a gate result."""
    gate_name: str
    reason_code: str
    authorized_by: str
    timestamp: str
    expires: Optional[str] = None


@dataclass
class Policy:
    """
    Complete policy configuration.

    Includes gate configurations and override handling.
    """
    name: str
    version: str
    description: str = ""
    gates: list[Gate] = field(default_factory=list)
    overrides: list[PolicyOverride] = field(default_factory=list)
    event_calendar: dict[str, list[str]] = field(default_factory=dict)

    # Default parameters
    default_dte_min: int = 7
    default_dte_max: int = 45
    default_delta_min: float = 0.15
    default_delta_max: float = 0.35

    # Transaction cost parameters
    cost_commission: float = 0.65
    cost_price_improvement: float = 0.10

    # Risk limits
    max_position_concentration: float = 0.10
    max_margin_utilization: float = 0.80

    # Strategy parameters
    prefer_roll_credit: bool = True
    allow_roll_debit: bool = False
    max_roll_debit: float = 0.50

    def policy_hash(self) -> str:
        """
        Hash of the full effective policy for the audit trail: gate
        thresholds and hard/soft flags, defaults, limits, strategy
        parameters, and overrides — loosening any threshold changes
        the hash.
        """
        data = {
            "name": self.name,
            "version": self.version,
            "gates": [
                {
                    "name": g.name,
                    "hard": g.hard,
                    "override_allowed": g.override_allowed,
                    "config": g.config,
                }
                for g in self.gates
            ],
            "overrides": [
                {
                    "gate": o.gate_name,
                    "reason": o.reason_code,
                    "authorized_by": o.authorized_by,
                    "expires": o.expires,
                }
                for o in self.overrides
            ],
            "event_calendar": self.event_calendar,
            "defaults": {
                "dte_min": self.default_dte_min,
                "dte_max": self.default_dte_max,
                "delta_min": self.default_delta_min,
                "delta_max": self.default_delta_max,
            },
            "costs": {
                "commission": self.cost_commission,
                "price_improvement": self.cost_price_improvement,
            },
            "limits": {
                "concentration": self.max_position_concentration,
                "margin_utilization": self.max_margin_utilization,
            },
            "strategy": {
                "prefer_roll_credit": self.prefer_roll_credit,
                "allow_roll_debit": self.allow_roll_debit,
                "max_roll_debit": self.max_roll_debit,
            },
        }
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()


class PolicyEngine:
    """
    Engine for evaluating policy gates.

    Processes all gates and handles overrides.
    """

    def __init__(self, policy: Policy):
        """
        Initialize policy engine.

        Args:
            policy: Policy configuration
        """
        self.policy = policy
        self._override_map: dict[str, PolicyOverride] = {
            o.gate_name: o for o in policy.overrides
        }

    def evaluate(self, context: GateContext) -> list[GateResult]:
        """
        Evaluate all gates in the policy.

        Args:
            context: Gate evaluation context

        Returns:
            List of gate results
        """
        # Merge policy calendar into context (policy entries win on clashes,
        # but caller-supplied events are preserved).
        merged_calendar = dict(context.event_calendar or {})
        merged_calendar.update(self.policy.event_calendar)
        context.event_calendar = merged_calendar

        results = []
        for gate in self.policy.gates:
            result = gate.evaluate(context)

            # Check for override
            if result.status != GateStatus.PASS:
                override = self._override_map.get(gate.name)
                if override and self._override_applies(override, result, context):
                    # Apply override
                    result = GateResult(
                        gate_name=result.gate_name,
                        status=GateStatus.WARN,  # Downgrade to warn
                        message=f"OVERRIDDEN: {result.message}",
                        details=result.details,
                        threshold=result.threshold,
                        actual_value=result.actual_value,
                        override_allowed=result.override_allowed,
                        override_reason=override.reason_code,
                    )

            results.append(result)

        return results

    @staticmethod
    def _override_applies(
        override: PolicyOverride,
        result: GateResult,
        context: GateContext,
    ) -> bool:
        """An override applies only if the gate allows it and it hasn't expired."""
        if not result.override_allowed:
            return False
        if override.expires:
            # Compare on the date portion of ISO strings; expired means
            # strictly before the evaluation date.
            if override.expires[:10] < context.as_of[:10]:
                return False
        return True

    def is_blocked(self, results: list[GateResult]) -> bool:
        """Check if any gate blocks the action."""
        return any(r.status == GateStatus.BLOCK for r in results)

    def get_blocking_gates(self, results: list[GateResult]) -> list[str]:
        """Get names of gates that block."""
        return [r.gate_name for r in results if r.status == GateStatus.BLOCK]

    def get_warnings(self, results: list[GateResult]) -> list[str]:
        """Get warning messages."""
        return [r.message for r in results if r.status == GateStatus.WARN]


def load_policy(path: str) -> Policy:
    """
    Load policy from YAML file.

    Args:
        path: Path to YAML file

    Returns:
        Policy object
    """
    import yaml

    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {path}")

    with open(policy_path, 'r') as f:
        config = yaml.safe_load(f)

    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError(
            f"Policy file must contain a YAML mapping at the top level: {path}"
        )

    return _build_policy_from_config(config)


def _build_policy_from_config(config: dict) -> Policy:
    """Build Policy object from parsed config."""
    gates = []

    # Build gates from config. Empty YAML sections parse as None; treat
    # them the same as absent sections with all-default values.
    gates_config = config.get('gates') or {}
    for key in list(gates_config):
        if gates_config[key] is None:
            gates_config[key] = {}
    defaults = config.get('defaults') or {}
    costs = config.get('costs') or {}
    limits = config.get('limits') or {}
    strategy = config.get('strategy') or {}

    # Liquidity gate
    if 'liquidity' in gates_config:
        liq = gates_config['liquidity']
        gates.append(LiquidityGate(
            max_spread_pct=liq.get('max_spread_pct', 0.20),
            min_open_interest=liq.get('min_open_interest', 100),
            min_volume=liq.get('min_volume', 10),
            hard=liq.get('hard', True),
        ))

    # Event gate
    if 'events' in gates_config:
        ev = gates_config['events']
        gates.append(EventGate(
            blackout_days_before=ev.get('blackout_days_before', 2),
            blackout_days_after=ev.get('blackout_days_after', 1),
            hard=ev.get('hard', True),
        ))

    # Dividend gate
    if 'dividend' in gates_config:
        div = gates_config['dividend']
        gates.append(DividendGate(
            days_before_ex=div.get('days_before_ex', 5),
            min_extrinsic_ratio=div.get('min_extrinsic_ratio', 1.5),
            hard=div.get('hard', True),
        ))

    # Margin gate
    if 'margin' in gates_config:
        mrg = gates_config['margin']
        gates.append(MarginGate(
            min_margin_buffer=mrg.get('min_buffer', 0.20),
            max_margin_utilization=mrg.get('max_utilization', 0.80),
            hard=mrg.get('hard', True),
        ))

    # Roll credit gate
    if 'roll_credit' in gates_config:
        rc = gates_config['roll_credit']
        gates.append(RollCreditGate(
            min_net_credit=rc.get('min_credit', 0.0),
            allow_small_debit=rc.get('allow_debit', False),
            max_debit=rc.get('max_debit', 0.0),
            hard=rc.get('hard', True),
        ))

    # Concentration gate
    if 'concentration' in gates_config:
        conc = gates_config['concentration']
        gates.append(ConcentrationGate(
            max_position_pct=conc.get('max_pct', 0.10),
            max_notional=conc.get('max_notional'),
            hard=conc.get('hard', True),
        ))

    # DTE gate
    if 'dte' in gates_config:
        dte = gates_config['dte']
        gates.append(DTEGate(
            min_dte=dte.get('min', 7),
            max_dte=dte.get('max', 45),
            hard=dte.get('hard', False),
        ))

    # Delta gate
    if 'delta' in gates_config:
        delta = gates_config['delta']
        gates.append(DeltaGate(
            min_delta=delta.get('min', 0.15),
            max_delta=delta.get('max', 0.35),
            hard=delta.get('hard', False),
        ))

    # Parse event calendar. PyYAML parses unquoted dates as datetime.date;
    # normalize keys to ISO strings.
    event_calendar = {}
    for date_key, events in (config.get('event_calendar') or {}).items():
        date_str = (
            date_key.isoformat() if hasattr(date_key, 'isoformat')
            else str(date_key)
        )
        if isinstance(events, list):
            event_calendar[date_str] = [str(e) for e in events]
        else:
            event_calendar[date_str] = [str(events)]

    # Parse overrides
    overrides = []
    for ov in (config.get('overrides') or []):
        if isinstance(ov, dict):
            overrides.append(PolicyOverride(
                gate_name=ov.get('gate', ''),
                reason_code=ov.get('reason', ''),
                authorized_by=ov.get('authorized_by', 'system'),
                timestamp=str(ov.get('timestamp', '')),
                expires=str(ov['expires']) if ov.get('expires') else None,
            ))

    return Policy(
        name=config.get('name', 'default'),
        version=str(config.get('version', '1.0')),
        description=config.get('description', ''),
        gates=gates,
        overrides=overrides,
        event_calendar=event_calendar,
        default_dte_min=defaults.get('dte_min', 7),
        default_dte_max=defaults.get('dte_max', 45),
        default_delta_min=defaults.get('delta_min', 0.15),
        default_delta_max=defaults.get('delta_max', 0.35),
        cost_commission=costs.get('commission', 0.65),
        cost_price_improvement=costs.get('price_improvement', 0.10),
        max_position_concentration=limits.get('concentration', 0.10),
        max_margin_utilization=limits.get('margin_utilization', 0.80),
        prefer_roll_credit=strategy.get('prefer_roll_credit', True),
        allow_roll_debit=strategy.get('allow_roll_debit', False),
        max_roll_debit=strategy.get('max_roll_debit', 0.50),
    )


def create_default_policy() -> Policy:
    """Create a default policy with standard gates."""
    return Policy(
        name="default",
        version="1.0",
        description="Default covered call policy",
        gates=[
            LiquidityGate(max_spread_pct=0.20, min_open_interest=100, hard=True),
            DividendGate(days_before_ex=5, hard=True),
            MarginGate(max_margin_utilization=0.80, hard=True),
            ConcentrationGate(max_position_pct=0.10, hard=True),
            DTEGate(min_dte=7, max_dte=45, hard=False),
            DeltaGate(min_delta=0.15, max_delta=0.35, hard=False),
        ],
    )
