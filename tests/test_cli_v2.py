from __future__ import annotations

import json
from pathlib import Path

from marginal.cli import main
from marginal.ledger import DecisionLedgerContext, JsonlDecisionLedger


def test_cli_validates_and_reports_decision_ledger(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ledger.jsonl"
    JsonlDecisionLedger(path, context=DecisionLedgerContext(run_id="run")).emit({"event": "custom"})
    assert main(["ledger-validate", str(path)]) == 0
    assert "valid decision ledger" in capsys.readouterr().out
    assert main(["ledger-report", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["events"] == 1


def test_public_eval_cli_accepts_statistical_configuration(tmp_path: Path, capsys) -> None:
    baseline = tmp_path / "baseline.jsonl"
    marginal = tmp_path / "marginal.jsonl"
    baseline.write_text(
        '{"instance_id":"task","resolved":true,"tokens":100}\n',
        encoding="utf-8",
    )
    marginal.write_text(
        '{"instance_id":"task","resolved":true,"tokens":50}\n',
        encoding="utf-8",
    )

    assert (
        main(
            [
                "public-eval",
                str(baseline),
                str(marginal),
                "--json",
                "--confidence-level",
                "0.9",
                "--quality-margin-pp",
                "0.5",
                "--seed",
                "7",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["savings"]["confidence_level"] == 0.9
    assert payload["quality"]["non_inferiority_margin_pp"] == 0.5


def test_cli_exports_safe_and_aggregate_privacy_profiles(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.jsonl"
    JsonlDecisionLedger(
        source,
        context=DecisionLedgerContext(
            run_id="customer-acme",
            task_id="customer-acme",
            model="internal-model",
        ),
    ).emit(
        {
            "event": "authorization",
            "action": {
                "name": "review termination clause",
                "kind": "verification",
                "cost": {"tokens": 100, "usd": 0.0, "latency_ms": 0, "risk": 0.0},
                "fingerprint": "guessable",
                "metadata": {"repository": "secret-merger-project"},
            },
            "decision": {
                "allowed": True,
                "recommended": True,
                "reason": "approved confidential review",
                "reason_code": "APPROVED",
                "recommendation_reason": "approved confidential review",
                "recommendation_reason_code": "APPROVED",
                "expected_gain": 0.2,
            },
        }
    )

    safe = tmp_path / "safe.jsonl"
    key = tmp_path / "privacy.key"
    assert (
        main(
            [
                "ledger-export",
                str(source),
                str(safe),
                "--privacy-profile",
                "safe_telemetry",
                "--privacy-key-file",
                str(key),
            ]
        )
        == 0
    )
    assert "exported" in capsys.readouterr().out
    safe_text = safe.read_text(encoding="utf-8")
    assert "customer-acme" not in safe_text
    assert "termination clause" not in safe_text

    aggregate = tmp_path / "aggregate.jsonl"
    assert (
        main(
            [
                "ledger-export",
                str(source),
                str(aggregate),
                "--privacy-profile",
                "aggregate_export",
                "--minimum-group-size",
                "1",
            ]
        )
        == 0
    )
    rows = [json.loads(line) for line in aggregate.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["privacy_profile"] == "aggregate_export"
    assert rows[0]["count"] == 1


def test_cli_refuses_to_overwrite_privacy_export(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.jsonl"
    JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run")).emit(
        {"event": "custom"}
    )
    destination = tmp_path / "existing.jsonl"
    destination.write_text("do not replace", encoding="utf-8")

    assert (
        main(
            [
                "ledger-export",
                str(source),
                str(destination),
                "--privacy-profile",
                "aggregate_export",
            ]
        )
        == 1
    )
    assert "already exists" in capsys.readouterr().err
    assert destination.read_text(encoding="utf-8") == "do not replace"


def test_ledger_export_uses_owner_only_permissions(tmp_path: Path) -> None:
    import os

    source = tmp_path / "source.jsonl"
    ledger = JsonlDecisionLedger(
        source,
        context=DecisionLedgerContext(run_id="run", task_id="task"),
    )
    ledger.emit({"event": "custom"})
    destination = tmp_path / "aggregate.jsonl"

    assert (
        main(
            [
                "ledger-export",
                str(source),
                str(destination),
                "--privacy-profile",
                "aggregate_export",
            ]
        )
        == 0
    )

    if os.name != "nt":
        assert destination.stat().st_mode & 0o077 == 0


def test_top_level_diagnostics_commands_share_json_reports(tmp_path: Path, capsys) -> None:
    assert main(["status", "--data-dir", str(tmp_path), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["authority"]["current"] == "L0"

    assert main(["privacy", "inspect", "--json"]) == 0
    privacy = json.loads(capsys.readouterr().out)
    assert "derived_enums" in privacy["persisted_categories"]

    assert main(["explain", "missing", "--data-dir", str(tmp_path), "--json"]) == 1
    explanation = json.loads(capsys.readouterr().out)
    assert explanation == {
        "decision_id": "missing",
        "found": False,
        "reason_code": "DECISION_NOT_FOUND",
    }
