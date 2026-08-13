from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from scripts.build_codex_plugin import build_plugin_runtime
from scripts.build_codex_plugin_submission import build_submission_archive

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


def test_manifest_has_directory_publication_metadata() -> None:
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

    assert manifest["homepage"] == "https://signallayerlabs.github.io/Marginal/"
    assert manifest["repository"] == "https://github.com/SignalLayerLabs/Marginal"
    assert manifest["license"] == "Apache-2.0"
    assert {"compute-governance", "codex", "token-efficiency"} <= set(manifest["keywords"])

    interface = manifest["interface"]
    assert interface["websiteURL"] == manifest["homepage"]
    assert interface["privacyPolicyURL"].endswith("/privacy.html")
    assert interface["termsOfServiceURL"].endswith("/terms.html")
    assert interface["brandColor"] == "#22D3EE"
    assert interface["composerIcon"] == "./assets/marginal-logo.png"
    assert interface["logo"] == "./assets/marginal-logo.png"
    assert 1 <= len(interface["defaultPrompt"]) <= 3
    assert all(len(prompt) <= 128 for prompt in interface["defaultPrompt"])


def test_directory_logo_is_square_png() -> None:
    logo = PLUGIN / "assets" / "marginal-logo.png"
    data = logo.read_bytes()

    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    assert width == height
    assert width >= 512


def test_directory_submission_archive_is_reproducible_and_complete(tmp_path: Path) -> None:
    first = build_submission_archive(REPO, output_dir=tmp_path / "first")
    second = build_submission_archive(REPO, output_dir=tmp_path / "second")

    assert _sha256(first) == _sha256(second)
    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
    assert {
        ".codex-plugin/plugin.json",
        "skills/marginal/SKILL.md",
        "skills/marginal/agents/openai.yaml",
        "hooks/hooks.json",
        "runtime/marginal_runtime.pyz",
        "assets/marginal-logo.png",
    } <= names
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)


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
