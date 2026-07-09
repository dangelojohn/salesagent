"""Source adapters subpackage.

Re-exports the adapter classes from adapters.py so callers can do
`from salesagent.sources import PlacesAdapter, JobBoardAdapter, ...`
(see demo_run.py).
"""

from __future__ import annotations

from .adapters import (
    CommunityAdapter,
    ContactResolverAdapter,
    DealerShowcaseAdapter,
    JobBoardAdapter,
    PPSAAdapter,
    PlacesAdapter,
    RegistryAdapter,
    ReviewAdapter,
    TriggerFeedAdapter,
    WebsiteAdapter,
)

__all__ = [
    "PlacesAdapter",
    "WebsiteAdapter",
    "JobBoardAdapter",
    "ReviewAdapter",
    "CommunityAdapter",
    "PPSAAdapter",
    "RegistryAdapter",
    "DealerShowcaseAdapter",
    "TriggerFeedAdapter",
    "ContactResolverAdapter",
]
