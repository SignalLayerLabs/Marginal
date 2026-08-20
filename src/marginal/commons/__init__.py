"""Privacy-preserving, model-specific MARGINAL Commons primitives."""

from .cache import CommonsCache, CommonsLifecycle, CommonsPrior
from .client import CommonsAck, CommonsClient
from .config import CommonsConfig, CommonsMode, configure_commons_mode, load_commons_config
from .evidence import CommonsEvidenceAtom, compile_verified_evidence
from .identity import (
    CanonicalModelIdentity,
    resolve_canonical_model,
    resolve_model_attribution,
)
from .outbox import CommonsOutbox, OutboxEntry
from .sync import CommonsSyncResult, synchronize_commons

__all__ = [
    "CanonicalModelIdentity",
    "CommonsAck",
    "CommonsCache",
    "CommonsClient",
    "CommonsConfig",
    "CommonsEvidenceAtom",
    "CommonsLifecycle",
    "CommonsMode",
    "CommonsOutbox",
    "CommonsPrior",
    "CommonsSyncResult",
    "OutboxEntry",
    "compile_verified_evidence",
    "configure_commons_mode",
    "load_commons_config",
    "resolve_canonical_model",
    "resolve_model_attribution",
    "synchronize_commons",
]
