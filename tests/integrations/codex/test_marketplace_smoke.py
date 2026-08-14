from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from scripts.smoke_codex_plugin import smoke_plugin

REPO = Path(__file__).resolve().parents[3]


def test_plugin_bundle_registers_user_prompt_submit_hook() -> None:
    payload = json.loads((REPO / "plugins" / "marginal" / "hooks" / "hooks.json").read_text())

    assert "UserPromptSubmit" in payload["hooks"]


@pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is not installed")
def test_marketplace_install_and_remove(tmp_path: Path) -> None:
    result = smoke_plugin(
        codex=Path(shutil.which("codex") or "codex"),
        isolation_root=tmp_path,
        marketplace=REPO,
    )

    assert result.installed is True
    assert result.shadow_block_count == 0
    assert result.hook_coverage == 1.0
    assert result.evidence_records >= 4
    assert result.completed_sessions == 1
    assert result.native_control_observed is True
    assert result.native_control_mode == "shadow"
    assert result.launcher_python_version.startswith("Python 3.")
    assert result.raw_secret_occurrences == 0
    assert result.removed is True
