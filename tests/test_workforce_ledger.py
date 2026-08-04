"""Tests for the hash-chained audit ledger: integrity and tamper detection."""

import json
import pytest

from lsto_workforce.ledger import GENESIS_HASH, HashChainLedger


@pytest.fixture
def ledger(tmp_path):
    return HashChainLedger(str(tmp_path / "ledger.jsonl"))


class TestChainBasics:
    def test_empty_ledger_head_is_genesis(self, ledger):
        assert ledger.head_hash == GENESIS_HASH
        assert ledger.entry_count == 0

    def test_append_extends_chain(self, ledger):
        e1 = ledger.append("system", "a", "dec-1", {"k": 1})
        e2 = ledger.append("system", "b", "dec-1", {"k": 2})
        assert e1.prev_hash == GENESIS_HASH
        assert e2.prev_hash == e1.entry_hash
        assert ledger.head_hash == e2.entry_hash
        assert ledger.entry_count == 2

    def test_reopen_resumes_chain(self, ledger, tmp_path):
        e1 = ledger.append("system", "a", "dec-1", {})
        reopened = HashChainLedger(str(tmp_path / "ledger.jsonl"))
        assert reopened.head_hash == e1.entry_hash
        e2 = reopened.append("system", "b", "dec-1", {})
        assert e2.prev_hash == e1.entry_hash
        assert e2.seq == 2

    def test_read_by_decision(self, ledger):
        ledger.append("system", "a", "dec-1", {})
        ledger.append("system", "a", "dec-2", {})
        ledger.append("system", "b", "dec-1", {})
        assert len(ledger.read_by_decision("dec-1")) == 2
        assert len(ledger.read_by_decision("dec-2")) == 1


class TestVerification:
    def test_clean_chain_verifies(self, ledger):
        for i in range(5):
            ledger.append("system", f"act{i}", "dec-1", {"i": i})
        result = ledger.verify()
        assert result.valid
        assert result.entries == 5
        assert result.errors == []

    def test_edited_payload_detected(self, ledger):
        for i in range(3):
            ledger.append("system", f"act{i}", "dec-1", {"i": i})
        lines = ledger.path.read_text().splitlines()
        tampered = json.loads(lines[1])
        tampered["payload"]["i"] = 999  # rewrite history
        lines[1] = json.dumps(tampered, sort_keys=True)
        ledger.path.write_text("\n".join(lines) + "\n")

        result = ledger.verify()
        assert not result.valid
        assert result.first_bad_seq == 2
        assert any("entry_hash mismatch" in p
                   for e in result.errors for p in e["problems"])

    def test_deleted_entry_detected(self, ledger):
        for i in range(3):
            ledger.append("system", f"act{i}", "dec-1", {"i": i})
        lines = ledger.path.read_text().splitlines()
        del lines[1]
        ledger.path.write_text("\n".join(lines) + "\n")

        result = ledger.verify()
        assert not result.valid
        assert result.first_bad_seq == 3  # seq 3 now follows seq 1

    def test_reordered_entries_detected(self, ledger):
        for i in range(3):
            ledger.append("system", f"act{i}", "dec-1", {"i": i})
        lines = ledger.path.read_text().splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        ledger.path.write_text("\n".join(lines) + "\n")

        result = ledger.verify()
        assert not result.valid
        assert result.first_bad_seq == 2  # file order: first row has seq 2

    def test_forged_tail_entry_detected(self, ledger):
        ledger.append("system", "a", "dec-1", {})
        forged = {
            "seq": 2, "timestamp": "2026-01-01T00:00:00Z", "actor": "attacker",
            "action": "human_approved", "decision_id": "dec-1",
            "payload": {"approved_by": "attacker"},
            "prev_hash": ledger.head_hash, "entry_hash": "f" * 64,
        }
        with open(ledger.path, "a") as f:
            f.write(json.dumps(forged) + "\n")

        result = ledger.verify()
        assert not result.valid
        assert result.first_bad_seq == 2

    def test_anchor_reports_head(self, ledger):
        e = ledger.append("system", "a", "dec-1", {})
        anchor = ledger.anchor()
        assert anchor["entries"] == 1
        assert anchor["head_hash"] == e.entry_hash
