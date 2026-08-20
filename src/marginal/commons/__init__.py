"""Privacy-preserving, model-specific MARGINAL Commons primitives."""

from .config import CommonsConfig, CommonsMode, configure_commons_mode, load_commons_config
from .evidence import CommonsEvidenceAtom, compile_verified_evidence
from .identity import (
    CanonicalModelIdentity,
    resolve_canonical_model,
    resolve_model_attribution,
)

__all__ = [
    "CanonicalModelIdentity",
    "CommonsConfig",
    "CommonsEvidenceAtom",
    "CommonsMode",
    "compile_verified_evidence",
    "configure_commons_mode",
    "load_commons_config",
    "resolve_canonical_model",
    "resolve_model_attribution",
]
