# ALPHA-HUNT — Round 3: Schwab pivot (10 June 2026)

*Preliminary research, not investment advice. Workflow: `workflows/alpha-hunt.md`.
Execution constraint introduced: trades clear through Schwab. ICE Endex (TTF, JKM, Brent
options, LSGO cracks) are NOT available on Schwab Futures — Schwab clears CME Group
(NYMEX/COMEX/CBOT) and Cboe only. The Round 2 winner (long TTF Cal-28) dies as a direct
expression; the THESIS survives via a Schwab-native equity proxy.*

---

## THE TRADE — Long VG (Venture Global) Jan-2028 $15 / $25 call spreads

VG is the cleanest Schwab-listed expression of the Round 2 physical thesis (Qatari capacity
down through 2028 per Al-Kaabi 3–5y guidance + suspended NFE + Skikda asymmetric tail), with
an additional kicker that the Round 2 TTF Cal-28 trade did not have: **an identified forced
seller (post-IPO lockup insider supply) that has crushed the stock independent of cargo
economics**.

### Why VG, not EQNR or LNG

| | VG | EQNR | LNG (Cheniere) |
|---|---|---|---|
| Pure-play LNG export | ✓ 100% | ✗ mixed gas/oil/refining | ✓ tolling model |
| Spot/TTF leverage | ✓ 16% open sliver + Phase II adds more | Partial (22.5% TTF in internal pricing) | ✗ ~95% contracted |
| Schwab-executable | ✓ NYSE + LEAPS | ✓ ADR + options | ✓ NYSE |
| Forced-seller dynamic | ✓ Post-IPO lockup, 300M+ insider shares dumped | ✗ mature dividend stock | ✗ no |
| Phase II ramp into H2-27/28 thesis window | ✓ mid-2027 startup | n/a | ✗ Stage 3 already priced |
| 2026 EBITDA guidance | $8.2–8.5bn (RAISED 1 Jun) at $9.50–10.50/MMBtu | n/a | Stable |

### Key reads (10 Jun 2026)
- **Stock**: $12.44 close 9 Jun (–3% intraday). Range $12.40–12.84. Source: [stockanalysis.com/VG](https://stockanalysis.com/stocks/vg/).
- **Chain**: Jan 2027 and Jan 2028 LEAPS confirmed available. Source: [stockoptionschannel.com/VG](https://www.stockoptionschannel.com/symbol/vg/). Depth at $15/$25 strikes is the load-bearing unverified item.
- **2026 EBITDA raised guidance**: $8.2–8.5bn on liquefaction fees of $9.50–10.50/MMBtu; 494–523 cargos. Plaquemines Phase II financed without equity dilution. Source: [VG 8-K 1 Jun 2026](https://www.stocktitan.net/sec-filings/VG/8-k-venture-global-inc-reports-material-event-25d8466e9bb7.html).
- **Short interest**: 33.13M shares = **1.33% of float — NOT crowded short**. Source: [Finviz](https://finviz.com/quote.ashx?t=VG&ty=si).
- **Analyst PTs**: avg $15.68, low $5.05, high $17.85. Morgan Stanley $22 OW, Citi $17 (upgrade from $12). Source: [MarketBeat](https://www.marketbeat.com/stocks/NYSE/VG/forecast/).
- **The forced seller**: IPO lockup expired 23 July 2025; insiders dumped 300M+ shares into early 2026; stock fell from high-$20s to $12. CP2 funded via debt only, no further dilution. Forced supply has now largely cleared.

### Asymmetry (12–18 month hold)

| Case | Prob | Stock | $15/$25 call spread |
|---|---|---|---|
| Bear: Phase I LT contracts compress 27 EBITDA, US glut, Qatar restart fast | 25% | $9 (–28%) | −1.0× premium |
| Base: avg PT $15.68 hits by mid-27, normal Phase II ramp | 50% | $16 (+29%) | +1.2–1.8× premium |
| Bull: TTF tight on Qatar 3–5y persistence + Phase II spot upside; Citi/MS PTs hit | 25% | $22–25 (+77–100%) | +4.0–8.0× (capped at spread width) |

**EV ≈ +2.0× to +3.0× on premium at risk**, bounded loss −1.0× premium. Equal to or above the
Round 2 TTF Cal-28 trade, and uniquely *executable on the principal's stack*.

### Catalysts (dated)
- VG Q2-26 print (~7 Aug) — 2H26 cargo cadence and spot premium realisation.
- VG Q3-26 print (~Nov) — first Plaquemines Phase II construction milestones.
- Q1-27 EU storage burn-down outturn (Mar 2027) — confirms 27/28 setup.
- Plaquemines Phase II first cargo (mid-2027).
- QatarEnergy quarterly updates on Trains 4/6.

### Invalidation
- VG re-issues equity (low probability post the just-closed $2.25bn senior secured notes 1 Jun).
- Plaquemines Phase II startup slips past Q4-27.
- QatarEnergy retracts 3–5y guidance with credible faster timeline.
- US LNG ramp accelerates so fast the Atlantic basin floods through 2028.

### Sizing & execution gates
- **4–6% of deployable risk** in premium.
- **G1**: Pull live Jan-2028 chain at $15, $17.50, $20, $25. If <50 OI at $25 strike, switch to
  outright Jan-2028 $15 calls and accept higher premium-at-risk.
- **G2**: Confirm Schwab options approval level (Level 2+ needed for spreads — likely already
  in place given prior derivatives work in the repo).
- **G3**: IV-rank check. If single-name IV is at >90th percentile sector-wide, prefer ratio
  spread or diagonal (sell Jan-27 $15 against Jan-28 $15 long).
- **G4**: Open VG borrow rate (if running pair with short XOM as hedge to isolate gas exposure
  — optional).

---

## Schwab-executable bench (also alive after the constraint)

| Trade | Status | Note |
|---|---|---|
| SOFR Dec-26 call spreads (SR3Z26) | Schwab Futures clearable | Conditional on May CPI ≤ consensus 4.2% YoY; FOMC 16–17 Jun |
| FRO Jan-27 calls | NYSE-listed options | Win-both-ways tanker skew intact |
| UAL Jan-27 spreads + NYMEX CL Dec-26 calls (R0 incumbent) | Fully native | Oil mean-reversion now partially priced; lower EV than before |
| HBB equity long | NYSE-listed | Contingent on CIT-plaintiff confirmation in next 10-Q |

## What dies on Schwab (the explicit cost of the constraint)

- **ICE TTF / ICE Endex futures and options** (direct expression of the Round 2 winner) — must
  proxy via VG, EQNR, LNG, or NYMEX HH.
- **ICE Brent options, ICE LSGO crack spreads** — refining-margin short dies.
- **JKM on ICE** (CME has JKM but liquidity sits on ICE).
- **Direct European sovereign or EM USD sovereign bonds** above the desk's standing bond
  inventory.

The TTF physical thesis is preserved; the vehicle has changed from ICE futures + options to
NYSE-listed pure-play LNG export equity + LEAPS overlay. The asymmetry holds, the downside is
bounded, and the ticket is clickable.

**Loop status: CONVERGED on the Schwab-native expression. Next trigger for Round 4: any of
the four execution gates fails, VG breaks $10 without a corresponding TTF cal-28 retreat, or
QatarEnergy retracts the 3–5y guidance.**
