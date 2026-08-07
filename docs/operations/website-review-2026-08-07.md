# Website Review — 2026-08-07

## Review objective

Evaluate whether the MARGINAL website helps a skeptical developer understand the product, inspect its evidence standard and decide whether the project deserves a technical trial.

## Finding 1: the previous hero was technically correct but too abstract

The previous site opened with compute governance vocabulary and an architecture-like decision flow. That was accurate, but it forced a first-time visitor to understand the theory before seeing a concrete reason to care.

**Change:** the new hero starts with an illustrative repeated-verification trace. It is explicitly labeled “not a benchmark,” avoiding the temptation to use invented numbers as proof.

## Finding 2: the value proposition did not price MARGINAL itself

The old page explained token/cost governance but did not foreground the cost introduced by the governor. That creates an obvious credibility problem for a product whose purpose is economic discipline.

**Change:** “MARGINAL must earn its own compute” is now a primary product principle. The proof section distinguishes gross savings from net savings after governance tax.

## Finding 3: model-progress risk was treated as an objection instead of a requirement

A visitor could reasonably ask why MARGINAL survives a future model that no longer exhibits today's inefficient loops.

**Change:** the new site presents Graceful Irrelevance. `pass_through` is a legitimate result when the governor has no demonstrated net benefit.

## Finding 4: the evidence section was too far from the value claim

The previous site did contain scientific caveats, but users had to scroll through product concepts before reaching them.

**Change:** the proof standard is now the second major section. It names matched OFF/ON runs, effective tokens per resolved task, false stops, repeated calls and uncertainty.

## Finding 5: community criticism was invisible after it was processed

The project asked for open-source participation but gave no structured indication of how criticism affects decisions.

**Change:** the landing page now exposes a compact pressure-test section and links to the Community Feedback Log. Accepted and rejected feedback are both visible.

## Finding 6: some previous copy was too broad

Statements such as “agent runtimes often execute work because a model requested it” are directionally plausible but easy to read as a universal indictment.

**Change:** copy now uses narrower claims: coding agents *can* spend compute on actions whose incremental value is unclear or diminishing. The website does not speculate about provider motives.

## Information architecture after review

The intended narrative is now:

```text
observable problem
→ concrete trace
→ proof standard
→ governance tax / graceful irrelevance
→ generic mechanism
→ community decisions
→ benchmark discipline
→ roadmap
```

Architecture, privacy and learning-loop detail remain in GitHub documentation rather than competing with first-screen comprehension.

## Accessibility and operational constraints

The site remains dependency-free, responsive and tracking-free. It preserves one `h1`, semantic sectioning, keyboard navigation, reduced-motion handling and the existing GitHub Pages deployment model.
