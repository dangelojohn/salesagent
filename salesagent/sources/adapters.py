"""Source adapters.

Each adapter attaches cited Evidence and/or capability facts. Adapters
never score -- scoring is centralized so weights stay auditable.

Every adapter takes a `fetch` callable so it runs against live sources in
production and against fixtures in tests. No network in the core package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable

from .. import extractors as ex
from ..models import Prospect, Stage

Fetch = Callable[[Prospect], Any]


# --------------------------------------------------------------------------
# S0 / S1
# --------------------------------------------------------------------------
@dataclass
class PlacesAdapter:
    """Google Places: manufacturer tag, hours, review count/velocity, phone."""
    fetch: Fetch
    name: str = "places"
    stage: Stage = Stage.SCORE
    cost_per_call: float = 0.002

    def enrich(self, p: Prospect) -> Prospect:
        d = self.fetch(p) or {}
        url = d.get("url", f"places://{p.prospect_id}")

        types = d.get("types", [])
        p.firmographic.manufacturer_tag = "manufacturer" in types
        if "manufacturer" not in types and "store" in types:
            p.firmographic.manufacturer_tag = False   # retailer -> DQ downstream

        p.firmographic.review_count = d.get("rating_count")
        p.firmographic.review_velocity_ratio = d.get("velocity")
        p.firmographic.opens_before_0730 = d.get("opens_before_0730")
        p.firmographic.industrial_address = d.get("industrial_address")
        p.contact.business_phone = d.get("phone")
        p.contact.physical_address = d.get("address")

        for e in ex.extract_firmographic(
            manufacturer_tag=p.firmographic.manufacturer_tag,
            employees=p.firmographic.employees_est,
            industrial=p.firmographic.industrial_address,
            opens_early=p.firmographic.opens_before_0730,
            velocity=p.firmographic.review_velocity_ratio,
            url=url,
        ):
            p.add(e)
        return p


@dataclass
class WebsiteAdapter:
    """Company site: CNC copy, software names, router brands."""
    fetch: Fetch
    name: str = "website"
    stage: Stage = Stage.SCORE
    cost_per_call: float = 0.01

    def enrich(self, p: Prospect) -> Prospect:
        d = self.fetch(p) or {}
        text, url = d.get("text", ""), d.get("url", "")
        if not text or not url:
            return p

        evs, software, routers = ex.extract_website(text, url)
        for e in evs:
            p.add(e)
        p.capability.software.extend(s for s in software if s not in p.capability.software)
        p.capability.router_brands.extend(
            r for r in routers if r not in p.capability.router_brands
        )
        return p


# --------------------------------------------------------------------------
# S2 -- the absence proof
# --------------------------------------------------------------------------
@dataclass
class JobBoardAdapter:
    """Indeed / Job Bank / LinkedIn.

    The richest source in the entire system. A posting is a company publicly
    declaring what it lacks and what it is about to spend money on.
    Cheapest daily poll available. If only one job runs every morning, this.
    """
    fetch: Fetch                # -> Iterable[dict(title, body, url)]
    name: str = "job_boards"
    stage: Stage = Stage.CONFIRM
    cost_per_call: float = 0.02

    def enrich(self, p: Prospect) -> Prospect:
        for post in self.fetch(p) or []:
            for e in ex.extract_job_posting(
                post.get("title", ""), post.get("body", ""), post.get("url", "")
            ):
                p.add(e)
                if e.disqualifying:
                    return p
        return p


@dataclass
class ReviewAdapter:
    """Google / Houzz / HomeStars. MRP symptoms published by their customers."""
    fetch: Fetch                # -> Iterable[tuple[text, url]]
    name: str = "reviews"
    stage: Stage = Stage.CONFIRM
    cost_per_call: float = 0.005

    def enrich(self, p: Prospect) -> Prospect:
        for e in ex.extract_reviews(self.fetch(p) or []):
            p.add(e)
        return p


@dataclass
class CommunityAdapter:
    """Cabinet Vision / Mozaik / Woodweb / CNCzone public posts.

    Highest-quality absence evidence available anywhere: a first-person,
    timestamped, attributable statement of MRP absence.

    READ ONLY. Public posts only. No DMs, no pretexting, no private groups.
    Scoring input and demo context ONLY -- never an outreach hook. Quoting a
    person's forum complaint back at them in a cold email makes you the vendor
    the whole community warns each other about.
    """
    fetch: Fetch                # -> Iterable[dict(text, url)]
    name: str = "community"
    stage: Stage = Stage.CONFIRM
    cost_per_call: float = 0.01
    outreach_safe: bool = False   # enforced downstream; never quote these

    def enrich(self, p: Prospect) -> Prospect:
        for post in self.fetch(p) or []:
            for e in ex.extract_community_post(post.get("text", ""), post.get("url", "")):
                p.add(e)
        return p


@dataclass
class PPSAAdapter:
    """Ontario PPSA lien registry. Public equipment-financing filings.

    A lien securing a Biesse tells you what they bought, roughly when, and
    that they finance capex.
    """
    fetch: Fetch                # -> Iterable[dict(collateral, url, months_ago)]
    name: str = "ppsa"
    stage: Stage = Stage.CONFIRM
    cost_per_call: float = 0.05

    def enrich(self, p: Prospect) -> Prospect:
        for lien in self.fetch(p) or []:
            evs = ex.extract_ppsa(lien.get("collateral", ""), lien.get("url", ""),
                                  lien.get("months_ago", 999))
            for e in evs:
                p.add(e)
            if evs:
                months = lien.get("months_ago")
                cur = p.capability.ppsa_lien_months_ago
                if months is not None and (cur is None or months < cur):
                    p.capability.ppsa_lien_months_ago = months
        return p


@dataclass
class RegistryAdapter:
    """Ontario Business Registry / Corporations Canada.

    Also resolves extra-provincial registrations -> US shops operating in
    Ontario. That segment carries dual CoA, multi-currency, cross-border duty,
    and consolidation pain. Odoo does all of it natively; Cabinet Vision does
    none of it; Insight and INNERGY are US products with thin CA localization.
    Essentially no incumbent.
    """
    fetch: Fetch                # -> dict(incorporated, url, domicile_country)
    name: str = "registry"
    stage: Stage = Stage.CONFIRM
    cost_per_call: float = 0.03

    def enrich(self, p: Prospect) -> Prospect:
        d = self.fetch(p) or {}
        inc, url = d.get("incorporated"), d.get("url", "")
        if inc and url:
            p.firmographic.incorporated = inc
            for e in ex.extract_incorporation(inc, url, date.today().year):
                p.add(e)
        if dom := d.get("domicile_country"):
            p.locality.domicile_country = dom
        return p


@dataclass
class DealerShowcaseAdapter:
    """Akhurst / CNC Automation / Taurus Craco / Biesse / Homag showcases.

    The machinery ecosystem publishes, for its own marketing reasons, exactly
    the list you want: who just bought a CNC.

    Also screens ERP vendor case studies -> confirmed customer -> archive.
    """
    fetch: Fetch                # -> Iterable[dict(page_text, url, kind))
    name: str = "dealer_showcase"
    stage: Stage = Stage.CONFIRM
    cost_per_call: float = 0.01

    def enrich(self, p: Prospect) -> Prospect:
        for page in self.fetch(p) or []:
            text, url = page.get("page_text", ""), page.get("url", "")
            if page.get("kind") == "erp_vendor_case_study":
                for e in ex.extract_vendor_case_study(p.company, text, url):
                    p.add(e)
                    return p
            for e in ex.extract_dealer_showcase(p.company, text, url):
                p.add(e)
        return p


# --------------------------------------------------------------------------
# S3 -- timing
# --------------------------------------------------------------------------
@dataclass
class TriggerFeedAdapter:
    """Job boards (daily), permits, for-sale listings, registry deltas, press.

    Fit says they SHOULD buy. Trigger says they are deciding NOW.
    """
    fetch: Fetch                # -> dict(type, detected, expires) | None
    name: str = "trigger_feed"
    stage: Stage = Stage.TRIGGER
    cost_per_call: float = 0.02

    def enrich(self, p: Prospect) -> Prospect:
        from ..pipeline import set_trigger   # local import: avoid cycle
        t = self.fetch(p)
        if t and t.get("type"):
            set_trigger(p, t["type"], t.get("detected", ""), t.get("expires"))
        return p


# --------------------------------------------------------------------------
# S4 -- compliant channel resolution
# --------------------------------------------------------------------------
@dataclass
class ContactResolverAdapter:
    """Published business contact only.

    Permitted: company website, directory listing, Places, registry record,
    team page, trade press.
    Forbidden: purchased lists, breach data, scraped personal inboxes,
    ToS circumvention, private groups, DMs.
    """
    fetch: Fetch                # -> dict(owner_name, owner_source, business_email)
    name: str = "contact_resolver"
    stage: Stage = Stage.CONTACT
    cost_per_call: float = 0.005

    def enrich(self, p: Prospect) -> Prospect:
        d = self.fetch(p) or {}
        p.contact.owner_name = d.get("owner_name")
        p.contact.owner_source = d.get("owner_source")
        p.contact.business_email = d.get("business_email")
        if p.contact.business_email:
            p.contact.consent_basis = "implied_published_business_contact"
        return p
