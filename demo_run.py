#!/usr/bin/env python3
"""Runnable demo: full C1/C2 cycle over real Ontario cabinetry shops.

Fixtures stand in for live sources. Swap the `fetch` callables for real
crawlers and this runs unchanged -- that's the point of the adapter protocol.

    python3 demo_run.py
"""

from __future__ import annotations

import json
import os
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
from salesagent.sources.jobbank import JobBankFetcher
from salesagent.models import Stage


def _jobs_fetch(fixture_fetch, live: bool = False):
    """The JobBoardAdapter fetch callable.

    Live Job Bank Canada fetcher when ``live`` is True; otherwise the
    deterministic fixture fetch. Only the job board is wired to a live source
    (highest-confidence signal, c=0.35). ``live`` is resolved once, in
    build_pipeline, so callers that need reproducibility (calibrate.py) can
    force it off regardless of the environment.
    """
    if live:
        return JobBankFetcher(province="Ontario")
    return fixture_fetch

FIXTURES_PATH = Path(__file__).parent / "data" / "ontario_fixtures.json"


def load_fixtures(path=FIXTURES_PATH) -> dict:
    return json.loads(Path(path).read_text())


FIXTURES = load_fixtures()


def build_pipeline(fixtures: dict | None = None,
                   live_jobs: bool | None = None) -> Pipeline:
    """Assemble the S0-S4 pipeline over a fixture set.

    Defaults to the shipped demo fixtures; pass another dict (e.g. the real
    Ontario corpus) to run the same pipeline over different seeds.

    live_jobs: None -> resolve from SALESAGENT_LIVE_JOBS (opt-in); True/False
    forces the job board on/off explicitly (calibrate.py passes False so it is
    always offline and reproducible).
    """
    fixtures = FIXTURES if fixtures is None else fixtures
    if live_jobs is None:
        live_jobs = bool(os.environ.get("SALESAGENT_LIVE_JOBS"))

    def f(section: str):
        """Fixture fetcher bound to a section of the fixture file."""
        def _fetch(p: Prospect):
            return fixtures.get(p.prospect_id, {}).get(section)
        return _fetch

    seeds = [
        Prospect(
            prospect_id=pid,
            company=d["company"],
            locality=Locality(**d.get("locality", {})),
        )
        for pid, d in fixtures.items()
    ]
    for p in seeds:
        p.firmographic.employees_est = fixtures[p.prospect_id].get("employees")

    adapters = {
        Stage.SCORE:   [PlacesAdapter(f("places")), WebsiteAdapter(f("website"))],
        Stage.CONFIRM: [
            JobBoardAdapter(_jobs_fetch(f("jobs"), live_jobs)),
            ReviewAdapter(lambda p: [
                (r["text"], r["url"]) for r in (fixtures.get(p.prospect_id, {}).get("reviews") or [])
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
