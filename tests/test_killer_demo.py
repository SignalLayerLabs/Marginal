from __future__ import annotations

import json
from pathlib import Path

from marginal.killer_demo import (
    render_killer_demo_html,
    render_killer_demo_markdown,
    run_killer_demo,
)


def test_killer_demo_preserves_verified_outcome_and_saves_over_ninety_percent() -> None:
    result = run_killer_demo()

    assert result["demo"] == "marginal-killer-demo-v1"
    assert result["initial_verified_success"] is False
    assert result["baseline"]["verified_success"] is True
    assert result["marginal"]["verified_success"] is True
    assert result["savings"]["tokens_percent"] >= 90.0
    assert result["savings"]["calls_percent"] >= 60.0
    assert result["baseline"]["calls"] == 9
    assert result["marginal"]["calls"] == 3


def test_killer_demo_funds_targeted_actions_and_explains_rejections() -> None:
    result = run_killer_demo()

    selected = [stage["selected"] for stage in result["stages"]]
    assert selected == [
        "inspect the failing assertion",
        "apply the targeted one-line patch",
        "run the targeted verifier",
    ]

    rejected = [
        candidate
        for stage in result["stages"]
        for candidate in stage["candidates"]
        if candidate["name"] != stage["selected"]
    ]
    assert rejected
    assert all(candidate["allowed"] is False for candidate in rejected)
    assert any("ROI" in candidate["reason"] for candidate in rejected)


def test_killer_demo_writes_reproducible_artifacts(tmp_path: Path) -> None:
    result = run_killer_demo(tmp_path)

    result_path = tmp_path / "result.json"
    markdown_path = tmp_path / "RESULTS.md"
    html_path = tmp_path / "index.html"
    svg_path = tmp_path / "comparison.svg"
    trace_path = tmp_path / "trace.jsonl"

    assert json.loads(result_path.read_text()) == result
    assert markdown_path.read_text() == render_killer_demo_markdown(result)
    assert html_path.read_text() == render_killer_demo_html(result)
    assert "Baseline" in svg_path.read_text()
    assert "candidate_ranking" in trace_path.read_text()


def test_killer_demo_reports_are_explicitly_deterministic() -> None:
    result = run_killer_demo()
    markdown = render_killer_demo_markdown(result)
    html = render_killer_demo_html(result)

    assert "deterministic" in markdown.lower()
    assert "not a production benchmark" in markdown.lower()
    assert "94" in markdown
    assert "MARGINAL Killer Demo" in html
    assert "not a production benchmark" in html.lower()


def test_committed_killer_demo_artifacts_are_current(tmp_path: Path) -> None:
    run_killer_demo(tmp_path)
    committed = Path("demos/killer-demo")

    for name in ("result.json", "RESULTS.md", "index.html", "comparison.svg", "trace.jsonl"):
        assert (committed / name).read_bytes() == (tmp_path / name).read_bytes()
