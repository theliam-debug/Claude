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
        """Generate hash of policy for audit trail."""
        data = {
            "name": self.name,
            "version": self.version,
            "gates": [g.name for g in self.gates],
            "overrides": [o.gate_name for o in self.overrides],
        }
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:16]


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
        # Add event calendar to context
        context.event_calendar = self.policy.event_calendar

        results = []
        for gate in self.policy.gates:
            result = gate.evaluate(context)

            # Check for override
            if result.status != GateStatus.PASS:
                override = self._override_map.get(gate.name)
                if override:
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
    # Use simple YAML parsing (avoid external dependency)
    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {path}")

    content = policy_path.read_text()

    # Simple YAML parser for our structured format
    config = _parse_simple_yaml(content)

    return _build_policy_from_config(config)


def _parse_simple_yaml(content: str) -> dict:
    """
    Parse a simple YAML file.

    Supports basic key: value pairs and nested structures.
    Limited parser to avoid external dependencies.
    """
    result: dict = {}
    current_section = result
    section_stack = [(0, result)]
    current_key = None
    list_key = None

    for line in content.split('\n'):
        # Skip comments and empty lines
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # Calculate indent level
        indent = len(line) - len(line.lstrip())

        # Pop sections if we've dedented
        while section_stack and indent <= section_stack[-1][0] and len(section_stack) > 1:
            section_stack.pop()

        current_section = section_stack[-1][1]

        # Handle list items
        if stripped.startswith('- '):
            item = stripped[2:].strip()
            if list_key and list_key in current_section:
                if ':' in item:
                    # Nested dict in list
                    key, val = item.split(':', 1)
                    item_dict = {key.strip(): _parse_value(val.strip())}
                    current_section[list_key].append(item_dict)
                else:
                    current_section[list_key].append(_parse_value(item))
            continue

        # Handle key: value pairs
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                # Simple value
                current_section[key] = _parse_value(value)
                list_key = None
            else:
                # Start of section or list
                if key not in current_section:
                    current_section[key] = {}
                section_stack.append((indent, current_section[key]))
                list_key = key
                # Check if it's a list (next line starts with -)
                if isinstance(current_section[key], dict) and not current_section[key]:
                    current_section[key] = []

    return result


def _parse_value(value: str) -> Any:
    """Parse a YAML value."""
    # Remove quotes
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # Boolean
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False

    # Number
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def _build_policy_from_config(config: dict) -> Policy:
    """Build Policy object from parsed config."""
    gates = []

    # Build gates from config
    gates_config = config.get('gates', {})

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

    # Parse event calendar
    event_calendar = {}
    if 'event_calendar' in config:
        for date_str, events in config['event_calendar'].items():
            if isinstance(events, list):
                event_calendar[str(date_str)] = events
            else:
                event_calendar[str(date_str)] = [str(events)]

    # Parse overrides
    overrides = []
    if 'overrides' in config:
        for ov in config['overrides']:
            if isinstance(ov, dict):
                overrides.append(PolicyOverride(
                    gate_name=ov.get('gate', ''),
                    reason_code=ov.get('reason', ''),
                    authorized_by=ov.get('authorized_by', 'system'),
                    timestamp=ov.get('timestamp', ''),
                ))

    return Policy(
        name=config.get('name', 'default'),
        version=config.get('version', '1.0'),
        description=config.get('description', ''),
        gates=gates,
        overrides=overrides,
        event_calendar=event_calendar,
        default_dte_min=config.get('defaults', {}).get('dte_min', 7),
        default_dte_max=config.get('defaults', {}).get('dte_max', 45),
        default_delta_min=config.get('defaults', {}).get('delta_min', 0.15),
        default_delta_max=config.get('defaults', {}).get('delta_max', 0.35),
        cost_commission=config.get('costs', {}).get('commission', 0.65),
        cost_price_improvement=config.get('costs', {}).get('price_improvement', 0.10),
        max_position_concentration=config.get('limits', {}).get('concentration', 0.10),
        max_margin_utilization=config.get('limits', {}).get('margin_utilization', 0.80),
        prefer_roll_credit=config.get('strategy', {}).get('prefer_roll_credit', True),
        allow_roll_debit=config.get('strategy', {}).get('allow_roll_debit', False),
        max_roll_debit=config.get('strategy', {}).get('max_roll_debit', 0.50),
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
