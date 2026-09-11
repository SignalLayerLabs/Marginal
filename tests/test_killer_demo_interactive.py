from __future__ import annotations

from pathlib import Path

from marginal.controls import ActionOutcomeStatus, NoProgressDetector
from marginal.killer_demo import (
    build_killer_demo_playback,
    build_no_progress_trace,
    render_killer_demo_css,
    render_killer_demo_html,
    render_killer_demo_js,
    render_no_progress_trace,
    run_killer_demo,
)


def test_playback_replays_same_nine_candidates_with_three_funded_actions() -> None:
    result = run_killer_demo()
    playback = build_killer_demo_playback(result)

    ticks = playback["ticks"]
    assert len(ticks) == 9
    assert [tick["stage"] for tick in ticks] == [
        "Diagnose",
        "Diagnose",
        "Diagnose",
        "Fix",
        "Fix",
        "Fix",
        "Verify",
        "Verify",
        "Verify",
    ]
    assert sum(tick["marginal"]["funded"] for tick in ticks) == 3
    assert all(tick["baseline"]["decision"] == "EXECUTE" for tick in ticks)
    assert sum(tick["baseline"]["calls"] for tick in ticks) == 9
    assert sum(tick["marginal"]["calls"] for tick in ticks) == 3
    assert sum(tick["marginal"]["decision"] == "REJECT BEFORE SPEND" for tick in ticks) == 6
    assert sum(tick["marginal"]["decision"] == "FUND + EXECUTE" for tick in ticks) == 3

    assert playback["final"]["baseline"]["verified_success"] is True
    assert playback["final"]["marginal"]["verified_success"] is True
    assert playback["final"]["baseline"]["tokens"] == 72_800
    assert playback["final"]["marginal"]["tokens"] == 4_300


def test_interactive_html_is_a_race_not_a_landing_page() -> None:
    result = run_killer_demo()
    rendered = render_killer_demo_html(result)

    required = (
        "SAME BUG. SAME START. WATCH THE EXTRA WORK.",
        "RUN THE SAME TASK",
        'data-lane="baseline"',
        'data-lane="marginal"',
        'data-action="run"',
        'data-action="pause"',
        'data-action="step"',
        'data-action="reset"',
        'id="demo-data"',
        'href="demo.css"',
        'src="demo.js"',
        "REJECT BEFORE SPEND",
        "FUND + EXECUTE",
        "Same verifier. Same PASS.",
    )
    for phrase in required:
        assert phrase in rendered


def test_interactive_assets_expose_playback_controls() -> None:
    css = render_killer_demo_css()
    js = render_killer_demo_js()

    assert ".race-grid" in css
    assert ".lane.baseline" in css
    assert ".lane.marginal" in css
    assert ".waste-meter" in css
    assert "prefers-reduced-motion" in css

    assert "function advanceRace" in js
    assert "function resetRace" in js
    assert "function playRace" in js
    assert "ArrowRight" in js
    assert "tick.marginal.decision" in js
    assert "fetch(" not in js


def test_committed_interactive_assets_are_generated(tmp_path: Path) -> None:
    run_killer_demo(tmp_path)
    committed = Path("demos/killer-demo")

    for name in ("demo.css", "demo.js"):
        assert (committed / name).read_bytes() == (tmp_path / name).read_bytes()


def test_no_progress_trace_is_replayed_from_the_shipped_control() -> None:
    rows = build_no_progress_trace()

    assert [row["reason_code"] for row in rows] == [
        "NO_PROGRESS_CLEAR",
        "NO_PROGRESS_CLEAR",
        "NO_PROGRESS_OBSERVED",
        "NO_PROGRESS_ENFORCEMENT_ELIGIBLE",
    ]
    assert [row["should_recommend_stop"] for row in rows] == [False, False, False, True]
    assert [row["enforcement_eligible"] for row in rows] == [False, False, False, True]

    assert [row["action"] for row in rows] == [
        "patch:apply",
        "verify:targeted",
        "verify:targeted",
        "verify:targeted",
    ]

    detector = NoProgressDetector()
    for row in rows:
        signal = detector.evaluate(row["action"], row["state"], row["evidence"])
        assert signal.reason_code == row["reason_code"]
        assert signal.reason == row["reason"]
        detector.observe(
            row["action"],
            row["state"],
            row["evidence"],
            ActionOutcomeStatus.SUCCESS,
        )


def test_no_progress_snippet_is_labeled_and_keeps_the_authority_boundary() -> None:
    snippet = render_no_progress_trace()

    assert "illustrative deterministic sequence" in snippet
    assert "not provider telemetry, not an enforcement benchmark" in snippet
    assert "max_same_evidence_completions=2" in snippet
    assert "t2  verify:targeted" in snippet
    assert "t4  verify:targeted" in snippet
    assert "Shadow Mode         records the stop recommendation" in snippet
    assert "Earned Enforcement  is separate." in snippet


def test_interactive_html_publishes_a_copyable_no_progress_trace() -> None:
    rendered = render_killer_demo_html(run_killer_demo())

    required = (
        'id="no-progress"',
        'data-action="copy-trace"',
        'id="no-progress-trace"',
        'id="copy-status"',
        'aria-live="polite"',
        'aria-label="Illustrative no-progress trace"',
        "tabindex=",
        "NO_PROGRESS_ENFORCEMENT_ELIGIBLE",
        "not provider telemetry",
    )
    for phrase in required:
        assert phrase in rendered, phrase


def test_copy_affordance_keeps_keyboard_and_reduced_motion_support() -> None:
    css = render_killer_demo_css()
    js = render_killer_demo_js()

    assert ".snippet-body" in css
    assert ".snippet-body:focus-visible" in css
    assert "prefers-reduced-motion" in css

    assert "function copyTrace" in js
    assert "restore.focus()" in js
    assert '"PRE"' in js
    assert "ArrowRight" in js
    assert "fetch(" not in js
