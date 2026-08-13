from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST_CASES = REPO / "docs" / "operations" / "codex-plugin-test-cases.json"
SUBMISSION = REPO / "docs" / "operations" / "codex-plugin-submission.md"


def test_readme_and_site_lead_with_install_remove_and_truthful_capability() -> None:
    required = (
        "codex plugin marketplace add SignalLayerLabs/Marginal --ref main",
        "codex plugin add marginal@marginal",
        "codex plugin remove marginal@marginal",
        "Tool Enforcement",
        "Earned Enforcement",
        "Shadow Mode",
        "24.93%",
        "pass_through",
    )
    for path in (REPO / "README.md", REPO / "site" / "index.html"):
        text = path.read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in text, f"{phrase!r} missing from {path}"


def test_submission_packet_has_required_positive_and_negative_cases() -> None:
    packet = json.loads(TEST_CASES.read_text(encoding="utf-8"))

    assert packet["schema_version"] == 1
    assert len(packet["positive"]) >= 5
    assert len(packet["negative"]) >= 3
    assert all(case["expected"] for case in packet["positive"] + packet["negative"])


def test_submission_status_is_exact_and_not_overclaimed() -> None:
    text = SUBMISSION.read_text(encoding="utf-8")

    assert "status: not_submitted" in text
    assert "status_date: 2026-08-13" in text
    assert "published" not in text.casefold().replace("not published", "")


def test_public_legal_and_support_surfaces_exist() -> None:
    site = (REPO / "site" / "index.html").read_text(encoding="utf-8")
    for filename in ("PRIVACY.md", "TERMS.md", "SUPPORT.md"):
        assert (REPO / filename).is_file()
        assert filename in site
