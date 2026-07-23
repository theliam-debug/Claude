"""
Tamper-evident, hash-chained audit ledger.

Improves on the plain JSONL ledger in derivatives_strategies: every entry
embeds the hash of the previous entry, so any edit, deletion, or reordering
of history breaks the chain and is detected by verify(). Deleting the whole
file remains detectable only by external anchoring — anchor() returns the
head hash, which the operator should record out-of-band (e.g. in a commit
message or a separate store).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from lsto_workforce.models import canonical_json, sha256_hex, utc_now_iso

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class ChainEntry:
    """One immutable ledger entry."""
    seq: int
    timestamp: str
    actor: str            # role name, "system", or a named human
    action: str           # e.g. "request_opened", "evidence_added", "override"
    decision_id: str
    payload: dict
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "decision_id": self.decision_id,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


def compute_entry_hash(
    seq: int,
    timestamp: str,
    actor: str,
    action: str,
    decision_id: str,
    payload: dict,
    prev_hash: str,
) -> str:
    """Hash over every field except entry_hash itself."""
    return sha256_hex(canonical_json({
        "seq": seq,
        "timestamp": timestamp,
        "actor": actor,
        "action": action,
        "decision_id": decision_id,
        "payload": payload,
        "prev_hash": prev_hash,
    }))


@dataclass
class VerificationResult:
    """Outcome of a full-chain verification."""
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


class HashChainLedger:
    """
    Append-only JSONL ledger with a SHA-256 hash chain.

    Entries are written synchronously; the head hash is kept in memory and
    re-derived from the file on open, so multiple sequential sessions extend
    the same chain.
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq, self._head = self._load_head()

    def _load_head(self) -> tuple:
        """Read the last entry to resume the chain; genesis if empty."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return 0, GENESIS_HASH
        last_line = ""
        with open(self.path, "r") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if not last_line:
            return 0, GENESIS_HASH
        last = json.loads(last_line)
        return last["seq"], last["entry_hash"]

    @property
    def head_hash(self) -> str:
        """Current chain head — record this out-of-band to anchor the ledger."""
        return self._head

    @property
    def entry_count(self) -> int:
        return self._seq

    def append(
        self,
        actor: str,
        action: str,
        decision_id: str,
        payload: Optional[dict] = None,
    ) -> ChainEntry:
        """Append an entry, extending the hash chain."""
        seq = self._seq + 1
        timestamp = utc_now_iso()
        payload = payload or {}
        entry_hash = compute_entry_hash(
            seq, timestamp, actor, action, decision_id, payload, self._head
        )
        entry = ChainEntry(
            seq=seq,
            timestamp=timestamp,
            actor=actor,
            action=action,
            decision_id=decision_id,
            payload=payload,
            prev_hash=self._head,
            entry_hash=entry_hash,
        )
        with open(self.path, "a") as f:
            f.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
        self._seq = seq
        self._head = entry_hash
        return entry

    def read_all(self) -> list:
        """All entries as dicts, in file order."""
        entries = []
        if self.path.exists():
            with open(self.path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        return entries

    def read_by_decision(self, decision_id: str) -> list:
        return [e for e in self.read_all() if e.get("decision_id") == decision_id]

    def verify(self) -> VerificationResult:
        """
        Walk the chain from genesis. Detects edited payloads, deleted or
        reordered entries, and forged hashes. Reports every broken link.
        """
        entries = self.read_all()
        errors = []
        first_bad = None
        prev_hash = GENESIS_HASH
        expected_seq = 1
        for e in entries:
            problems = []
            if e.get("seq") != expected_seq:
                problems.append(f"seq {e.get('seq')} != expected {expected_seq}")
            if e.get("prev_hash") != prev_hash:
                problems.append("prev_hash does not match prior entry (chain break)")
            recomputed = compute_entry_hash(
                e.get("seq"), e.get("timestamp"), e.get("actor"), e.get("action"),
                e.get("decision_id"), e.get("payload", {}), e.get("prev_hash"),
            )
            if recomputed != e.get("entry_hash"):
                problems.append("entry_hash mismatch (payload altered)")
            if problems:
                if first_bad is None:
                    first_bad = e.get("seq")
                errors.append({"seq": e.get("seq"), "problems": problems})
            prev_hash = e.get("entry_hash")
            expected_seq = (e.get("seq") or expected_seq) + 1
        return VerificationResult(
            valid=not errors,
            entries=len(entries),
            first_bad_seq=first_bad,
            errors=errors,
        )

    def anchor(self) -> dict:
        """
        Anchor summary for out-of-band storage: entry count + head hash.
        Committing this alongside the ledger makes whole-file replacement
        detectable too.
        """
        return {
            "entries": self._seq,
            "head_hash": self._head,
            "anchored_at": utc_now_iso(),
        }
