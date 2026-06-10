# ALPHA-HUNT — Round 2 (10 June 2026)

*Preliminary research, not investment advice. Workflow: `workflows/alpha-hunt.md`.
Round 2 used four sharper lenses: adversarial steelman of the Round 1 winner, engineering
verification of the load-bearing physical claim, Federal Circuit docket analysis of the
event-driven sleeve's legal risk, and a repo scan for the structuring toolkit.
Decision: **CONVERGE on a re-pitched expression** — physics survives red team, structure does not.*

---

## What Round 2 changed

**Round 1 winner (TTF Q1-27 €60/€120 call spread) FAILS the red team at the structure level
while surviving on physics.** Re-pitched to Cal-28 length where the bear case does not reach.

### Steelman of original trade (verified, damaging)
- **Crowded, not contrarian**: managed-money net length on TTF already elevated post-Ras Laffan;
  call skew is steeply favoured — the upside wing is the *most expensive* part of the surface
  (Energy Aspects, CFTC COT 5 Jun).
- **El Niño 96% probability for D-J-F 2026/27** (NOAA CPC, ECMWF) → milder NW European winter
  with positive NAO bias — asymmetric downside for a cold-winter strike.
- **EU storage target relaxed from 90% to 80%** (European Commission) — gap closes by early
  November at modest injection pace.
- **US LNG re-supply lands directly in the Q1-27 trade window**: Plaquemines Phase 2 ramping,
  Corpus Christi Stage 3 Train 5 complete March 2026 (Cheniere 10-Q), Rio Grande P1 first LNG
  H1-27, Port Arthur P1 startup 2027 — combined Atlantic-basin incremental ≈ 6+ Bcf/d through
  end-2027 vs the Qatari hole of ~1.7 Bcf/d. **The market gets re-supplied exactly when the
  €60 strike would otherwise hit.**
- **Demand response is structural**: EU gas demand already –19% / ~80 bcm vs 2017–21 baseline
  (REPowerEU dashboard). €60+ TTF triggers further industrial rationing *before* the strike is
  ITM — the strike is essentially a ceiling, not a floor.
- **JKM–TTF collapsed from $0.95 (2024) to $0.23 (2025)** — Asia is not outbidding Europe at
  €60+ TTF; incremental cargoes flow west.

### What the steelman *did not* kill — and the re-pitch
- 12.8 mtpa lost through winter 26/27 is *near-certain* (QatarEnergy force majeure extended to
  mid-August already on long-term offtakers; no plausible liquefaction restart in 6 months).
- The "2–4 year turbine lead time" framing was actually *under-stating* QatarEnergy's own
  guidance: Minister al-Kaabi 19 March 2026 publicly guided **3–5 years for full repair**.
  The binding constraints are MCHE (Air Products/Linde, 18–30m) and reactor/cold-box
  reconstruction, not Frame 9E turbines (which Baker Hughes could re-prioritise).
- **NFE construction suspended post-strike** — the +32 mtpa offset that was supposed to arrive
  2026–27 is delayed, NFW startup slipped to 2031.
- **Skikda 2004 base rate**: one destroyed train rebuilt in ~9 years; two never rebuilt.
  Asymmetric tail toward "12.8 mtpa never returns at all".

**Conclusion**: the front of the curve is contested by the steelman; the back of the curve is
not. Re-pitching from Q1-27 to **Cal-28** captures the part the market actually mis-prices.

### Independent verifications that landed
- **Engineering**: damage assessment lined up with "extensive damage, sizeable fires" rather
  than "destroyed"; train designation is "Trains 4 and 6" not "S4/S6" (memo provenance flag).
  QatarEnergy 3–5y guidance is the official anchor. Source: ENR, Al Jazeera, Bloomberg,
  Baker Hughes Q1'26 8-K, Skikda restart literature.
- **Legal/docket**:
  - SCOTUS *Learning Resources v. Trump*, No. 24-1287, decided 20 Feb 2026, 6-3, Roberts (joined
    by Sotomayor, Kagan, Gorsuch, Barrett, Jackson) — IEEPA does not authorise tariff
    imposition.
  - USCIT refund order: Sr. Judge Richard K. Eaton, 4 March 2026, with 17 April supplemental
    order extending refunds to "finally liquidated" entries for non-litigants. Eaton
    distinguished *Trump v. CASA, Inc.*, 606 U.S. 831 (2025) on Uniformity Clause /
    28 U.S.C. § 1581 grounds.
  - DOJ Federal Circuit appeal filed 2 June 2026. **DOJ is contesting only the "finally
    liquidated non-litigant" sliver — plaintiff refunds and unliquidated-entry refunds are
    NOT contested.**
  - Stay motion ruling expected late June to mid-July; merits decision Q4-26/Q1-27 on
    expedited track.
  - **Round 1 ranking was wrong**: WEYS is *most exposed* (CAPE filings are administrative,
    not litigation; long collection window means most entries are finally liquidated). HBB
    is *most robust* **iff confirmed as a CIT plaintiff** — execution gate is the 10-K/10-Q
    litigation footnote.
- **Repo scan**: the `derivatives_strategies v3` toolkit on the sibling branch is equity
  covered-call analytics only — no commodity futures, no multi-leg structuring. Not usable
  for TTF expression. Need an external structuring desk.

---

## THE RE-PITCHED TRADE — Long TTF Cal-28 futures (with optional defined-risk overlay)

- **Instrument**: ICE TTF Cal-28 futures (calendar strip of all 12 months 2028, code TFM).
  Optional overlay: long Cal-28 €50 / short Cal-28 €70 call spread to bound premium-at-risk
  while preserving most of the convexity in the realistic outcome range. EUR exposure
  incidental.
- **Strategy bucket**: Global macro / commodity term-structure RV.
- **Thesis (the sharpened version)**: The market prices winter 26/27 ferociously (consensus
  Hormuz/storage trade) and prices 2027–28 as if everything normalises (Goldman 2027 €23, BofA
  €30). What the curve does NOT price: (i) QatarEnergy's own 3–5 year repair guidance means
  12.8 mtpa is still down through 2028 even on the optimistic case; (ii) NFE delays remove
  the +32 mtpa offset that was supposed to depress 2028 prices; (iii) by 2028 the US LNG
  ramp is fully delivered — no further incremental supply relief; (iv) Skikda asymmetric tail
  toward partial-permanent-loss. The Cal-28 strip should trade meaningfully above €23–30; on
  Brent-equivalent BTU parity with normalised crude in the mid-$70s, fair value sits around
  €35–45/MWh.
- **Asymmetry (estimated, conservative)**: Bear (~30%) US ramp fills entire Atlantic basin and
  QatarEnergy actually recovers 8+ mtpa by end-27 → Cal-28 holds €25–30 → −15% on futures /
  −1× premium on spread. Base (~50%) realistic recovery 2–4 mtpa by end-27, structural EU
  demand still –15% baseline, El Niño +1y, normalised oil mid-$70s → Cal-28 settles €38–45 →
  +30–50% futures / +6–8× on spread. Tail (~20%) Skikda-style permanent loss + cold winter +
  Russian transit disruption → €60+ → +60%+ futures / +12×+ spread. **EV ≈ 2.5–3.5× on
  defined-risk overlay; 25–35% IRR on outright futures.**
- **Catalysts (dated)**:
  - QatarEnergy quarterly updates on Trains 4/6 reconstruction (Q3/Q4 milestones).
  - NFE-1 restart guidance from QatarEnergy mid-26.
  - First US LNG cargo from each of Plaquemines P2, Rio Grande P1, Port Arthur P1 — each
    confirms supply trajectory but does not affect 2028.
  - EU winter 26/27 outturn (Mar 2027) — confirms storage-rebuild speed.
- **Invalidation**:
  - QatarEnergy retracts the 3–5y guidance with credible faster timeline (single biggest risk).
  - El Niño extends 2 winters and EU demand falls another 10%+.
  - Federal Circuit affirms IEEPA refund order without stay → no impact on TTF directly, but
    triggers HBB rotation that may compete for risk budget.
- **Sizing**: 4–6% of deployable risk (premium-at-risk on the spread overlay; futures sized
  to equivalent vega).
- **Confidence**: M-H — the physics is robustly verified; the trade economics depend on
  live ICE Cal-28 strip and option premiums which must be pulled before sizing.

---

## Round 2 ranked board (after gates, haircuts, red team)

| Rank | Trade | EV mult | Status |
|---|---|---|---|
| 1 | **TTF Cal-28 futures + €50/€70 call spread overlay** | 2.5–3.5× | **NEW INCUMBENT** — re-pitched from Round 1 winner |
| 2 | SOFR Dec-26 call spreads (fade hike whiplash) | 2.2× cond. | Conditional on May CPI ≤ consensus 4.2% YoY headline; FOMC 16-17 Jun is the gate |
| 3 | HBB long — *contingent on CIT plaintiff status verification* | 2.0× | DOJ appeal narrower than Round 1 assumed; verify 10-K litigation footnote |
| 4 | FRO Jan-27 calls (tanker reopening) | 2.0× | Unchanged, win-both-ways skew intact |
| 5 | UAL fuel-reversion package (R0 incumbent) | 1.5× | Slightly weaker — oil mean-reversion now consensus, less alpha |
| 6 | BARK long | 1.5× | Microcap noise; refund timing within FY27 unverified |
| 7 | TTF Q1-27 €60/€120 call spread (R1 winner) | 0.8× | **DEMOTED** — structure fails; physics re-targeted to #1 |
| 8 | WEYS long | 1.1× | **DOWNGRADED** — claims-filed ≠ plaintiff status; exposed to DOJ appeal |

### Execution gates (the only items between this memo and tickets)
1. Live ICE TTF Cal-28 strip + Cal-28 €50/€70 option premiums.
2. May 2026 CPI print (released 8:30 ET this morning; consensus 0.5% MoM headline, 0.3% MoM
   core, 4.2% YoY headline) and the resulting SR3Z26 futures move.
3. HBB 10-K and 10-Q litigation footnote — is HBB a named plaintiff in any USCIT case?
4. WEYS — same plaintiff-status check before any further sizing.
5. FRO Jan-27 IV and chain depth.

### Cross-correlation note (sharpened)
The Cal-28 TTF trade has lower correlation with the rest of the book than the Q1-27 version did,
because it is *not* a Hormuz-normalisation play — it is a Qatari-capacity-and-NFE-delay play,
which is orthogonal to the oil curve. This *increases* its value as a portfolio additive even at
similar standalone EV.

**Loop status: CONVERGED at Round 2 on the re-pitched expression. Next trigger for Round 3:
(a) any of the five execution gates above resolves adversely, (b) QatarEnergy issues a retraction
of the 3–5y guidance, (c) Cal-28 TTF trades through €40 (thesis partially in, asymmetry
compressed).**
