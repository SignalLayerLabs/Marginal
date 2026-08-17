from __future__ import annotations

import json
from pathlib import Path

import pytest

from marginal.public_eval import load_runs


def _write(path: Path, row: dict[str, object]) -> None:
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_public_eval_rejects_string_resolved_value(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    _write(path, {"instance_id": "task", "resolved": "false", "tokens": 1})

    with pytest.raises(ValueError, match="invalid benchmark row"):
        load_runs(path)


def test_public_eval_rejects_string_token_value(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    _write(path, {"instance_id": "task", "resolved": False, "tokens": "1"})

    with pytest.raises(ValueError, match="invalid benchmark row"):
        load_runs(path)


def test_public_eval_supports_configurable_quality_margin_and_confidence() -> None:
    from marginal.public_eval import RunRecord, compare_runs

    baseline = {
        f"task-{index}": RunRecord(
            instance_id=f"task-{index}",
            resolved=True,
            tokens=100,
            usd=1.0,
        )
        for index in range(100)
    }
    marginal = {
        key: RunRecord(
            instance_id=key,
            resolved=index >= 2,
            tokens=50,
            usd=0.5,
        )
        for index, key in enumerate(baseline)
    }

    strict = compare_runs(
        baseline,
        marginal,
        bootstrap_samples=200,
        confidence_level=0.90,
        quality_margin_pp=1.0,
    )
    relaxed = compare_runs(
        baseline,
        marginal,
        bootstrap_samples=200,
        confidence_level=0.90,
        quality_margin_pp=2.0,
    )

    assert strict["quality"]["preserved_within_margin"] is False
    assert relaxed["quality"]["preserved_within_margin"] is True
    assert relaxed["quality"]["non_inferiority_margin_pp"] == 2.0
    assert relaxed["savings"]["confidence_level"] == 0.90
    assert relaxed["efficiency"]["baseline"]["tokens_per_resolved"] == 100.0
    assert relaxed["efficiency"]["marginal"]["tokens_per_resolved"] > 50.0


def test_public_eval_rejects_invalid_statistical_configuration() -> None:
    from marginal.public_eval import RunRecord, compare_runs

    runs = {"task": RunRecord(instance_id="task", resolved=True, tokens=1)}
    for kwargs in (
        {"confidence_level": 1.0},
        {"confidence_level": 0.0},
        {"quality_margin_pp": -1.0},
    ):
        with pytest.raises(ValueError):
            compare_runs(runs, runs, bootstrap_samples=10, **kwargs)


def test_public_report_includes_efficiency_and_configured_criterion() -> None:
    from marginal.public_eval import RunRecord, compare_runs, render_public_report

    baseline = {"task": RunRecord(instance_id="task", resolved=True, tokens=100, usd=1.0)}
    marginal = {"task": RunRecord(instance_id="task", resolved=True, tokens=50, usd=0.5)}

    report = render_public_report(
        compare_runs(
            baseline,
            marginal,
            bootstrap_samples=20,
            confidence_level=0.90,
            quality_margin_pp=0.5,
        )
    )

    assert "Tokens per resolved task" in report
    assert "USD per resolved task" in report
    assert "90.0% bootstrap interval" in report
    assert "0.50 pp non-inferiority margin" in report


def test_unmeasured_usd_and_zero_success_quality_are_not_claimed() -> None:
    from marginal.public_eval import RunRecord, compare_runs, render_public_report

    baseline = {
        "task": RunRecord(instance_id="task", resolved=False, tokens=100, usd_measured=False)
    }
    marginal = {
        "task": RunRecord(instance_id="task", resolved=False, tokens=50, usd_measured=False)
    }
    result = compare_runs(baseline, marginal, bootstrap_samples=20)
    report = render_public_report(result)

    assert result["baseline"]["effective_usd"] is None
    assert result["quality"]["preserved_within_margin"] is None
    assert result["net_savings"]["tokens_confidence_interval"] is None
    assert "not evaluable" in report
    assert "bootstrap interval" not in report
