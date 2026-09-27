# Five Products — Information Architecture
2026-09-20 · the design Phase 5 builds against

## The problem being solved

Five products were reachable only through a `<select>` in the app bar. There was no way to discover
them, no per-product entry point, no comparison, and the page they landed on (`portfolios.html`) was
still structured as the three-candidate research study that preceded them.

## The shape

Three layers, not one.

```
  RANGE            portfolios.html         "what are the five, and which one?"
    |                                      discovery · comparison · choosing
    v
  PRODUCT          index.html?p=<key>      "what is THIS portfolio?"
    |                                      the product landing — hero, allocation, sleeves, evidence
    v
  ANALYSIS         7 deep pages ?p=<key>   "prove it"
                                           construction · holdings · performance · attribution
                                           · risk · stress · monte carlo
```

The selector is kept, but demoted: it is for switching *while inside* a product, not for discovering
that products exist. Discovery happens on the range page; entry happens through a product card.

## What belongs where

**Range (`portfolios.html`)** — everything that is about the *set*:
| Section | Question | Source |
|---|---|---|
| 01 The five products | What is each one for? | `versions` — role, horizon, thesis, dials, status, live NAV |
| 02 Choosing | Which one suits which job? | `metrics` + horizon; risk/return positioning |
| 03 Side by side | How do they compare on one window? | `metrics`, all five + six benchmarks |
| 04 Built differently | Where do the books actually differ? | `versions[*].sleeves` — sleeve matrix |
| 05 Crisis behaviour | Who defends when it matters? | `crises` |
| 06 The active layer | What do DAA and Alpha do that the others don't? | `da` — scoped to the two active products |
| 07 What remains open | What is unfinished? | `gates` |

**Product (`index.html?p=`)** — everything about *one* portfolio. Already built and working; it keeps
its hero, allocation, positioning, hierarchy, sleeve-thesis cards, risk, diversification, track
record, drawdown, calendar returns, trailing, stress.

**Analysis (deep pages)** — unchanged, all seven, all selector-driven.

## Page set varies by product type

Attribution is a page about active management. Certain, Endowment and SAA hold policy weights by
design, so their active return is zero *by construction* — a page of zero rows is not information.

- **Active products (DAA, Alpha)** — all 8 analysis pages.
- **Static products (Certain, Endowment, SAA)** — Attribution is marked in the nav as active-only and
  explains why rather than rendering an empty decomposition.

This is handled in the nav, not by hiding the page: hiding it would make the platform look smaller
again. The link stays, labelled.

## What is shared and what is per-product

| Shared (house-level) | Per-product |
|---|---|
| Methodology · Playbook · Growth Engine | Allocation · Holdings · Risk · Stress · Monte Carlo |
| Construction *principles* | Construction *outputs* |
| The MRS regime read | How each product responds to it (or does not) |
| Benchmarks and the common window | Track record · Live NAV · Attribution |

## Routing

`?p=<key>` is kept — it already works, persists to `localStorage`, and lets one renderer serve five
payloads. Product cards link to `index.html?p=<key>`, so a card is a real entry point and the URL is
shareable. No per-product HTML files: five copies of eight pages would be five times the surface to
keep correct, and the single-renderer decision is the most valuable thing in the dashboard.

## What is explicitly NOT changed

The eight deep pages, `app.js`, the payload contract, the selector mechanism, the platform taxonomy,
the benchmark set, and every analytical module. This is an addition of a layer above, not a
restructure of what exists.
