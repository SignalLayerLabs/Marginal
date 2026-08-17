"""Shared building blocks for hook-based engine adapters.

``hookkit`` holds the parts of a hook integration that are genuinely engine
independent: normalized events, privacy-safe action normalization, conservative
outcome classification, workspace state evidence, and session correlation.

Each engine adapter keeps its own parser for its own native payload and declares
only what that engine documents. The Codex integration predates this module and
still carries its own copies; migrating it is deliberately separate work so that
the validated Codex path is not disturbed by a new adapter.
"""

from .bootstrap import (
    OBSERVE_CAPABILITIES,
    ObserveSession,
    build_observe_session,
    session_hash,
    workspace_hash,
)
from .events import HookEvent, SessionBoundary, ToolCallEnd, ToolCallStart
from .normalization import classify_action, normalize_tool_call, semantic_key
from .outcomes import classify_structured_result, completion_evidence_hash
from .session import HookIntegrationError, HookSessionRuntime
from .state import workspace_state_hash

__all__ = [
    "OBSERVE_CAPABILITIES",
    "HookEvent",
    "HookIntegrationError",
    "HookSessionRuntime",
    "ObserveSession",
    "SessionBoundary",
    "ToolCallEnd",
    "ToolCallStart",
    "build_observe_session",
    "classify_action",
    "classify_structured_result",
    "completion_evidence_hash",
    "normalize_tool_call",
    "semantic_key",
    "session_hash",
    "workspace_hash",
    "workspace_state_hash",
]
