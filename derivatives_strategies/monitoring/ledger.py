"""
Append-only, hash-chained ledger for audit trail.

All recommendations and actions are logged with full context. Each entry
embeds the hash of the previous entry, so edits, deletions, or reordering
of history break the chain and are detected by verify().
"""

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from derivatives_strategies.data.models import (
    LedgerEntry,
    Recommendation,
    Position,
)

GENESIS_HASH = "0" * 64


@dataclass
class LedgerVerification:
    """Outcome of a full-chain ledger verification."""
    valid: bool
    entries: int
    first_bad_seq: Optional[int] = None
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "entries": self.entries,
            "first_bad_seq": self.first_bad_seq,
            "errors": list(self.errors),
        }


class Ledger:
    """
    Append-only ledger for audit trail.

    Entries are JSON lines forming a SHA-256 hash chain. The chain head is
    re-derived from the file on open, so sequential runs extend one chain.
    """

    def __init__(self, path: str):
        """
        Initialize ledger.

        Args:
            path: Path to ledger file (will be created if doesn't exist)
        """
        self.path = Path(path)
        self._ensure_exists()
        self._seq, self._head = self._load_head()

    def _ensure_exists(self) -> None:
        """Ensure ledger file exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _load_head(self) -> tuple:
        """Resume the chain from the last entry; genesis when empty."""
        last = None
        with open(self.path, 'r') as f:
            for line in f:
                if line.strip():
                    last = line
        if last is None:
            return 0, GENESIS_HASH
        data = json.loads(last)
        # Pre-chaining entries (no seq/entry_hash) restart the count but the
        # verify() report will flag them explicitly.
        return data.get('seq', 0), data.get('entry_hash', GENESIS_HASH)

    @property
    def head_hash(self) -> str:
        """Current chain head — anchor this out-of-band (e.g. in run.json)."""
        return self._head

    def append(self, entry: LedgerEntry) -> LedgerEntry:
        """
        Append entry to ledger, extending the hash chain.

        Args:
            entry: Ledger entry to append (seq/prev_hash/entry_hash are set here)

        Returns:
            The entry with chain fields populated
        """
        entry.seq = self._seq + 1
        entry.prev_hash = self._head
        entry.entry_hash = entry.compute_hash()
        with open(self.path, 'a') as f:
            f.write(entry.to_json_line() + '\n')
        self._seq = entry.seq
        self._head = entry.entry_hash
        return entry

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

    def verify(self) -> LedgerVerification:
        """
        Walk the chain from genesis, detecting edited payloads, deleted or
        reordered entries, and forged hashes.
        """
        entries = self.read_all()
        errors = []
        first_bad = None
        prev_hash = GENESIS_HASH
        expected_seq = 1
        for raw in entries:
            problems = []
            if raw.get('seq') != expected_seq:
                problems.append(
                    f"seq {raw.get('seq')} != expected {expected_seq}"
                )
            if raw.get('prev_hash') != prev_hash:
                problems.append("prev_hash mismatch (chain break)")
            recomputed = hashlib.sha256(json.dumps(
                {k: v for k, v in raw.items() if k != 'entry_hash'},
                sort_keys=True, default=str,
            ).encode()).hexdigest()
            if recomputed != raw.get('entry_hash'):
                problems.append("entry_hash mismatch (content altered)")
            if problems:
                if first_bad is None:
                    first_bad = raw.get('seq')
                errors.append({"seq": raw.get('seq'), "problems": problems})
            prev_hash = raw.get('entry_hash', prev_hash)
            expected_seq = (raw.get('seq') or expected_seq) + 1
        return LedgerVerification(
            valid=not errors,
            entries=len(entries),
            first_bad_seq=first_bad,
            errors=errors,
        )


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
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

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
    ).hexdigest()

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
