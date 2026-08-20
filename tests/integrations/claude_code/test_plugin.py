"""The shipped plugin package must match the documented Claude Code contracts."""

import json
from pathlib import Path

import pytest

from marginal.integrations.claude_code.decisions import (
    build_post_tool_use_output,
    build_pre_tool_use_output,
)
from marginal.integrations.claude_code.events import SUPPORTED_EVENTS
from marginal.integrations.claude_code.installer import MARKETPLACE_NAME, PLUGIN_NAME

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / PLUGIN_NAME


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_marketplace_lists_the_plugin() -> None:
    marketplace = _load(REPOSITORY_ROOT / ".claude-plugin" / "marketplace.json")
    assert marketplace["name"] == MARKETPLACE_NAME
    plugins = marketplace["plugins"]
    assert isinstance(plugins, list)
    entry = next(plugin for plugin in plugins if plugin["name"] == PLUGIN_NAME)
    assert (REPOSITORY_ROOT / str(entry["source"])).is_dir()


def test_the_plugin_manifest_matches_the_installer_selector() -> None:
    manifest = _load(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
    assert manifest["name"] == PLUGIN_NAME
    assert manifest["license"] == "Apache-2.0"
    description = manifest["description"]
    assert isinstance(description, str)
    assert "Shadow Mode" in description


def test_the_plugin_declares_only_supported_hooks() -> None:
    hooks = _load(PLUGIN_ROOT / "hooks" / "hooks.json")["hooks"]
    assert isinstance(hooks, dict)
    assert set(hooks) == set(SUPPORTED_EVENTS)


def test_every_hook_runs_the_bundled_launcher() -> None:
    hooks = _load(PLUGIN_ROOT / "hooks" / "hooks.json")["hooks"]
    assert isinstance(hooks, dict)
    for matchers in hooks.values():
        for matcher in matchers:
            for hook in matcher["hooks"]:
                assert hook["type"] == "command"
                assert "${CLAUDE_PLUGIN_ROOT}/scripts/marginal_hook.py" in hook["command"]
                assert hook["timeout"] <= 10


def test_the_launcher_exists_and_never_raises_on_import() -> None:
    launcher = PLUGIN_ROOT / "scripts" / "marginal_hook.py"
    source = launcher.read_text(encoding="utf-8")
    assert "CLAUDE_PLUGIN_ROOT" in source
    assert "except Exception" in source


def test_shadow_mode_emits_no_output() -> None:
    assert build_pre_tool_use_output(allowed=True, reason="allowed", reason_code="APPROVED") is None
    assert build_post_tool_use_output(blocked=False, reason="ok", reason_code="APPROVED") is None


def test_the_deny_shape_follows_the_documented_contract() -> None:
    output = build_pre_tool_use_output(
        allowed=False,
        reason="Repeated proven-success action produced no new evidence",
        reason_code="NO_PROGRESS_ENFORCED",
    )
    assert output is not None
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert specific["permissionDecision"] == "deny"
    assert specific["permissionDecisionReason"].endswith("[NO_PROGRESS_ENFORCED]")


def test_the_block_shape_follows_the_documented_contract() -> None:
    output = build_post_tool_use_output(
        blocked=True,
        reason="Completion evidence did not change",
        reason_code="NO_PROGRESS_ENFORCED",
    )
    assert output is not None
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"
    assert specific["decision"] == "block"


@pytest.mark.parametrize("reason_code", ["", "   "])
def test_a_blank_reason_code_is_rejected(reason_code: str) -> None:
    with pytest.raises(ValueError):
        build_pre_tool_use_output(allowed=False, reason="denied", reason_code=reason_code)


def test_a_blank_reason_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_pre_tool_use_output(allowed=False, reason="  ", reason_code="NO_PROGRESS_ENFORCED")
