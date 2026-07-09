"""Pipeline: S0 SEED -> S1 SCORE -> S2 CONFIRM -> S3 TRIGGER -> S4 CONTACT.

Sources are STAGES, not equal-weight inputs. Cheap sources seed; expensive
sources confirm. Cost per qualified prospect is held down by the funnel
shape, not by throttling.

Hard rules enforced here:
  S2 never runs on fit_score < 6
  S3 never runs on fit_score < 7
  The cost governor cannot be overridden by any agent. Only John raises ceilings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

from .models import Decision, Prospect, Stage, Trigger, TriggerPriority
from .scoring import queue_key, score
from .taxonomy import TRIGGERS

S2_GATE = 6   # never confirm below this fit
S3_GATE = 7   # never look for triggers below this fit


class CostCeilingExceeded(Exception):
    """Governor tripped. Halts the cycle. Only a human raises the ceiling."""


@dataclass
class CostGovernor:
    """The financial brake. Cannot be overridden by any agent."""
    per_cycle_ceiling: float
    per_day_ceiling: float
    throttle_at: float = 0.85          # fraction of ceiling that triggers warning
    cycle_spend: float = 0.0
    day_spend: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def charge(self, amount: float, what: str) -> None:
        self.cycle_spend += amount
        self.day_spend += amount

        if self.cycle_spend > self.per_cycle_ceiling:
            raise CostCeilingExceeded(
                f"Per-cycle ceiling ${self.per_cycle_ceiling:.2f} exceeded "
                f"at '{what}' (spend ${self.cycle_spend:.2f})."
            )
        if self.day_spend > self.per_day_ceiling:
            raise CostCeilingExceeded(
                f"Per-day ceiling ${self.per_day_ceiling:.2f} exceeded "
                f"at '{what}' (spend ${self.day_spend:.2f})."
            )
        if self.cycle_spend > self.per_cycle_ceiling * self.throttle_at:
            self.warnings.append(
                f"Cycle spend at {self.cycle_spend / self.per_cycle_ceiling:.0%} of ceiling."
            )

    def reset_cycle(self) -> None:
        self.cycle_spend = 0.0


class KillSwitch:
    """A single human stop. Supreme over every agent. Checked at each stage."""

    def __init__(self) -> None:
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    @property
    def stopped(self) -> bool:
        return self._stopped

    def assert_running(self) -> None:
        if self._stopped:
            raise RuntimeError("Kill switch engaged. All outbound halted.")


# --------------------------------------------------------------------------
# Source adapter protocol. Implement per source; the pipeline stays ignorant.
# --------------------------------------------------------------------------
class SourceAdapter(Protocol):
    name: str
    stage: Stage
    cost_per_call: float

    def enrich(self, p: Prospect) -> Prospect:
        """Attach cited Evidence and/or capability facts. Never scores."""
        ...


@dataclass
class Pipeline:
    seeds: list[Prospect]
    adapters: dict[Stage, list[SourceAdapter]]
    governor: CostGovernor
    kill: KillSwitch = field(default_factory=KillSwitch)
    on_stage: Callable[[Stage, Prospect], None] | None = None

    # -- stages ------------------------------------------------------------
    def _run(self, p: Prospect, stage: Stage) -> Prospect:
        self.kill.assert_running()
        for a in self.adapters.get(stage, []):
            self.governor.charge(a.cost_per_call, f"{stage.value}:{a.name}")
            p = a.enrich(p)
        if self.on_stage:
            self.on_stage(stage, p)
        return p

    def score_stage(self, p: Prospect) -> Prospect:
        p = self._run(p, Stage.SCORE)
        return score(p)

    def confirm_stage(self, p: Prospect) -> Prospect:
        if p.scores.fit_score < S2_GATE:
            return p                     # funnel discipline: never confirm cheap names
        p = self._run(p, Stage.CONFIRM)
        return score(p)

    def trigger_stage(self, p: Prospect) -> Prospect:
        if p.scores.fit_score < S3_GATE:
            return p
        p = self._run(p, Stage.TRIGGER)
        return score(p)

    def contact_stage(self, p: Prospect) -> Prospect:
        if p.decision is not Decision.BUILD:
            return p
        return self._run(p, Stage.CONTACT)

    # -- full cycle --------------------------------------------------------
    def run(self) -> list[Prospect]:
        out: list[Prospect] = []
        for p in self.seeds:
            self.governor.reset_cycle()
            try:
                p = self.score_stage(p)
                if p.decision is Decision.ARCHIVE:
                    out.append(p)
                    continue
                p = self.confirm_stage(p)
                if p.decision is Decision.ARCHIVE:
                    out.append(p)
                    continue
                p = self.trigger_stage(p)
                p = self.contact_stage(p)
            except CostCeilingExceeded as e:
                p.routed_to = f"HALTED:{e}"
            out.append(p)
        return out

    # -- outputs -----------------------------------------------------------
    def build_queue(self, prospects: Iterable[Prospect]) -> list[Prospect]:
        """Timing beats fit. Sorted by trigger priority, then confidence, then fit."""
        return sorted(
            (p for p in prospects if p.decision is Decision.BUILD),
            key=queue_key,
        )

    @staticmethod
    def summary(prospects: Iterable[Prospect]) -> dict[str, int]:
        counts: dict[str, int] = {d.value: 0 for d in Decision}
        for p in prospects:
            counts[p.decision.value] += 1
        return counts


def set_trigger(p: Prospect, trigger_type: str, detected: str,
                expires: str | None = None) -> Prospect:
    """Attach a trigger. Priority comes from the taxonomy, never ad hoc."""
    prio = TRIGGERS.get(trigger_type)
    if prio is None:
        raise ValueError(f"Unknown trigger type: {trigger_type}")
    p.scores.trigger = Trigger(
        type=trigger_type,
        priority=TriggerPriority(prio),
        detected=detected,
        expires=expires,
    )
    return p
