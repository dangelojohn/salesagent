#!/usr/bin/env python3
"""Runnable demo: full C1/C2 cycle over real Ontario cabinetry shops.

Fixtures stand in for live sources. Swap the `fetch` callables for real
crawlers and this runs unchanged -- that's the point of the adapter protocol.

    python3 demo_run.py
"""

from __future__ import annotations

import json
from pathlib import Path

from salesagent import (
    ComplianceFailure, ComplianceGate, CostGovernor, Decision, KillSwitch,
    Pipeline, Prospect, SenderIdentity, SuppressionList, hottest_signature,
)
from salesagent.models import Locality
from salesagent.sources import (
    ContactResolverAdapter, DealerShowcaseAdapter, JobBoardAdapter,
    PPSAAdapter, PlacesAdapter, RegistryAdapter, ReviewAdapter,
    TriggerFeedAdapter, WebsiteAdapter,
)
from salesagent.models import Stage

FIXTURES = json.loads((Path(__file__).parent / "data" / "ontario_fixtures.json").read_text())


def f(section: str):
    """Fixture fetcher bound to a section of the fixture file."""
    def _fetch(p: Prospect):
        return FIXTURES.get(p.prospect_id, {}).get(section)
    return _fetch


def build_pipeline() -> Pipeline:
    seeds = [
        Prospect(
            prospect_id=pid,
            company=d["company"],
            locality=Locality(**d.get("locality", {})),
        )
        for pid, d in FIXTURES.items()
    ]
    for p in seeds:
        p.firmographic.employees_est = FIXTURES[p.prospect_id].get("employees")

    adapters = {
        Stage.SCORE:   [PlacesAdapter(f("places")), WebsiteAdapter(f("website"))],
        Stage.CONFIRM: [
            JobBoardAdapter(f("jobs")),
            ReviewAdapter(lambda p: [
                (r["text"], r["url"]) for r in (FIXTURES[p.prospect_id].get("reviews") or [])
            ]),
            PPSAAdapter(f("ppsa")),
            RegistryAdapter(f("registry")),
            DealerShowcaseAdapter(f("dealer")),
        ],
        Stage.TRIGGER: [TriggerFeedAdapter(f("trigger"))],
        Stage.CONTACT: [ContactResolverAdapter(f("contact"))],
    }

    return Pipeline(
        seeds=seeds,
        adapters=adapters,
        governor=CostGovernor(per_cycle_ceiling=1.00, per_day_ceiling=50.00),
        kill=KillSwitch(),
    )


def main() -> None:
    pl = build_pipeline()
    results = pl.run()

    print("=" * 78)
    print("C1/C2 DISCOVERY + VALIDATION -- Ontario cabinetry, Southbrook template")
    print("=" * 78)

    for p in sorted(results, key=lambda x: (x.decision.value, -x.scores.fit_score)):
        conf = p.scores.absence_confidence
        trig = p.scores.trigger.priority.value
        hot = "  <<< HOTTEST SIGNATURE" if hottest_signature(p) else ""
        print(f"\n{p.decision.value:<8} {p.company[:42]:<42} "
              f"fit={p.scores.fit_score:>3}  conf={conf:.2f}  "
              f"trig={trig:<4} track={p.track.value}{hot}")
        print(f"         software={p.capability.software_tier.value:<12} "
              f"router={p.capability.router_tier.value}")
        if p.dq_reasons:
            for r in p.dq_reasons:
                print(f"         DQ: {r}")
        for e in p.evidence[:3]:
            print(f"         + {e.signal} (w={e.w}, c={e.c}) :: {e.matched_text[:52]!r}")
        if len(p.evidence) > 3:
            print(f"         ... {len(p.evidence) - 3} more cited signals")

    print("\n" + "=" * 78)
    print("SUMMARY:", pl.summary(results))
    print(f"cycle spend: ${pl.governor.cycle_spend:.4f}  "
          f"day spend: ${pl.governor.day_spend:.4f}")

    queue = pl.build_queue(results)
    print(f"\nBUILD QUEUE ({len(queue)}) -- ordered by trigger, then confidence, then fit:")
    for i, p in enumerate(queue, 1):
        print(f"  {i}. [{p.scores.trigger.priority.value}] {p.company} "
              f"(fit {p.scores.fit_score}, conf {p.scores.absence_confidence:.2f}, "
              f"{p.track.value})")

    # ---- compliance gate on the queue -----------------------------------
    print("\n" + "-" * 78)
    print("COMPLIANCE GATE (nothing ships that fails)")
    gate = ComplianceGate(
        sender=SenderIdentity(
            "REAL Partners Ltd. (OdooIQ)",
            "130 Queens Quay East, Toronto, ON",
            "437-220-8793", "dangelo.john@gmail.com",
        ),
        suppression=SuppressionList(),
        unsubscribe_base="https://odooiq.example",
        audit_log=Path("/tmp/audit.jsonl"),
    )
    for p in queue:
        try:
            rec = gate.authorize(p, quality_passed=True)
            print(f"  PASS  {p.company:<38} juris={rec.jurisdictions} "
                  f"rule={rec.jurisdiction_rule}")
        except ComplianceFailure as e:
            print(f"  BLOCK {p.company:<38} {e}")

    if queue:
        print("\n--- sample footer (mandatory on every CEM) ---")
        print(gate.footer(queue[0]))


if __name__ == "__main__":
    main()
