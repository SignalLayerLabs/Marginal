"""Compatibility re-export of the engine-neutral session transport.

The transport carries no Codex-specific behavior, so it now lives in
``marginal.integrations.transport`` where every hook-based adapter can share it.
This module remains a stable import path for existing callers.
"""

from __future__ import annotations

from ..transport import (
    MAX_MESSAGE_BYTES,
    ConnectionInfo,
    SessionHandler,
    SessionServer,
    connection_filename,
    request_session,
)

__all__ = [
    "MAX_MESSAGE_BYTES",
    "ConnectionInfo",
    "SessionHandler",
    "SessionServer",
    "connection_filename",
    "request_session",
]
