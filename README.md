# Derivatives Strategies v3

**Institutional, Policy-Driven Options Overlay Toolkit**

A packaged, testable, auditable engine for options strategy analysis supporting:
- Market data ingestion via pluggable providers
- Implied volatility surface building
- Discrete dividends and early exercise gating
- Transaction cost modeling
- Policy engine with hard/soft gates
- Margin model hooks
- Deterministic recommendations and audit logging

> **Note:** This is analytics and workflow tooling. It does NOT implement broker execution, credential storage, or live trading.

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd derivatives_strategies

# Install in development mode
pip install -e .

# Or run directly
python -m derivatives_strategies run --help
```

### Basic Usage

```bash
# Run with demo provider (built-in sample data)
python -m derivatives_strategies run --out ./out

# Run with custom policy and positions
python -m derivatives_strategies run \
    --policy examples/policy.example.yml \
    --positions examples/positions.example.json \
    --out ./out

# Run with CSV data provider
python -m derivatives_strategies run \
    --data examples/data \
    --policy examples/policy.example.yml \
    --out ./out

# Also export results into a git-backable Obsidian vault
python -m derivatives_strategies run --out ./out --vault ./vault
```

### Outputs

After a run, the following files are produced in the output directory:

| File | Description |
|------|-------------|
| `run.json` | Run metadata and summary statistics |
| `recommendations.json` | Detailed recommendations with gate results |
| `orders.json` | Order intents for approved recommendations |
| `risk_report.md` | Human-readable risk report |
| `ledger.jsonl` | Append-only audit log (JSON lines format) |

## Obsidian Vault Export

Pass `--vault <dir>` to any `run` and the engine additionally writes an
[Obsidian](https://obsidian.md)-compatible vault of interlinked markdown notes,
designed to be version-controlled and backed up with the **Obsidian Git**
community plugin.

### What gets written

```
vault/
├── .obsidian/                  # Pre-configured app + Obsidian Git plugin
│   ├── community-plugins.json  # Enables "obsidian-git"
│   └── plugins/obsidian-git/data.json  # Auto commit/pull/push every 10 min
├── .gitignore                  # Ignores Obsidian workspace cache
├── Dashboard.md                # Map-of-content; running log of all runs
├── Runs/<run>.md               # One note per run (frontmatter + summary)
├── Symbols/<SYMBOL>.md         # One note per underlying (accumulates history)
└── Recommendations/<...>.md    # One note per recommendation
```

Notes carry YAML frontmatter (`type`, `symbol`, `action`, `approved`, `tags`,
…), `[[wikilinks]]` between runs, symbols, and recommendations, and nested
`#tags` (e.g. `action/roll`, `status/blocked`) so Obsidian's graph, search, and
backlinks work out of the box.

The export is **incremental**: `Symbols/` and `Dashboard.md` use managed marker
blocks (`<!-- ds:runs:start -->`) so re-running the engine appends to history
without overwriting your own hand-written notes. Run and recommendation notes
are rewritten per run.

### Backing up with Obsidian Git

The exporter pre-seeds the [Obsidian Git](https://github.com/Vinzent03/obsidian-git)
plugin so the vault stays mirrored to a remote (see the
[setup guide](https://forum.obsidian.md/t/the-easiest-way-to-setup-obsidian-git-to-backup-notes/51429)):

1. Generate the vault: `python -m derivatives_strategies run --vault ./vault`
2. Initialize git and push to your remote:
   ```bash
   cd vault
   git init && git add . && git commit -m "Initial vault"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```
3. Open the folder as a vault in Obsidian and **enable the Git community
   plugin** (it is already listed in `community-plugins.json`). Auto commit,
   pull, and push are pre-set to a 10-minute interval; adjust under
   *Settings → Community plugins → Git*.

## Architecture

```
derivatives_strategies/
├── data/           # Data models and providers
├── options/        # Pricing and Greeks
├── surface/        # IV solver and vol surface
├── dividends/      # Discrete dividend analysis
├── costs/          # Transaction cost model
├── policy/         # Gates and policy engine
├── margin/         # Margin model hooks
├── engine/         # Recommendation engine and CLI
└── monitoring/     # Ledger, reporting, and Obsidian vault export
```

## Data Providers

### Demo Provider

Built-in provider with deterministic synthetic data for AAPL and MSFT:
- Realistic option chains with multiple expiries
- Quarterly dividend schedules
- Standard risk-free rate (5.25%)

### CSV Provider

Read market data from CSV files:

```
data/
├── spot.csv      # symbol,bid,ask,last,timestamp
├── chain.csv     # symbol,expiry,strike,option_type,bid,ask,...
├── dividends.csv # symbol,ex_date,amount,record_date,pay_date
└── rates.csv     # as_of_date,rate,tenor_days
```

## Policy Configuration

Policies are defined in YAML format:

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
    - "AAPL Earnings"
```

### Available Gates

| Gate | Purpose | Hard/Soft |
|------|---------|-----------|
| `LiquidityGate` | Bid-ask spread and volume requirements | Hard |
| `EventGate` | Earnings/FOMC blackout periods | Hard |
| `DividendGate` | Early assignment risk protection | Hard |
| `MarginGate` | Margin utilization limits | Hard |
| `RollCreditGate` | Ensure rolls generate credit | Hard |
| `ConcentrationGate` | Position concentration limits | Hard |
| `DTEGate` | Days-to-expiry constraints | Soft |
| `DeltaGate` | Delta range constraints | Soft |

**Hard gates** block trades when violated.
**Soft gates** warn but allow trades to proceed.

## Marking Conventions

### Pricing

- **Selling options:** Conservative fill at bid (+ optional price improvement)
- **Buying options:** Fill at ask
- All prices use mid-market for analysis, conservative fills for economics

### Transaction Costs

Default cost model includes:
- Commission: $0.65/contract
- Exchange fees: $0.05/contract
- ORF: $0.03/contract
- SEC fee: 0.00278% of sale proceeds
- Slippage estimate: $0.02/contract + volume-based component

### Greeks

Greeks are computed using Black-Scholes with:
- Delta: Rate of change vs underlying
- Gamma: Rate of change of delta
- Theta: Daily time decay (negative for long options)
- Vega: Sensitivity to 1% vol change

## Dividend Handling

### Early Assignment Risk

For short calls, early assignment may be optimal when:
1. Option is in-the-money
2. Extrinsic value < PV(upcoming dividend)
3. Ex-date is before option expiry

The `DividendGate` automatically detects and blocks high-risk positions.

### Dividend PV Calculation

```python
PV = dividend_amount * exp(-rate * days_to_ex / 365)
```

Uses ACT/365 day count convention.

## Output Formats

### Recommendation Structure

```json
{
  "run_id": "uuid",
  "timestamp": "2025-01-15T10:00:00Z",
  "position": {
    "symbol": "AAPL",
    "quantity": -1,
    "position_type": "call",
    "strike": 180.0,
    "expiry": "2025-02-21"
  },
  "action": "roll",
  "target_strike": 185.0,
  "target_expiry": "2025-03-21",
  "gate_results": [...],
  "economics": {
    "gross_premium": 150.00,
    "transaction_costs": {...},
    "net_premium": 145.50
  },
  "greeks": {
    "delta": 0.28,
    "gamma": 0.015,
    "theta": -0.08,
    "vega": 0.35
  },
  "approved": true,
  "warnings": []
}
```

### Ledger Entry

Each action is logged to `ledger.jsonl`:

```json
{
  "run_id": "uuid",
  "timestamp": "2025-01-15T10:00:00.123Z",
  "action": "recommendation",
  "inputs_hash": "abc123...",
  "policy_hash": "def456...",
  "details": {...}
}
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test module
python -m pytest tests/test_iv_solver.py -v

# Run with coverage
python -m pytest tests/ --cov=derivatives_strategies
```

### Test Coverage

- **IV Solver:** Convergence on known prices, edge cases
- **Dividend Gate:** Early assignment detection, ITM/OTM handling
- **Surface:** Interpolation, monotonicity, determinism
- **Policy:** Gate evaluation, blocking logic, warnings

## Development

### Adding a New Gate

1. Create gate class in `derivatives_strategies/policy/gates.py`:

```python
class MyGate(Gate):
    def __init__(self, threshold: float, hard: bool = True):
        super().__init__(name="MyGate", hard=hard)
        self.threshold = threshold

    def evaluate(self, context: GateContext) -> GateResult:
        # Implement evaluation logic
        if some_condition:
            return self._make_result(True, "Gate passed")
        return self._make_result(False, "Gate failed")
```

2. Add to policy engine in `derivatives_strategies/policy/engine.py`

3. Add tests in `tests/test_policy.py`

### Adding a New Data Provider

Implement the `DataProvider` interface:

```python
class MyProvider(DataProvider):
    def get_chain(self, symbol: str) -> Optional[Chain]: ...
    def get_spot(self, symbol: str) -> Optional[SpotQuote]: ...
    def get_dividends(self, symbol: str, ...) -> list[DividendEvent]: ...
    def get_risk_free_rate(self, ...) -> RateData: ...
    def get_symbols(self) -> list[str]: ...
    def get_as_of_date(self) -> str: ...
```

## Configuration Reference

### Environment Variables

None required. All configuration via CLI arguments and policy files.

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--policy` | Path to policy YAML | Built-in default |
| `--positions` | Path to positions JSON | Demo positions |
| `--data` | Path to data directory | Demo provider |
| `--out` | Output directory | `./out` |
| `--demo` | Use demo provider | `true` |
| `--portfolio-value` | Total portfolio value | `100000.0` |
| `--vault` | Obsidian vault directory for note export | None (disabled) |

## Limitations

- **No live trading:** This is analysis tooling only
- **No network calls:** All data must be provided via files or demo
- **Simplified margin:** Reg-T approximation for analysis only
- **European pricing:** Black-Scholes base; binomial tree for American diagnostics
- **Single currency:** USD only

## License

[License information]

## Contributing

[Contribution guidelines]

---

*Generated by derivatives_strategies v3*
