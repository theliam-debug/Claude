# LsTo Agent Workforce — Governance, Ethics & Accountability Standard

This document is the human-readable statement of the rules the
`lsto_workforce` package enforces in code. The machine-readable form is the
charter (`lsto_workforce/charter.py`, overridable via YAML); its hash is
stamped into every decision record, so an auditor can prove which rules
were in force for any given decision.

## 1. Operating principles

1. **Truthfulness.** Every factual claim in a decision traces to a
   registered, hashed evidence item. Claims without provenance do not pass
   the `ProvenanceGate`.
2. **Real-data primacy.** Model estimates and agent judgments are labeled
   `model_estimate` and never count toward primary-evidence quotas
   (`EvidenceSufficiencyGate`). A measurement and an inference are never
   presented interchangeably.
3. **Human accountability.** Agents advise; named humans decide. Every
   decision above LOW impact carries a named decision owner, and HIGH /
   CRITICAL decisions cannot finalize without a named human approver
   (`HumanApprovalGate` — never overridable).
4. **Auditability.** Every step — evidence, assessments, dissent,
   recommendations, gate results, overrides, approvals — is appended to a
   SHA-256 hash-chained ledger. Editing, deleting, or reordering history
   breaks the chain and is detected by `verify-ledger`.
5. **Dissent is a feature.** Red-team review is mandatory at HIGH and
   CRITICAL impact. Dissents are never deleted; MATERIAL and FATAL
   dissents block finalization until resolved in writing, and a FATAL
   dissent cannot be overridden away (`RedTeamGate`).
6. **Lawfulness and fairness.** Sensitive categories (personnel,
   legal/tax, health, lending, privacy, and similar) always require an
   ethics-reviewer assessment regardless of impact tier, and prohibited
   content (deception of regulators or counterparties, discrimination,
   sanctions evasion, misuse of inside information) blocks outright with
   no override (`EthicsGate`).
7. **Privacy.** Records carry the minimum necessary personal data — names
   appear only where accountability requires them (owners, approvers,
   override authorizers, dissent resolvers).
8. **Calibration.** Recommendations state confidence in [0, 1]. HIGH and
   CRITICAL decisions attach a falsifiable forecast with a judge-by date;
   resolved forecasts are scored (Brier) on the workforce scorecard. The
   `CalibrationGate` flags overconfidence (>95% on high-stakes calls) and
   missing "what would change our mind" conditions.
9. **Non-deception.** No output may be designed to mislead a counterparty,
   market, or regulator. This is a prohibited-content class, not a
   preference.
10. **Stop conditions.** Any role can halt a decision by filing a FATAL
    dissent. Overrides require a named human, a written reason, and a
    ledger entry; CRITICAL-tier decisions allow no overrides at all.

## 2. Decision rights matrix (default charter)

| Tier | Required roles | Min evidence (primary/internal) | Max evidence age | Red team | Ethics review | Human approval | Overrides |
|---|---|---|---|---|---|---|---|
| LOW | analyst | 1 (0) | 365d | – | category-driven | – | allowed |
| MEDIUM | analyst, risk | 2 (1) | 180d | – | category-driven | – | allowed |
| HIGH | analyst, steward, risk, red team, synthesizer | 3 (2) | 90d | required | required | **required** | allowed |
| CRITICAL | all seven roles | 5 (3) | 30d | required | required | **required** | **none** |

Impact tiers are assigned by reversibility and stakes, honestly — the
`RISK_OFFICER` mandate includes classifying the tier, and misclassifying a
CRITICAL decision as LOW to dodge rigor is itself an audit finding.

## 3. Roles

| Role | Mandate |
|---|---|
| research_analyst | Gather evidence from registered sources; cite every claim |
| data_steward | Verify provenance, freshness, and tier; reject unsourced input |
| risk_officer | Quantify downside, reversibility, exposure; set the impact tier |
| ethics_reviewer | Screen legal/fairness/privacy/deception concerns; escalate |
| red_team | Argue the strongest case against; file dissents, not soft notes |
| synthesizer | Produce the decision brief; preserve dissent verbatim |
| auditor | Verify ledger integrity and process compliance |

One agent session may fill multiple roles on LOW/MEDIUM decisions, but the
red team must be adversarial in substance — a rubber-stamp "no objections"
assessment on a HIGH-impact call defeats the design and should be treated
as a process violation by the auditor.

## 4. Data source registry

The workforce cites only registered sources, each with an honest
reliability tier:

- **primary** — origin/official data (SEC EDGAR, FRED, US Treasury, FINRA,
  BLS, ECB, FDIC, CourtListener, ClinicalTrials.gov, PubMed)
- **secondary** — reputable aggregators (FMP, MSCI, Schwab market data,
  MT Newswires, Consensus)
- **internal** — this repo's analytics (`derivatives_strategies` runs,
  workforce records)
- **model_estimate** — agent inference; labeled, never laundered upward

Registering a new source is a charter change (it alters the charter hash).
The orchestrator rejects evidence whose claimed tier differs from the
registered tier — a secondary source cannot be cited as primary.

## 5. The decision brief

The deliverable for the decision maker is the brief
(`lsto_workforce/brief.py`): recommendation and confidence first, then the
falsifiable forecast, alternatives considered, what would change our mind,
the evidence table (claim / source / tier / age), role assessments,
dissent verbatim with resolutions, gate outcomes with any overrides, and
the record hash for ledger verification. Everything in the brief is
reconstructable from the decision record; the brief adds no facts.

## 6. Measurement

Accountability is measurable or it is theater. The scorecard
(`python -m lsto_workforce scorecard`) reports: decision counts by status,
gate pass/warn/block and override rates, evidence per decision and
primary-source share, model-estimate share, dissent raise/resolve counts,
and calibration (Brier score, hit rate, average confidence) over resolved
forecasts. Review it at least monthly; a rising override rate or a
model-estimate share crowding out primary evidence is an early warning.

## 7. Change control

- Charter changes (roles, tiers, sources, prohibited terms) change the
  charter hash and must be committed to this repository — never applied
  ad hoc inside a session.
- Weakening `HumanApprovalGate`, dissent handling, or ledger chaining
  requires an explicit human decision recorded in the PR description.
- The ledger anchor (entry count + head hash) should be recorded
  out-of-band — committing `ledger_anchor.json` alongside outputs makes
  whole-file ledger replacement detectable.
