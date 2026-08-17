"""OpenCode integration.

Capability label: **Observe**. The adapter records normalized tool-call evidence and
repeated-work recommendations in a local Decision Ledger. It never blocks a tool
call and never changes what OpenCode does next.

OpenCode's plugin runs inside the engine process, so the plugin owns one bridge child
process rather than paying interpreter startup per tool call. Tool output never
reaches MARGINAL: the plugin sends a digest plus an allowlist of outcome signals.

Outcome observability is weaker here than in engines that report success and failure
as separate events. The shell tool reports an exit code, which is provable; most
other tools report nothing that separates success from a completed failure, and
those are recorded as ``unknown``. A tool that throws produces no completion hook at
all, so its proposal is settled as unobservable when the session closes.
"""

from .bridge import BridgeService, main, serve
from .events import (
    SessionRequest,
    ToolEndRequest,
    ToolStartRequest,
    parse_request,
)
from .installer import (
    OpenCodeDoctorReport,
    OpenCodeInstallation,
    bundled_plugin_path,
    inspect_opencode,
    install,
    is_marginal_plugin,
    render_plugin,
    uninstall,
)
from .normalization import ENGINE, classify_outcome, tool_call_end, tool_call_start
from .targets import OPENCODE, PRIVACYCODE, TARGETS, OpenCodeTarget, resolve_target

__all__ = [
    "ENGINE",
    "OPENCODE",
    "PRIVACYCODE",
    "TARGETS",
    "BridgeService",
    "OpenCodeDoctorReport",
    "OpenCodeInstallation",
    "OpenCodeTarget",
    "SessionRequest",
    "ToolEndRequest",
    "ToolStartRequest",
    "bundled_plugin_path",
    "classify_outcome",
    "inspect_opencode",
    "install",
    "is_marginal_plugin",
    "main",
    "parse_request",
    "render_plugin",
    "resolve_target",
    "serve",
    "tool_call_end",
    "tool_call_start",
    "uninstall",
]
