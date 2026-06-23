# HANDOFF — Asset-Allocation Dashboard (public hosting repo)

## What this repo is
The **published static dashboard** for the multi-asset SAA portfolio. It is a
mirror of the dashboard built in the private research repo
(`Summer_Investment_Platform` → `Research/Portfolio_Construction/dashboard/`).
Only the static site lives here; **all source code, data pipeline, and research
stay private.**

## Live URL
`https://ankitv25.github.io/Asset-Allocation/` (GitHub Pages, source = `main` /root).

## Structure
```
index.html                 entry point (tile-grid, chart-led)
assets/css/style.css        institutional styling
assets/js/app.js            renders all tiles from the embedded data
assets/vendor/plotly.min.js Plotly, vendored locally (no CDN, works offline)
data/portfolio.js           window.PORTFOLIO_DATA — the embedded dataset
data/portfolio.json         same data as JSON (reference)
.nojekyll                   tells Pages to serve assets as-is
```

## How it loads (important)
The page reads its data from `data/portfolio.js` (a JS global), **not** `fetch()`,
and loads Plotly **locally** — so it works three ways with no server and no
internet: opened by double-click (`file://`), served locally, and on GitHub Pages.
(Earlier versions used `fetch()` + a CDN + ES-modules, which silently fail under
`file://` — do not reintroduce those.)

## Sections
KPI ribbon · Allocation (donut) · Positioning · Construction (holdings treemap +
sleeve theses) · Risk (vol gauge, factor, capital-vs-risk, instrument-level
risk) · Diversification (correlation heatmap + ratio/effective-bets) ·
Performance (NAV, trailing returns, drawdown, calendar-year) · Stress tests
(historical crises) · Outlook (regime → stance).

## How to update the dashboard
In the **private** repo:
1. Refresh the data + UI: `python3 Src/build_portfolio_dashboard_data.py`
   (writes `dashboard/data/portfolio.json` **and** `portfolio.js`).
2. Copy the dashboard folder contents into this repo (root) and push:
   ```
   cp -R <private>/Research/Portfolio_Construction/dashboard/. <this-repo>/
   git add -A && git commit -m "Refresh dashboard data" && git push
   ```
   Pages redeploys automatically on push to `main`.

## Hosting notes
- Pages is served **deploy-from-branch** (`main`, `/root`) — the repo is public,
  so the Free plan supports it. (The private repo cannot host Pages on the Free
  plan; that is why this dedicated public repo exists, mirroring the MRS /
  `Macro-Regime-Score` setup.)
- Data tier: exploratory (Yahoo Finance) — see the private repo's methodology and
  rebuild notes for caveats. Figures are net of cost.
