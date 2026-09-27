# Summer Portfolio Platform — five products, one renderer

> Part of the multi-asset research platform → **[ankitv25.github.io](https://ankitv25.github.io)**
> · regime backbone: **[Macro-Regime-Score](https://github.com/ankitv25/Macro-Regime-Score)**

**Live:** https://ankitv25.github.io/Asset-Allocation/

An institutional multi-asset platform for **five portfolios** — Certain · Endowment · SAA · DAA ·
Alpha — each with its own sleeve set, its own construction constraints and its own benchmark. Eleven
pages, all interpretation-first: every page leads with a read-through computed from the numbers, and
uses charts as evidence rather than decoration.

This repository is the **published mirror**: the site that is served, the code that builds it, the
methodology it implements, and the current engineering handoff. The private research repo remains the
source of truth — see [What is here, and what is not](#what-is-here-and-what-is-not).

---

## The five products

Each fund declares its own sleeve set. A holding a fund does not believe in is bounded to zero rather
than left for the optimiser to discover — which is why the table below is mostly dashes.

| | Horizon | Role | Reference | Run |
|---|---|---|---|---|
| **Certain** | 3+ years | Capital preservation — purchasing power first | ACWI 40 / Agg 60 | static |
| **Endowment** | 10+ years | Long-horizon real-asset tier | ACWI 60 / Agg 40 | static |
| **SAA** | 20+ years | House policy portfolio — the strategic anchor | ACWI 80 / Agg 20 | static |
| **DAA** | 20+ years | The policy portfolio run actively | ACWI 80 / Agg 20 | active |
| **Alpha** | 10+ years | Equity-level risk, run actively | S&P 500 | active |

| Holding (%) | Certain | Endowment | SAA | DAA |
|---|---:|---:|---:|---:|
| US equity | 9.0 | 23.5 | 35.0 | 35.9 |
| Developed ex-US equity | 5.0 | 4.5 | 7.0 | 8.4 |
| Emerging-market equity | – | 6.0 | 9.0 | 10.4 |
| US Treasuries (intermediate) | 22.0 | 8.0 | 6.0 | 3.7 |
| US Treasuries (long) | – | 15.0 | 20.0 | 17.1 |
| IG corporate credit | 8.0 | 5.0 | – | – |
| TIPS | 16.0 | 8.0 | – | – |
| Listed real estate | – | 4.0 | – | – |
| Listed infrastructure | – | 7.0 | – | – |
| Broad commodities | 4.0 | 5.0 | 3.0 | 4.0 |
| Gold | 7.0 | 8.0 | 8.0 | 8.8 |
| Managed futures (trend) | – | – | 8.0 | 7.4 |
| Swiss franc | 3.0 | – | – | – |
| Cash (T-bills) | 26.0 | 6.0 | 4.0 | 4.3 |

Alpha is equity-led against the S&P 500 and carries its own ~14% volatility budget rather than the
policy portfolio's; its book is in the build record. DAA and Alpha are the two actively run books —
they re-read five engines (valuation from a live CMA, trend, relative strength, regime, and the size
of the diversifier sleeve) at each month end.

### Record — a backtest of today's weights, 1997–2026

Not the live track record. These are **today's** weights carried back over history, net of dealing
costs and a 15bp annual fee, from the build record
`validation/fund_suite_v6/fund_suite_v6.json` (2026-09-20). The funds' actual track record starts
15 July 2026 and is on the [Live NAV](https://ankitv25.github.io/Asset-Allocation/live.html) page.

| | CAGR | Vol | Sharpe | Worst loss |
|---|---:|---:|---:|---:|
| Certain | 4.94 | 4.1 | 0.67 | −10.0 |
| Endowment | 7.28 | 8.1 | 0.64 | −24.3 |
| SAA | 7.81 | 8.8 | 0.65 | −25.5 |
| DAA | 8.09 | 8.3 | 0.72 | −20.8 |
| Alpha | 9.34 | 13.5 | 0.57 | −44.0 |
| ACWI 40 / Agg 60 | 6.04 | 7.3 | 0.54 | −23.6 |
| ACWI 60 / Agg 40 | 6.94 | 10.0 | 0.50 | −35.6 |
| ACWI 80 / Agg 20 | 7.73 | 13.0 | 0.47 | −46.1 |
| S&P 500 | 9.69 | 15.4 | 0.54 | −50.8 |
| MSCI ACWI | 8.41 | 16.0 | 0.45 | −55.0 |

### Live NAV

All five launched **15 July 2026 at NAV 100.00 per unit**, priced daily from dividend-adjusted market
closes, net of a 15bp annual fee and 10bp per side. The NAV is recomputed from inception on every run
rather than appended, and ingestion **exits** if any vehicle is missing prices or a day's weights do
not sum to 1 — see [UPDATING.md](UPDATING.md) for why that check is not theoretical.

---

## Three layers, eleven pages

```
RANGE      portfolios.html        which of the five, and why — the cards are the entry points
  │
PRODUCT    index.html?p=<key>     what THIS portfolio is
  │
ANALYSIS   7 deep pages ?p=<key>  prove it
```

| Page | Answers |
|---|---|
| **Portfolios** | Which of the five, and why — the range, side by side |
| **Overview** | What is this portfolio doing, and why? |
| **Construction** | How is it built, bottom-up — universe → sleeves → optimisation → bands |
| **Holdings** | What exactly do I own, with a per-line rationale and a data-vintage panel |
| **Performance** | Has it worked — against its own reference, with the basis declared |
| **Attribution** | Where did return and risk come from, and what did the active process add |
| **Risk** | What risk am I taking — MCTR, concentration, correlation, the 3×3 style box |
| **Stress** | How does it behave in crises — historical episodes and forward factor shocks |
| **Monte Carlo** | What is the *range* of outcomes — 10k block-bootstrap paths |
| **Live NAV** | The actual priced track record since 15 Jul 2026 |
| **Methodology** | The research lineage the books were built from |

Attribution is labelled **active only** for Certain / Endowment / SAA and explains why rather than
rendering zero rows — their active return is zero *by construction*, not by underperformance.

### The design decision that makes this work

`assets/js/app.js` reads `window.PORTFOLIO_DATA` and renders **by element id**.
`assets/js/portfolio-select.js` binds one of five payloads to that global *before* app.js runs. So all
eight selector-driven pages render any of the five portfolios **without the renderer changing** — it
was never modified to add a portfolio. Selection persists via `?p=<key>` and `localStorage`.

The site opens by double-click (`file://`): data is embedded as JS (`data/portfolio_books.js`), Plotly
is vendored locally, and there is no fetch, CDN or ES-module anywhere.

---

## Two class taxonomies, on purpose

The portfolios' own classes (Equity / Defensive / Real assets / Diversifiers / Cash) drive the
optimiser. The platform's six (Equities / FixedIncome / Commodities / RealEstate / Cash /
AltsInsurance) drive the shared components. The crosswalk is `fund_registry.PLATFORM_CLASS`; gold →
Commodities and Swiss franc → Cash are owner-confirmed.

## Risk limits are three different objects

Never merged into the word "budget":

- **Construction constraint** — the vol / CDaR / drawdown caps the optimiser was actually held to,
  read live from the build record. Where a declared cap was infeasible, `pc_fs6_build` loosens it via
  `fs4_core.solve_fund` and records what it used: Endowment's declared 16% CDaR / 22% drawdown was
  infeasible and solved at **20% / 27.5%**.
- **Mandate limit** — an owner decision in the record. One exists: SAA −22%.
- **Measured** — forecast and realised, no frame.

Nothing renders as a limit unless it traces to an approved source; contract C3 fails the build
otherwise.

---

## What is here, and what is not

**Here**

| | |
|---|---|
| `*.html`, `assets/` | the eleven pages served, the renderer, the vendored Plotly |
| `data/` | the payloads the pages read — the five books, the range, the live NAV |
| `src/` | the 22-module build chain that produces those payloads |
| `methodology/` | the approved methodology the code implements |
| `docs/` | the information architecture and the architecture audit |
| `HANDOFF.md` | the current engineering handoff — read this before changing anything |
| `UPDATING.md` | how to refresh the data and re-verify |
| `module_contract.json` | element id → payload path, the contract C1 enforces |

**Not here, deliberately**

- **Raw third-party inputs.** The daily price panel, the World Bank commodity file and the
  Fama-French factor file are not redistributed. The upstream solver stage (`fs2_core` / `fs3_core`)
  therefore **cannot be run from this mirror** — it is published to be read and audited, not to be
  re-executed. The stages that consume already-derived inputs are noted in
  [UPDATING.md](UPDATING.md).
- **Intermediate validation output** beyond what the pages need.
- **The wider platform** — the full handoff archive, the research lineage and the other work streams
  stay in the private repo.

`src/verify_dashboard.py` **is** runnable here, against this mirror, and is the check that matters:

```
python3 src/verify_dashboard.py --dash .
```

## Requirements

`python3` with the packages in [requirements.txt](requirements.txt). `verify_dashboard.py` is
stdlib-only and needs none of them.

---

*Not investment advice. The 1997–2026 series is a backtest of current weights, not a track record;
the live NAV is 15 Jul 2026 onward and is far too short to be one either. NAV is priced from market
closes and is not a custodial record.*
