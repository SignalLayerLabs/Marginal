# Visual Studio / GitHub Copilot Commit Prompt

Apply this ZIP to the root of the checked-out `SignalLayerLabs/Marginal` repository, preserving all paths.

## Procedure

1. Create branch `docs/readme-pages-redesign`.
2. Copy every ZIP file into the repository.
3. Search `.github/workflows/` for `actions/deploy-pages`. Exactly one active Pages deployer must remain. Keep `.github/workflows/pages.yml`; remove or consolidate any older Pages/Killer Demo deployer.
4. Confirm these existing files are present:
   `assets/marginal-readme-hero.png`, `demos/killer-demo/RESULTS.md`, `docs/quickstart.md`, `docs/architecture.md`, `docs/privacy.md`, `docs/api.md`, `docs/integrations.md`, `docs/benchmarking.md`, `docs/public-benchmarks.md`, `ROADMAP.md`, `SECURITY.md`, `CONTRIBUTING.md`, `LICENSE`.
5. Preserve the claim guardrails:
   - vendor adapters remain labeled roadmap/planned;
   - the Killer Demo remains deterministic and estimate-based;
   - no guaranteed per-request savings;
   - measured savings require preserved verified quality;
   - pseudonymization is not anonymization.
6. Run:
   ```bash
   python scripts/validate_readme_pages.py
   ruff format --check .
   ruff check .
   mypy src/marginal
   pytest -q
   python -m build
   python -m twine check dist/*
   ```
7. Preview:
   ```bash
   python -m http.server 8000 --directory site
   ```
   Check desktop/mobile, keyboard navigation, links, and contrast.
8. In GitHub Settings → Pages, choose **GitHub Actions**.
9. Update repository About:
   - Description: `Open-source compute governance and token optimization for AI agents. Observe, measure, learn and enforce which model calls, tools, retries and sub-agents are worth the cost.`
   - Website: `https://signallayerlabs.github.io/Marginal/`
   - Topics: `ai-agents`, `llm`, `token-optimization`, `cost-optimization`, `compute-governance`, `agent-observability`, `codex`, `claude-code`, `github-copilot`, `opencode`, `python`, `local-first`
10. Commit: `docs: redesign README and launch product website`
11. Push and open PR: `docs: redesign README and launch GitHub Pages website`.

PR summary:
- concise SEO-oriented technical README;
- accessible dependency-free product website;
- one consolidated Pages deployment including Killer Demo;
- website operations and claim guardrails documented.

Include exact verification outputs in the PR. Do not merge if a second workflow still deploys Pages.
