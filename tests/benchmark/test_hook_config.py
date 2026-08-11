from __future__ import annotations

import json
from pathlib import Path

from benchmark.codex_adapter.hook_config import install_project_hooks


def test_project_hook_config_covers_pre_and_post_without_async_execution(tmp_path: Path) -> None:
    python = tmp_path / "python"
    client = tmp_path / "hook_client.py"
    python.write_text("", encoding="utf-8")
    client.write_text("", encoding="utf-8")

    config_path = install_project_hooks(
        tmp_path, python_executable=python, hook_client=client, timeout_seconds=60
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config_path == tmp_path / ".codex" / "hooks.json"
    assert set(config["hooks"]) == {"PreToolUse", "PostToolUse"}
    for event, operation in (("PreToolUse", "pre"), ("PostToolUse", "post")):
        group = config["hooks"][event][0]
        assert "matcher" not in group
        hook = group["hooks"][0]
        assert hook["type"] == "command"
        assert hook["timeout"] == 60
        assert hook["async"] is False
        assert str(python) in hook["command"]
        assert str(client) in hook["command"]
        assert hook["command"].endswith(operation)
