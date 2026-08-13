from __future__ import annotations

import json
from pathlib import Path

from marginal.integrations.codex.commands import codex_command


def test_status_defaults_to_shadow_without_receipt(tmp_path: Path, capsys) -> None:
    exit_code = codex_command("status", data_dir=tmp_path, as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "shadow"
    assert payload["capability"] == "Tool Enforcement"


def test_unready_promotion_returns_two(tmp_path: Path, capsys) -> None:
    exit_code = codex_command("promote", data_dir=tmp_path, as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error_code"] == "EVIDENCE_NOT_READY"


def test_demote_is_idempotent(tmp_path: Path, capsys) -> None:
    assert codex_command("demote", data_dir=tmp_path, as_json=True) == 0
    capsys.readouterr()
    assert codex_command("demote", data_dir=tmp_path, as_json=True) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "shadow"

