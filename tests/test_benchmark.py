from __future__ import annotations

from marginal.benchmark import render_markdown, run_benchmark


def test_benchmark_is_reproducible_and_preserves_verified_success() -> None:
    first = run_benchmark()
    second = run_benchmark()

    assert first == second
    assert first["baseline"]["verified_success_rate"] == 1.0
    assert first["marginal"]["verified_success_rate"] == 1.0


def test_benchmark_reduces_tokens_and_calls_by_at_least_forty_percent() -> None:
    result = run_benchmark()

    assert result["savings"]["tokens_percent"] >= 40.0
    assert result["savings"]["calls_percent"] >= 40.0
    assert result["marginal"]["tokens"] < result["baseline"]["tokens"]


def test_benchmark_markdown_is_explicitly_labeled_synthetic() -> None:
    markdown = render_markdown(run_benchmark())

    assert "Synthetic benchmark" in markdown
    assert "not a production performance claim" in markdown
    assert "Token savings" in markdown
