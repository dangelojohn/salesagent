"""Core data models for the discovery/validation agent.

Two independent axes govern every prospect:
  fit_score          -- how well they match the ICP (integer, DQ terms are absolute)
  absence_confidence -- how sure we are MRP is genuinely ABSENT (0.0-1.0)

You cannot confirm a negative from outside. Silence is not evidence.
Hence the confidence floor in scoring.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Decision(str, Enum):
    BUILD = "BUILD"        # fit + confidence both clear threshold -> hand to C3
    ENRICH = "ENRICH"      # good fit, unproven absence -> deepen S2, do NOT build
    PARK = "PARK"          # marginal fit -> re-score next refresh
    ARCHIVE = "ARCHIVE"    # disqualified or hopeless


class Stage(str, Enum):
    SEED = "S0_SEED"
    SCORE = "S1_SCORE"
    CONFIRM = "S2_CONFIRM"
    TRIGGER = "S3_TRIGGER"
    CONTACT = "S4_CONTACT"


class SoftwareTier(str, Enum):
    NONE = "none"
    DESIGN_ONLY = "design_only"    # showroom design, no manufacturing
    CAM_ONLY = "cam_only"          # nesting/toolpath only
    CAD_CAM = "cad_cam"            # draws + nests + G-code, nothing downstream -> IDEAL
    HYBRID = "hybrid"              # partial BOM/estimating, ERP-integrable -> contested
    ERP = "erp"                    # bid-to-install -> DISQUALIFY


class RouterTier(str, Enum):
    NONE = "none"
    HOBBY = "hobby"                # 1-5 people -> too small
    PROSUMER = "prosumer"          # 5-15 -> marginal
    INDUSTRIAL = "industrial"      # 15-60+ nested-based -> ICP bullseye
    ENTERPRISE = "enterprise"      # 60+ -> probably already on ERP, force verify


class TriggerPriority(str, Enum):
    P0 = "P0"   # deciding now (~4 weeks)
    P1 = "P1"   # capex unfrozen / scaling
    P2 = "P2"   # momentum, softer timing
    NONE = "NONE"


class Track(str, Enum):
    """Which messaging/template variant this prospect routes to."""
    STANDARD = "standard"
    CROSS_BORDER = "cross_border"   # US-domiciled, Canadian ops
    CONTESTED = "contested"         # Microvellum et al -- ERP vendor already in the room


DQ_CONFIDENCE = 0.0
NO_EVIDENCE_FLOOR = 0.20   # never higher than this with zero S2 evidence


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Evidence:
    """A single cited signal. No citation -> the signal does not count.

    This is the validation anchor. C2 may not emit a score without these.
    """
    signal: str
    source_url: str
    matched_text: str
    stage: Stage
    w: int = 0                      # contribution to fit_score
    c: float = 0.0                  # contribution to absence_confidence
    disqualifying: bool = False
    extracted_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.source_url or not self.matched_text:
            raise ValueError(
                f"Evidence '{self.signal}' lacks source_url or matched_text. "
                "Uncited signals are rejected by design."
            )


@dataclass
class Locality:
    operating_country: str = "CA"
    province: str | None = "ON"
    domicile_country: str = "CA"
    data_region: str = "ca-central"

    @property
    def cross_border(self) -> bool:
        return self.domicile_country != self.operating_country

    @property
    def jurisdictions(self) -> list[str]:
        """CASL applies where the message is ACCESSED, not where the sender sits.
        Ambiguous -> apply every applicable ruleset simultaneously (strictest_of).
        """
        j: list[str] = []
        if self.operating_country == "CA":
            j.append("CASL")
        if "US" in (self.operating_country, self.domicile_country):
            j.append("CAN-SPAM")
        return j or ["CASL"]

    @property
    def jurisdiction_rule(self) -> str:
        return "strictest_of" if len(self.jurisdictions) > 1 else "single"


@dataclass
class Firmographic:
    employees_est: int | None = None
    employees_source: str | None = None
    incorporated: str | None = None       # ISO date
    industrial_address: bool | None = None
    manufacturer_tag: bool | None = None
    opens_before_0730: bool | None = None
    review_count: int | None = None
    review_velocity_ratio: float | None = None   # last 12mo vs prior 12mo


@dataclass
class Capability:
    cnc_confirmed: bool = False
    router_brands: list[str] = field(default_factory=list)
    router_tier: RouterTier = RouterTier.NONE
    software: list[str] = field(default_factory=list)
    software_tier: SoftwareTier = SoftwareTier.NONE
    erp_detected: str | None = None
    ppsa_lien_months_ago: int | None = None


@dataclass
class Trigger:
    type: str | None = None
    priority: TriggerPriority = TriggerPriority.NONE
    detected: str | None = None
    expires: str | None = None


@dataclass
class Contact:
    owner_name: str | None = None
    owner_source: str | None = None
    business_phone: str | None = None
    business_email: str | None = None
    physical_address: str | None = None
    consent_basis: str | None = None
    suppression_checked: bool = False


@dataclass
class Scores:
    fit_score: int = 0
    absence_confidence: float = NO_EVIDENCE_FLOOR
    trigger: Trigger = field(default_factory=Trigger)


@dataclass
class Prospect:
    prospect_id: str
    company: str
    naics: str = "337110"           # wood kitchen cabinet manufacturing
    locality: Locality = field(default_factory=Locality)
    firmographic: Firmographic = field(default_factory=Firmographic)
    capability: Capability = field(default_factory=Capability)
    contact: Contact = field(default_factory=Contact)
    scores: Scores = field(default_factory=Scores)
    evidence: list[Evidence] = field(default_factory=list)
    decision: Decision = Decision.PARK
    track: Track = Track.STANDARD
    dq_reasons: list[str] = field(default_factory=list)
    routed_to: str | None = None

    def add(self, ev: Evidence) -> None:
        self.evidence.append(ev)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["locality"]["cross_border"] = self.locality.cross_border
        d["locality"]["jurisdiction"] = self.locality.jurisdictions
        d["locality"]["jurisdiction_rule"] = self.locality.jurisdiction_rule
        return d
