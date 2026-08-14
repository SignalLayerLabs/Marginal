"""Ephemeral user-control intent and strict MARGINAL control-plane recognition."""

from __future__ import annotations

import re
import shlex
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .events import PreToolUseEvent

_CONTROL_SUBCOMMANDS = frozenset({"status", "doctor", "review", "promote", "demote"})
_PYTHON_LAUNCHERS = frozenset({"python", "python3", "py"})
_SHELL_SYNTAX = re.compile(r"[;&|<>`$\r\n]")
_NEGATED_CONTROL = re.compile(
    r"\b(?:do\s+not|don't|dont|never)\s+(?:please\s+)?"
    r"(?:repeat|redo|run|execute|proceed|force|pause|stop|suspend|resume|unpause|reactivate)\b|"
    r"\b(?:non|mai)\s+(?:"
    r"ripetere|rifare|eseguire|esegui|procedere|procedi|forzare|mettere\s+in\s+pausa|"
    r"fermare|sospendere|"
    r"riprendere|riattivare"
    r")\b"
)
_ACTION_OPTIONS = {
    "status": frozenset({"--workspace", "--json"}),
    "doctor": frozenset({"--json"}),
    "review": frozenset({"--workspace", "--candidate", "--verdict", "--json"}),
    "promote": frozenset({"--workspace", "--json"}),
    "demote": frozenset({"--workspace", "--json"}),
}
_VALUE_OPTIONS = frozenset({"--workspace", "--candidate", "--verdict"})
_ACTION_HASH = re.compile(r"[0-9a-fA-F]{64}\Z")


@dataclass(frozen=True, slots=True)
class UserIntent:
    """User-requested control retained only by the live authenticated session."""

    repeat_requested: bool = False
    force_run: bool = False
    pause_marginal: bool = False
    resume_marginal: bool = False
    status_requested: bool = False


def _normalized_prompt(prompt: str) -> str:
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    return " ".join(unicodedata.normalize("NFKC", prompt).casefold().split())


def _contains(prompt: str, expression: str) -> bool:
    return re.search(expression, prompt) is not None


def normalize_user_prompt(prompt: str) -> UserIntent:
    """Recognize only explicit English/Italian controls; uncertainty returns no intent."""

    text = _normalized_prompt(prompt)
    if not text or _NEGATED_CONTROL.search(text):
        return UserIntent()

    repeat_requested = _contains(
        text,
        r"\b(?:repeat|rifai|ripeti)\b|\b(?:run|do|try|execute)\s+(?:it\s+)?(?:again|once more)\b|"
        r"\b(?:esegui|fallo)\s+di\s+nuovo\b",
    )
    force_run = _contains(
        text,
        r"\bforce\s+(?:the\s+)?(?:run|execution|action)\b|\brun\s+(?:it\s+)?anyway\b|"
        r"\b(?:proceed|execute)\s+anyway\b|\bforza\s+l'?esecuzione\b|"
        r"\b(?:esegui|procedi)\s+comunque\b",
    )
    pause_marginal = "marginal" in text and _contains(
        text, r"\b(?:pause|stop|suspend|pausa|ferma|sospendi)\b"
    )
    resume_marginal = "marginal" in text and _contains(
        text, r"\b(?:resume|unpause|reactivate|riprendi|riattiva)\b"
    )
    status_requested = "marginal" in text and _contains(text, r"\b(?:status|state|stato)\b")
    if pause_marginal and resume_marginal:
        return UserIntent()
    return UserIntent(
        repeat_requested=repeat_requested,
        force_run=force_run,
        pause_marginal=pause_marginal,
        resume_marginal=resume_marginal,
        status_requested=status_requested,
    )


def _has_symlink(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    if current.is_symlink():
        return True
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            return True
    return False


def _valid_control_arguments(arguments: list[str]) -> bool:
    """Validate the small wrapper contract without executing its parser."""

    if not arguments or arguments[0].casefold() not in _CONTROL_SUBCOMMANDS:
        return False
    command = arguments[0].casefold()
    allowed = _ACTION_OPTIONS[command]
    values: dict[str, str] = {}
    flags: set[str] = set()
    index = 1
    while index < len(arguments):
        option = arguments[index]
        if option not in allowed or option in flags or option in values:
            return False
        if option in _VALUE_OPTIONS:
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
                return False
            values[option] = arguments[index + 1]
            index += 2
        else:
            flags.add(option)
            index += 1

    candidate = values.get("--candidate")
    verdict = values.get("--verdict")
    if (candidate is None) != (verdict is None):
        return False
    if candidate is not None and _ACTION_HASH.fullmatch(candidate) is None:
        return False
    return verdict is None or verdict in {"helpful", "waste"}


def is_control_plane_action(event: PreToolUseEvent, plugin_root: Path) -> bool:
    """Accept only a direct invocation of the installed MARGINAL control script."""

    if not isinstance(event, PreToolUseEvent) or event.tool_name.casefold() not in {
        "bash",
        "shell",
    }:
        return False
    command = event.tool_input.get("command")
    if not isinstance(command, str) or _SHELL_SYNTAX.search(command):
        return False
    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        return False
    if len(argv) < 3 or argv[0].casefold() not in _PYTHON_LAUNCHERS:
        return False
    script_index = 2 if argv[0].casefold() == "py" and argv[1] == "-3" else 1
    if len(argv) <= script_index + 1:
        return False
    script_argument = Path(argv[script_index])
    if not script_argument.is_absolute() or ".." in script_argument.parts:
        return False
    try:
        root = Path(plugin_root)
        if not root.is_absolute() or root.is_symlink():
            return False
        root = root.resolve(strict=True)
        expected = root / "scripts" / "marginal_control.py"
        if not (root / ".codex-plugin" / "plugin.json").is_file() or _has_symlink(expected, root):
            return False
        if script_argument.resolve(strict=True) != expected.resolve(strict=True):
            return False
    except (OSError, RuntimeError):
        return False
    return _valid_control_arguments(argv[script_index + 1 :])
