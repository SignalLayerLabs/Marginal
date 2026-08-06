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
assert 1200 <= words <= 2200, f"README words: {words}"
for heading in [
    "# MARGINAL",
    "## Why MARGINAL",
    "## How it works",
    "## Install",
    "## Quickstart",
    "## The Learning Loop Foundation",
    "## Universal Agent Runtime",
    "## Privacy by design",
    "## Evidence, not hype",
    "## Project status",
    "## Documentation",
]:
    assert heading in readme, heading
for forbidden in [
    "guarantees fewer tokens",
    "saves tokens on every request",
    "Codex adapter is available",
    "Claude Code adapter is available",
]:
    assert forbidden.lower() not in readme.lower(), forbidden

required = [
    "docs/quickstart.md",
    "docs/architecture.md",
    "docs/privacy.md",
    "docs/api.md",
    "docs/integrations.md",
    "docs/benchmarking.md",
    "docs/public-benchmarks.md",
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
    "actions/upload-pages-artifact@v3",
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
print("Website SEO and dependency audit: PASS")
print("Pages workflow consolidation: PASS")
