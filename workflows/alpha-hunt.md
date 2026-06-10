# ALPHA-HUNT — iterative best-trade workflow

**Goal**: identify the single trade with the highest probability-weighted dollar profit per unit of
bounded downside ("most money"), for a permanent-capital family office with prime brokerage and
futures clearing. LsTo 4D + KISS. Anti-consensus filter: *if it's there and obvious, it's already
too late.*

## Loop structure

Each round has five phases. The loop runs until CONVERGENCE (below).

### Phase 1 — TAPE (refresh, never trust stale data)
Re-pull the regime on every round: rates & Fed pricing, credit spreads, vol surface, USD, commodity
curves (shape, not just level), event calendar. Any input older than 5 trading days must be
re-verified before it may support a numeric claim.

### Phase 2 — DIVERGE (parallel candidate generation)
Fan out ≥4 independent research lenses (e.g. volatility/derivatives, event-driven/special
situations, commodity second-order, credit/rates/FX cross-asset). Hard rules per lens:
- Excluded list: every idea already on the book or previously rejected — no re-pitches.
- Every candidate must name **who the forced or irrational seller is** (why the mispricing exists).
  No identifiable counterparty error → no idea.
- Primary-source citation with retrieval date for every number.

### Phase 3 — GATES (kill fast)
A candidate must pass ALL of:
- **G1 Bounded downside**: a structural floor (seniority, collateral, premium-defined risk,
  contractual terms, demonstrated mean reversion) — quantified, not asserted.
- **G2 Catalyst ≤ 12 months**: a dated event path, not "eventually the market agrees".
- **G3 Non-consensus evidence**: positioning, flows, or sentiment data showing the crowd is on the
  other side or absent. Sell-side unanimity = automatic fail.
- **G4 Verification**: every load-bearing number traced to a primary source dated within 5 days.
- **G5 Capacity**: executable at family-office size (flag ADV < $10M; spreads, borrow, margin).

### Phase 4 — SCORE
EV multiple = Σ pᵢ × payoffᵢ ÷ |max loss|, time-normalised to 12 months.
Tie-breakers: (1) convexity of the payoff (options > linear), (2) independence from the existing
book's dominant risk factor, (3) robustness of the downside bound under a 2-sigma stress.

### Phase 5 — RED TEAM
For the top candidate: argue the other side with the same research effort. Name the smartest
holder of the opposite position and steelman them. If the steelman survives contact with the
primary sources, the candidate is demoted and the loop continues.

## CONVERGENCE
Stop when either:
- A candidate beats the incumbent best trade's EV multiple by ≥1.5× and survives red team, **or**
- A full round produces no candidate that beats the incumbent → the incumbent stands as the answer.

The incumbent entering Round 1 (10 Jun 2026): **UAL Jan-27 call spreads + deferred OTM WTI calls**
(fuel-shock mean reversion priced by the oil forward curve but not by airline equities).
EV multiple ≈ 2.0–2.5× on premium, 6–9 months, bounded at −1.0× premium.

## Standing rules
- UK English, dollar denomination. No fabricated figures. Numeric claim ⇒ cited primary source.
- Preliminary research, not investment advice.
- Output of each round: ranked candidate table, gate results, red-team verdict, decision
  (CONVERGE or LOOP), and the updated incumbent.
