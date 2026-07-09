"""Tests. The ones that matter are the ones that stop the machine
from doing something stupid at scale.
"""

from __future__ import annotations

import pytest

from salesagent import (
    ComplianceFailure, ComplianceGate, CostCeilingExceeded, CostGovernor,
    Decision, Evidence, KillSwitch, Prospect, SenderIdentity, Stage,
    SuppressionList, Track, score, set_trigger,
)
from salesagent.extractors import extract_job_posting
from salesagent.models import RouterTier, SoftwareTier
from salesagent.taxonomy import software_tier


def mk(company="Test Cabinets", **kw) -> Prospect:
    p = Prospect(prospect_id="t-1", company=company)
    for k, v in kw.items():
        obj, _, attr = k.partition("__")
        setattr(getattr(p, obj), attr, v)
    return p


def evidenced(p: Prospect) -> Prospect:
    """Attach corroborating evidence across independent categories.

    Under noisy-OR a single category can never reach the confidence gate.
    Real BUILD prospects always carry corroboration; so must fixtures.
    """
    p.add(Evidence("excel_or_quickbooks_in_production_role", "u1", "Excel",
                   Stage.CONFIRM, w=3, c=0.35))
    p.add(Evidence("review_pain_leadtime_or_spec", "u2", "two months late",
                   Stage.CONFIRM, w=2, c=0.20))
    p.add(Evidence("ppsa_lien_cnc", "u3", "Biesse Rover", Stage.CONFIRM, w=2, c=0.10))
    p.add(Evidence("community_pain_post", "u4", "job costing in excel",
                   Stage.CONFIRM, w=2, c=0.30))
    return p


# -- the taxonomy asymmetry that nearly poisoned the pipeline ---------------
def test_cyncly_owns_both_ideal_and_disqualifying_software():
    """Mozaik (CAD/CAM, ideal) and Insight (ERP, DQ) ship from the same vendor."""
    assert software_tier(["mozaik"]) is SoftwareTier.CAD_CAM
    assert software_tier(["insight"]) is SoftwareTier.ERP
    # One ERP hit dominates a pile of good signals.
    assert software_tier(["mozaik", "cabinet vision", "insight"]) is SoftwareTier.ERP


def test_microvellum_is_hybrid_not_greenfield():
    """Microvellum integrates with INNERGY ERP -> contested territory."""
    assert software_tier(["microvellum"]) is SoftwareTier.HYBRID


def test_hybrid_routes_to_contested_track():
    p = mk(capability__software=["microvellum"],
           capability__router_brands=["biesse"],
           firmographic__manufacturer_tag=True)
    p.add(Evidence("excel_or_quickbooks_in_production_role", "u", "Excel",
                   Stage.CONFIRM, w=3, c=0.35))
    score(p)
    assert p.track is Track.CONTESTED


# -- the confidence floor: you cannot confirm a negative -------------------
def test_perfect_fit_no_absence_evidence_enriches_never_builds():
    """The failure mode this whole design exists to prevent."""
    p = mk(capability__router_brands=["biesse"],
           capability__software=["cabinet vision"],
           firmographic__manufacturer_tag=True,
           firmographic__employees_est=30,
           firmographic__industrial_address=True,
           firmographic__opens_before_0730=True)
    for sig, w in [("manufacturer_tag", 1), ("employees_in_icp_band", 1),
                   ("industrial_address", 1), ("opens_before_0730", 1),
                   ("cnc_declared_in_copy", 3)]:
        p.add(Evidence(sig, "https://x", "snippet", Stage.SCORE, w=w, c=0.0))
    score(p)

    assert p.scores.fit_score >= 7
    assert p.scores.absence_confidence < 0.65   # 0.20 floor + 0.25 software + 0.05 router
    assert p.decision is Decision.ENRICH        # NOT build
    assert p.routed_to == "S2_deepening"


def test_s2_evidence_lifts_confidence_over_threshold():
    p = mk(capability__router_brands=["biesse"],
           capability__software=["cabinet vision"],
           firmographic__manufacturer_tag=True)
    p.add(Evidence("manufacturer_tag", "u", "s", Stage.SCORE, w=1))
    p.add(Evidence("cnc_declared_in_copy", "u", "CNC", Stage.SCORE, w=3))
    evidenced(p)
    score(p)
    assert p.scores.absence_confidence >= 0.76
    assert p.decision is Decision.BUILD
    assert p.routed_to == "C3_invention"


def test_single_category_evidence_is_not_enough_to_build():
    """Noisy-OR: one job signal alone does not cross the confidence gate.
    Independent corroboration from a second category is required."""
    p = mk(capability__router_brands=["biesse"],
           capability__software=["cabinet vision"],
           firmographic__manufacturer_tag=True)
    p.add(Evidence("manufacturer_tag", "u", "s", Stage.SCORE, w=5))
    p.add(Evidence("excel_or_quickbooks_in_production_role", "u", "Excel",
                   Stage.CONFIRM, w=3, c=0.35))
    score(p)
    assert p.scores.fit_score >= 7
    assert p.scores.absence_confidence < 0.65
    assert p.decision is Decision.ENRICH


def test_correlated_signals_do_not_compound():
    """Three job posts naming Excel is ONE fact, not three."""
    def conf(n):
        p = mk(capability__router_brands=["biesse"],
               capability__software=["cabinet vision"],
               firmographic__manufacturer_tag=True)
        for i in range(n):
            p.add(Evidence("excel_or_quickbooks_in_production_role", f"u{i}", "Excel",
                           Stage.CONFIRM, w=0, c=0.35))
        sp = score(p)
        return sp.scores.absence_confidence, sp.scores.fit_score
    assert conf(1) == conf(3)   # neither confidence NOR fit compounds


def test_no_evidence_confidence_never_exceeds_floor():
    p = mk()
    score(p)
    assert p.scores.absence_confidence == pytest.approx(0.20)


# -- disqualification dominates score --------------------------------------
def test_erp_detected_archives_regardless_of_fit():
    p = mk(capability__router_brands=["biesse"],
           capability__software=["cabinet vision", "innergy"],
           firmographic__manufacturer_tag=True)
    for _ in range(6):
        p.add(Evidence("manufacturer_tag", "u", "s", Stage.SCORE, w=2))
    score(p)
    assert p.decision is Decision.ARCHIVE
    assert p.scores.absence_confidence == 0.0
    assert any("ERP confirmed" in r for r in p.dq_reasons)


def test_hobby_router_archives():
    p = mk(capability__router_brands=["shopbot"], firmographic__manufacturer_tag=True)
    p.add(Evidence("cnc_declared_in_copy", "u", "CNC", Stage.SCORE, w=3))
    score(p)
    assert p.decision is Decision.ARCHIVE
    assert p.capability.router_tier is RouterTier.HOBBY


def test_retailer_no_shop_floor_archives():
    p = mk(firmographic__manufacturer_tag=False)
    score(p)
    assert p.decision is Decision.ARCHIVE


def test_hiring_erp_admin_is_disqualifying_and_short_circuits():
    evs = extract_job_posting(
        "ERP Administrator",
        "Seeking an ERP administrator to manage our production system. Excel a plus.",
        "https://jobs/1",
    )
    assert len(evs) == 1
    assert evs[0].disqualifying


# -- the strongest single tell ---------------------------------------------
def test_excel_in_production_role_is_the_strongest_signal():
    evs = extract_job_posting(
        "Production Scheduler",
        "Must be proficient in Excel and QuickBooks to manage the cut schedule.",
        "https://jobs/2",
    )
    sigs = {e.signal for e in evs}
    assert "excel_or_quickbooks_in_production_role" in sigs
    top = max(evs, key=lambda e: e.c)
    assert top.c == 0.35


def test_excel_in_a_marketing_role_is_not_the_signal():
    evs = extract_job_posting(
        "Marketing Coordinator", "Proficient in Excel.", "https://jobs/3")
    assert not any(e.signal == "excel_or_quickbooks_in_production_role" for e in evs)


# -- evidence discipline ---------------------------------------------------
def test_uncited_evidence_is_rejected_by_construction():
    with pytest.raises(ValueError, match="Uncited"):
        Evidence("some_signal", "", "", Stage.SCORE)


# -- cross border ----------------------------------------------------------
def test_us_domiciled_ontario_ops_gets_both_rulesets_and_crossborder_track():
    p = mk(locality__domicile_country="US")
    assert p.locality.cross_border
    assert p.locality.jurisdictions == ["CASL", "CAN-SPAM"]
    assert p.locality.jurisdiction_rule == "strictest_of"
    score(p)
    assert p.track is Track.CROSS_BORDER


# -- queue ordering: timing beats fit --------------------------------------
def test_trigger_outranks_fit_in_the_queue():
    from salesagent.pipeline import Pipeline

    def build(name, fit_w, trig):
        p = mk(name, capability__router_brands=["biesse"],
               capability__software=["cabinet vision"],
               firmographic__manufacturer_tag=True)
        p.add(Evidence("manufacturer_tag", "u", "s", Stage.SCORE, w=fit_w))
        evidenced(p)
        score(p)
        if trig:
            set_trigger(p, trig, "2026-07-01")
        return p

    quiet_high_fit = build("Quiet", 3, None)
    hot_low_fit = build("Hot", 1, "estimator_posting")
    assert quiet_high_fit.scores.fit_score >= hot_low_fit.scores.fit_score

    pl = Pipeline(seeds=[], adapters={}, governor=CostGovernor(1, 1))
    queue = pl.build_queue([quiet_high_fit, hot_low_fit])
    assert queue[0].company == "Hot"   # timing beats fit


# -- governor and kill switch ----------------------------------------------
def test_cost_governor_halts_at_ceiling():
    g = CostGovernor(per_cycle_ceiling=0.05, per_day_ceiling=10.0)
    g.charge(0.04, "s1")
    with pytest.raises(CostCeilingExceeded):
        g.charge(0.02, "s2")


def test_kill_switch_is_supreme():
    k = KillSwitch()
    k.stop()
    with pytest.raises(RuntimeError, match="Kill switch"):
        k.assert_running()


# -- compliance gate: outbound cannot bypass -------------------------------
@pytest.fixture
def gate(tmp_path):
    return ComplianceGate(
        sender=SenderIdentity("REAL Partners Ltd.", "130 Queens Quay E, Toronto ON",
                              "437-220-8793", "dangelo.john@gmail.com"),
        suppression=SuppressionList(path=tmp_path / "supp.json"),
        unsubscribe_base="https://odooiq.example",
        audit_log=tmp_path / "audit.jsonl",
    )


def _sendable() -> Prospect:
    p = mk(capability__router_brands=["biesse"],
           capability__software=["cabinet vision"],
           firmographic__manufacturer_tag=True)
    p.add(Evidence("manufacturer_tag", "u", "s", Stage.SCORE, w=1))
    evidenced(p)
    score(p)
    assert p.decision is Decision.BUILD
    p.contact.business_email = "info@testcabinets.ca"
    p.contact.owner_source = "company_website"
    p.contact.consent_basis = "implied_published_business_contact"
    return p


def test_gate_blocks_when_quality_gate_failed(gate):
    with pytest.raises(ComplianceFailure, match="quality gate"):
        gate.authorize(_sendable(), quality_passed=False)


def test_gate_blocks_purchased_list(gate):
    p = _sendable()
    p.contact.owner_source = "purchased_list"
    with pytest.raises(ComplianceFailure, match="forbidden"):
        gate.authorize(p, quality_passed=True)


def test_gate_refuses_assumed_express_consent(gate):
    p = _sendable()
    p.contact.consent_basis = "express"
    with pytest.raises(ComplianceFailure, match="never assumed"):
        gate.authorize(p, quality_passed=True)


def test_gate_blocks_suppressed_recipient(gate):
    p = _sendable()
    gate.suppression.add(p.contact.business_email)
    with pytest.raises(ComplianceFailure, match="suppression"):
        gate.authorize(p, quality_passed=True)


def test_gate_blocks_non_build_decision(gate):
    p = _sendable()
    p.decision = Decision.ENRICH
    with pytest.raises(ComplianceFailure, match="not BUILD"):
        gate.authorize(p, quality_passed=True)


def test_gate_passes_and_audits(gate):
    rec = gate.authorize(_sendable(), quality_passed=True)
    assert rec.gate_passed
    assert rec.jurisdictions == ["CASL"]
    assert rec.consent_basis == "implied_published_business_contact"


def test_footer_carries_identification_and_unsubscribe(gate):
    f = gate.footer(_sendable())
    assert "REAL Partners Ltd." in f
    assert "130 Queens Quay E" in f
    assert "Unsubscribe:" in f
    assert "10 days" in f


def test_blocked_send_is_still_audited(gate, tmp_path):
    p = _sendable()
    p.contact.owner_source = "breach_data"
    with pytest.raises(ComplianceFailure):
        gate.authorize(p, quality_passed=True)
    log = (tmp_path / "audit.jsonl").read_text()
    assert '"gate_passed": false' in log


# -- the hottest signature -------------------------------------------------
def test_hottest_signature_detected():
    from salesagent import hottest_signature
    p = mk(capability__router_brands=["biesse"],
           capability__software=["cabinet vision"],
           capability__ppsa_lien_months_ago=5,
           firmographic__manufacturer_tag=True)
    evidenced(p)
    score(p)
    set_trigger(p, "estimator_posting", "2026-07-01")
    assert hottest_signature(p)
