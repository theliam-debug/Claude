# LsTo Agent Workforce — Gap Analysis & Remediation Record (2026-07-23)

Scope: the LsTo agent workforce system (the practice of running AI agent
sessions against LsTo's data stack to support decisions) and all versioned
artifacts in this repository. Method: three independent audit passes
(quantitative modules; workflow/policy modules; tests/packaging/docs), every
finding verified by executing code before being accepted, then fixed with
regression tests. This document is the standing record: what was wrong, what
was done, and what remains open.

## 1. System-level gaps (the workforce itself)

| # | Gap | Status |
|---|---|---|
| S1 | **The workforce had no versioned definition at all** — no roles, no decision rights, no evidence standards, no ethics rules; every agent session improvised its own process, leaving nothing reviewable or repeatable | **Fixed** — `lsto_workforce` package + `docs/GOVERNANCE.md`; charter is code, hashed into every decision |
| S2 | No accountability trail: prior sessions produced conclusions with no decision records, no provenance, no dissent capture | **Fixed** — DecisionRecord + hash-chained ledger; every step ledgered; briefs carry the record hash |
| S3 | No ethics standard: nothing prevented an agent output from resting on unsourced claims, model guesses dressed as data, or sensitive-domain calls without human review | **Fixed** — ProvenanceGate, EvidenceSufficiencyGate (model estimates never fill quotas), EthicsGate (sensitive categories force review; prohibited content blocks without override), HumanApprovalGate |
| S4 | No calibration loop: recommendations carried no confidence and were never scored afterward | **Fixed** — confidence + falsifiable forecasts required at HIGH/CRITICAL; Brier scoring in the scorecard |
| S5 | The flagship analytics tool ("auditable engine") had a non-tamper-evident audit log and a silently broken policy loader — the accountability layer beneath the workforce was unsound | **Fixed** — see sections 2–3 |
| S6 | No CI: nothing verified the toolchain kept working between sessions | **Fixed** — GitHub Actions workflow runs the suite + all three CLI smoke runs on 3.11/3.12 |
| S7 | No repo guide for future agent sessions (conventions, commands, invariants) | **Fixed** — `CLAUDE.md` |
| S8 | No scheduled operating cadence (routines) for recurring workforce duties (scorecard review, forecast resolution) | **Open** — deliberate: schedules should be set by the decision maker; recommended cadence in GOVERNANCE §6 |

## 2. derivatives_strategies — critical & high findings (all fixed)

Every item below was CONFIRMED by execution before fixing; each fix has a
regression test in `tests/test_audit_fixes.py` / `tests/test_math_fixes.py`.

| # | Finding | Fix |
|---|---|---|
| C1 | Hand-rolled YAML parser orphaned every nested section: the shipped example policy **crashed**, and a gates-only policy loaded with **zero gates** — total silent risk-control bypass, while `policy_hash` was still stamped into the ledger as if enforced | Replaced with `yaml.safe_load` (PyYAML now a declared dependency); None-section guards; unquoted-date normalization |
| C2 | `--demo` defaulted to always-true → `--data` could never activate the CSV provider; users following the README silently got demo prices presented as their data | `--demo` now opt-in; explicit `--data` selects CSVProvider; conflict resolved in favor of explicitness |
| C3 | `RollCreditGate` used the underlying **spot price** as the roll's "net credit" — a documented hard gate that could never fire | Engine now passes real roll economics (`net_credit`, total dollars, costs included) into gate context |
| C4 | `MarginGate` treated exhausted margin (`available <= 0`) as "no margin data" and passed | `margin_available=None` = no data (skip, marked `skipped`); `<= 0` with usage = 100% utilization → BLOCK; CLI gained `--margin-used/--margin-available` |
| C5 | `ConcentrationGate` hard-coded 1 contract (under-measured multi-lot positions by their full size) and blocked *managing* already-large positions | Quantity-aware notional; action-aware: OPEN blocks, ROLL/CLOSE/HOLD warn (maintenance adds no exposure) |
| C6 | Roll economics silently omitted the buyback cost when the current leg had no market quote — fictional credits | Rolls now require a current-leg quote; otherwise candidates are skipped and the recommendation carries an explicit warning |
| C7 | Overrides applied even when `override_allowed=False` and after `expires`; overrides were never ledgered | Both respected; `expires` compared to the evaluation date |
| C8 | `policy_hash` covered gate *names* only — loosening every threshold produced the identical hash | Hash now covers full gate configs, defaults, limits, strategy, calendar, and overrides |
| C9 | "Append-only" ledger had zero tamper evidence (no chaining, truncated 16-hex hashes, no verify API) and non-deterministic `inputs_hash` (unsorted `set` ordering) | SHA-256 hash chain (`prev_hash`/`entry_hash`), `Ledger.verify()` detects edits/deletions/reordering, full-length hashes, sorted symbols, ledger anchor written into `run.json` |
| C10 | `Recommendation.inputs_hash` omitted economics, gate results, and the approved flag — opposite outcomes hashed identically | Hash now binds run, position, action, targets, economics, gates, and approval |
| C11 | `DividendGate` hard/soft inversion: the "caution" branch **blocked** the very roll/close that removes assignment risk | Caution branch is now an explicit WARN regardless of the gate's hard flag |
| C12 | `buy_to_close` order intents carried **negative** limit prices | Positive per-share limit derived from close cost |
| C13 | Uncovered-stock recommendations hardcoded `approved=True` while carrying blocking gate results | Approval now reflects gate outcomes |
| C14 | Theta had the dividend-yield term sign-flipped in both branches (put theta could come out **positive**) | Corrected; matches finite differences to 1e-8 across q grid |
| C15 | American binomial tree was structurally inconsistent with discrete dividends (two different stock prices at one node; +10.6% overpricing in the audit case; bias did not shrink with steps) | Rewritten on the escrowed-dividend convention; matches the independent escrowed-CRR reference (1.1121) to 2e-3; European limit agrees with `option_price` |
| C16 | Tree had no σ≤0 or p∈[0,1] guards (σ=0 → ZeroDivisionError; σ=0.01,r=0.10 → ATM call "worth" 140) | Both guarded with actionable errors; dividends ≥ spot rejected in tree and BS pricing |
| C17 | `early_exercise_boundary` returned the first bisection midpoint everywhere (55.0 for all puts, 300.0 for all calls) | Rewritten as region-membership bisection; no-boundary steps omitted; put boundary shape and q=0-call emptiness verified |
| C18 | IV solver silently clamped impossible prices to 5.0 and returned unconverged iterates; price-space-only convergence let deep-ITM IVs come back as the untouched initial guess | Above-bound prices raise; non-convergence raises; Brent adds a vol-bracket criterion; Newton requires a stabilized iterate |
| C19 | `early_assignment_risk` ignored its own window (flagged HIGH risk 40 days out); `should_roll_before_dividend` could recommend rolls for dividends already paid | Window enforced with a distinct "monitor" message; passed ex-dates return no-roll |
| C20 | Slippage silently 100× the documented per-contract rate (7% of premium on a 1-lot) | Per-contract, matching every other fee and the README |
| C21 | Surfaces rebuilt per roll candidate (O(candidates × chain) IV solves; ~30× measured blowup) | One surface per position analysis, shared by all candidates |
| C22 | `Economics` mixed per-share and per-contract dollars in one object; reports compared them in a single table | Standardized: all monetary fields are total dollars for the action; documented on the model and in the report header |
| C23 | CSV provider: missing columns → raw `KeyError`; one bad cell aborted the whole load; unknown option types silently vanished; `as_of` locked to today with no override (example data evaluated at DTE −517) | Structural errors raise `CSVDataError` naming the columns; bad rows skip into `load_warnings`; `c`/`p` accepted, unknown types warned; `--as-of` CLI flag |
| C24 | EventGate: any symbol's event blocked every symbol ("MSFT Earnings" blocked AAPL) | Symbol-scoped with a macro-term allowlist (FOMC/CPI/… stay global) |

## 3. Medium/low findings

| # | Finding | Status |
|---|---|---|
| M1 | `setup.py` + `pyproject.toml` duplicated (and disagreed on) metadata; wheel discovery swept stray root dirs into the package | **Fixed** — setup.py removed; explicit `packages.find.include` |
| M2 | MIT license claimed in metadata with no LICENSE file; README placeholders | **Fixed** — LICENSE added; README updated |
| M3 | Deprecated `datetime.utcnow()` at 5 sites while claiming 3.12 support | **Fixed** — timezone-aware everywhere |
| M4 | Gate default drift (DTEGate 60 vs 45; DeltaGate 0.40 vs 0.35) | **Fixed** — aligned to documented defaults |
| M5 | Demo dividends vanished for as_of after mid-October (DividendGate vacuously passed) | **Fixed** — 8 quarters spanning two years |
| M6 | GOOGL present in example spot/positions but absent from chain.csv → permanent NoData block | **Fixed** — realistic GOOGL chain + dividend rows |
| M7 | Falsy-zero serialization dropped legitimate 0.0 values (rho, breakeven, annualized_return) | **Fixed** — `is not None` |
| M8 | `margin/model.py` was dead code (arithmetic verified correct, never called, zero coverage) | **Fixed** — `RegTMargin` is now wired into the engine: `MarginGate` evaluates the proposed roll's coverage-aware Reg-T requirement post-trade (covered contracts net to ~0; only genuinely naked contracts add margin), so the gate can block a trade the book cannot absorb. Under unit test. |
| M9 | Orchestration layer had ~0–38% test coverage; `load_policy` was imported by tests but never called | **Fixed** — 68 new regression tests target exactly the previously-dark paths (187 total, from 52) |
| M10 | Dividend at exactly `t_div == T` ignored (1.18 price cliff at the boundary); ATM smile-dedup order-dependence; deep-ITM American put quotes rejected by European bounds then flat-extrapolated | **Documented, open** — convention/edge items; acceptable for the current scope, listed here so they are chosen, not unknown |
| M11 | `ExpirySmile.get_iv` linear scan; repeated ISO date parsing in surface lookups; `validate_surface` recomputing slopes | **Open** — micro-efficiencies; not user-visible at current chain sizes |

## 4. Verified-good (independent checks that passed)

Black-Scholes prices against Hull reference values; put-call parity to
2.8e-14 across a 432-case grid including q>0; delta/gamma/vega/rho against
finite differences; IV round-trip across a 348-case grid; smile and
total-variance time interpolation against hand references; escrowed-forward
parity in `option_price`; dividend PV discounting conventions; EventGate
window arithmetic at boundaries; SEC fee applied to sells only; Reg-T margin
arithmetic (naked 20%/10% rules, covered/partial decomposition).

## 5. Residual risks the decision maker should know

1. **Analytics ≠ advice.** `derivatives_strategies` remains analysis
   tooling with documented simplifications (Reg-T approximation, European
   pricing core with binomial diagnostics, USD only, no live execution).
2. **The EthicsGate is a screen, not a verdict.** It routes decisions to
   human ethics review and blocks a keyword class of prohibited content; it
   cannot certify a decision as ethical. That judgment stays human.
3. **Ledgers prove integrity, not truth.** A hash chain shows records were
   not altered after the fact; it cannot make a bad input good — that is
   what the provenance/sufficiency gates and the data-steward role are for.
4. **Calibration needs time.** Brier scores are meaningless until forecasts
   resolve; resolve them on their judge-by dates (scorecard shows the
   backlog).
5. **The M10/M11 edge items remain open by choice** — tracked here rather
   than silently absent. Per-trade margin (M8) is now wired in, but it is a
   Reg-T *approximation* that treats the short leg conservatively (naked
   unless covered by shares in the same portfolio); it is not a substitute
   for the broker's own margin determination.
