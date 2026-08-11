# LsTo Investment Research Playbook v1

The operating standard for stock and investment research, distilled from six
months of practice. Every rule here earned its place by working at least once;
the evidence for each is in [`RESEARCH_REVIEW.md`](RESEARCH_REVIEW.md).

This supersedes `workflows/alpha-hunt.md` (June 2026, on the unmerged PR #3
branch), which it absorbs and extends with the source-ledger discipline of the
July scans, the pre-registration discipline of the August strategy work, and
the accountability gates already implemented in `lsto_workforce`.

**Standing frame:** UK English, USD denomination, permanent-capital family
office. Anti-consensus filter — *if it's there and obvious, it's already too
late.* Preliminary research, not investment advice.

---

## Phase 0 — CHARTER (write once, version it, load it every run)

Before any idea is generated, the run loads a charter stating what is even
*possible*. Two full rounds of excellent 2026 work on ICE TTF died on a
clearing fact; that belongs here, not in round three.

| Field | Content |
|---|---|
| Mandate | Objective, horizon, permanent capital, prohibited strategies |
| Venue & clearing | e.g. Schwab clears CME/Cboe — **not ICE Endex**; what dies as a result |
| Entitlements | Options approval level, futures clearing, borrow access, ADR/OTC access |
| Tax posture | Federal/state rates; after-tax EV is the only EV that counts |
| Size limits | % of deployable risk per idea; ADV/capacity floor |
| Excluded list | On the book, or previously rejected — no re-pitches |

A charter change is a versioned commit, never an in-session improvisation.
`lsto_workforce.charter` already implements this pattern in code, and stamps
its hash into every decision record.

---

## Phase 1 — TAPE

Re-pull the regime every round: rates and Fed pricing, credit spreads, the vol
surface, USD, commodity curve *shape*, the event calendar.

> Any input older than **5 trading days** must be re-verified before it may
> support a numeric claim.

---

## Phase 2 — CONTEXT PACK

Write the verified fact base **before** asking the question. This is the single
highest-leverage habit in the corpus (see the April BDC prompt).

- Every fact: value, entity, date, source, locator.
- Head it explicitly: *"the following are confirmed and should be treated as
  established facts."*
- **State your own prior and demand it be challenged** — *"My prior suggests
  15-20%. Validate or challenge this."*
- Name the specific entities to analyse. Not "software LBOs" but
  "Medallia ($6.4B, Thoma Bravo), Zendesk ($10.2B, 20+ BDC holders), …".
- Decompose the ask into numbered parts with lettered sub-questions, each
  naming **the mechanism to quantify** — not the topic to discuss.

---

## Phase 3 — DIVERGE

Fan out **≥4 independent lenses** (e.g. volatility/derivatives, event-driven,
commodity second-order, credit/rates/FX cross-asset). Per lens, hard rules:

1. **Name the forced or irrational seller.** Why does this mispricing exist,
   and who is on the other side by compulsion or blindness? *No identifiable
   counterparty error → no idea.* This rule generated the two best ideas of
   2026 (ASC 450 gain-contingency invisibility; post-IPO lockup supply).
2. Primary-source citation with retrieval date for every number.
3. Excluded list enforced — no re-pitches.

---

## Phase 4 — GATES (kill fast)

A candidate must pass **all** of:

| Gate | Test |
|---|---|
| **G1 Bounded downside** | A structural floor — seniority, collateral, premium-defined risk, contractual terms — **quantified, not asserted** |
| **G2 Dated catalyst ≤12m** | A dated event path, not "eventually the market agrees" |
| **G3 Non-consensus** | Positioning/flow/sentiment data showing the crowd is absent or opposite. Sell-side unanimity is an automatic fail — *and so is crowded length in the very wing you are buying* |
| **G4 Verification** | Every load-bearing number traced to a primary source dated within 5 days |
| **G5 Capacity & access** | Executable at size on the charter's venue, with entitlement, borrow and tax cleared. Flag ADV < $10M |
| **G6 After-tax EV > 0** | Conservative after-tax expected value, not gross |
| **G7 Route proof** | Route A ≥ 3.0× on the bounded-risk ratio, **or** Route B convexity quantified |

G3 is the gate most often failed by one's own prior winner: Round 2 killed
Round 1's TTF spread because managed-money length was already elevated and
call skew was the most expensive part of the surface.

---

## Phase 5 — SCORE

`EV multiple = Σ pᵢ × payoffᵢ ÷ |max loss|`, time-normalised to 12 months.

Tie-breakers, in order: (1) payoff convexity — options over linear;
(2) independence from the book's dominant risk factor; (3) robustness of the
downside bound under a 2σ stress.

Haircut the research agent's own numbers before ranking.

---

## Phase 6 — CHALLENGE (firewalled, binding)

Run by a **separate session or agent that has not seen the bull case's
reasoning**. Three roles minimum:

- **Risk challenger** — steelman the smartest holder of the opposite position
  with the same research effort. Attack on three independent axes:
  **is the thesis true? is this the right structure? can we actually trade it?**
  A thesis that survives may still lose its expression or its venue — that is
  the loop working, not failing.
- **Compliance monitor** — entitlement, tax, access, market-state vetoes.
  Closed-market quotes are never executable.
- **Completeness critic** — what modality was not run, what claim is
  unverified, what source unread?

**Findings are binding.** Record them as explicit verdicts
(`DEMOTE_X_TO_REJECT`) and record the remediation cycle that accepted them. An
advisory red team gets overruled; a binding one does not.

---

## Phase 7 — EMIT THE TRIPLE

Every run writes three files under a stable `<scan-id>`:

| File | Contents |
|---|---|
| `<scan-id>.md` | Narrative: frozen lineage, gate results, registry, watchlist with **exact catalyst trigger / exact entry trigger / binding limitation** per candidate, reject registry with binding reasons, reliance statement |
| `<scan-id>-source-ledger.json` | Every source: id, claim, official locator, as-of, retrieval time, payload hash |
| `<scan-id>-validation.json` | Deterministic checks, registry counts, reviewer verdicts, and **SHA-256 of the parent and root runs, expected vs observed** |

Before a continuation run may proceed it re-verifies its parent's hashes and
re-fetches every external locator, recording HTTP status and `checked_at`.

**Registry states:** `SURVIVOR` · `HOLD` · `WATCH` · `REJECT` · `EXCLUDED`.
Rejects and their reasons are preserved as lineage, never deleted.

For decisions above LOW impact, also open a `lsto_workforce` DecisionRecord so
the evidence tiers, dissent, named approver and ledger entry exist in code:

```python
wf = Workforce(ledger_path=..., records_dir=...)
rec = wf.open_request(question=..., impact=ImpactTier.HIGH, ...)
# evidence → assessments → red-team dissent + resolution → recommendation
wf.finalize(rec.decision_id)        # -> PENDING_APPROVAL
wf.approve(rec.decision_id, "liam") # named human
```

---

## Phase 8 — RESOLVE (the loop that has never run)

Every forecast carries a probability and a **judge-by date**. On that date it
is scored — no exceptions, no quiet expiry.

```bash
python -m lsto_workforce scorecard --records ./out/workforce/decisions
```

Track Brier score, hit rate, average confidence, and **which lens generated
each resolved call**. Without this the practice cannot tell which of its four
lenses is worth running.

**Cadence:** scan weekly · resolve forecasts on their judge-by dates ·
scorecard monthly. Rising override rates or a model-estimate share crowding
out primary evidence are early warnings.

---

## Convergence

Stop when either:

- a candidate beats the incumbent's EV multiple by **≥1.5×** and survives the
  binding challenge, **or**
- a full round produces no candidate that beats the incumbent — the incumbent
  stands.

**`NO_TRADE` is a valid, respected, final answer.** The 20 July 2026 scan
returned 0 survivors from 15 candidates and skipped market data entirely
because the docket was empty; the 4 August strategy project returned
`NO_TRADE` and preserved four rejected hypotheses with their actual Sharpes. A
process that can only produce "buy this" is a marketing process.

---

## Standing rules

1. **Never substitute worse data.** If the point-in-time inputs are absent,
   return `NO_TRADE` and list what is missing. Do not fall back to a
   convenience source. Estimates must have been observable *before* the event
   they predict.
2. **Flag unverified numbers inline, at the number** — `€4/MWh (UNVERIFIED —
   pull ICE screen)`. Never in a footnote.
3. **Segregate KNOWN FACT / REASONABLE ESTIMATE / SPECULATIVE ANALYSIS.** A
   model estimate never counts toward a primary-evidence quota.
4. **Verify by execution, not inspection.** The dangerous control is not the
   missing one — it is the control that *looks* present and is absent. A gate
   you have never watched fire is a gate you do not have.
5. **Pre-register before you test.** Lock the spec, partition dev / validation
   / untouched OOS, fix promotion gates in advance, keep exploratory work in a
   separate firewalled directory, and preserve rejected hypotheses with their
   numbers.
6. **End in triggers and invalidation, never in analysis.** Dated catalysts,
   exact entry triggers, explicit invalidation conditions, sizing, and the
   execution checklist that is the only thing between the memo and tickets.
7. **State the reliance limit plainly.** What was not verified, what is not
   executable, what precision was not invented.
8. **Nothing important lives only in a chat.** Session transcripts are not
   retrievable. If it matters, it is a committed file.

---

## Anti-patterns observed, and their fixes

| Anti-pattern | Fix |
|---|---|
| Venue/entitlement constraint discovered late | Phase 0 charter filters at generation time |
| Best workflow stranded on an unmerged branch | Standards live on the mainline, versioned |
| Dated forecasts never scored | Phase 8, on the judge-by date |
| Two governance systems, neither used on the research | One standard; triple + DecisionRecord |
| Brief silently generated from synthetic sample data | Wire live sources, or make the offline source refuse to emit a brief |
| Duplicated/near-identical artifacts across folders | One `<scan-id>` per run; lineage by hash, not by filename |

---

*Preliminary research process standard, not investment advice.*
