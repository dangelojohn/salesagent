"""Signal extractors.

Every extractor returns cited Evidence or nothing. No citation -> no signal.

Deterministic regex handles the high-precision strings ("proficient in Excel
and QuickBooks"). The classify_* hooks are where a model is called for the
nuanced judgments -- job-post semantics and review-pain classification --
because those decide absence_confidence, the number that matters most.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable

from .models import Evidence, Stage
from .taxonomy import (
    DQ_SIGNALS,
    ROUTERS,
    S1_SIGNALS,
    S2_SIGNALS,
    SOFTWARE,
)

# --------------------------------------------------------------------------
# Precompiled patterns
# --------------------------------------------------------------------------
_CNC_COPY = re.compile(
    r"\b(cnc|computer[- ]cut|5[- ]axis|nested[- ]based|precision[- ]machined)\b", re.I
)
_PRODUCTION_ROLE = re.compile(
    r"\b(cnc|machin\w+|production|shop|estimat\w+|schedul\w+|drafter|programmer)\b", re.I
)
_EXCEL_QB = re.compile(r"\b(excel|quickbooks|spread ?sheets?)\b", re.I)
_ESTIMATOR = re.compile(r"\b(estimator|quoting coordinator|quote\s+(?:desk|admin))\b", re.I)
_SCHEDULER = re.compile(r"\b(production scheduler|production planner)\b", re.I)
_CNC_OP = re.compile(r"\b(cnc operator|nesting|cnc programmer)\b", re.I)
_ERP_ADMIN = re.compile(r"\b(erp (administrator|admin|analyst|manager))\b", re.I)

_REVIEW_PAIN = re.compile(
    r"(months?\s+late|took\s+(?:much\s+)?longer|behind\s+schedule|missed\s+the\s+deadline"
    r"|wrong\s+(?:measurement|size|dimension)s?|not\s+(?:as\s+)?per\s+(?:the\s+)?drawing"
    r"|didn'?t\s+(?:return|answer)\s+(?:my\s+)?(?:call|phone)|never\s+called\s+back"
    r"|lost\s+my\s+order|delay(?:ed|s)?)",
    re.I,
)

_COMMUNITY_PAIN = re.compile(
    r"(cut\s*lists?\s+into|how\s+do\s+(?:i|we|you)\s+(?:track|cost|schedule)"
    r"|re-?key(?:ing)?\s+(?:the\s+)?quotes?|track\s+wip|job\s+costing\s+in\s+excel)",
    re.I,
)


def _find(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    lo = max(0, m.start() - 40)
    hi = min(len(text), m.end() + 40)
    return text[lo:hi].strip()


def _ev(signal: str, url: str, snippet: str, stage: Stage,
        table: dict[str, tuple[int, float, str]]) -> Evidence:
    w, c, _ = table[signal]
    return Evidence(signal=signal, source_url=url, matched_text=snippet,
                    stage=stage, w=w, c=c)


# --------------------------------------------------------------------------
# S1 -- website / social copy
# --------------------------------------------------------------------------
def extract_website(text: str, url: str) -> tuple[list[Evidence], list[str], list[str]]:
    """Returns (evidence, software_names, router_brands)."""
    ev: list[Evidence] = []
    software: list[str] = []
    routers: list[str] = []

    if snip := _find(_CNC_COPY, text):
        ev.append(_ev("cnc_declared_in_copy", url, snip, Stage.SCORE, S1_SIGNALS))

    low = text.lower()
    for name in SOFTWARE:
        if name in low:
            software.append(name)
    for brand in ROUTERS:
        if re.search(rf"\b{re.escape(brand)}\b", low):
            routers.append(brand)

    return ev, software, routers


# --------------------------------------------------------------------------
# S2 -- job postings. The richest source in the entire system.
# --------------------------------------------------------------------------
def extract_job_posting(title: str, body: str, url: str) -> list[Evidence]:
    ev: list[Evidence] = []
    blob = f"{title}\n{body}"

    # Disqualifier first -- dominates everything else in the posting.
    if snip := _find(_ERP_ADMIN, blob):
        ev.append(Evidence(
            signal="hiring_erp_admin", source_url=url, matched_text=snip,
            stage=Stage.CONFIRM, w=-5, c=0.0, disqualifying=True,
        ))
        return ev

    for name in SOFTWARE:
        if name in blob.lower() and SOFTWARE[name][0].value == "erp":
            ev.append(Evidence(
                signal="erp_detected", source_url=url,
                matched_text=f"job post names ERP: {name}",
                stage=Stage.CONFIRM, w=-5, c=0.0, disqualifying=True,
            ))
            return ev

    # The strongest single tell: Excel/QuickBooks required in a PRODUCTION role.
    if _PRODUCTION_ROLE.search(title) and (snip := _find(_EXCEL_QB, blob)):
        ev.append(_ev("excel_or_quickbooks_in_production_role", url, snip,
                      Stage.CONFIRM, S2_SIGNALS))

    if snip := _find(_ESTIMATOR, blob):
        ev.append(_ev("hiring_estimator_or_quoting", url, snip, Stage.CONFIRM, S2_SIGNALS))
    if snip := _find(_SCHEDULER, blob):
        ev.append(_ev("hiring_production_scheduler", url, snip, Stage.CONFIRM, S2_SIGNALS))
    if snip := _find(_CNC_OP, blob):
        ev.append(_ev("hiring_cnc_operator", url, snip, Stage.CONFIRM, S2_SIGNALS))

    return ev


# --------------------------------------------------------------------------
# S2 -- customer reviews. MRP symptoms, published by their own customers.
# --------------------------------------------------------------------------
def extract_reviews(reviews: Iterable[tuple[str, str]]) -> list[Evidence]:
    """reviews: iterable of (review_text, source_url)."""
    ev: list[Evidence] = []
    for text, url in reviews:
        if snip := _find(_REVIEW_PAIN, text):
            ev.append(_ev("review_pain_leadtime_or_spec", url, snip,
                          Stage.CONFIRM, S2_SIGNALS))
            break   # one is enough; don't double-count a pile-on
    return ev


# --------------------------------------------------------------------------
# S2 -- user-community posts. READ ONLY. Scoring input, never an outreach hook.
# --------------------------------------------------------------------------
def extract_community_post(text: str, url: str) -> list[Evidence]:
    """First-person, attributable statement of MRP absence.

    Highest-quality absence evidence available anywhere.

    CONSTRAINT: public posts only, read-only, no DMs, no pretexting.
    Never quote a person's forum post back at them in outreach. In a network
    this tight that is a one-shot mistake.
    """
    if snip := _find(_COMMUNITY_PAIN, text):
        return [_ev("community_pain_post", url, snip, Stage.CONFIRM, S2_SIGNALS)]
    return []


# --------------------------------------------------------------------------
# S2 -- registry / lien / dealer
# --------------------------------------------------------------------------
def extract_ppsa(collateral: str, url: str, months_ago: int) -> list[Evidence]:
    if not re.search(r"\b(cnc|router|edgebander|beam saw|machining centre)\b",
                     collateral, re.I):
        return []
    ev = [_ev("ppsa_lien_cnc", url, collateral[:120], Stage.CONFIRM, S2_SIGNALS)]
    return ev


def extract_incorporation(iso_date: str, url: str, today_year: int) -> list[Evidence]:
    try:
        year = int(iso_date[:4])
    except (ValueError, TypeError):
        return []
    if today_year - year > 15:
        return [_ev("incorporated_over_15y", url,
                    f"incorporated {iso_date}", Stage.CONFIRM, S2_SIGNALS)]
    return []


def extract_dealer_showcase(shop_name: str, page_text: str, url: str) -> list[Evidence]:
    if shop_name.lower() in page_text.lower():
        snip = _find(re.compile(re.escape(shop_name), re.I), page_text) or shop_name
        return [_ev("machinery_dealer_showcase", url, snip, Stage.CONFIRM, S2_SIGNALS)]
    return []


def extract_vendor_case_study(shop_name: str, page_text: str, url: str) -> list[Evidence]:
    """An ERP vendor naming the shop = confirmed customer = archive."""
    if shop_name.lower() in page_text.lower():
        return [Evidence(
            signal="vendor_case_study", source_url=url,
            matched_text=f"{shop_name} named in ERP vendor case study",
            stage=Stage.CONFIRM, w=-5, c=0.0, disqualifying=True,
        )]
    return []


# --------------------------------------------------------------------------
# S1 -- firmographic derivations
# --------------------------------------------------------------------------
def extract_firmographic(*, manufacturer_tag: bool | None, employees: int | None,
                         industrial: bool | None, opens_early: bool | None,
                         velocity: float | None, url: str) -> list[Evidence]:
    ev: list[Evidence] = []
    if manufacturer_tag:
        ev.append(_ev("manufacturer_tag", url, "Places type: manufacturer",
                      Stage.SCORE, S1_SIGNALS))
    if employees and 8 <= employees <= 60:
        ev.append(_ev("employees_in_icp_band", url, f"{employees} employees",
                      Stage.SCORE, S1_SIGNALS))
    if industrial:
        ev.append(_ev("industrial_address", url, "industrial zoning",
                      Stage.SCORE, S1_SIGNALS))
    if opens_early:
        ev.append(_ev("opens_before_0730", url, "opens <= 07:30",
                      Stage.SCORE, S1_SIGNALS))
    if velocity and velocity >= 2.0:
        ev.append(_ev("review_velocity_rising", url, f"velocity {velocity:.1f}x",
                      Stage.SCORE, S1_SIGNALS))
    return ev


# --------------------------------------------------------------------------
# Model hooks. Deterministic regex above is the floor; these are the ceiling.
# Wire to Claude for job-post semantics and review-pain nuance.
# --------------------------------------------------------------------------
Classifier = Callable[[str], tuple[bool, str]]


def classify_with_model(text: str, classifier: Classifier | None,
                        signal: str, url: str, stage: Stage,
                        table: dict[str, tuple[int, float, str]]) -> list[Evidence]:
    """Escalate an ambiguous string to a model. Returns cited Evidence or []."""
    if classifier is None:
        return []
    hit, snippet = classifier(text)
    if not hit or not snippet:
        return []
    return [_ev(signal, url, snippet, stage, table)]


__all__ = [
    "extract_website", "extract_job_posting", "extract_reviews",
    "extract_community_post", "extract_ppsa", "extract_incorporation",
    "extract_dealer_showcase", "extract_vendor_case_study",
    "extract_firmographic", "classify_with_model", "DQ_SIGNALS",
]
