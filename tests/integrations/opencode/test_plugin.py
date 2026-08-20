"""The shipped OpenCode plugin must keep its safety properties.

The plugin is JavaScript, so these are source-level contract checks rather than
behavioral tests. The bridge protocol it speaks is covered in test_bridge.py.
"""

from marginal.integrations.opencode.installer import bundled_plugin_path
from marginal.integrations.opencode.targets import PLUGIN_MARKER


def _source() -> str:
    return bundled_plugin_path().read_text(encoding="utf-8")


def _statements() -> list[str]:
    """Return source lines with comment-only lines removed."""

    return [
        line
        for line in _source().splitlines()
        if not line.strip().startswith("//") and line.strip()
    ]


def test_the_plugin_carries_its_ownership_marker() -> None:
    assert PLUGIN_MARKER in _source()


def test_the_plugin_registers_only_observation_hooks() -> None:
    source = _source()
    assert '"tool.execute.before"' in source
    assert '"tool.execute.after"' in source
    assert "dispose" in source
    # Blocking in OpenCode means throwing out of a hook, and Shadow Mode never does.
    assert not [line for line in _statements() if "throw" in line]
    assert "permission.ask" not in source


def test_the_plugin_never_forwards_tool_output() -> None:
    assert "evidence_digest: digest(" in _source()
    # Tool output is only ever read inside the digest call.
    for line in _statements():
        if "output?.output" in line:
            assert "digest(" in line


def test_the_plugin_forwards_only_allowlisted_outcome_signals() -> None:
    source = _source()
    assert 'OUTCOME_SIGNAL_KEYS = ["exit", "exit_code", "exitCode", "success", "status"]' in source
    assert "signals: outcomeSignals(output?.metadata)" in source


def test_the_plugin_spawns_the_documented_bridge_module() -> None:
    source = _source()
    assert '"-m", "marginal.integrations.opencode.bridge"' in source
    assert "MARGINAL_PYTHON" in source
    assert "MARGINAL_RUNTIME" in source


def test_the_plugin_becomes_a_no_op_when_the_bridge_is_unavailable() -> None:
    source = _source()
    assert "if (!bridge.available) return {}" in source
    assert "REQUEST_TIMEOUT_MS" in source
