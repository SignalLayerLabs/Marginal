"""Optional controls that harden MARGINAL without coupling the core to one engine."""

from .diminishing import (
    DiminishingReturnConfig,
    DiminishingReturnDetector,
    DiminishingReturnSignal,
)
from .governance import GovernanceTracker
from .progress import (
    ActionOutcomeStatus,
    NoProgressConfig,
    NoProgressDetector,
    NoProgressSignal,
)

__all__ = [
    "ActionOutcomeStatus",
    "DiminishingReturnConfig",
    "DiminishingReturnDetector",
    "DiminishingReturnSignal",
    "GovernanceTracker",
    "NoProgressConfig",
    "NoProgressDetector",
    "NoProgressSignal",
]
