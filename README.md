# Multi-Asset Portfolio Analytics Platform

An institutional portfolio-analytics dashboard for a regime-aware, multi-asset
strategy. It is **interpretation-first**: every page leads with a generated
read-through (computed from the numbers, never hardcoded prose) and uses charts
as evidence, not decoration.

**Live:** https://ankitv25.github.io/Asset-Allocation/
**Source of truth:** the private research repo, `Research/Portfolio_Construction/dashboard/`.
Opens by double-click (`file://`) — data is embedded (`data/portfolio.js`) and
Plotly is vendored locally; no fetch / CDN / ES-modules.

---

## The platform (6 pages)

| Page | Answers | Highlights |
|---|---|---|
| **Overview** | What is the book doing, and why? | KPIs, allocation, positioning, construction snapshot, risk lens, diversification, stress |
| **Construction** | How is it built, bottom-up? | universe → sleeve hierarchy → BL optimization → constraint bands → strategic→dynamic bridge |
| **Performance** | Has it worked? | SAA vs DAA + benchmarks, **rebased Growth-of-$1**, drawdown, rolling 12m metrics |
| **Attribution** | Where did return/risk come from? **What did the dynamic process add?** | layer waterfall, sleeve/asset-class/risk/regime/benchmark attribution, **9×9 matrix** |
| **Risk** | What risk am I taking? | vol gauge, MCTR, concentration, block & SAA-vs-DAA risk, correlation/diversification |
| **Stress** | How does it behave in crises? | historical episodes, forward factor-shock scenarios, interactive custom builder |

SAA = static strategic policy. DAA = full dynamic system (regime overlay +
tactical tilts + risk budget). The platform's central question, answered on the
Attribution page: **what did the dynamic allocation process add beyond the
strategic policy?**

---

## Current status / session handoff (2026-06-23, iteration 3)

**Built this session**
- **Attribution Engine 3** (`Src/portfolio_attribution.py`) — return, risk,
  sleeve, asset-class, **SAA-vs-DAA** (by sleeve *and* by dynamic layer),
  benchmark-relative (factor lens), and regime/market-state attribution. One
  exact additive framework; reconciliation asserted in code. Reports in
  `reports/attribution/`.
- **Attribution page** (`attribution.html`) — surfaces the engine: a value-add
  **waterfall** (regime / tilt / risk-budget / cost / compounding → net active),
  active-by-sleeve, return & risk attribution, a market-state bar (where the
  value is earned), and benchmark-relative bars.
- **9×9 cross-sectional matrix** — risk-return scatter (bubble = max drawdown) +
  a heat-shaded metric grid placing SAA, DAA, S&P 500, 60/40, Equal-Weight and
  All-Equity on the same axes.
- **Rebased Growth-of-$1** — pick any start date and the series **rebase to $1**
  from that point (not just pan the timeline); log/linear toggle.
- **Design** — page intros with the question each page answers, feature-tile
  accents, wider layout on large screens, KPI ribbon fitted to content.
- **Methodology correction (flagged):** the backtest now charges the static
  benchmarks (SAA, 60/40) their **real rebalancing turnover** instead of a flat
  2bp/month proxy that overstated their cost ~3.4×. Effect: SAA Sharpe 0.44→0.46,
  60/40 0.63→0.65; **FullSystem unchanged**. The DAA-vs-SAA active is now a
  consistent **+18bp/yr** (compound, net) — its value is drawdown reduction
  (~38%→~20% max DD), not a return premium. See
  `docs/handoffs/Attribution_Engine_Handoff.md`.

**Key numbers (net of cost, 2008–2026)**
- DAA: 7.1% CAGR · 10.2% vol · 0.57 Sharpe · **−19.7% max DD** (best tail of any option).
- DAA vs SAA: +0.10 Sharpe, **−18pp max DD**, +18bp/yr compound active.
- DAA vs 60/40: −0.9%/yr (a lower-equity-beta / US-dominance reality, not a layer fix).

**What the next build should do**
1. **Holdings blotter** — sortable/exportable instrument-level book (weights,
   P&L contribution) with a data-vintage panel.
2. **Attribution over time** — a decision-log time series (how stance/tilts
   evolved) and per-month attribution drill-down, not just full-window.
3. **Deeper stress narratives** — per-episode "what happened / which sleeves lost
   / which protected / the recovery", and forward scenario libraries.
4. **Fixed-income analytics** — duration / curve / credit decomposition.
5. **Benchmark & window selectors**; stronger mobile responsiveness.

**Open owner gates (before live capital)** — G-2 (CMA sign-off + live valuation
feed), G-4 (real cash series), Yahoo→CRSP data-tier, and confirm the corrected
static-benchmark cost basis above.

---

## Files

```
dashboard/
  index.html  construction.html  performance.html
  attribution.html  risk.html  stress.html      # 6 pages, shared header/nav
  assets/css/style.css                           # institutional design system
  assets/js/app.js                               # page-aware; renderers guarded by element id
  assets/vendor/plotly.min.js                    # vendored (offline)
  data/portfolio.js  data/portfolio.json         # generated payload (data + narrative)
  .nojekyll  README.md
```

## Refresh + deploy

```bash
# in the private research repo — rebuild data, then mirror to the public repo
python3 Src/pc_full_system_backtest.py            # if the strategy/cost model changed
python3 Src/portfolio_attribution.py              # refresh attribution reports
python3 Src/build_portfolio_dashboard_data.py     # regenerate data/portfolio.{json,js}
cp -R Research/Portfolio_Construction/dashboard/. <clone-of-Asset-Allocation>/
cd <clone-of-Asset-Allocation> && git add -A && git commit -m "Refresh dashboard" && git push
# GitHub Pages redeploys on push (~1 min).
```

## Data / scope caveats
All figures are net of cost on exploratory-tier (Yahoo) data; the cash sleeve is
a FRED T-bill proxy (G-4). Caveats are shown in the narratives, not hidden.
