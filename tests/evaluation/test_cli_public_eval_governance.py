from __future__ import annotations

import json
from pathlib import Path

from marginal.cli import main


def _write(path: Path, row: dict[str, object]) -> None:
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_public_eval_cli_exposes_net_value_gates(tmp_path: Path, capsys) -> None:
    baseline = tmp_path / "baseline.jsonl"
    marginal = tmp_path / "marginal.jsonl"
    _write(baseline, {"instance_id": "task", "resolved": True, "tokens": 1000})
    _write(
        marginal,
        {
            "instance_id": "task",
            "resolved": True,
            "tokens": 850,
            "governance_tokens": 100,
        },
    )

    exit_code = main(
        [
            "public-eval",
            str(baseline),
            str(marginal),
            "--bootstrap-samples",
            "20",
            "--minimum-net-token-savings-percent",
            "10",
            "--json",
        ]
    )

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["net_savings"]["tokens_percent"] == 5.0
    assert report["intervention"]["status"] == "pass_through"
