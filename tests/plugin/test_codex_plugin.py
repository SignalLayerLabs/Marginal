from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.build_codex_plugin import build_plugin_runtime

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "marginal"
MARKETPLACE = REPO / ".agents" / "plugins" / "marketplace.json"
VALIDATOR = Path(
    "/Users/renatovinai/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_marketplace_points_to_native_plugin() -> None:
    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))

    assert marketplace["name"] == "marginal"
    assert marketplace["plugins"][0]["source"] == {
        "source": "local",
        "path": "./plugins/marginal",
    }


def test_manifest_is_validator_clean() -> None:
    if not VALIDATOR.exists():
        pytest.skip("official Codex plugin validator is not installed")
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(PLUGIN)],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_hooks_cover_exact_supported_lifecycle() -> None:
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))

    assert set(hooks["hooks"]) == {"SessionStart", "PreToolUse", "PostToolUse", "SessionEnd"}
    for groups in hooks["hooks"].values():
        command = groups[0]["hooks"][0]
        assert command["type"] == "command"
        assert "$PLUGIN_ROOT" in command["command"]
        assert command["commandWindows"]
        assert command["timeout"] <= 10


def test_generated_runtime_matches_provenance(tmp_path: Path) -> None:
    rebuilt = build_plugin_runtime(REPO, output_dir=tmp_path)
    provenance = json.loads((PLUGIN / "runtime" / "provenance.json").read_text(encoding="utf-8"))

    assert _sha256(rebuilt.zipapp) == provenance["sha256"]
    assert _sha256(PLUGIN / "runtime" / "marginal_runtime.pyz") == provenance["sha256"]
    assert rebuilt.source_hash == provenance["source_hash"]


def test_plugin_runtime_contains_no_live_repository_paths() -> None:
    runtime = (PLUGIN / "runtime" / "marginal_runtime.pyz").read_bytes()

    assert str(REPO).encode() not in runtime


def test_skill_teaches_truthful_earned_enforcement_workflow() -> None:
    skill_path = PLUGIN / "skills" / "marginal" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]

    assert "name: marginal" in frontmatter
    assert "description: Use when" in frontmatter
    for phrase in (
        "Shadow Mode",
        "Tool Enforcement",
        "marginal codex status",
        "marginal codex promote",
        "never claim token savings",
    ):
        assert phrase.casefold() in text.casefold()
