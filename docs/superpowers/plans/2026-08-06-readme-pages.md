# README and GitHub Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the long README with a concise technical landing page and add a dependency-free GitHub Pages website.

**Architecture:** README, website, docs, and roadmap have distinct responsibilities. One Pages workflow assembles the static site, existing hero asset, and Killer Demo.

**Tech Stack:** GitHub Markdown, semantic HTML5, CSS, vanilla JavaScript, GitHub Actions Pages.

## Tasks

1. Replace `README.md`, preserving install, quickstart, evidence, privacy, roadmap, docs, contribution, citation, and license.
2. Add `site/index.html`, styles, navigation script, robots, sitemap, and 404 page.
3. Add one `.github/workflows/pages.yml` deployment that also publishes the Killer Demo.
4. Add `docs/operations/website.md` and update `CHANGELOG.md`.
5. Run `scripts/validate_readme_pages.py`, repository CI checks, local preview, and final diff review.
