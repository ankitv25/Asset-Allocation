# Handoff — five products, restored analytics, style box

**State: done and deployed.** https://ankitv25.github.io/Asset-Allocation/
**As of 2026-09-21.** Mirrors the private repo's
`Research/Portfolio_Construction/docs/handoffs/Five_Product_Platform_Handoff_2026-09-21.md`.

This replaces the June 2026 handoff, which described an eight-page single-book platform and was three
months stale. Read this before changing anything in this repository.

## What a reader should know first

- **Three analytical modules were once missing and nobody was told.** `matrix`, `risk_detail` and
  `stress_forward` were omitted on the reasoning that they belonged to the older v3.8 book. `app.js`
  guards them with `if (d.x)`, so a missing payload key renders **nothing and throws nothing**: nine
  tiles on attribution / risk / stress were blank while the page check reported clean. All three are
  built per portfolio now. **Do not "safely omit" a guarded module again** — that is what contract C1
  exists for.
- **Risk limits are three objects, never merged into "budget".** Construction constraint (what the
  optimiser was held to, read from the build record) · mandate limit (an owner decision; one exists,
  SAA −22%) · measured (forecast and realised). See the README.
- **Caps come from the build record, not the declaration.** `pc_fs6_build` loosens an infeasible cap
  via `fs4_core.solve_fund` and records what it used. Endowment's declared 16% CDaR / 22% drawdown was
  infeasible and was solved at **20% / 27.5%**. Showing the declared −22% made its realised −24.3%
  look like an overshoot when it was inside the real cap.
- **Two things share the word "performance".** The 1997–2026 series is a **backtest of today's
  weights**; the **live NAV** starts 15 Jul 2026. Every series declares basis / window / weights /
  rebalance / costs in a band beside the chart.
- **The 3×3 style box is descriptive only** — no target, no band, no limit.

## Architecture

```
RANGE      portfolios.html        which of the five, and why
  │
PRODUCT    index.html?p=<key>     what THIS portfolio is
  │
ANALYSIS   7 deep pages ?p=<key>  prove it
```

`?p=` is carried through the nav and the sleeve drill-down. `app.js` renders by element id from
`window.PORTFOLIO_DATA`; `portfolio-select.js` binds one of five payloads to it before app.js runs, so
the renderer takes a new portfolio without being edited. Full write-up in
[`docs/Five_Product_IA.md`](docs/Five_Product_IA.md).

## The build chain

```
src/fund_registry.py         identity: name, role, horizon, benchmark, managed flag, class crosswalk
src/sleeve_registry.py       sleeve thesis / role / risk character, per-vehicle role + rationale
        │
src/pc_fs6_build.py          books + backtest        ──> validation/fund_suite_v6/
src/fund_nav.py              priced daily NAV        ──> validation/fund_nav/
src/pit_backtest.py          walk-forward books, PIT covariance
src/style_box.py             the 3x3, returns-based style analysis
        │
        ├── src/build_portfolios_dashboard_data.py  ──> data/portfolios.js      (Portfolios page)
        ├── src/build_portfolio_books_data.py       ──> data/portfolio_books.js (the 8 deep pages)
        └── src/pc_fund_live_page.py                ──> data/live_nav.js        (Live NAV page)
```

Refresh order and the interpreter to use are in [`UPDATING.md`](UPDATING.md).

## Verification standard

The old standard (`#status-footer` for "Error:" + count `<svg>`) **cannot see silent module loss**:
other tiles on the same page still draw an SVG, and a missing module is not an exception. Two layers:

**1. Contracts — `python3 src/verify_dashboard.py --dash .`** (fast, no browser, gates the deploy)

| | Checks |
|---|---|
| C1 | module presence — if a page carries an element id, every portfolio payload carries the path that fills it |
| C2 | stale page copy — no selector-driven page may describe a different product or a superseded book |
| C3 | parameter provenance — no risk limit renders without a source |
| C4 | series provenance — every performance series declares what it is |
| C5 | sleeve narrative — no sleeve renders as a bare label |

**2. Render check — headless browser, 45 page × portfolio combinations.** Dump the DOM and assert:
`#status-footer` has no "Error:"; charts drew; every contracted container is **non-empty after
render**; no `undefined` / `NaN` in visible text.

> Counting charts: match **`svg-container`**, not `class="svg-container"` — Plotly emits
> `class="user-select-none svg-container"`.

## Traps worth knowing

- **Plotly mutates the layout you hand it.** It writes `type`, `range`, `autorange` back onto the axis
  objects. A shared `BASE.xaxis` means the first date-axis chart stamps `type:"date"` onto every chart
  after it — that is what collapsed the asset-class bars onto one date and stacked them to 500%.
  `BASE`'s axes are **getters returning a fresh object**; `portfolios.js` builds layouts via `L()`.
  Never hand Plotly a shared nested layout.
- **`json.dump` writes a bare `NaN`.** Invalid JSON, but legal JavaScript — so `portfolios.js` loaded
  it and compounded it into "Growth of $1: **$NaN**". Always `allow_nan=False`. The funds start
  **1997-06**; the panel had been padded back to 1995-01, so the stated common window was wrong too.
- **Don't `dropna()` across sleeves a fund cannot hold.** It cost the walk-forward a decade and gave
  Endowment no series at all.
- **`suite['impl']` is an implementation string, not a rationale.** Using it for the sleeve thesis and
  every instrument rationale reduced the sleeve cards to their own ticker printed three times.
  Narrative comes from `src/sleeve_registry.py`.
- **Diff the payload schema before writing one.** The `portfolio.json` contract is ~403 paths deep.
  Guessing one missing field per render cycle wastes hours; a path-by-path diff against the reference
  gives the whole list at once.

## Known limitations — stated on the pages, not hidden

1. **The walk-forward is not fully point-in-time.** Risk is re-estimated at each rebalance; the return
   view is not, because `fs3_core.model()` builds its CMA from a current snapshot and there are no
   historical CMA vintages. It answers "how much does the book depend on the covariance window?", not
   "would we have chosen this in 2008?".
2. **Custom-scenario slider betas are estimates.** The scenario set itself is the approved
   `fund_suite_v6.scenarios_def` and the per-fund impacts match it to 0.1pp.
3. **The style box runs 2010-10 →**, bounded by the inception of the vehicles the funds hold, and
   infers style from returns rather than looking through to holdings.
4. **Live NAV is a few dozen trading days.** Not a track record; the page says so.

## Open / next

1. **`methodology/Risk_Limit_Framework_Proposal.md` needs an owner decision.** NOT ACTIVE. Until then
   the platform shows measured risk and construction constraints only.
2. **Endowment's declared CDaR is infeasible at every walk-forward date**, not just on the full
   window. A fact about the fund's construction, not a bug — worth a decision.
3. **PC-22 remains unimplemented as a tilt layer.** The style box makes visible that the range takes
   no size or style bet (+0.10 size vs the total market, ~0 style). Whether to use that dimension is a
   methodology call.
4. **Write the payload contract down.** `module_contract.json` covers element ids, not the full ~403
   path payload schema.
5. **Payload size.** `data/portfolio_books.js` is 2.9 MB for five portfolios and
   `data/portfolio.json` 932 KB; splitting per portfolio and lazy-loading would help first paint.
6. **The Methodology page still describes the v3.8 lineage only.** Deliberate — it is the lineage the
   books were built from. Documenting the current five there is a content decision.

## Added 2026-09-26 — factor attribution of the live NAV

`src/factor_attrib.py`. The page could say which holding moved the NAV; it could not say what the book
was **exposed to**. Holdings-based, not a fund-level regression: thirteen factors on fifty-one daily
observations would estimate nothing, so the exposure is not estimated at all — it is the real daily
weights (`fund_nav` now persists them) times each vehicle's betas, fitted on 2,194 days from 2018.

```
NAV move = cash + Σ (exposure × factor return) + costs + residual      (reconciles exactly, or it refuses to write)
```

**Two modelling errors found by measuring rather than assuming, both worth keeping in mind:**

1. **Cash is not a factor.** Every book holds 100% of its money and earns the bill rate on all of it.
   With no cash leg, Certain's 26% T-bill position read as unexplained return. Attribute on excess
   returns and carry cash as its own line.
2. **One rate factor cannot span a curve.** With only long Treasuries over cash, the bond-heavy books
   fell apart — Certain's residual was −0.86 on a +0.14 total, and the intermediate/TIPS/credit
   vehicles fitted at R² 0.79–0.83. Splitting into **Rates** (IEF − cash) and **Curve** (VGLT − IEF)
   took Certain's residual to −0.22 and those vehicles to R² 0.95+.

The residual is published, never spread over the factors. `SGOV` fits at R² 0.000 by construction —
it *is* the cash leg, and that is the correct reading, not a failure.

What it shows: the range takes **no size or style bet** (exposures ≈ 0.00), which is what `style_box.py`
already said about positioning — now with the price of that non-decision attached. PC-22 remains
unimplemented; this makes the cost of leaving it unimplemented visible rather than theoretical.

## 2026-09-27 — Live NAV page brought to standard, and a NAV pricing defect corrected

**A pricing defect, found by independent validation and fixed.** `fund_nav.py` seeded `held` to the
target book before the pricing loop, so the day-one `turn = |t − held|` was identically zero and the
100% turnover of *buying* the book at launch was never charged. Certain and Alpha showed
`dealing = 0.00000000` for their entire life and every portfolio's since-inception return was
overstated by ~10bp. `held` now starts from cash. NAVs restated:

| | was | now |
|---|---:|---:|
| Certain | 100.14 | 100.04 |
| Endowment | 99.92 | 99.82 |
| SAA | 101.27 | 101.17 |
| DAA | 101.71 | 101.61 |
| Alpha | 102.69 | 102.59 |

**A cascade that blanked a third of the page.** `sbxPanel()` was still called after its markup moved
to Attribution; it threw, and because the whole bootstrap was one statement, every panel after it —
holdings, dealing log, mandates, **the entire disclosure block** — silently never rendered while the
page still reported clean. Panels now run independently and a failure names itself in the footer.

**Identity colours were wrong at the source.** The renderer's hand-copied colour map had drifted:
Certain drew in SAA's colour, SAA in DAA's, DAA in a benchmark's. Colours are now published from
`fund_registry` in the payload and must never be re-typed in a renderer.

**Standing rules this page now honours** (see `docs/LIVE_NAV_REQUIREMENTS.md`, the cumulative ledger):
- One selected portfolio drives every panel. There were three independent selections.
- `excess` has one definition (arithmetic). The cards used a NAV ratio, the table a return difference.
- The 20% vehicle cap claim is stated with its one real exception: Certain's single-vehicle T-bill
  sleeve runs at 26%, which the cap cannot bind.
- "Nothing is annualised" is scoped to returns; volatility, tracking error and backtest CAGR are.
- The drawdown cap shown is the **construction constraint from the build record**, with Endowment's
  loosened case flagged — `declared` in that record is the CDaR, not a drawdown, and is labelled so.
- Size/style is credited to the 3×3 style box, not to PC-22, which is the sector tilt layer.

Payload trimmed 66 KB → 46 KB by removing blocks nothing rendered.

## 2026-09-27 (later) — Live NAV rebuilt as five product pages

The owner's objection: the five could not be analysed or even seen — five small cards, then 5-across
tables, with four independent chip rows choosing the portfolio. Now:

- **Switcher** (sticky under the app bar): the five as tabs with NAV and move on the day. One selection
  drives every panel, is carried in `?p=<key>`, and uses the same `summer.portfolio` key as
  `portfolio-select.js`, so the nav's deep-page links follow it.
- **Product page for the selected portfolio**: hero (objective, identity, NAV, since launch, vs its own
  reference, from its high), key-facts strip, links into that portfolio's deep pages; NAV chart with
  three views (NAV / against its reference / from its high) and a period selector; **Where it sits in
  the range** (each characteristic as a track across the five); returns vs reference with an explicit
  difference row; risk vs the three benchmarks; month by month vs reference; holdings with weight and
  since-launch contribution in one row; exposure bar lists (asset class / platform class / sleeve,
  geography); dealing log; long-run backtest labelled as such; the holdings bridge as a waterfall from
  100.00 to today's NAV; factor attribution.
- **The range side by side**: all five on one axis (selected highlighted, every line named, click to
  select, benchmarks toggle), characteristics, discrete and monthly returns, mandates, terms — table
  headers and rows select a portfolio.

Chart fixes: weekends and holidays removed from the date axis (they drew as flat ramps), round tick
steps, the launch line actually dashed, x-axis ending on the last price. Magnitude bars use one neutral
hue — identity colours mark which portfolio only (Alpha's registry colour is the loss red).
The mobile menu toggle was never wired on this page (it does not load `app.js`); it is now.
Nothing in the payload or the build chain changed; `live.js` renders only what `live_nav.js` publishes.

### Same day — modern skin for Live NAV (scoped to `body.lv-page`)

One palette, each colour with one job: slate for text and structure, one blue (`#2563eb`) for
magnitude and interaction, emerald/red for gain and loss only, registry identity colours only as the
marker of which portfolio. Chart colours live in one `P` object in `live.js`. Cards are borderless
with soft depth; section headers are titles, not numbered chapters; every card's explanatory note
collapses to two lines with Read more (content unchanged). Measured, not assumed: every text colour
is ≥ 4.5:1 on every background it sits on (the first draft's faint grey was 2.6:1). Table headers and
rows that select a portfolio are keyboard-operable. Tooltips carry the series name inside the box —
Plotly draws a separate `<extra>` name outside it in the series colour, unreadable for pale identity
colours. Other pages are untouched; the same skin can be widened to them by changing the scope.
