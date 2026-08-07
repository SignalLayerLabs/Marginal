# MARGINAL website

The product website is a dependency-free static site published through GitHub Pages at:

`https://signallayerlabs.github.io/Marginal/`

## Responsibility split

- `README.md` is the fast technical entry point for developers.
- `site/` is the product-level marketing and discovery experience.
- `docs/` remains the source for detailed technical documentation.
- GitHub remains the source of truth for code, releases, benchmarks, issues, and evidence.
- `demos/killer-demo/` is published under `/demo/` by the Pages workflow.

The website must not make claims stronger than the repository evidence. Planned engine adapters remain labeled as planned. The Killer Demo remains labeled as a deterministic demonstration based on declared cost estimates.

## Deployment

GitHub Pages must use **GitHub Actions** as its source. Only one workflow in the repository may call `actions/deploy-pages`. Before merging, search `.github/workflows/` and remove or consolidate any previous Pages workflow.

The workflow assembles:

```text
site/                          → /
assets/marginal-readme-hero.png → /assets/
demos/killer-demo/             → /demo/
```

## Local preview

```bash
python -m http.server 8000 --directory site
```

To reproduce the deployment layout:

```bash
rm -rf _site
mkdir -p _site/assets _site/demo
cp -R site/. _site/
cp assets/marginal-readme-hero.png _site/assets/marginal-readme-hero.png
cp -R demos/killer-demo/. _site/demo/
python -m http.server 8000 --directory _site
```

## SEO, accessibility, and privacy guardrails

The site includes one descriptive `h1`, canonical and social metadata, `robots.txt`, sitemap, semantic structure, keyboard navigation, responsive layouts, and reduced-motion support.

It contains no analytics or third-party runtime scripts. Any future analytics integration requires a documented privacy review.
