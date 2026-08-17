"""Claude Code integration.

Capability label: **Observe**. The adapter records normalized tool-call evidence
and repeated-work recommendations in a local Decision Ledger. It never blocks a
tool call and never changes what Claude Code does next.

Claude Code separates ``PostToolUse`` from ``PostToolUseFailure``, so success and
failure are engine-declared facts here rather than inferences, and ``duration_ms``
gives measured latency. Per-tool token usage is not exposed by the hook surface and
is reported as unavailable rather than as zero.
"""

from .events import (
    PostToolUseEvent,
    PostToolUseFailureEvent,
    PreToolUseEvent,
    SessionEvent,
    parse_hook_event,
)
from .installer import (
    PLUGIN_SELECTOR,
    ClaudeCodeDoctorReport,
    ClaudeCodeInstallation,
    inspect_claude_code,
    install,
    uninstall,
)
from .normalization import ENGINE, session_boundary, tool_call_end, tool_call_start
from .service import (
    HookResult,
    hook_main,
    observe_outcome,
    run_hook,
    start_session_service,
    stop_session_service,
)

__all__ = [
    "ENGINE",
    "PLUGIN_SELECTOR",
    "ClaudeCodeDoctorReport",
    "ClaudeCodeInstallation",
    "HookResult",
    "PostToolUseEvent",
    "PostToolUseFailureEvent",
    "PreToolUseEvent",
    "SessionEvent",
    "hook_main",
    "inspect_claude_code",
    "install",
    "observe_outcome",
    "parse_hook_event",
    "run_hook",
    "session_boundary",
    "start_session_service",
    "stop_session_service",
    "tool_call_end",
    "tool_call_start",
    "uninstall",
]
