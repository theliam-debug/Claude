"""
Append-only ledger for audit trail.

All recommendations and actions are logged with full context.
"""

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from derivatives_strategies.data.models import (
    LedgerEntry,
    Recommendation,
    Position,
)


class Ledger:
    """
    Append-only ledger for audit trail.

    All entries are written as JSON lines to ensure immutability
    and easy parsing.
    """

    def __init__(self, path: str):
        """
        Initialize ledger.

        Args:
            path: Path to ledger file (will be created if doesn't exist)
        """
        self.path = Path(path)
        self._ensure_exists()

    def _ensure_exists(self) -> None:
        """Ensure ledger file exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, entry: LedgerEntry) -> None:
        """
        Append entry to ledger.

        Args:
            entry: Ledger entry to append
        """
        with open(self.path, 'a') as f:
            f.write(entry.to_json_line() + '\n')

    def read_all(self) -> list[dict]:
        """
        Read all entries from ledger.

        Returns:
            List of entry dictionaries
        """
        entries = []
        if self.path.exists():
            with open(self.path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        return entries

    def read_by_run_id(self, run_id: str) -> list[dict]:
        """
        Read entries for a specific run.

        Args:
            run_id: Run identifier

        Returns:
            List of entries for the run
        """
        return [e for e in self.read_all() if e.get('run_id') == run_id]

    def get_last_entry(self) -> Optional[dict]:
        """Get the most recent entry."""
        entries = self.read_all()
        return entries[-1] if entries else None

    def get_entry_count(self) -> int:
        """Get total number of entries."""
        return len(self.read_all())


def create_ledger_entry(
    run_id: str,
    action: str,
    recommendation: Optional[Recommendation] = None,
    position: Optional[Position] = None,
    policy_hash: str = "",
    details: Optional[dict] = None,
) -> LedgerEntry:
    """
    Create a ledger entry with computed hashes.

    Args:
        run_id: Run identifier
        action: Action type (e.g., "recommendation", "gate_result", "override")
        recommendation: Related recommendation (if any)
        position: Related position (if any)
        policy_hash: Hash of the policy used
        details: Additional details

    Returns:
        LedgerEntry ready to append
    """
    timestamp = datetime.utcnow().isoformat() + 'Z'

    # Compute inputs hash
    inputs_data = {}
    if recommendation:
        inputs_data['recommendation'] = recommendation.inputs_hash()
    if position:
        inputs_data['position'] = position.to_dict()
    if details:
        inputs_data['details'] = details

    inputs_hash = hashlib.sha256(
        json.dumps(inputs_data, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    return LedgerEntry(
        run_id=run_id,
        timestamp=timestamp,
        action=action,
        inputs_hash=inputs_hash,
        policy_hash=policy_hash,
        details=details or {},
    )


def log_run_start(
    ledger: Ledger,
    run_id: str,
    policy_hash: str,
    positions_count: int,
    symbols: list[str],
) -> None:
    """Log the start of a run."""
    entry = create_ledger_entry(
        run_id=run_id,
        action="run_start",
        policy_hash=policy_hash,
        details={
            "positions_count": positions_count,
            "symbols": symbols,
        },
    )
    ledger.append(entry)


def log_recommendation(
    ledger: Ledger,
    run_id: str,
    recommendation: Recommendation,
    policy_hash: str,
) -> None:
    """Log a recommendation."""
    entry = create_ledger_entry(
        run_id=run_id,
        action="recommendation",
        recommendation=recommendation,
        policy_hash=policy_hash,
        details={
            "symbol": recommendation.position.symbol,
            "action": recommendation.action.value,
            "approved": recommendation.approved,
            "blocked_by": recommendation.blocked_by,
            "gate_count": len(recommendation.gate_results),
        },
    )
    ledger.append(entry)


def log_gate_result(
    ledger: Ledger,
    run_id: str,
    gate_name: str,
    status: str,
    message: str,
    policy_hash: str,
    details: Optional[dict] = None,
) -> None:
    """Log a gate evaluation result."""
    entry = create_ledger_entry(
        run_id=run_id,
        action="gate_result",
        policy_hash=policy_hash,
        details={
            "gate_name": gate_name,
            "status": status,
            "message": message,
            **(details or {}),
        },
    )
    ledger.append(entry)


def log_override(
    ledger: Ledger,
    run_id: str,
    gate_name: str,
    reason: str,
    authorized_by: str,
    policy_hash: str,
) -> None:
    """Log a gate override."""
    entry = create_ledger_entry(
        run_id=run_id,
        action="override",
        policy_hash=policy_hash,
        details={
            "gate_name": gate_name,
            "reason": reason,
            "authorized_by": authorized_by,
        },
    )
    ledger.append(entry)


def log_run_complete(
    ledger: Ledger,
    run_id: str,
    policy_hash: str,
    recommendations_count: int,
    approved_count: int,
    blocked_count: int,
) -> None:
    """Log the completion of a run."""
    entry = create_ledger_entry(
        run_id=run_id,
        action="run_complete",
        policy_hash=policy_hash,
        details={
            "recommendations_count": recommendations_count,
            "approved_count": approved_count,
            "blocked_count": blocked_count,
        },
    )
    ledger.append(entry)
