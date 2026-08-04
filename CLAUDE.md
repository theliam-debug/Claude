# Repository guide

Two Python packages, stdlib + PyYAML only, Python >= 3.11:

- `derivatives_strategies/` — policy-driven options overlay analytics
  (pricing, IV surface, dividend/assignment analysis, policy gates,
  recommendation engine, hash-chained audit ledger). Analysis tooling only:
  no broker execution, no network calls, no credential storage.
- `lsto_workforce/` — the LsTo Agent Workforce governance harness
  (charter, evidence provenance, accountability gates, tamper-evident
  ledger, decision records/briefs, calibration metrics).

## Commands

```bash
pip install -e ".[dev]"             # install both packages + pytest
python -m pytest tests/ -q          # full suite; must stay green
python -m derivatives_strategies run --out ./out           # demo run
python -m derivatives_strategies run --data examples/data \
    --policy examples/policy.example.yml \
    --positions examples/positions.example.json \
    --as-of 2025-01-15 --out ./out                          # CSV run
python -m lsto_workforce demo --out ./out/workforce        # workforce demo
python -m lsto_workforce verify-ledger <ledger.jsonl>      # audit check
```

## Conventions

- Frozen dataclasses for immutable facts; enums with string values;
  ISO-8601 string timestamps (UTC, `Z` suffix); `datetime.now(timezone.utc)`
  — never the deprecated `datetime.utcnow()`.
- Hashes are full SHA-256 over `json.dumps(..., sort_keys=True)`. Both
  ledgers are hash-chained; never write entries by hand — go through
  `Ledger.append` / `HashChainLedger.append`.
- `Economics` monetary fields are TOTAL DOLLARS for the whole action
  (all contracts, 100x multiplier included); `breakeven` is per-share.
- Cost-model fees are per contract; slippage carries no 100x multiplier.
- Gates return PASS/WARN/BLOCK. Hard gates block; a gate that cannot
  evaluate marks `details={"skipped": True}` rather than passing silently.
- Every bug fix ships with a regression test; the audit fixes live in
  `tests/test_audit_fixes.py`, `tests/test_math_fixes.py`.

## Governance

`docs/GOVERNANCE.md` defines the ethics and accountability standard for
the workforce; `docs/WORKFORCE_AUDIT.md` is the standing gap analysis.
Decisions above LOW impact require a named human owner — do not weaken
`HumanApprovalGate`, dissent handling, or ledger chaining without an
explicit human decision recorded in the PR description.
