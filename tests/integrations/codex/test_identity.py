from __future__ import annotations

import hashlib
from pathlib import Path

from marginal.integrations.codex.identity import DEFAULT_HOOK_HASH

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_default_hook_identity_matches_shipped_plugin() -> None:
    hook_bytes = (REPOSITORY_ROOT / "plugins" / "marginal" / "hooks" / "hooks.json").read_bytes()

    assert hashlib.sha256(hook_bytes).hexdigest() == DEFAULT_HOOK_HASH
