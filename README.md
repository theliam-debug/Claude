# LsTo Decision-Support Toolkit

Two packages that together give a decision maker AI-assisted analysis with
real-data grounding, ethics standards, and a tamper-evident accountability
trail:

| Package | Purpose |
|---|---|
| [`lsto_workforce`](#lsto-agent-workforce) | Governance harness for the LsTo Agent Workforce: charter, evidence provenance, accountability gates, hash-chained audit ledger, decision briefs, calibration scorecard |
| [`derivatives_strategies`](#derivatives-strategies-v3) | Policy-driven options overlay analytics: pricing, IV surface, dividend/assignment analysis, policy gates, deterministic recommendations |

Governance standard: [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md) ·
Standing gap analysis: [`docs/WORKFORCE_AUDIT.md`](docs/WORKFORCE_AUDIT.md)

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

---

## LsTo Agent Workforce

`lsto_workforce` turns "some agent sessions produced a conclusion" into a
governed decision process:

- **Charter as code** — roles, decision-rights matrix, ethics principles,
  and a registry of allowed data sources; the charter hash is stamped into
  every decision record.
- **Evidence with provenance** — every claim cites a registered source with
  a reliability tier (primary / secondary / internal / model_estimate),
  retrieval time, data as-of date, and payload hash. Model estimates never
  masquerade as measurements.
- **Accountability gates** — Provenance, EvidenceSufficiency, Freshness,
  RoleCoverage, RedTeam (dissent must be resolved in writing), Ethics
  (sensitive categories force review; prohibited content blocks without
  override), ConflictOfInterest, Calibration, HumanApproval (named human
  required at HIGH/CRITICAL; never overridable).
- **Tamper-evident ledger** — every step is appended to a SHA-256
  hash-chained JSONL ledger; `verify-ledger` detects any edit, deletion, or
  reordering.
- **Decision briefs** — recommendation, confidence, falsifiable forecast,
  alternatives, "what would change our mind", evidence table, dissent
  verbatim, gate outcomes, record hash.
- **Scorecard** — process integrity plus Brier-scored forecast calibration.

### Quick start

```bash
# End-to-end demo decision (deterministic, offline)
python -m lsto_workforce demo --out ./out/workforce

# Verify the audit ledger's hash chain
python -m lsto_workforce verify-ledger ./out/workforce/workforce_ledger.jsonl

# Workforce performance scorecard
python -m lsto_workforce scorecard --records ./out/workforce/decisions

# Inspect the active charter (and its hash)
python -m lsto_workforce show-charter
```

### Using it from a session

```python
from lsto_workforce import (
    Workforce, ImpactTier, Evidence, Assessment, Dissent,
    DissentSeverity, Forecast, RoleType, SourceTier, render_brief,
)

wf = Workforce(ledger_path="out/wf/ledger.jsonl", records_dir="out/wf/decisions")
rec = wf.open_request(
    question="Adopt vendor X for market data?",
    impact=ImpactTier.HIGH, category="vendor", requested_by="liam",
    as_of="2026-07-23",
)
wf.add_evidence(rec.decision_id, Evidence.create(
    claim="Vendor X SOC 2 Type II report is current (2026-05).",
    source_name="SEC EDGAR", source_tier=SourceTier.PRIMARY,
    as_of="2026-05-31", ref="edgar:...", method="api",
))
# ... assessments for each required role, red-team dissent + resolution ...
wf.set_recommendation(rec.decision_id, "Adopt with a 90-day pilot.", 0.7,
                      what_would_change_our_mind=["pilot SLA breaches"],
                      forecast=Forecast("Pilot meets SLA", 0.7, "2026-11-01"))
wf.finalize(rec.decision_id)          # -> PENDING_APPROVAL (HIGH tier)
wf.approve(rec.decision_id, "liam")   # named human
record = wf.finalize(rec.decision_id) # -> APPROVED
print(render_brief(record))
```

A custom charter YAML can extend sources, sensitive categories, and
per-tier requirements: `python -m lsto_workforce demo --charter my.yml`.

---

# Derivatives Strategies v3

**Institutional, Policy-Driven Options Overlay Toolkit**

A packaged, testable, auditable engine for options strategy analysis supporting:
- Market data ingestion via pluggable providers
- Implied volatility surface building
- Discrete dividends and early exercise gating
- Transaction cost modeling
- Policy engine with hard/soft gates
- Margin model hooks
- Deterministic recommendations and hash-chained audit logging

> **Note:** This is analytics and workflow tooling. It does NOT implement
> broker execution, credential storage, or live trading.

## Quick Start

```bash
# Run with demo provider (built-in sample data)
python -m derivatives_strategies run --out ./out

# Run with CSV data + policy + positions. --as-of pins the valuation date
# (the example data is dated 2025-01-15).
python -m derivatives_strategies run \
    --data examples/data \
    --policy examples/policy.example.yml \
    --positions examples/positions.example.json \
    --as-of 2025-01-15 \
    --out ./out

# Provide margin inputs so MarginGate can evaluate
python -m derivatives_strategies run --out ./out \
    --margin-used 20000 --margin-available 30000
```

### Outputs

| File | Description |
|------|-------------|
| `run.json` | Run metadata: engine version, provider, as-of, input paths, portfolio config, policy hash, ledger anchor |
| `recommendations.json` | Detailed recommendations with gate results |
| `orders.json` | Order intents for approved recommendations |
| `risk_report.md` | Human-readable risk report |
| `ledger.jsonl` | Hash-chained append-only audit log (verify with `Ledger.verify()`) |

## Architecture

```
derivatives_strategies/
├── data/           # Data models and providers
├── options/        # Pricing and Greeks (incl. escrowed-dividend binomial)
├── surface/        # IV solver and vol surface
├── dividends/      # Discrete dividend analysis
├── costs/          # Transaction cost model
├── policy/         # Gates and policy engine
├── margin/         # Margin model hooks (Reg-T approximation)
├── engine/         # Recommendation engine and CLI
└── monitoring/     # Hash-chained ledger and reporting
```

## Data Providers

**Demo Provider** — deterministic synthetic data for AAPL and MSFT
(realistic chains, quarterly dividends spanning two years, 5.25% rate).

**CSV Provider** — reads `spot.csv`, `chain.csv`, `dividends.csv`,
`rates.csv` from a directory. Structural problems (missing columns) raise
immediately with the column names; malformed rows are skipped and collected
in `provider.load_warnings`; `call/put` and `c/p` type codes are accepted.
Pass `--as-of YYYY-MM-DD` when the data is historical.

## Policy Configuration

Policies are YAML (parsed with PyYAML — full YAML syntax supported):

```yaml
name: "covered_call_conservative"
version: "1.0"

defaults:
  dte_min: 7
  dte_max: 45
  delta_min: 0.15
  delta_max: 0.35

gates:
  liquidity:
    max_spread_pct: 0.20
    min_open_interest: 100
    hard: true
  dividend:
    days_before_ex: 5
    hard: true
  margin:
    max_utilization: 0.80
    hard: true
  dte:
    min: 7
    max: 45
    hard: false  # Warning only

event_calendar:
  "2025-01-28":
    - "AAPL Earnings"   # symbol-scoped: blocks AAPL only
  "2025-01-29":
    - "FOMC Decision"   # macro term: blocks all symbols

overrides: []
  # - gate: LiquidityGate
  #   reason: "LOW_LIQUIDITY_APPROVED"
  #   authorized_by: "risk_manager"
  #   timestamp: "2025-01-15T10:00:00Z"
  #   expires: "2025-01-20T00:00:00Z"   # respected; expired overrides ignored
```

### Available Gates

| Gate | Purpose | Hard/Soft |
|------|---------|-----------|
| `LiquidityGate` | Bid-ask spread and volume requirements | Hard |
| `EventGate` | Earnings/FOMC blackouts (symbol-scoped; macro events global) | Hard |
| `DividendGate` | Early assignment risk protection (caution window warns, never blocks) | Hard |
| `MarginGate` | Margin utilization limits (skips only when no margin data given) | Hard |
| `RollCreditGate` | Ensures rolls generate real net credit (engine-computed, costs included) | Hard |
| `ConcentrationGate` | Exposure limits — blocks exposure-adding opens; warns on rolls/closes of existing positions | Hard |
| `DTEGate` | Days-to-expiry constraints | Soft |
| `DeltaGate` | Delta range constraints (uses engine-computed delta when quotes carry none) | Soft |

**Hard gates** block trades when violated (subject to authorized,
unexpired overrides on gates that allow them). **Soft gates** warn.

## Marking Conventions

### Pricing
- **Selling options:** conservative fill at bid (+ optional price improvement)
- **Buying options:** fill at ask

### Unit convention
All monetary fields in `Economics` (gross/net premium, max profit/loss) are
**total dollars for the whole action** — every contract, 100× multiplier
included. `breakeven` is per-share. Order-intent limit prices are per-share.

### Transaction Costs (defaults)
- Commission: $0.65/contract
- Exchange fees: $0.05/contract; ORF $0.03/contract
- SEC fee: 0.00278% of sale proceeds (sells only)
- Slippage: $0.02/contract + $0.001/contract × order size (per contract —
  no 100× multiplier)

### Greeks
Black-Scholes with continuous dividend yield: delta, gamma, theta (per
day; correct under q > 0), vega (per 1% vol). American diagnostics use an
escrowed-dividend CRR binomial tree (`options/american.py`) whose European
limit agrees with the escrowed BS price.

## Dividend Handling

For short calls, early assignment risk is flagged when the option is ITM,
extrinsic < PV(dividend), **and the ex-date is inside the monitoring
window** (further-out ex-dates report "monitor", not "at risk").
`PV = amount * exp(-rate * days_to_ex / 365)` (ACT/365).

## Audit Ledger

`ledger.jsonl` entries are SHA-256 hash-chained (`prev_hash`/`entry_hash`).
`Ledger.verify()` walks the chain and reports the first tampered, deleted,
or reordered entry. `run.json` records the chain anchor (entry count +
head hash) so whole-file replacement is detectable too. Policy hashes cover
the full effective configuration — loosening any threshold changes the hash.

## Testing

```bash
python -m pytest tests/ -q            # 187 tests
python -m pytest tests/ --cov=derivatives_strategies --cov=lsto_workforce
```

Coverage spans the math core (parity, finite-difference greeks, IV
round-trips, escrowed-tree references), the policy/workflow layer
(policy loading, gate logic, overrides, ledger integrity, CSV robustness,
CLI provider selection), margin models, and the full workforce governance
harness. Regression tests for the 2026-07 audit live in
`tests/test_audit_fixes.py` and `tests/test_math_fixes.py`.

## CLI Reference

| Argument | Description | Default |
|----------|-------------|---------|
| `--policy, -p` | Path to policy YAML | Built-in default |
| `--positions, -P` | Path to positions JSON | Demo positions |
| `--data, -d` | Data directory (selects CSV provider) | Demo provider |
| `--out, -o` | Output directory | `./out` |
| `--demo` | Force demo provider even with `--data` | off |
| `--as-of` | Valuation date for CSV data (YYYY-MM-DD) | today |
| `--portfolio-value` | Total portfolio value | `100000.0` |
| `--margin-used` | Current margin used ($) | `0.0` |
| `--margin-available` | Available margin ($); omit to skip margin checks | unset |

## Limitations

- **No live trading:** analysis tooling only
- **No network calls:** all data via files or the demo provider
- **Simplified margin:** Reg-T approximation; per-trade margin is not yet
  computed by the engine (margin inputs come from CLI flags)
- **European pricing core:** Black-Scholes base; escrowed-dividend binomial
  tree for American diagnostics
- **Single currency:** USD only

## License

MIT — see [LICENSE](LICENSE).
