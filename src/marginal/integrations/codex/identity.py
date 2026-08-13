"""Stable local identity for repository-scoped Codex promotion receipts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .installer import CommandRunner, SubprocessRunner, inspect_codex
from .promotion import PromotionIdentity

PLUGIN_VERSION = "0.3.1"
ADAPTER_VERSION = "1"
POLICY_HASH = hashlib.sha256(b"marginal:no-progress:v1:max-same-evidence=2").hexdigest()
DEFAULT_HOOK_HASH = "46b7a85a3a542957d055c615ab501f9fee284bb3193ac9ecfbe8951cce5a9942"


def repository_identity_hash(workspace: str | Path) -> str:
    return hashlib.sha256(str(Path(workspace).resolve()).encode("utf-8")).hexdigest()


def _installed_plugin_root(runner: CommandRunner) -> Path | None:
    result = runner.run(["codex", "plugin", "list", "--json"])
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    installed = payload.get("installed") if isinstance(payload, dict) else None
    if not isinstance(installed, list):
        return None
    for plugin in installed:
        if not isinstance(plugin, dict) or plugin.get("pluginId") != "marginal@marginal":
            continue
        source = plugin.get("source")
        if isinstance(source, dict) and isinstance(source.get("path"), str):
            candidate = Path(source["path"]).resolve()
            if candidate.is_dir():
                return candidate
    return None


def _plugin_identity(
    plugin_root: str | Path | None,
    runner: CommandRunner,
) -> tuple[str, str]:
    selected_root = Path(plugin_root).resolve() if plugin_root is not None else None
    if selected_root is None:
        environment_root = os.environ.get("PLUGIN_ROOT")
        selected_root = Path(environment_root).resolve() if environment_root else None
    if selected_root is None:
        selected_root = _installed_plugin_root(runner)
    if selected_root is None:
        return PLUGIN_VERSION, DEFAULT_HOOK_HASH
    manifest_path = selected_root / ".codex-plugin" / "plugin.json"
    hook_path = selected_root / "hooks" / "hooks.json"
    version = PLUGIN_VERSION
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(manifest, dict) and isinstance(manifest.get("version"), str):
                version = manifest["version"]
        except (OSError, json.JSONDecodeError):
            pass
    hook_hash = (
        hashlib.sha256(hook_path.read_bytes()).hexdigest()
        if hook_path.is_file()
        else DEFAULT_HOOK_HASH
    )
    return version, hook_hash


def current_promotion_identity(
    workspace: str | Path,
    *,
    codex_version: str | None = None,
    plugin_root: str | Path | None = None,
    runner: CommandRunner | None = None,
) -> PromotionIdentity:
    selected = runner or SubprocessRunner()
    resolved_codex_version = codex_version
    if resolved_codex_version is None:
        resolved_codex_version = inspect_codex(runner=selected).version or "unobservable"
    plugin_version, hook_hash = _plugin_identity(plugin_root, selected)
    return PromotionIdentity(
        repository_hash=repository_identity_hash(workspace),
        codex_version=resolved_codex_version,
        plugin_version=plugin_version,
        adapter_version=ADAPTER_VERSION,
        policy_hash=POLICY_HASH,
        hook_hash=hook_hash,
    )
