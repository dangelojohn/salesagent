#!/usr/bin/env python3
"""Calibration harness. Run this BEFORE the agent runs unattended.

Hand-score ten shops. Compare against the agent.

    If the agent disagrees with you more than twice in ten
        -> the C weights are wrong, not the model.
    If it NEVER disagrees
        -> your threshold is too loose, and you will build demos
           for shops that already have an ERP.

Also checks for SATURATION: if absence_confidence pins at 1.00 across most
of the corpus, the axis has stopped discriminating and the threshold is
decorative. That is a silent, expensive failure -- it means every high-fit
prospect passes the confidence gate regardless of evidence quality.

    python3 calibrate.py

The corpus is data/ontario_real.json -- ten REAL Ontario cabinetry/millwork
manufacturers, every fact sourced (see data/ontario_real_SOURCES.md). Fill in
HAND_SCORED below with your own judgments, then re-run. Until you do, this
prints the agent's decision + evidence per shop so you can score by hand.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

from demo_run import build_pipeline, load_fixtures
from salesagent import Decision, Prospect

REAL_FIXTURES = Path(__file__).parent / "data" / "ontario_real.json"

# --------------------------------------------------------------------------
# YOUR hand judgments -- the ground truth the agent is calibrated against.
#
# TODO(you): score each of the ten real shops BY HAND from the sourced
# evidence (data/ontario_real_SOURCES.md and the per-shop report this script
# prints). Do NOT copy the agent's decision -- the whole point of the harness
# is that your independent judgment disagrees with the agent 1-2 times in ten.
# Uncomment and set each to Decision.BUILD / ENRICH / PARK / ARCHIVE.
# --------------------------------------------------------------------------
HAND_SCORED: dict[str, Decision] = {
    # "on-cab-r001": Decision.???,   # Deslaurier Custom Cabinets (Renfrew)
    # "on-cab-r002": Decision.???,   # Laurysen Kitchens (Carleton Place)
    # "on-cab-r003": Decision.???,   # Chervin Kitchen & Bath (Hawkesville)
    # "on-cab-r004": Decision.???,   # AyA Kitchens and Baths (Mississauga)
    # "on-cab-r005": Decision.???,   # Cartier Kitchens (Brampton)
    # "on-cab-r006": Decision.???,   # Downsview Kitchens (Mississauga)
    # "on-cab-r007": Decision.???,   # Muti Kitchen & Bath (Toronto)
    # "on-cab-r008": Decision.???,   # Magnum Kitchens (Mississauga)
    # "on-cab-r009": Decision.???,   # Bloomsbury Fine Cabinetry (Newmarket)
    # "on-cab-r010": Decision.???,   # Tuscan Woodworks (North York)
}

SATURATION_CEILING = 0.98
SATURATION_SHARE = 0.40      # >40% of live prospects pinned at ceiling = broken axis
MAX_DISAGREEMENTS = 2
MIN_DISAGREEMENTS = 1        # zero disagreement means the threshold is decorative


@dataclass
class Row:
    prospect: Prospect
    expected: Decision

    @property
    def agrees(self) -> bool:
        return self.prospect.decision is self.expected


def _print_agent_report(results: dict[str, Prospect]) -> None:
    """The agent's read of each shop, with cited evidence -- score against this."""
    print("=" * 78)
    print("AGENT READ OF THE REAL CORPUS -- hand-score against this")
    print("=" * 78)
    for pid, p in sorted(results.items()):
        print(f"\n{pid}  {p.company}")
        print(f"    agent={p.decision.value:<8} fit={p.scores.fit_score:>3} "
              f"conf={p.scores.absence_confidence:.2f} track={p.track.value} "
              f"software={p.capability.software_tier.value} "
              f"router={p.capability.router_tier.value}")
        for r in p.dq_reasons:
            print(f"    DQ: {r}")
        for e in p.evidence[:4]:
            print(f"    + {e.signal} (w={e.w}, c={e.c}) :: {e.matched_text[:56]!r}")
        if len(p.evidence) > 4:
            print(f"    ... {len(p.evidence) - 4} more cited signals")


def main() -> int:
    fixtures = load_fixtures(REAL_FIXTURES)
    pl = build_pipeline(fixtures, live_jobs=False)  # calibration is always offline
    results = {p.prospect_id: p for p in pl.run()}

    _print_agent_report(results)

    if not HAND_SCORED:
        print("\n" + "-" * 78)
        print("NOT CALIBRATED: HAND_SCORED is empty. Fill it in calibrate.py with")
        print("YOUR judgments, then re-run to calibrate the weights.")
        # Non-zero on purpose: an unscored corpus is NOT 'safe to run unattended'.
        # Never let a green exit stand in for a calibration that never ran.
        return 1

    rows = [Row(results[pid], exp) for pid, exp in HAND_SCORED.items() if pid in results]

    print("\n" + "=" * 74)
    print("CALIBRATION -- agent vs. hand-scored ground truth")
    print("=" * 74)

    disagreements = []
    for r in rows:
        p = r.prospect
        mark = "ok " if r.agrees else "XX "
        print(f"{mark} {p.company[:36]:<36} agent={p.decision.value:<8} "
              f"hand={r.expected.value:<8} fit={p.scores.fit_score:>3} "
              f"conf={p.scores.absence_confidence:.2f}")
        if not r.agrees:
            disagreements.append(r)

    n = len(rows)
    d = len(disagreements)
    print(f"\nagreement: {n - d}/{n}")

    problems: list[str] = []

    # -- verdict on disagreement count ------------------------------------
    if d > MAX_DISAGREEMENTS:
        problems.append(
            f"{d} disagreements (> {MAX_DISAGREEMENTS}). The C weights are wrong, "
            "not the model. Retune before running unattended."
        )
    elif d < MIN_DISAGREEMENTS:
        problems.append(
            "Zero disagreements. The threshold is too loose -- the agent is "
            "agreeing with you by construction, not by discrimination. "
            "Tighten CONFIDENCE_THRESHOLD until it pushes back."
        )

    # -- saturation check: the silent failure -----------------------------
    live = [r.prospect for r in rows if r.prospect.decision is not Decision.ARCHIVE]
    if live:
        confs = [p.scores.absence_confidence for p in live]
        pinned = [c for c in confs if c >= SATURATION_CEILING]
        share = len(pinned) / len(confs)
        spread = max(confs) - min(confs) if len(confs) > 1 else 0.0

        print(f"\nconfidence axis: n={len(confs)} mean={statistics.mean(confs):.2f} "
              f"spread={spread:.2f} pinned_at_ceiling={share:.0%}")

        if share > SATURATION_SHARE:
            problems.append(
                f"SATURATION: {share:.0%} of live prospects pin absence_confidence "
                f">= {SATURATION_CEILING}. The axis has stopped discriminating and "
                "the threshold is decorative -- every high-fit prospect passes the "
                "confidence gate regardless of evidence quality.\n"
                "    Fix: the C contributions are additive and compound too fast. "
                "Either (a) cap per-category contribution (one software signal, one "
                "job signal, one review signal), or (b) switch to a diminishing "
                "combiner: conf = 1 - PROD(1 - c_i), which is what independent "
                "evidence actually implies."
            )

    # -- fit score sanity --------------------------------------------------
    fits = [r.prospect.scores.fit_score for r in rows]
    if max(fits) > 20:
        problems.append(
            f"Fit scores reach {max(fits)} against a threshold of 7. The scale is "
            "meaningless above ~14. Either normalize, or accept that fit is a "
            "binary gate and stop reading it as a ranking."
        )

    print()
    if problems:
        print("PROBLEMS FOUND -- do not run unattended:\n")
        for i, p_ in enumerate(problems, 1):
            print(f"  {i}. {p_}\n")
        return 1

    print("Calibrated. Safe to run unattended at the current ramp.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
