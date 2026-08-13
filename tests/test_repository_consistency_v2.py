from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_repository_identity_is_consistent() -> None:
    forbidden = ("BlumFinancialLab", "github.com/BlumFinancialLab/marginal")
    paths = [
        ROOT / "ACKNOWLEDGMENTS.md",
        ROOT / "docs" / "governance.md",
        ROOT / ".github" / "CODEOWNERS",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert not any(value in text for value in forbidden), path
        assert "SignalLayer Labs" in text or "SignalLayerLabs" in text, path

    codemeta = json.loads((ROOT / "codemeta.json").read_text(encoding="utf-8"))
    assert codemeta["version"] == "0.3.0"
    assert codemeta["codeRepository"] == "https://github.com/SignalLayerLabs/Marginal"
    assert codemeta["issueTracker"] == "https://github.com/SignalLayerLabs/Marginal/issues"
    assert codemeta["author"]["name"] == "SignalLayer Labs"


def test_killer_demo_is_real_and_committed() -> None:
    source = (ROOT / "src" / "marginal" / "killer_demo.py").read_text(encoding="utf-8")
    assert "Local test stub" not in source
    assert "render_killer_demo_html" in source
    for name in ("result.json", "RESULTS.md", "index.html", "comparison.svg", "trace.jsonl"):
        assert (ROOT / "demos" / "killer-demo" / name).is_file(), name


def test_release_workflow_matches_ci_scope() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "ruff format --check ." in workflow
    assert "ruff check ." in workflow


def test_all_relative_markdown_links_resolve() -> None:
    import re

    missing: list[tuple[str, str]] = []
    for path in ROOT.rglob("*.md"):
        if any(part in {".git", ".pytest_cache", "dist"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            normalized = target.strip().split()[0].strip("<>")
            if normalized.startswith(("#", "http://", "https://", "mailto:")):
                continue
            normalized = normalized.split("#", 1)[0]
            if normalized and not (path.parent / normalized).exists():
                missing.append((str(path.relative_to(ROOT)), normalized))
    assert not missing, missing


def test_apache_license_text_is_complete() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text
    assert len(license_text.splitlines()) > 150


def test_readme_html_assets_are_committed() -> None:
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sources = re.findall(r'<(?:img|source)\b[^>]*\bsrc="([^"]+)"', readme)
    local_sources = [source for source in sources if not source.startswith(("http://", "https://"))]
    assert local_sources
    missing = [source for source in local_sources if not (ROOT / source).is_file()]
    assert not missing, missing
