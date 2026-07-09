"""salesagent -- C1/C2 discovery + validation agent.

Package root re-exports the names the entry points import directly from
`salesagent` (see demo_run.py, calibrate.py, tests/test_agent.py). Submodules
(salesagent.models, .taxonomy, .scoring, .pipeline, .extractors, .sources)
remain importable by their full path.
"""

from __future__ import annotations

from .models import Decision, Evidence, Prospect, Stage, Track
from .scoring import hottest_signature, score
from .pipeline import (
    CostCeilingExceeded,
    CostGovernor,
    KillSwitch,
    Pipeline,
    set_trigger,
)
from .compliance import (
    ComplianceFailure,
    ComplianceGate,
    SenderIdentity,
    SuppressionList,
)

__all__ = [
    # models
    "Decision",
    "Evidence",
    "Prospect",
    "Stage",
    "Track",
    # scoring
    "score",
    "hottest_signature",
    # pipeline
    "Pipeline",
    "CostGovernor",
    "CostCeilingExceeded",
    "KillSwitch",
    "set_trigger",
    # compliance
    "ComplianceGate",
    "ComplianceFailure",
    "SenderIdentity",
    "SuppressionList",
]
