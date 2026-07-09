"""Scoring engine.

Two independent axes. This is the whole point:

    fit_score          -- do they match the ICP?
    absence_confidence -- are we sure they have NO MRP?

You can confirm "has CNC". You can never confirm "has no MRP" from outside.
So silence is capped at NO_EVIDENCE_FLOOR (0.20) and can only be raised by
cited S2 evidence. A perfect-fit shop with no absence evidence goes to
ENRICH, never to BUILD.

That single rule prevents the most embarrassing failure mode in the system:
emailing a bespoke MRP demo to a shop that quietly bought Epicor in 2023.
"""

from __future__ import annotations

from .models import (
    DQ_CONFIDENCE,
    NO_EVIDENCE_FLOOR,
    Decision,
    Prospect,
    RouterTier,
    SoftwareTier,
    Stage,
    Track,
    TriggerPriority,
)
from .taxonomy import (
    CONFIDENCE_THRESHOLD,
    FIT_THRESHOLD,
    PARK_FLOOR,
    ROUTER_TIER_SCORE,
    SOFTWARE,
    router_tier,
    software_tier,
)

# Software tiers that permit a build. HYBRID is allowed but routed to a
# contested track; ERP is never allowed.
BUILDABLE_SOFTWARE = {
    SoftwareTier.NONE,
    SoftwareTier.DESIGN_ONLY,
    SoftwareTier.CAM_ONLY,
    SoftwareTier.CAD_CAM,
    SoftwareTier.HYBRID,
}
BUILDABLE_ROUTER = {
    RouterTier.PROSUMER,
    RouterTier.INDUSTRIAL,
    RouterTier.ENTERPRISE,
}

_PRIORITY_ORDER = {
    TriggerPriority.P0: 0,
    TriggerPriority.P1: 1,
    TriggerPriority.P2: 2,
    TriggerPriority.NONE: 3,
}


def _resolve_capability(p: Prospect) -> None:
    """Derive tiers from raw detected names, and fold them into evidence weights."""
    p.capability.software_tier = software_tier(p.capability.software)
    p.capability.router_tier = router_tier(p.capability.router_brands)

    if p.capability.router_tier is not RouterTier.NONE:
        p.capability.cnc_confirmed = True

    if p.capability.software_tier is SoftwareTier.ERP:
        erp = next(
            (n for n in p.capability.software
             if SOFTWARE.get(n.lower(), (None,))[0] is SoftwareTier.ERP),
            "unknown",
        )
        p.capability.erp_detected = erp


def _has_dq(p: Prospect) -> bool:
    """Absolute disqualifiers. Independent of, and dominant over, score."""
    hit = False

    if any(e.disqualifying for e in p.evidence):
        for e in p.evidence:
            if e.disqualifying:
                p.dq_reasons.append(f"{e.signal}: {e.matched_text[:80]}")
        hit = True

    if p.capability.software_tier is SoftwareTier.ERP:
        p.dq_reasons.append(
            f"ERP confirmed present ({p.capability.erp_detected}) -- "
            "migration sale, not this motion."
        )
        hit = True

    if p.capability.router_tier is RouterTier.HOBBY:
        p.dq_reasons.append("Hobby-tier router -- shop below ICP size floor.")
        hit = True

    if p.firmographic.manufacturer_tag is False:
        p.dq_reasons.append("No shop floor -- retailer/reseller.")
        hit = True

    return hit


# Signals that attest to the SAME underlying fact must not compound.
# Three job posts saying "Excel" is one fact, not three.
_CATEGORY: dict[str, str] = {
    "excel_or_quickbooks_in_production_role": "job",
    "hiring_estimator_or_quoting": "job",
    "hiring_production_scheduler": "job",
    "review_pain_leadtime_or_spec": "review",
    "community_pain_post": "community",
    "ppsa_lien_cnc": "capex",
    "machinery_dealer_showcase": "capex",
    "incorporated_over_15y": "age",
    "review_velocity_rising": "growth",
    "shop_floor_visual": "growth",
}


FIT_CEILING = 14   # the scale is meaningless above this; threshold is 7


def _fit(p: Prospect) -> int:
    """Best-per-category, not sum.

    Same reasoning as _confidence: three job posts naming Excel attest to
    one fact. Summing them inflates the scale until it stops ranking
    anything and becomes a binary gate wearing a number's clothes.
    """
    best: dict[str, int] = {}

    def offer(cat: str, w: int) -> None:
        if w > 0:
            best[cat] = max(best.get(cat, 0), w)

    for e in p.evidence:
        offer(_CATEGORY.get(e.signal, e.signal), e.w)

    offer("router", ROUTER_TIER_SCORE[p.capability.router_tier][0])

    for name in p.capability.software:
        tier, w, _ = SOFTWARE.get(name.strip().lower(), (SoftwareTier.NONE, 0, 0.0))
        if tier is not SoftwareTier.ERP:   # ERP handled as DQ, not as a weight
            offer("software", w)

    return min(FIT_CEILING, sum(best.values()))


def _confidence(p: Prospect) -> float:
    """Noisy-OR over independent evidence, with per-category caps.

    Addition was wrong: it saturates after ~3 signals and makes the
    threshold decorative. Independent evidence combines as

        conf = 1 - PROD(1 - c_i)

    which asymptotes toward 1.0 without ever pinning there, so more
    evidence always helps and never lies.

    Per-category caps stop correlated signals (three job posts naming
    Excel) from being counted as three independent facts.
    """
    if p.capability.software_tier is SoftwareTier.ERP:
        return DQ_CONFIDENCE

    # Strongest contribution per category, not the sum.
    best: dict[str, float] = {}

    def offer(cat: str, c: float) -> None:
        if c > 0:
            best[cat] = max(best.get(cat, 0.0), c)

    for e in p.evidence:
        offer(_CATEGORY.get(e.signal, e.signal), e.c)

    offer("router", ROUTER_TIER_SCORE[p.capability.router_tier][1])

    for name in p.capability.software:
        tier, _, cc = SOFTWARE.get(name.strip().lower(), (SoftwareTier.NONE, 0, 0.0))
        if tier is not SoftwareTier.ERP:
            offer("software", cc)

    # Noisy-OR, seeded by the no-evidence floor.
    residual = 1.0 - NO_EVIDENCE_FLOOR
    for c in best.values():
        residual *= (1.0 - min(c, 0.95))

    return round(min(1.0, 1.0 - residual), 4)


def _track(p: Prospect) -> Track:
    if p.locality.cross_border:
        return Track.CROSS_BORDER
    if p.capability.software_tier is SoftwareTier.HYBRID:
        return Track.CONTESTED   # INNERGY et al already in the room
    return Track.STANDARD


def _decide(p: Prospect) -> Decision:
    if p.dq_reasons:
        return Decision.ARCHIVE

    fit, conf = p.scores.fit_score, p.scores.absence_confidence

    if fit < PARK_FLOOR:
        return Decision.ARCHIVE
    if fit < FIT_THRESHOLD:
        return Decision.PARK

    # Enterprise routers must have absence positively verified, never inferred.
    if p.capability.router_tier is RouterTier.ENTERPRISE and not _has_s2_evidence(p):
        return Decision.ENRICH

    if p.capability.software_tier not in BUILDABLE_SOFTWARE:
        return Decision.ARCHIVE
    if p.capability.router_tier not in BUILDABLE_ROUTER:
        return Decision.ENRICH   # CNC unconfirmed -> go find it

    if conf < CONFIDENCE_THRESHOLD:
        return Decision.ENRICH   # good fit, unproven absence. Do NOT build.

    return Decision.BUILD


def _has_s2_evidence(p: Prospect) -> bool:
    return any(e.stage is Stage.CONFIRM for e in p.evidence)


def score(p: Prospect) -> Prospect:
    """Full scoring pass. Idempotent. Mutates and returns the prospect."""
    p.dq_reasons = []
    _resolve_capability(p)

    if _has_dq(p):
        p.scores.fit_score = _fit(p)
        p.scores.absence_confidence = DQ_CONFIDENCE
        p.decision = Decision.ARCHIVE
        p.track = _track(p)
        return p

    p.scores.fit_score = _fit(p)
    p.scores.absence_confidence = _confidence(p)
    p.track = _track(p)
    p.decision = _decide(p)

    if p.decision is Decision.BUILD:
        p.routed_to = "C3_invention"
    elif p.decision is Decision.ENRICH:
        p.routed_to = "S2_deepening"

    return p


def queue_key(p: Prospect) -> tuple[int, float, int]:
    """Ordering for the BUILD set.

    Timing beats fit. A 7-fit shop hiring an estimator beats a 12-fit shop
    that is quiet -- the first one is four weeks from spending $70K on the
    problem you delete.
    """
    return (
        _PRIORITY_ORDER[p.scores.trigger.priority],
        -p.scores.absence_confidence,
        -p.scores.fit_score,
    )


def hottest_signature(p: Prospect) -> bool:
    """The single hottest signature in the whole system.

    Industrial router financed <18mo ago + CAD/CAM software + no ERP
    + estimator posting <30d. Six figures of production capability,
    digital BOMs going nowhere, about to hire a human to do software's job.
    """
    lien = p.capability.ppsa_lien_months_ago
    return (
        p.capability.router_tier is RouterTier.INDUSTRIAL
        and lien is not None and lien <= 18
        and p.capability.software_tier in {SoftwareTier.CAD_CAM, SoftwareTier.CAM_ONLY}
        and p.capability.erp_detected is None
        and p.scores.trigger.type == "estimator_posting"
    )
