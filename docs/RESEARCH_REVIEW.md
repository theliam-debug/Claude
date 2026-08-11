# Investment Research Practice — Retrospective (2026-02 → 2026-08)

Scope: every stock/investment research artifact reachable from this session —
this repository and its five branches, the five GitHub pull requests, the
Dropbox research workspaces (`Equity Reports/`, `equity reports/`,
`Private Credit BDC Research — April 2026/`), and the Google Drive investment
files. Method: read the artifacts, then verify the structural claims by
executing against the repo rather than asserting them.

Companion document: [`RESEARCH_PLAYBOOK.md`](RESEARCH_PLAYBOOK.md) — the
standard distilled from what worked here. This document is the evidence; the
playbook is the instruction.

**Boundary of this review.** Claude.ai chat transcripts are not readable from
a Claude Code session. Session IDs appear in commit trailers
(`session_01WXvYEF…`, `session_01LzJVdk…`, `session_01VLX59…`,
`session_01VhdCxH…`, `session_01G5cAXt…`) but their conversations cannot be
retrieved. Everything below is drawn from durable artifacts. That gap is
itself a finding — see §4.1.

---

## 1. What was actually built

| Date | Artifact | Location |
|---|---|---|
| 2026-02-01 | `derivatives_strategies v3` — options overlay engine, 52 tests | repo `9112ed7` |
| 2026-02-07 | ServiceNow (NOW) equity research memo | Drive |
| 2026-03-07/08 | META research plan + institutional memo + source PDFs | Dropbox `equity reports/META/` |
| 2026-04-04 → 04-17 | **Private Credit BDC forensic programme** — engineered prompt, master report, 12 numbered workstreams, securities-counsel review, published article | Dropbox `Private Credit BDC Research — April 2026/` |
| 2026-04-30 | MSFT sell-side source set (Morningstar / BofA / Morgan Stanley) + extracted text | Dropbox `Equity Reports/MSFT/` |
| 2026-05-11 | `build_lsto_research_pnl_v3.py` — research P&L attribution | Dropbox `Equity Reports/` |
| 2026-06-10 | **alpha-hunt** — iterative best-trade loop, Rounds 1–3 | repo PR #3 |
| 2026-06-14 | `derivatives_strategies.research` — MCP source registry, equity/futures briefs | repo PR #4 |
| 2026-07-13 → 07-20 | **asymmetric-opportunity-scan** — hash-chained, multi-agent, source-ledgered scans | Dropbox `Equity Reports/` |
| 2026-07-23/24 | `lsto_workforce` governance harness; 24 audited defects fixed; 197 tests | repo PR #5 (merged) |
| 2026-08-04 | `lsto_earnings_continuation_v1` — pre-registered, locked strategy | Dropbox `Equity Reports/` |
| 2026-08-05 | BROXF, Preferred-Hybrid-35 single-name work | Dropbox `Equity Reports/` |

Six months, five distinct research programmes, converging on a steadily more
rigorous method. The method improved faster than the outputs were preserved.

---

## 2. What worked — and why

### 2.1 Pre-loading a verified fact base into the prompt

`12 — Prompts & Methodology/PRIVATE_CREDIT_DEEP_RESEARCH_PROMPT.md` spends
~1,500 words on **"CONTEXT: WHAT HAS ALREADY HAPPENED … confirmed and should
be treated as established facts"** — named entities, exact figures, exact
dates — *before* it asks a single question.

**Why it worked.** It removes the model's need to guess or shakily retrieve the
foundations, and it sets a specificity floor: every answer must be at least as
concrete as the setup. Contrast the alpha-hunt memos, where the load-bearing
option premiums were never pulled and the entire trade stayed conditional.

### 2.2 Decomposition into numbered parts naming the *mechanism* to quantify

Not "analyse the BDC crisis" but: decompose the non-accrual gap into
(a) PIK as shadow default, (b) amend-and-extend, (c) the TDR loophole,
(d) liability management exercises, (e) build the true-distress waterfall.

**Why it worked.** Each sub-part is independently checkable and independently
rejectable. Generality has nowhere to hide.

### 2.3 Stating your own prior and inviting its falsification

> "My prior research suggests 15-20%. **Validate or challenge this.**"

**Why it worked.** The cheapest anti-sycophancy device available. It converts
the model from *agreeing with the frame* to *adjudicating the frame*.

### 2.4 Rounds that kill the previous round's answer on a **new axis**

The alpha-hunt sequence is the clearest demonstration in the corpus:

- **Round 1** — long TTF Q1-27 €60/€120 call spreads, EV ~3–4×. Converged.
- **Round 2** — steelman *destroys the structure while confirming the physics*:
  managed-money length already elevated and call skew the most expensive part
  of the surface (so the trade failed its own G3 non-consensus gate); El Niño
  96% for D-J-F; EU target already relaxed 90%→80%; and Atlantic-basin US LNG
  re-supply of ~6+ Bcf/d landing **exactly in the Q1-27 window** against a
  Qatari hole of ~1.7 Bcf/d. Re-pitched to Cal-28, where the bear case does
  not reach.
- **Round 3** — venue constraint kills the *instrument*: Schwab clears CME/Cboe,
  not ICE Endex. Thesis re-expressed as VG Jan-2028 $15/$25 call spreads.

**Why it worked.** Three independent classes of error — *is the thesis true?*,
*is this the right structure?*, *can we actually trade it?* — got attacked
separately. The thesis survived all three only because it was held separate
from the expression and the venue.

Round 2 also demonstrates genuine verification rather than confirmation: it
**corrected Round 1's ranking** (WEYS was rated robust; docket analysis showed
it most exposed — "claims filed ≠ plaintiff status"), **corrected its
provenance** ("S4/S6" → "Trains 4 and 6"), and found Round 1 had *understated*
its own case (2–4 year turbine lead time vs Al-Kaabi's own 3–5 year public
guidance). Real verification moves numbers in both directions.

### 2.5 "Name the forced or irrational seller" as the idea generator

alpha-hunt Phase 2 hard rule: *"Every candidate must name who the forced or
irrational seller is. No identifiable counterparty error → no idea."*

It produced the two best-mechanised ideas in the corpus:
- **HBB / BARK** — a tariff-refund claim worth 15–17% of market cap that ASC 450
  gain-contingency accounting keeps off every screen. *"Nobody is forced to
  sell — they're blind."*
- **VG** — post-IPO lockup expiry, 300M+ insider shares dumped, high-$20s → $12,
  entirely independent of cargo economics.

**Why it worked.** It converts "the market is wrong" (unfalsifiable) into a
named, checkable mechanism.

### 2.6 The output triple: report + source ledger + validation manifest

Every `asymmetric-opportunity-scan` run emits three files — the narrative
`.md`, a `-source-ledger.json` (100–250 KB), and a `-validation.json`. The
validation manifest re-verifies the **root and parent runs by SHA-256
(expected vs observed)** before continuing, re-fetches **every SEC EDGAR
locator** recording HTTP status and `checked_at`, and runs 29 named
deterministic checks.

**Why it worked.** It makes the research *chain* tamper-evident and
re-runnable. You can prove what you knew, when, and from where — which is
exactly what `lsto_workforce`'s ledger was designed for, deployed
independently and in production.

### 2.7 A firewalled challenger whose findings are **binding**

The 20 July manifest records four independent reviewers by agent ID:
`primary_equity_analyst`, `cio_lead`, `firewalled_risk_challenger`,
`compliance_monitor` — plus final `desk_verifier` and `completeness_critic`
gates. The challenger returned `FAIL_NO_SURVIVOR_NO_MONDAY_DOCKET` with
`binding_findings: [DEMOTE_DXLG_TO_REJECT, DEMOTE_INVE_TO_REJECT]`, and the
remediation record shows `ACCEPTED_DXLG_AND_INVE_DEMOTIONS`.

**Why it worked.** A red team whose findings are advisory gets overruled.
Binding findings plus a recorded remediation cycle is the difference between
review and theatre — as `GOVERNANCE.md` §3 already warns: *"a rubber-stamp
'no objections' assessment on a HIGH-impact call defeats the design."*

### 2.8 The system's willingness to return **nothing**

This is the strongest signal in the entire corpus.

- **20 July 2026**: SURVIVOR 0, HOLD 0, WATCH 3, REJECT 10.
  `quote_decision: SKIPPED_EMPTY_DOCKET` — no candidate cleared every
  non-price gate, so market pricing *could not cure* the unresolved
  entitlement, valuation, after-tax EV, access and tax requirements. The run
  also recorded its own scheduling bug honestly
  (`schedule_status: FIRED_4_HOURS_EARLY`) and then explained why it did not
  affect the decision.
- **4 August 2026**: `lsto_earnings_continuation_v1` status **`NO_TRADE`**, with
  `rejected_hypotheses.json` recording four rejected strategies *and their
  actual numbers* — sector rotation Sharpe ≈0.37 on ~33% max drawdown and
  ~30.6× turnover; trend breakout OOS Sharpe ≈0.04, cost-fragile; monthly
  sector strength OOS CAGR ≈ −0.23%.

**Why it worked.** A research process that can only produce "buy this" is a
marketing process. This one produces "nothing clears" with the arithmetic
attached, and preserves the negative results.

### 2.9 Pre-registration — lock the spec before you test

`lsto_earnings_continuation_v1` holds an immutable `strategy_spec.json`
protected by `strategy_lock.json`; development / validation / **locked OOS**
date partitions; promotion gates on sample size, expectancy, profit factor,
Sharpe, drawdown, robustness, ticker concentration and bootstrap lower bound;
and a separate `v2_exploratory` directory keeping exploration firewalled from
the locked project.

Its README states the epistemics correctly:

> "Passing unit tests proves that the code follows the specified rules on
> controlled inputs. **It does not prove profitability.**"

**Why it worked.** This is the only real defence against backtest overfitting,
and it is applied *structurally* rather than promised.

### 2.10 Refusing to substitute worse data

`rejected_hypotheses.json` is stamped `REJECTED_EXPLORATORY_ONLY` —
*"Exploratory Yahoo-derived results are discarded and may not be used for
promotion."* The pipeline returns `NO_TRADE` because point-in-time S&P 100
constituents and timestamped pre-release estimates are absent, and *"never
substitutes exploratory Yahoo data."* Every source-manifest row must be
`RECONCILED` with a SHA-256 and an as-of timestamp, and **estimates must have
been observable before the issuer release**.

**Why it worked.** Survivorship and lookahead bias are the quiet killers of
backtests. Refusing to run beats running on contaminated data.

### 2.11 Verify by execution, not by inspection

The repo audit (`WORKFORCE_AUDIT.md`) accepted **no finding that had not been
reproduced by running code**, and shipped a regression test with every fix
(52 → 197 tests). It caught the failure mode that matters most:

- the policy loader parsed a gates-only policy into **zero gates** while still
  stamping `policy_hash` into the ledger as if enforced — a total silent
  risk-control bypass;
- `RollCreditGate` used the underlying **spot price** as the roll's "net
  credit" — a documented hard gate that could never fire;
- slippage was silently **100×** the documented per-contract rate.

**Why it generalises to research.** The dangerous control is not the missing
one — it is **the control that looks present and is absent**. A gate you have
never watched fire is a gate you do not have.

### 2.12 Terminating in triggers and invalidation, never in analysis

Every strong artifact ends in an actionable frame. The BDC prompt's Part 7 is
an exposure-audit questionnaire, a relative-value ranking, hedging costs, an
opportunity map and *"a decision tree with specific observable triggers."*
Each alpha-hunt memo ends with dated catalysts, explicit invalidation
conditions, sizing, and an *"Execution checklist — the only things between
this memo and tickets."* The 20 July watchlist gives, per candidate, an
**exact catalyst trigger**, an **exact entry trigger**, and a **binding
limitation**.

**Why it worked.** It makes research falsifiable and time-bound, and converts
a memo into a monitorable position.

---

## 3. The honesty devices worth naming separately

Three habits recur across every good artifact and cost almost nothing:

1. **Flag unverified numbers inline, next to the number** — `"€4/MWh
   (UNVERIFIED — pull ICE screen)"` — not in a footnote, not in a caveats
   section.
2. **Segregate KNOWN FACT / REASONABLE ESTIMATE / SPECULATIVE ANALYSIS**, per
   the BDC prompt's standing instruction, and mirrored in code by
   `lsto_workforce`'s rule that `model_estimate` evidence never counts toward
   a primary-evidence quota.
3. **State the reliance limit plainly** — *"no live quote was collected, no
   trade is executable from this packet, and no probability precision was
   invented."*

---

## 4. What did not work

### 4.1 The calibration loop has never closed — the largest unclaimed win

`GOVERNANCE.md` §6 mandates monthly scorecard review; audit item **S8
(operating cadence) is still open by design**. Meanwhile:

- alpha-hunt Round 1's SOFR trade was conditional on the **same-day** CPI print
  (10 June 2026).
- Round 3's VG catalyst was the Q2-26 print (~7 August 2026) — now past.
- Every memo carries explicit probabilities and dated catalysts.

No scored outcome for any of it exists in any reachable artifact. The Brier
machinery in `lsto_workforce/metrics.py` has never been run against a real
research forecast. Six months of dated, probabilistic, falsifiable calls have
gone unresolved — which means the practice cannot yet tell which of its lenses
is any good.

### 4.2 Good work stranded on unmerged branches

PRs #2, #3 and #4 remain **open drafts**; only #5 merged. `workflows/alpha-hunt.md`
— arguably the single most reusable asset in the repository — exists only on
an unmerged branch and is therefore invisible to any new session that clones
the mainline. The repository has **no `main`/`master` branch at all**.

This is exactly audit finding **S1** recurring in a new place: *"every agent
session improvised its own process, leaving nothing reviewable or
repeatable."*

### 4.3 A live merge hazard (verified)

PRs #3 and #4 both branch from `9112ed7` (1 February), **before** PR #5 merged
the governance system on 4 August. Verified in this session:

```
git merge-base --is-ancestor 7e578b5 origin/claude/lsto-research-tools-7n005v        # fails
git merge-base --is-ancestor 7e578b5 origin/claude/asymmetric-opportunities-analysis # fails
```

Merging PR #4 as it stands would **delete** `lsto_workforce/`,
`docs/GOVERNANCE.md`, `docs/WORKFORCE_AUDIT.md` and all workforce tests
(−5,904 lines). Both branches need rebasing onto `7e578b5` before merge.

### 4.4 Two governance systems that never met

| | `lsto_workforce` (repo) | scan machinery (Dropbox) |
|---|---|---|
| Language | Python | JSON manifests |
| Provenance | Evidence + source tier + payload hash | `-source-ledger.json` + locator re-fetch |
| Integrity | SHA-256 hash-chained ledger | SHA-256 parent/root lineage |
| Adversary | `RedTeamGate`, dissent blocks | `firewalled_risk_challenger`, binding findings |
| Calibration | Brier scorecard | *(none)* |
| Human gate | `HumanApprovalGate` | `HOLD_FOR_PRINCIPAL_SIGNATURE` |

They solve the same problem, independently, in two languages, in two places,
and neither references the other. Worse: **the alpha-hunt memos were never run
through either.** Those are plainly HIGH-impact decisions — 4–6% of deployable
risk — with no decision record, no named approver, and no ledger entry.

### 4.5 Tooling built for a different problem than the research needed

Round 2 found this directly: *"the `derivatives_strategies v3` toolkit on the
sibling branch is equity covered-call analytics only — no commodity futures,
no multi-leg structuring. Not usable for TTF expression."*

The gap persists in PR #4: `research/registry.py` hardcodes **session-scoped
MCP server UUIDs** that are certainly dead, and `sources.py` defaults to
`SampleResearchSource` — deterministic *synthetic* data. A brief generated
today runs on fabricated inputs unless someone explicitly wires
`MCPResearchSource(call_tool=…)`. `mcp_schwab` (PR #3 branch) was built to
close that loop and was never connected.

### 4.6 The venue constraint arrived at Round 3 instead of Round 0

Two full rounds of high-quality work on ICE TTF died on a fact about the
clearing stack. Whether or not the constraint was known earlier, the lesson
for replication is unambiguous: **account, clearing, entitlement and tax
constraints belong in a standing charter that filters at generation time.**
By 20 July this lesson had been learned — access, tax and entitlement vetoes
are first-class gate reasons in the compliance monitor's findings.

### 4.7 Filing entropy

Two folders differing only in case (`equity reports/META/`,
`Equity Reports/MSFT/`); `Qnect_Anchor_Memo.docx` duplicated byte-identically
across two namespaces; and a file named
`…OM 030326--OLD ANALYSIS DO NOT USE NUMBERS.pdf` — a filename doing the job
a version register should be doing.

---

## 5. The finding underneath all the others

**The practice already contains its own best method.** Nothing in
§2 needs to be invented — it needs to be *collected*. The strongest components
are scattered across five locations and two languages, each invented in
isolation, none aware of the others:

- the engineered context pack (BDC, April)
- the four-lens divergence + forced-seller rule + gate ladder (alpha-hunt, June)
- the three-axis adversarial round structure (alpha-hunt, June)
- the report/ledger/validation triple with hashed lineage (scans, July)
- the firewalled binding challenger (scans, July)
- the charter, gates and Brier calibration (`lsto_workforce`, July)
- pre-registration, locked OOS and preserved negative results (earnings, August)

Consolidating them into one versioned, repo-resident standard is the entire
replication task. That standard is [`RESEARCH_PLAYBOOK.md`](RESEARCH_PLAYBOOK.md).

---

## 6. Recommended actions, in priority order

1. **Close the calibration loop.** Resolve every dated forecast from June's
   alpha-hunt rounds and July's scans against actual outcomes, score them, and
   publish the first scorecard. Until this runs, no lens can be ranked.
2. **Rebase and merge PR #3** so `workflows/alpha-hunt.md` and the three round
   memos reach the mainline. Rebase PR #4 onto `7e578b5` before it deletes the
   governance system.
3. **Create a real default branch.** A repository whose only branches are
   `claude/*` has no mainline for a new session to trust.
4. **Adopt one standard.** Run the next research cycle through
   `RESEARCH_PLAYBOOK.md`, emitting the report/ledger/validation triple *and* a
   `lsto_workforce` DecisionRecord.
5. **Set the operating cadence** (audit item S8): weekly scan, monthly
   scorecard, forecast resolution on judge-by dates.
6. **Wire live data or delete the offline default.** Either connect
   `MCPResearchSource`/`mcp_schwab`, or make `SampleResearchSource` refuse to
   produce a brief that could be mistaken for real analysis.

---

*Preliminary research process review, not investment advice.*
