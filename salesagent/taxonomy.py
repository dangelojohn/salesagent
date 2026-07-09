"""Taxonomy + weights.

The critical asymmetry, learned the hard way:
  Cyncly owns BOTH Mozaik (CAD/CAM -> ideal prospect)
  AND Insight (cabinet-shop ERP -> disqualification).
  Microvellum integrates with INNERGY ERP -> contested, not greenfield.

A binary "has design software = good" rule emails demos to a
competitor's existing customers. Three tiers, not one.
"""

from __future__ import annotations

from .models import RouterTier, SoftwareTier

# --------------------------------------------------------------------------
# Software: name -> (tier, fit_weight, confidence_contribution)
# --------------------------------------------------------------------------
SOFTWARE: dict[str, tuple[SoftwareTier, int, float]] = {
    # CAD/CAM -- draws it, nests it, cuts it. Nothing downstream. IDEAL.
    "cabinet vision":   (SoftwareTier.CAD_CAM, 2, 0.25),
    "screen-to-machine": (SoftwareTier.CAD_CAM, 2, 0.25),
    "mozaik":           (SoftwareTier.CAD_CAM, 2, 0.25),
    "kcdw":             (SoftwareTier.CAD_CAM, 2, 0.25),
    "kcd software":     (SoftwareTier.CAD_CAM, 2, 0.25),
    "ecabinet systems": (SoftwareTier.CAD_CAM, 2, 0.25),

    # CAD/CAM, small-shop flavour
    "cabinet pro":      (SoftwareTier.CAD_CAM, 1, 0.20),
    "polyboard":        (SoftwareTier.CAD_CAM, 1, 0.20),
    "sketchlist":       (SoftwareTier.CAD_CAM, 1, 0.20),
    "cabinetsense":     (SoftwareTier.CAD_CAM, 1, 0.20),
    "pro100":           (SoftwareTier.CAD_CAM, 1, 0.20),

    # CAM / nesting only
    "vectric":          (SoftwareTier.CAM_ONLY, 2, 0.20),
    "aspire":           (SoftwareTier.CAM_ONLY, 2, 0.20),
    "vcarve":           (SoftwareTier.CAM_ONLY, 2, 0.20),
    "enroute":          (SoftwareTier.CAM_ONLY, 2, 0.20),
    "alphacam":         (SoftwareTier.CAM_ONLY, 2, 0.20),
    "routercim":        (SoftwareTier.CAM_ONLY, 2, 0.20),

    # Showroom design only -- no manufacturing data
    "2020 design":      (SoftwareTier.DESIGN_ONLY, 1, 0.15),
    "prokitchen":       (SoftwareTier.DESIGN_ONLY, 1, 0.15),
    "winner design":    (SoftwareTier.DESIGN_ONLY, 1, 0.15),

    # Generic CAD
    "sketchup":         (SoftwareTier.DESIGN_ONLY, 1, 0.15),
    "fusion 360":       (SoftwareTier.DESIGN_ONLY, 1, 0.15),
    "chief architect":  (SoftwareTier.DESIGN_ONLY, 1, 0.15),

    # HYBRID -- partial BOM/estimating, ERP-integrable. Contested territory.
    "microvellum":      (SoftwareTier.HYBRID, 1, 0.05),
    "cad+t":            (SoftwareTier.HYBRID, 0, 0.00),

    # ERP tier -- DISQUALIFY. A migration sale is a different, longer motion.
    "innergy":          (SoftwareTier.ERP, -5, 0.0),
    "insight":          (SoftwareTier.ERP, -5, 0.0),   # Cyncly, fka 2020 Insight
    "allmoxy":          (SoftwareTier.ERP, -5, 0.0),
    "epicor":           (SoftwareTier.ERP, -5, 0.0),
    "global shop":      (SoftwareTier.ERP, -5, 0.0),
    "shoptech":         (SoftwareTier.ERP, -5, 0.0),
    "e2 shop":          (SoftwareTier.ERP, -5, 0.0),
    "jobboss":          (SoftwareTier.ERP, -5, 0.0),
    "genius erp":       (SoftwareTier.ERP, -5, 0.0),
    "netsuite":         (SoftwareTier.ERP, -5, 0.0),
    "sap":              (SoftwareTier.ERP, -5, 0.0),
    "infor":            (SoftwareTier.ERP, -5, 0.0),
    "katana":           (SoftwareTier.ERP, -5, 0.0),
    "fishbowl":         (SoftwareTier.ERP, -5, 0.0),
    "mrpeasy":          (SoftwareTier.ERP, -5, 0.0),
    "odoo":             (SoftwareTier.ERP, -5, 0.0),
}

# Tier ordering for "highest tier wins" resolution.
_TIER_RANK = {
    SoftwareTier.NONE: 0,
    SoftwareTier.DESIGN_ONLY: 1,
    SoftwareTier.CAM_ONLY: 2,
    SoftwareTier.CAD_CAM: 3,
    SoftwareTier.HYBRID: 4,
    SoftwareTier.ERP: 5,
}

# --------------------------------------------------------------------------
# CNC routers: brand -> tier. Brand is a better size proxy than headcount.
# --------------------------------------------------------------------------
ROUTERS: dict[str, RouterTier] = {
    # Hobby / entry -- garage-adjacent, too small
    "shopbot": RouterTier.HOBBY, "avid": RouterTier.HOBBY,
    "camaster": RouterTier.HOBBY, "laguna": RouterTier.HOBBY,
    "axiom": RouterTier.HOBBY, "baileigh": RouterTier.HOBBY,

    # Prosumer / small production
    "multicam": RouterTier.PROSUMER, "techno": RouterTier.PROSUMER,
    "axyz": RouterTier.PROSUMER,

    # Industrial nested-based -- ICP bullseye
    "biesse": RouterTier.INDUSTRIAL, "rover": RouterTier.INDUSTRIAL,
    "homag": RouterTier.INDUSTRIAL, "weeke": RouterTier.INDUSTRIAL,
    "scm": RouterTier.INDUSTRIAL, "morbidelli": RouterTier.INDUSTRIAL,
    "felder": RouterTier.INDUSTRIAL, "format-4": RouterTier.INDUSTRIAL,
    "holz-her": RouterTier.INDUSTRIAL, "holzher": RouterTier.INDUSTRIAL,
    "anderson": RouterTier.INDUSTRIAL, "busellato": RouterTier.INDUSTRIAL,
    "thermwood": RouterTier.INDUSTRIAL, "onsrud": RouterTier.INDUSTRIAL,

    # Enterprise cell -- 60+, verify ERP before spending a demo
    "schelling": RouterTier.ENTERPRISE,
}

ROUTER_TIER_SCORE: dict[RouterTier, tuple[int, float]] = {
    RouterTier.NONE:       (0, 0.0),
    RouterTier.HOBBY:      (-5, 0.0),   # DQ
    RouterTier.PROSUMER:   (1, 0.0),
    RouterTier.INDUSTRIAL: (3, 0.05),
    RouterTier.ENTERPRISE: (1, 0.0),    # + forced S2 verification
}

_ROUTER_RANK = {
    RouterTier.NONE: 0, RouterTier.HOBBY: 1, RouterTier.PROSUMER: 2,
    RouterTier.INDUSTRIAL: 3, RouterTier.ENTERPRISE: 4,
}

# --------------------------------------------------------------------------
# S2 job-board + registry signals. Job postings are the richest source
# in the entire system: a posting is a public declaration of what a
# company lacks and is about to spend money on.
# --------------------------------------------------------------------------
S2_SIGNALS: dict[str, tuple[int, float, str]] = {
    # signal -> (w, c, human description)
    "excel_or_quickbooks_in_production_role":
        (3, 0.35, "Strongest single tell. No ERP, stated publicly."),
    "hiring_estimator_or_quoting":
        (2, 0.25, "Quoting is manual; ~$65-80K/yr decision imminent."),
    "hiring_production_scheduler":
        (2, 0.20, "Outgrew whiteboard scheduling."),
    "hiring_cnc_operator":
        (3, 0.00, "CNC confirmed."),
    "ppsa_lien_cnc":
        (2, 0.10, "Financed a machine; capex-willing; date-stamped."),
    "incorporated_over_15y":
        (1, 0.10, "Legacy systems + succession exposure."),
    "machinery_dealer_showcase":
        (2, 0.15, "Bought hardware, no software layer above it."),
    "supplier_dealer_locator":
        (1, 0.00, "Real production volume."),
    "community_pain_post":
        (2, 0.30, "First-person, attributable statement of MRP absence."),
    "review_pain_leadtime_or_spec":
        (2, 0.20, "MRP symptoms published by their own customers."),
}

S1_SIGNALS: dict[str, tuple[int, float, str]] = {
    "cnc_declared_in_copy":    (3, 0.00, "CNC confirmed from site copy."),
    "review_velocity_rising":  (1, 0.05, "Growing faster than its systems."),
    "shop_floor_visual":       (1, 0.05, "Machines/bays/headcount visible."),
    "industrial_address":      (1, 0.00, "Industrial park, not retail strip."),
    "opens_before_0730":       (1, 0.00, "Production shop, not showroom."),
    "employees_in_icp_band":   (1, 0.00, "8-60 employees."),
    "manufacturer_tag":        (1, 0.00, "Has a shop floor."),
    "ckca_member":             (1, 0.00, "Vertical association member."),
}

# Absolute disqualifiers, independent of score.
DQ_SIGNALS: dict[str, str] = {
    "erp_detected":        "ERP confirmed present -- migration sale, not our motion.",
    "hobby_router":        "Hobby-tier router -- shop too small.",
    "retailer_no_floor":   "Retailer/reseller, no shop floor.",
    "vendor_case_study":   "Named in an ERP vendor case study -- confirmed customer.",
    "hiring_erp_admin":    "Hiring an ERP administrator -- confirmed present.",
}

# --------------------------------------------------------------------------
# S3 triggers. Fit says they SHOULD buy. Trigger says they're deciding NOW.
# Prioritize by trigger, not by fit.
# --------------------------------------------------------------------------
TRIGGERS: dict[str, str] = {
    "estimator_posting":        "P0",
    "business_listed_for_sale": "P0",
    "recently_sold_new_owner":  "P0",
    "cnc_lien_under_6mo":       "P1",
    "industrial_building_permit": "P1",
    "three_prod_roles_60d":     "P1",
    "grant_recipient":          "P1",
    "trade_press_feature":      "P2",
    "wms_expo_exhibitor":       "P2",
    "tariff_exposure_news":     "P2",
    "succession_notice":        "P2",
    "grant_deadline_near":      "P2",
}

# Thresholds. Owned by John, tunable, versioned.
FIT_THRESHOLD = 7
CONFIDENCE_THRESHOLD = 0.76   # tuned on the calibration corpus; see calibrate.py
PARK_FLOOR = 4
ICP_EMPLOYEE_BAND = (8, 60)


def software_tier(names: list[str]) -> SoftwareTier:
    """Highest tier present wins. One ERP hit dominates everything."""
    best = SoftwareTier.NONE
    for n in names:
        tier = SOFTWARE.get(n.strip().lower(), (SoftwareTier.NONE, 0, 0.0))[0]
        if _TIER_RANK[tier] > _TIER_RANK[best]:
            best = tier
    return best


def router_tier(brands: list[str]) -> RouterTier:
    """Highest tier present wins."""
    best = RouterTier.NONE
    for b in brands:
        tier = ROUTERS.get(b.strip().lower(), RouterTier.NONE)
        if _ROUTER_RANK[tier] > _ROUTER_RANK[best]:
            best = tier
    return best
