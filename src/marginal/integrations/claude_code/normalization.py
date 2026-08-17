"""Map Claude Code hook events onto the engine-neutral hook contract.

Claude Code separates success from failure at the event level: ``PostToolUse``
documents a tool call that completed successfully and ``PostToolUseFailure``
documents one that failed. That makes the outcome an engine-declared fact rather
than something inferred from response text.

An interrupted call is neither. The tool never reached its own conclusion, so it
is reported as ``UNKNOWN`` instead of being charged as a tool failure.
"""

from __future__ import annotations

from marginal.controls import ActionOutcomeStatus

from ..hookkit.events import SessionBoundary, ToolCallEnd, ToolCallStart
from .events import (
    PostToolUseEvent,
    PostToolUseFailureEvent,
    PreToolUseEvent,
    SessionEvent,
)

ENGINE = "claude-code"


def session_boundary(event: SessionEvent) -> SessionBoundary:
    if not isinstance(event, SessionEvent):
        raise TypeError("event must be a SessionEvent")
    return SessionBoundary(
        engine=ENGINE,
        session_id=event.session_id,
        workspace=event.cwd,
        kind="start" if event.hook_event_name == "SessionStart" else "end",
        source=event.source,
        reason=event.reason,
    )


def tool_call_start(event: PreToolUseEvent) -> ToolCallStart:
    if not isinstance(event, PreToolUseEvent):
        raise TypeError("event must be a PreToolUseEvent")
    return ToolCallStart(
        session_id=event.session_id,
        call_id=event.tool_use_id,
        tool_name=event.tool_name,
        tool_input=event.tool_input,
        turn_id=event.prompt_id,
    )


def tool_call_end(event: PostToolUseEvent | PostToolUseFailureEvent) -> ToolCallEnd:
    if isinstance(event, PostToolUseEvent):
        outcome = ActionOutcomeStatus.SUCCESS
        evidence: object = event.tool_response
    elif isinstance(event, PostToolUseFailureEvent):
        outcome = ActionOutcomeStatus.UNKNOWN if event.is_interrupt else ActionOutcomeStatus.FAILURE
        evidence = {"error": event.error, "is_interrupt": event.is_interrupt}
    else:
        raise TypeError("event must be a PostToolUse or PostToolUseFailure event")
    return ToolCallEnd(
        session_id=event.session_id,
        call_id=event.tool_use_id,
        tool_name=event.tool_name,
        outcome=outcome,
        tool_input=event.tool_input,
        evidence=evidence,
        duration_ms=event.duration_ms,
        turn_id=event.prompt_id,
    )
