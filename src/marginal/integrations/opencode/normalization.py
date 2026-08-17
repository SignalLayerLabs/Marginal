"""Map OpenCode bridge requests onto the engine-neutral hook contract.

OpenCode has no per-tool success flag. Its shell tool reports an exit code in
result metadata, which is a provable signal; most other tools report nothing that
distinguishes success from a completed failure. Those stay ``UNKNOWN``.

A tool that throws produces no ``tool.execute.after`` call at all, so its proposal
is never completed and is settled as unobservable when the session closes.
"""

from __future__ import annotations

from marginal.controls import ActionOutcomeStatus

from ..hookkit.events import ToolCallEnd, ToolCallStart
from ..hookkit.outcomes import classify_structured_result
from .events import ToolEndRequest, ToolStartRequest

ENGINE = "opencode"


def tool_call_start(request: ToolStartRequest) -> ToolCallStart:
    if not isinstance(request, ToolStartRequest):
        raise TypeError("request must be a ToolStartRequest")
    return ToolCallStart(
        session_id=request.session_id,
        call_id=request.call_id,
        tool_name=request.tool_name,
        tool_input=request.arguments,
    )


def classify_outcome(request: ToolEndRequest) -> ActionOutcomeStatus:
    """Classify only the outcome signals the plugin was able to prove."""

    if not isinstance(request, ToolEndRequest):
        raise TypeError("request must be a ToolEndRequest")
    return classify_structured_result(dict(request.signals))


def tool_call_end(request: ToolEndRequest) -> ToolCallEnd:
    return ToolCallEnd(
        session_id=request.session_id,
        call_id=request.call_id,
        tool_name=request.tool_name,
        outcome=classify_outcome(request),
        tool_input=request.arguments,
        evidence={"digest": request.evidence_digest} if request.evidence_digest else None,
        duration_ms=request.duration_ms,
    )
