#!/usr/bin/env python3
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.h1 = 0
        self.meta = {}
        self.scripts = []
        self.styles = []

    def handle_starttag(self, tag, attrs):
        data = {k: v or "" for k, v in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "meta":
            key = data.get("name") or data.get("property")
            if key:
                self.meta[key] = data.get("content", "")
        elif tag == "script":
            self.scripts.append(data.get("src", ""))
        elif tag == "link" and data.get("rel") == "stylesheet":
            self.styles.append(data.get("href", ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


readme = (ROOT / "README.md").read_text(encoding="utf-8")
words = len(re.findall(r"\b[\w\'-]+\b", readme))
assert 1000 <= words <= 2400, f"README words: {words}"
for heading in [
    "# MARGINAL",
    "## The problem in one trace",
    "## What changed after community review",
    "## MARGINAL must earn its own compute",
    "## State-aware diminishing returns",
    "## Governance accounting and false-stop review",
    "## Proof standard",
    "## Install",
    "## Quickstart",
    "## Architecture",
    "## Project status",
    "## Documentation",
]:
    assert heading in readme, heading
for forbidden in [
    "guarantees fewer tokens",
    "saves tokens on every request",
    "Codex adapter is available",
    "providers want agents to waste tokens",
]:
    assert forbidden.lower() not in readme.lower(), forbidden

required = [
    "docs/getting-started/quickstart.md",
    "docs/product/architecture.md",
    "docs/operations/privacy.md",
    "docs/reference/api.md",
    "docs/integrations/overview.md",
    "docs/evaluation/benchmarking.md",
    "docs/evaluation/public-benchmarks.md",
    "docs/evaluation/governance-evidence.md",
    "docs/project/community-feedback.md",
    "ROADMAP.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "assets/marginal-readme-hero.png",
    "demos/killer-demo/RESULTS.md",
]
missing = [p for p in required if not (ROOT / p).exists()]
assert not missing, missing

parser = Parser()
parser.feed((ROOT / "site/index.html").read_text(encoding="utf-8"))
assert parser.title.strip()
assert parser.h1 == 1
for key in ["description", "robots", "og:title", "og:description", "og:url", "twitter:card"]:
    assert parser.meta.get(key), key
assert parser.styles == ["styles.css"]
assert parser.scripts == ["app.js"]
assert not any(x.startswith(("http://", "https://")) for x in parser.styles + parser.scripts)

site_text = (ROOT / "site/index.html").read_text(encoding="utf-8")
for required_phrase in [
    "Illustrative trace",
    "Not a benchmark",
    "MARGINAL must earn its own compute",
    "Graceful irrelevance",
    "Community pressure test",
    "pass_through",
]:
    assert required_phrase in site_text, required_phrase

for path in [
    "site/styles.css",
    "site/app.js",
    "site/robots.txt",
    "site/sitemap.xml",
    "site/404.html",
]:
    assert (ROOT / path).is_file(), path

workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
for token in [
    "actions/configure-pages@v5",
    "actions/deploy-pages@v4",
    "demos/killer-demo",
    "assets/marginal-readme-hero.png",
]:
    assert token in workflow, token

deployers = []
for pattern in ("*.yml", "*.yaml"):
    for path in (ROOT / ".github/workflows").glob(pattern):
        if "actions/deploy-pages" in path.read_text(encoding="utf-8"):
            deployers.append(path.relative_to(ROOT).as_posix())
assert deployers == [".github/workflows/pages.yml"], deployers

print(f"README words: {words}")
print("README structure and claims: PASS")
print("Referenced files: PASS")
print("Website evidence-first structure: PASS")
print("Pages workflow consolidation: PASS")
