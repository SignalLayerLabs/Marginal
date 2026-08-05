from pathlib import Path
import json

from marginal.public_eval import load_runs, compare_runs, render_public_report


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_compare_public_runs_preserves_success_and_calculates_savings(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    marginal_path = tmp_path / "marginal.jsonl"
    _write(baseline_path, [
        {"instance_id": "a", "resolved": True, "tokens": 1000, "usd": 1.0, "latency_ms": 100, "tool_calls": 10},
        {"instance_id": "b", "resolved": False, "tokens": 2000, "usd": 2.0, "latency_ms": 200, "tool_calls": 20},
    ])
    _write(marginal_path, [
        {"instance_id": "a", "resolved": True, "tokens": 500, "usd": 0.5, "latency_ms": 80, "tool_calls": 6},
        {"instance_id": "b", "resolved": False, "tokens": 1000, "usd": 1.0, "latency_ms": 120, "tool_calls": 10},
    ])

    result = compare_runs(load_runs(baseline_path), load_runs(marginal_path), bootstrap_samples=200, seed=7)

    assert result["tasks"] == 2
    assert result["baseline"]["resolved"] == 1
    assert result["marginal"]["resolved"] == 1
    assert result["savings"]["tokens_percent"] == 50.0
    assert result["quality"]["resolved_delta_pp"] == 0.0
    assert result["quality"]["preserved_within_one_pp"] is True


def test_compare_requires_matching_instance_ids(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    marginal_path = tmp_path / "marginal.jsonl"
    _write(baseline_path, [{"instance_id": "a", "resolved": True, "tokens": 1}])
    _write(marginal_path, [{"instance_id": "b", "resolved": True, "tokens": 1}])

    try:
        compare_runs(load_runs(baseline_path), load_runs(marginal_path))
    except ValueError as exc:
        assert "instance IDs" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_report_labels_results_as_measured(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    marginal_path = tmp_path / "marginal.jsonl"
    _write(baseline_path, [{"instance_id": "a", "resolved": True, "tokens": 100}])
    _write(marginal_path, [{"instance_id": "a", "resolved": True, "tokens": 60}])
    report = render_public_report(compare_runs(load_runs(baseline_path), load_runs(marginal_path), bootstrap_samples=20))
    assert "Measured public benchmark comparison" in report
    assert "40.00%" in report
