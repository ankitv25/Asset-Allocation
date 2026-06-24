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

## The platform (8 pages)

| Page | Answers | Highlights |
|---|---|---|
| **Overview** | What is the book doing, and why? | lead **insight banner** (generated), allocation, positioning, **enlarged construction view + sleeve-thesis evidence cards**, vol-budget component, diversification, **date-picker Growth-of-$1**, stress |
| **Construction** | How is it built, bottom-up? | universe → **full-width sleeve hierarchy → evidence-card thesis** → BL optimization → constraint bands → strategic→dynamic bridge |
| **Holdings** | What exactly do I own? | **sortable / searchable / CSV-exportable instrument blotter** with per-line rationale + a **data-vintage panel** |
| **Performance** | Has it worked? | SAA vs DAA + benchmarks, **true date-picker Growth-of-$1 rebase**, drawdown, rolling 12m metrics |
| **Attribution** | Where did return/risk come from? **What did the dynamic process add?** | layer waterfall, **attribution over time** (cumulative active + growth-tilt decision log), market-state/sleeve/risk/benchmark attribution, **9×9 matrix** |
| **Risk** | What risk am I taking? | **vol-budget thermometer**, MCTR, concentration, block & SAA-vs-DAA risk, **enlarged correlation/diversification** |
| **Stress** | How does it behave in crises? | historical episodes, forward factor-shock scenarios, interactive custom builder |
| **Monte Carlo** | What is the *range* of outcomes? | 10k block-bootstrap paths (DAA/SAA/60-40), **probability bands**, terminal-value & drawdown **distributions**, **target-outcome probabilities** |

SAA = static strategic policy. DAA = full dynamic system (regime overlay +
tactical tilts + risk budget). The platform's central question, answered on the
Attribution page: **what did the dynamic allocation process add beyond the
strategic policy?**

---

## Current status / session handoff (2026-06-24, iteration 6 — experience elevation)

A presentation-layer pass to match the depth of the analytics, plus a depth pass on
the two pages that were thinnest.

- **Design system / story spine** — a global elevation in `style.css`: wider denser
  canvas, refined app-bar + active-pill nav, accent-railed KPI strip, polished tiles
  (title tick, hover lift), and two reusable patterns: a **`.hero` verdict band**
  (regime→stance + the comparisons that matter) and **numbered `.section-head` chapters**.
  The Overview now reads as a guided story (01 Positioning → 06 Resilience).
- **Monte Carlo, deepened into a complete area** — added **sample-path dispersion**
  (spaghetti, strategy toggle), a **cross-strategy median+cone comparison**, and a
  **bull/base/bear + CVaR scenario table**. Engine emits `sample_paths` + `scenarios`.
  Honest story sharpens: DAA's bear case ends **$1.21 vs SAA $0.98**; worst-5% tail
  **$1.06 vs $0.79**.
- **Performance, deepened** — new "Where the return came from" section: per-sleeve
  **contribution table** (avg weight × return, additive, reconciles to total), an
  **asset-class** breakdown (Equity / Fixed Income / Real Assets / Cash), **cumulative
  contribution by sleeve**, and **cumulative active value-add (DAA vs SAA) over time**.
- **Growth-number consistency fix** — the Outlook scenario strip used the raw PC16
  `STANCE_MATRIX` (Neutral = 69.4% growth), contradicting the live book's 55.3%
  (the live engine runs off a BL-anchored ~52% baseline, not PC16). `build_scenarios`
  now anchors the map to the live book and expresses regimes as stance *deltas*, so the
  current regime reads **55.3%** like everywhere else; the attribution-timeline hover no
  longer surfaces the backtest's absolute growth.

---

## Prior status / session handoff (2026-06-23, iteration 5)

**Built this session (iteration 5)** — completing the documented roadmap:
- **Monte Carlo page** (new `montecarlo.html`, 8th page) + engine
  `Src/portfolio_monte_carlo.py`: 10,000-path **stationary block bootstrap**
  (6-month blocks) of the realised monthly returns, **paired** across DAA/SAA/60-40
  so cross-strategy probabilities are coherent. Surfaces **probability bands**
  (5–95% / 25–75% fan, strategy toggle), terminal-value & worst-drawdown
  **distributions**, and **target-outcome probabilities** (P(2x), P(loss),
  P(DD>20%)). Honest result, consistent with the rest of the platform: DAA's
  median outcome ≈ SAA's, but it **halves the probability of a >20% drawdown
  (31% vs 59%)** — the edge is the left tail, not the median.
- **Attribution over time** (Attribution page): cumulative active value-add and
  a **growth-tilt decision log** (DAA−SAA growth weight, month by month, with
  adverse-regime shading) — shows the stance cutting growth −25/−30pp into 2008,
  2020, 2022. From a new `timeline` block in the attribution engine (reconciliation
  still PASS).

**Still open (future):** deeper per-episode stress narratives + scenario libraries ·
fixed-income analytics (duration/curve/credit) · CRSP/WRDS data-tier · owner gates
G-2 (CMA sign-off + valuation feed) / G-4 (real cash series).

---

## Prior status / session handoff (2026-06-23, iteration 4)

**Built this session (iteration 4)** — continuing the documented roadmap + a UX/quality pass:
- **Working mobile navigation** — a hamburger toggle opens a full-width dropdown nav
  (previously `.appnav` was simply hidden ≤1000px, leaving no way to switch pages).
  KPI ribbon drops to 2 columns and the appbar de-clutters on narrow screens.
- **True date-picker Growth-of-$1** — a real `<input type=date>` (plus quick chips)
  **rebases every series to $1 from the chosen date**; refactored into one reusable
  `mountRebaseGrowth` used on both Performance and the Overview (the Overview chart
  was previously raw, non-rebasing NAV).
- **Holdings blotter** (new `holdings.html`) — sortable / searchable / **CSV-export**
  instrument-level book with per-line rationale + a **data-vintage panel**. Built
  from data already in `portfolio.json` (no pipeline rerun).
- **Insight-first pass** — every page now opens with a `page-intro` (the question it
  answers) and, on Overview/Construction/Holdings, a generated **insight banner**
  (interpretation before charts). Charts sized up (`chart-md` 250→290, etc.).
- **Sleeve thesis redesigned as evidence cards** (MRS Pillar-Evidence style): two rows
  of weight · live-tilt · key-holdings · rationale, moved **below** an **enlarged
  full-width construction treemap** (`chart-tree-xl`, 560px) on Overview + Construction.
- **Volatility-vs-budget redesigned** — a purpose-built thermometer component
  (forecast vs budget zones, utilisation %, headroom, binding flag) replacing the
  placeholder Plotly gauge.
- **Correlation/diversification given more weight** — enlarged feature tile on Risk + Overview.
- **Data-consistency fix (correctness):** `growth_weight` now derives from the governed
  `SLEEVE_BLOCK` (registry) source of truth — Real Assets is a *Diversifier*, so the
  headline "growth assets %" reconciles exactly with the block bar (**61.5% → 55.3%**).
  Fixed in `Src/build_portfolio_dashboard_data.py`; data regenerated.

**Still open (roadmap, not done this session):** attribution *over time* (decision-log
time series / per-month drill-down) · deeper per-episode stress narratives + scenario
libraries · fixed-income analytics (duration/curve/credit) · **Monte Carlo** (10k paths,
SAA & DAA, probability bands, drawdown & target-probability — future enhancement) ·
**push iteration 4 to the public `ankitv25/Asset-Allocation` Pages repo** (needs a local
clone + auth — see "Refresh + deploy").

---

## Prior status / session handoff (2026-06-23, iteration 3)

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
