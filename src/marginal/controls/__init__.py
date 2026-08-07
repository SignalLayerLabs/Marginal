"""Optional controls that harden MARGINAL without coupling the core to one engine."""

from .diminishing import (
    DiminishingReturnConfig,
    DiminishingReturnDetector,
    DiminishingReturnSignal,
)
from .governance import GovernanceTracker

__all__ = [
    "DiminishingReturnConfig",
    "DiminishingReturnDetector",
    "DiminishingReturnSignal",
    "GovernanceTracker",
]
