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
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from demo_run import build_pipeline
from salesagent import Decision, Prospect

# --------------------------------------------------------------------------
# Your hand judgments. Fill these in from a half-day of job-board + site
# reading. This is the ground truth the agent is calibrated against.
# --------------------------------------------------------------------------
HAND_SCORED: dict[str, Decision] = {
    "on-cab-0001": Decision.BUILD,     # Greystone: CNC + Cabinet Vision + Excel estimator post
    "on-cab-0002": Decision.ARCHIVE,   # Northline: INNERGY rollout named in job post
    "on-cab-0003": Decision.BUILD,     # Lakeside: US-domiciled, cross-border wedge
    "on-cab-0004": Decision.ARCHIVE,   # Precision: Cyncly Insight on the website
    "on-cab-0005": Decision.ARCHIVE,   # Bay Street: showroom, no shop floor
    "on-cab-0006": Decision.ARCHIVE,   # Hollow Pine: ShopBot, too small
    "on-cab-0007": Decision.ARCHIVE,   # Grand River: INNERGY case study
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


def main() -> int:
    pl = build_pipeline()
    results = {p.prospect_id: p for p in pl.run()}

    rows = [Row(results[pid], exp) for pid, exp in HAND_SCORED.items() if pid in results]

    print("=" * 74)
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
