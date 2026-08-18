from __future__ import annotations

from pathlib import Path

from marginal.killer_demo import (
    build_killer_demo_playback,
    render_killer_demo_css,
    render_killer_demo_html,
    render_killer_demo_js,
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
    assert "REJECT BEFORE SPEND" in js
    assert "fetch(" not in js


def test_committed_interactive_assets_are_generated(tmp_path: Path) -> None:
    run_killer_demo(tmp_path)
    committed = Path("demos/killer-demo")

    for name in ("demo.css", "demo.js"):
        assert (committed / name).read_bytes() == (tmp_path / name).read_bytes()
