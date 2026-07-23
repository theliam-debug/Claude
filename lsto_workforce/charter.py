"""
Workforce charter: roles, decision rights, ethics standards, and the
registry of data sources the workforce is allowed to cite.

The charter is data, not prose — it is hashed into every decision record so
an auditor can prove which rules were in force when a decision was made.
A YAML file may override the defaults (see load_charter).
"""

from dataclasses import dataclass, field
from typing import Optional
from lsto_workforce.models import (
    DataSource,
    ImpactTier,
    RoleType,
    SourceTier,
    content_hash,
)


@dataclass(frozen=True)
class RoleCharter:
    """Mandate and boundaries for one workforce role."""
    role: RoleType
    mandate: str
    may_decide: bool = False   # roles advise; only humans decide above LOW impact

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "mandate": self.mandate,
            "may_decide": self.may_decide,
        }


@dataclass(frozen=True)
class TierRequirements:
    """Rigor requirements for one impact tier — the decision-rights matrix row."""
    tier: ImpactTier
    required_roles: tuple                 # tuple[RoleType]
    min_evidence: int
    min_primary_or_internal: int          # evidence items that must be PRIMARY or INTERNAL
    max_evidence_age_days: int
    red_team_required: bool
    ethics_review_required: bool
    human_approval_required: bool
    overrides_allowed: bool

    def to_dict(self) -> dict:
        return {
            "tier": self.tier.value,
            "required_roles": [r.value for r in self.required_roles],
            "min_evidence": self.min_evidence,
            "min_primary_or_internal": self.min_primary_or_internal,
            "max_evidence_age_days": self.max_evidence_age_days,
            "red_team_required": self.red_team_required,
            "ethics_review_required": self.ethics_review_required,
            "human_approval_required": self.human_approval_required,
            "overrides_allowed": self.overrides_allowed,
        }


@dataclass
class Charter:
    """The full operating charter for the workforce."""
    name: str
    version: str
    principles: list = field(default_factory=list)          # list[str]
    roles: list = field(default_factory=list)               # list[RoleCharter]
    tier_requirements: dict = field(default_factory=dict)   # ImpactTier -> TierRequirements
    sources: list = field(default_factory=list)             # list[DataSource]
    sensitive_categories: list = field(default_factory=list)  # categories forcing ethics review
    prohibited_terms: list = field(default_factory=list)      # request content that blocks outright

    def source_by_name(self, name: str) -> Optional[DataSource]:
        for s in self.sources:
            if s.name == name:
                return s
        return None

    def requirements_for(self, tier: ImpactTier) -> "TierRequirements":
        return self.tier_requirements[tier]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "principles": list(self.principles),
            "roles": [r.to_dict() for r in self.roles],
            "tier_requirements": {
                t.value: req.to_dict() for t, req in sorted(
                    self.tier_requirements.items(), key=lambda kv: kv[0].value
                )
            },
            "sources": [s.to_dict() for s in self.sources],
            "sensitive_categories": list(self.sensitive_categories),
            "prohibited_terms": list(self.prohibited_terms),
        }

    def charter_hash(self) -> str:
        """Stable hash of the charter — stamped into every decision record."""
        return content_hash(self.to_dict())


# ---------------------------------------------------------------------------
# Default charter
# ---------------------------------------------------------------------------

PRINCIPLES = [
    "Truthfulness: every factual claim traces to a registered, hashed evidence item.",
    "Real-data primacy: model estimates are labeled as such and never presented as measurements.",
    "Human accountability: a named human owns every decision above LOW impact; agents advise.",
    "Auditability: every step is written to a tamper-evident, hash-chained ledger.",
    "Dissent is a feature: red-team review is mandatory at high stakes; dissents are recorded, addressed, and never deleted.",
    "Lawfulness and fairness: legally or ethically sensitive categories require ethics review and human sign-off.",
    "Privacy: only the minimum necessary personal data enters records; names appear only for accountability roles.",
    "Calibration: recommendations state confidence, attach falsifiable forecasts where possible, and are scored after the fact.",
    "Non-deception: no output may be designed to mislead a counterparty, market, or regulator.",
    "Stop conditions: any role can escalate to halt; overrides require a named human, a written reason, and a ledger entry.",
]

DEFAULT_ROLES = [
    RoleCharter(
        RoleType.RESEARCH_ANALYST,
        "Gather evidence from registered sources; state findings with confidence and cite every claim.",
    ),
    RoleCharter(
        RoleType.DATA_STEWARD,
        "Verify provenance, freshness, and tier of all evidence; reject unsourced or stale inputs.",
    ),
    RoleCharter(
        RoleType.RISK_OFFICER,
        "Quantify downside, reversibility, and exposure; classify the impact tier honestly.",
    ),
    RoleCharter(
        RoleType.ETHICS_REVIEWER,
        "Screen for legal, fairness, privacy, and deception concerns; escalate rather than rationalize.",
    ),
    RoleCharter(
        RoleType.RED_TEAM,
        "Argue the strongest case against the recommendation; file dissents, not softened notes.",
    ),
    RoleCharter(
        RoleType.SYNTHESIZER,
        "Integrate assessments into a decision brief a busy decision maker can act on; preserve dissent verbatim.",
    ),
    RoleCharter(
        RoleType.AUDITOR,
        "Verify ledger integrity and process compliance; report gaps without exception.",
    ),
]

DEFAULT_TIER_REQUIREMENTS = {
    ImpactTier.LOW: TierRequirements(
        tier=ImpactTier.LOW,
        required_roles=(RoleType.RESEARCH_ANALYST,),
        min_evidence=1,
        min_primary_or_internal=0,
        max_evidence_age_days=365,
        red_team_required=False,
        ethics_review_required=False,
        human_approval_required=False,
        overrides_allowed=True,
    ),
    ImpactTier.MEDIUM: TierRequirements(
        tier=ImpactTier.MEDIUM,
        required_roles=(RoleType.RESEARCH_ANALYST, RoleType.RISK_OFFICER),
        min_evidence=2,
        min_primary_or_internal=1,
        max_evidence_age_days=180,
        red_team_required=False,
        ethics_review_required=False,
        human_approval_required=False,
        overrides_allowed=True,
    ),
    ImpactTier.HIGH: TierRequirements(
        tier=ImpactTier.HIGH,
        required_roles=(
            RoleType.RESEARCH_ANALYST,
            RoleType.DATA_STEWARD,
            RoleType.RISK_OFFICER,
            RoleType.RED_TEAM,
            RoleType.SYNTHESIZER,
        ),
        min_evidence=3,
        min_primary_or_internal=2,
        max_evidence_age_days=90,
        red_team_required=True,
        ethics_review_required=True,
        human_approval_required=True,
        overrides_allowed=True,
    ),
    ImpactTier.CRITICAL: TierRequirements(
        tier=ImpactTier.CRITICAL,
        required_roles=(
            RoleType.RESEARCH_ANALYST,
            RoleType.DATA_STEWARD,
            RoleType.RISK_OFFICER,
            RoleType.ETHICS_REVIEWER,
            RoleType.RED_TEAM,
            RoleType.SYNTHESIZER,
            RoleType.AUDITOR,
        ),
        min_evidence=5,
        min_primary_or_internal=3,
        max_evidence_age_days=30,
        red_team_required=True,
        ethics_review_required=True,
        human_approval_required=True,
        overrides_allowed=False,   # no shortcuts on irreversible decisions
    ),
}

# Sources the workforce actually has access to in this environment. Tiers
# reflect how close each is to the origin of the data, not vendor prestige.
DEFAULT_SOURCES = [
    DataSource("SEC EDGAR", SourceTier.PRIMARY, "US securities filings", "mcp:SEC_EDGAR_Personal"),
    DataSource("FRED", SourceTier.PRIMARY, "Federal Reserve economic data", "mcp:Macro_Intelligence_Custom"),
    DataSource("US Treasury", SourceTier.PRIMARY, "Treasury rates, auctions, debt", "mcp:Tresury_Custom_API"),
    DataSource("FINRA", SourceTier.PRIMARY, "Broker/market regulatory data", "mcp:FINRA_API"),
    DataSource("BLS", SourceTier.PRIMARY, "US labor statistics", "mcp:Global_Macro_Custom"),
    DataSource("ECB", SourceTier.PRIMARY, "European Central Bank data", "mcp:Global_Macro_Custom"),
    DataSource("FDIC", SourceTier.PRIMARY, "US bank data", "mcp:Global_Macro_Custom"),
    DataSource("CourtListener", SourceTier.PRIMARY, "US court records", "mcp:CourtListener"),
    DataSource("ClinicalTrials.gov", SourceTier.PRIMARY, "NIH trial registry", "mcp:Clinical_Trials"),
    DataSource("FMP", SourceTier.SECONDARY, "Financial Modeling Prep market data", "mcp:FMP"),
    DataSource("MSCI", SourceTier.SECONDARY, "Index and ESG analytics", "mcp:MSCI"),
    DataSource("Schwab", SourceTier.SECONDARY, "Brokerage market data", "mcp:Schwab_Perosnal_API"),
    DataSource("MT Newswires", SourceTier.SECONDARY, "Financial news", "mcp:MT_Newswires"),
    DataSource("Consensus", SourceTier.SECONDARY, "Academic literature search", "mcp:Consensus"),
    DataSource("PubMed", SourceTier.PRIMARY, "Biomedical literature index", "mcp:PubMed"),
    DataSource("derivatives_strategies", SourceTier.INTERNAL, "In-repo options overlay analytics", "python -m derivatives_strategies"),
    DataSource("lsto_workforce", SourceTier.INTERNAL, "Workforce records and scorecards", "python -m lsto_workforce"),
    DataSource("analyst_judgment", SourceTier.MODEL_ESTIMATE, "Agent inference not backed by a measurement", "n/a"),
]

# Decision categories that always force an ethics review regardless of tier.
DEFAULT_SENSITIVE_CATEGORIES = [
    "hiring", "termination", "personnel", "compensation",
    "legal", "regulatory", "tax",
    "health", "medical",
    "privacy", "surveillance",
    "lending", "credit", "insurance",
]

# Request content that blocks outright (EthicsGate hard block, no override).
DEFAULT_PROHIBITED_TERMS = [
    "insider information", "front-run", "front run",
    "mislead regulator", "mislead auditor", "falsify", "fabricate data",
    "evade sanctions", "launder",
    "discriminate by race", "discriminate by gender", "discriminate by age",
]


def default_charter() -> Charter:
    """The LsTo default charter."""
    return Charter(
        name="LsTo Agent Workforce Charter",
        version="1.0",
        principles=list(PRINCIPLES),
        roles=list(DEFAULT_ROLES),
        tier_requirements=dict(DEFAULT_TIER_REQUIREMENTS),
        sources=list(DEFAULT_SOURCES),
        sensitive_categories=list(DEFAULT_SENSITIVE_CATEGORIES),
        prohibited_terms=list(DEFAULT_PROHIBITED_TERMS),
    )


def load_charter(path: str) -> Charter:
    """
    Load a charter from YAML, starting from the defaults and applying
    overrides. Supported keys: name, version, principles (replace),
    sensitive_categories (extend), prohibited_terms (extend),
    sources (extend; each: name, tier, description, access),
    tier_requirements (per-tier field overrides).
    """
    import yaml

    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    charter = default_charter()
    charter.name = raw.get("name", charter.name)
    charter.version = str(raw.get("version", charter.version))

    if "principles" in raw:
        charter.principles = [str(p) for p in raw["principles"]]
    charter.sensitive_categories.extend(
        str(c) for c in raw.get("sensitive_categories", [])
    )
    charter.prohibited_terms.extend(
        str(t) for t in raw.get("prohibited_terms", [])
    )
    for s in raw.get("sources", []):
        charter.sources.append(DataSource(
            name=s["name"],
            tier=SourceTier(s.get("tier", "secondary")),
            description=s.get("description", ""),
            access=s.get("access", ""),
        ))

    for tier_name, overrides in (raw.get("tier_requirements") or {}).items():
        tier = ImpactTier(tier_name)
        base = charter.tier_requirements[tier]
        charter.tier_requirements[tier] = TierRequirements(
            tier=tier,
            required_roles=tuple(
                RoleType(r) for r in overrides.get(
                    "required_roles", [r.value for r in base.required_roles]
                )
            ),
            min_evidence=int(overrides.get("min_evidence", base.min_evidence)),
            min_primary_or_internal=int(overrides.get(
                "min_primary_or_internal", base.min_primary_or_internal
            )),
            max_evidence_age_days=int(overrides.get(
                "max_evidence_age_days", base.max_evidence_age_days
            )),
            red_team_required=bool(overrides.get(
                "red_team_required", base.red_team_required
            )),
            ethics_review_required=bool(overrides.get(
                "ethics_review_required", base.ethics_review_required
            )),
            human_approval_required=bool(overrides.get(
                "human_approval_required", base.human_approval_required
            )),
            overrides_allowed=bool(overrides.get(
                "overrides_allowed", base.overrides_allowed
            )),
        )

    return charter
