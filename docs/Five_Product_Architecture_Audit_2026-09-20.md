# Five-Product Architecture — Current-State Audit and Execution Plan
**2026-09-20 · no code changed for this document · supersedes nothing until approved**

This is the audit requested before any further implementation. It compares the portfolio experience as
it stood before the five-fund work, the state after commits `ac1f4a4 → ee4fa7d`, and what five products
actually require. Every claim below is traced to a file and line or to a query against the shipped
payload.

---

## 0. The single sentence

The renderer was never the problem — `app.js` (1,745 lines, untouched) still contains every module it
ever had. **The regression is in the payload and the page copy.** Three whole analytical modules are
absent from all five portfolio books, so their renderers silently no-op behind `if (d.x)` guards; and
the page copy still describes a three-candidate research study while a `<select>` swaps five products
underneath it. Nothing errors. That is why it verified clean and still reads as a downgrade.

---

## 1. Current-state inventory

### 1.1 What exists (13 pages, ~70 analytical tiles)

| Page | Tiles | Data source | Selector-aware |
|---|---|---|---|
| `index.html` Overview | 18 | `portfolio_books.js` → `app.js` | yes |
| `construction.html` | 9 | same | yes |
| `holdings.html` | 3 | same | yes |
| `performance.html` | 10 | same | yes |
| `attribution.html` | 14 | same | yes |
| `risk.html` | 11 | same | yes |
| `stress.html` | 5 | same | yes |
| `montecarlo.html` | 8 | same | yes |
| `portfolios.html` | 12 | `portfolios.js` (own payload) | no — renders all five at once |
| `live.html` | 6 | `live_nav.js` | no — renders all five at once |
| `playbook.html` | — | `playbook.js` | no |
| `growth.html` | — | `growth_engine.js` | no |
| `methodology.html` | — | static | no |

### 1.2 Classification

**KEEP — working, selector-aware, no change needed (48 tiles)**
Overview allocation/positioning/hierarchy/sleeve-thesis; Construction §1–§5 including the
sleeve→instrument drill with per-instrument `rationale`; Holdings blotter + donut filter + CSV;
Performance rolling 12m return/vol/Sharpe; Risk vol-gauge, factor, capital-vs-risk, instrument
drill, correlation heatmap, diversification stats; Stress historical episodes + crisis drill; all
8 Monte Carlo tiles. These render correctly for all five portfolios today.

**IMPROVE — renders, but the copy contradicts what is on screen (11 tiles)**
Page copy frozen at the two-book (SAA vs DAA) or three-candidate era while five products flow
through it. Evidence:
- `performance.html:39` — "The dynamic book (DAA) against its own static policy (SAA)" shown while
  Certain / Endowment / Alpha are selected.
- `montecarlo.html:41,60,114,121,135` — five references to "the dynamic book (DAA)" and "DAA vs SAA".
- `attribution.html:55,66,106` — "DAA vs SAA weight × return".
- `index.html:178,193`, `stress.html:59` — "Full System", a label from the superseded book.
- `live.html:105` — "Four mandates, four different books". There are five.
- `portfolios.html:116,124,130` — "the three books", "the three versions", ×3.
- `portfolios.html:187` — "every version is in-sample; **nothing here is live-approved**" — on a
  platform where all five have been live with real NAV since 15 Jul 2026.
- `portfolios.html` `<title>` still reads "Endowment · SAA · DAA/MRS".
- `portfolios.html:74` version-card grid is hardcoded `repeat(3,1fr)` for five products.

**REPLACE — architecturally wrong for five products (2 items)**
- `assets/js/portfolio-select.js` — five products exposed as an app-bar `<select>`. There is no
  product discovery surface, no per-product landing, no comparison, no durable per-product identity
  beyond `?p=`. This is the "five options at the top of one page" problem named directly.
- `portfolios.html` — structurally still the three-candidate research study (hero verdict, superseded
  banner, §06 "open gates"), with five products pushed through it. Its *job* should now be product
  discovery and cross-product comparison.

**MOVE — 1 item**
- `portfolios.html` §05 "DAA/MRS mechanics" (rotation over time, rotation value isolated, caveats).
  This is single-product mechanics sitting on what should be the family page. It belongs on the DAA
  product page. Note its `tile-sub` is also stale: it says "SPY-satellite size per month", but
  `dd43d3b` replaced that dial with the MRS composite — the label describes a mechanism that no
  longer exists.

**REMOVE — 0 items.** I am not proposing to remove anything. Everything currently missing (below) is
a restoration target, not a deletion.

---

## 2. Regression / information-loss audit

### 2.1 Three analytical modules absent from all five books — pages render empty, silently

Verified by path-diff of each book in `data/portfolio_books.json` against the reference payload
`data/portfolio.json` (769 paths). Missing in **all five**:

| Module | What it communicated | Where it is consumed | Result today |
|---|---|---|---|
| `matrix` | 9×9 peer matrix: risk-vs-return scatter + cross-sectional metric grid + narrative — where every book stands against every peer | `app.js:1730` → `attribution.html` `#matrix-scatter`, `#matrix-grid` | two tiles blank |
| `risk_detail` | Sleeve-level risk decomposition — MCTR, component vol, Herfindahl, effective bets, top-3 risk share, block capital-vs-risk, SAA vs DAA risk share | `app.js:1723` → `risk.html` `#risk-detail` | four tiles blank |
| `stress_forward` | Ex-ante factor stress — Equity/Duration/Credit/Inflation/Dollar betas per sleeve, scenario shocks, custom-scenario engine | `app.js:1726` → `stress.html` `#fwd-scen` | three tiles blank, including the interactive custom-scenario builder |

**Why this passed verification.** All three call sites are guarded — `if (d.risk_detail)`,
`if (d.stress_forward)`, `if (d.matrix && el("matrix-scatter"))`. A missing module is not an
exception, so `#status-footer` stays clean and the SVG count stays non-zero because *other* tiles on
the page still draw. The existing check (`/tmp/check_pages.sh`) cannot catch this class. **This is the
verification gap that let the platform get smaller without anyone being told.**

### 2.2 Peer set narrowed
`comparison.series` went from 7 peers to 5. **`PC16 anchor` and `Equal-Weight` were dropped.** Both are
still referenced in `app.js:565,668–670` with dedicated colours and line widths — the renderer expects
them. PC16 was the platform's own house anchor; Equal-Weight was the naive-diversification control.
Losing the naive control means no tile now answers "does the optimiser beat equal weight?"

### 2.3 Attribution timeline thinned
`active_attr.layer_cumulative` carried three decomposed layers (Regime stance / Risk budget /
Tactical tilt). The new books carry one. For Certain/Endowment/SAA that is *correct* — they are static,
active return is genuinely zero — but it means the Attribution page, which is entirely about active
management, shows a single zero row for three of five products. That is an architecture gap, not a
regression: **the page set should differ by product type.** (DAA and Alpha do carry five real layers:
Valuation / Trend / Relative strength / Regime / Diversifier sizing.)

### 2.4 Narrative loss on `portfolios.html`
`dd43d3b` replaced roughly 60 lines of written analysis in `assets/js/portfolios.js` with
payload-driven generics. Specifically lost: the crisis-episode read ("DAA's GFC defense is its verified
win — regime confirmed Slowdown 2007-12, nine months pre-Lehman; COVID it missed entirely"), the
rotation-value read, the regime-months read, the honest-loss note on Euro-2011, and the FI-leg
IG ≤ 5% breach check. The replacements state numbers without stating what they mean.

---

## 3. Unapproved methodology now live in the product — **corrected 2026-09-20**

`Src/build_portfolio_books_data.py` carried hand-typed `VOL_BUDGET` and `DD_BUDGET` dictionaries,
duplicated again as display strings in `Src/fund_registry.py`. My first reading — that all ten numbers
were invented — was **half wrong**, and the correction sharpens the finding rather than softening it.

**The volatility numbers were real.** 5.0 / 9.5 / 12.0 / 12.0 / 14.0 are exactly the `vol_cap` each
fund was solved under in `fs6_core.FUNDS6`. A genuine construction constraint, hand-copied into two
other files where it was free to drift. Now read from `fs6_core` directly.

**The loss limits were invented, and they contradicted the funds’ own approved drawdown caps:**

| Fund | Displayed "budget" | Approved `ddcap` | Realised worst loss | Page said | Truth |
|---|---|---|---|---|---|
| Certain | −8% | **−11%** | −10.0% | breach | **within its approved cap** |
| Endowment | −20% | **−22%** | −24.3% | breach | exceeded by 2.3pp, not 4.3pp |
| SAA | −22% | **−29%** | −25.5% | breach | within the cap; exceeds the owner’s −22% mandate limit |
| DAA | −22% | **−29%** | −20.8% | within | within |
| Alpha | −45% | **−58%** | −44.0% | within | within, with far more headroom |

Certain is the clearest case: a fund comfortably inside its approved −11% cap was displaying a breach
against a number nobody set.

**Treatment implemented.** Three distinct objects, never merged into the word "budget":
*construction constraint* (vol/CDaR/drawdown caps read live from `fs6_core`, all five funds),
*mandate limit* (owner decisions in the record — one exists, SAA −22% from `Fund_Suite_v5.md`, correctly
tighter than its −29% construction cap), and *measured* (forecast/realised, no frame). Where a realised
loss genuinely exceeds an approved number — Endowment against its −22% cap, SAA against its −22% mandate
limit, both in 2008 — the page now says so. A proposed monitoring layer is written up in
`docs/methodology/Risk_Limit_Framework_Proposal.md` and is **not active**.

## 4. Performance-data treatment

Two pages say "performance" and mean different things, with nothing on screen distinguishing them:

| | `live.html` | `performance.html` / `index.html` / `portfolios.html` |
|---|---|---|
| Series | daily NAV, 15 Jul 2026 → today | monthly, 1997-06 → 2026-08 |
| Nature | **actual** — real prices, net 15bp fee + 10bp/side dealing | **backtest** — reconstructed on current policy weights |
| Labelled? | yes, well — "priced daily", "not a custodial record", "two months is far too short" | **no** — chart is titled "Growth of $1 — net of cost" with no vintage, no basis, no rebalance convention |

`live.html` handles this correctly and should be the standard. The 29-year series does not. It is a
**backtest of today's weights applied to history** — it is not a track record, no capital was managed,
and the weights did not exist before 2026. Presented as "Growth of $1" next to a live NAV page, it
blurs exactly the distinction you named.

**Proposed treatment — a provenance contract every performance series must carry**, rendered as a
visible band on the chart, not a footnote:
`basis` (live | backtest | simulated) · `window` · `weights` (as-of date, static or point-in-time) ·
`rebalance` convention · `costs` included · `data vintage` · `what did not exist at t0`.
Live and backtest never share an axis without a visible inception marker.

Open question for you: the 1997 backtest applies **current** weights to history. Should it stay a
static-weight backtest (honest, simple, clearly labelled) or be rebuilt point-in-time? Static is
defensible if labelled; I will not change the basis without your call.

---

## 5. What five products actually require

Per-product state that exists today: name, color, thesis, horizon, dials, managed flag
(`Src/fund_registry.py`), plus a full book payload each. What is missing is the layer above.

**5.1 Product discovery — new.** A fund-range page: what each product is for, who it suits, its
horizon, its shape, its live NAV, one line of "choose this if". Entry point to each product. This is
what `portfolios.html` should become.

**5.2 Product identity and routing — replace.** Each product needs a durable landing surface, not a
query parameter on a shared page. Options: `?p=` retained but with a real per-product landing page, or
`funds/<key>.html` per product. Recommend the former — it preserves the "one renderer, five payloads"
decision that already works and avoids five copies of eight pages. The selector stays, but demoted to
in-context switching, not the primary discovery mechanism.

**5.3 Comparison — new.** No surface currently answers "how do these five differ?" for a reader.
`live.html`'s mandate table is the closest and is the right seed: sleeve-by-sleeve across all five.
Extend to risk/return, drawdown, crisis behaviour, cost, horizon.

**5.4 Page set varies by product type — new.** Attribution and the active layers are meaningful for
DAA and Alpha and empty-by-design for Certain/Endowment/SAA. The nav should reflect that rather than
offering every page for every product and showing a zero row.

**5.5 Shared vs per-product content — to be specified.** Methodology, Playbook, Growth Engine and
Construction principles are house-level. Allocation, holdings, risk, attribution, NAV are per-product.
Today all thirteen nav links look identical in scope. They are not.

---

## 6. Execution plan

Each phase: what changes · why · what is preserved · what is new · assumptions · validation · done.

### Phase 0 — Verification harness *(do first; nothing else is trustworthy without it)*
- **Change:** extend the page check from "no Uncaught + SVG count > 0" to a module-presence contract —
  assert every guarded renderer in `app.js` has its payload key, per product; assert no tile container
  is left empty; assert no page-copy token from a stale vocabulary (`three books`, `Full System`,
  `Four mandates`, `DAA vs SAA` on a non-DAA product).
- **Why:** §2.1 — the current check structurally cannot see silent module loss.
- **Preserved:** existing `check_pages.sh` behaviour, as a subset.
- **New:** `module_contract.json` — the list of payload keys each page requires.
- **Assumptions:** none.
- **Validation:** deliberately delete `risk_detail` from one book; the harness must fail.
- **Done:** harness fails on today's tree with exactly the 9 blank tiles from §2.1.

### Phase 1 — Restore the three missing modules
- **Change:** `Src/build_portfolio_books_data.py` emits `matrix`, `risk_detail`, `stress_forward` per
  product, computed from that product's own covariance and sleeve set. Restore `PC16 anchor` and
  `Equal-Weight` to `comparison`.
- **Why:** §2.1, §2.2 — restoring existing capability, not new work.
- **Preserved:** every renderer as-is; no `app.js` change.
- **New:** nothing user-facing beyond what already existed.
- **Assumptions:** the factor-beta estimation in `stress_forward` is re-estimated on each product's own
  sleeves. Flagging now: the reference betas were fitted on the v3.8 sleeve universe; the v6 products
  have their own sleeve sets, so these are new estimates, not a copy. I will state the estimation window.
- **Validation:** Phase 0 harness green; 9 tiles populated; spot-check MCTRs sum to portfolio vol.
- **Done:** path-diff of each book vs reference shows no missing module.

### Phase 2 — Strip unapproved parameters
- **Change:** remove `VOL_BUDGET` / `DD_BUDGET` from the generator and the dial strings from
  `fund_registry.py`. Risk tiles render forecast vol and realised worst loss without a budget line.
- **Why:** §3.
- **Preserved:** every risk number that is computed. Only the invented comparators go.
- **New:** a "Recommended — not active" section in the methodology doc proposing a risk-limit framework
  for your approval.
- **Assumptions:** Alpha 14% vol and SAA −22% stay, as they are in the record — confirm.
- **Validation:** grep the generator and payload for hand-typed risk constants; none remain.
- **Done:** no page displays a limit not traceable to an approved doc.

### Phase 3 — Performance provenance contract
- **Change:** add the §4 provenance block to every performance series and render it visibly.
- **Why:** §4.
- **Preserved:** all series and charts.
- **New:** the provenance band; an inception marker where live and backtest meet.
- **Assumptions:** basis stays static-weight backtest pending your §4 call.
- **Validation:** no chart renders without a resolved provenance block — harness-enforced.
- **Done:** a reader can state, for any series on the platform, what it is.

### Phase 4 — Page copy reconciliation
- **Change:** the 11 IMPROVE tiles in §1.2; copy becomes product-aware where it is product-specific.
- **Why:** §1.2.
- **Preserved:** every tile, chart and number. Copy only.
- **New:** none.
- **Assumptions:** none.
- **Validation:** stale-vocabulary check from Phase 0 passes on all five products × 13 pages.
- **Done:** no page describes a product other than the one selected.

### Phase 5 — Product architecture
- **Change:** `portfolios.html` becomes the fund range (§5.1); per-product landing; comparison surface
  (§5.3); nav varies by product type (§5.4); shared vs per-product made visible (§5.5); DAA mechanics
  moved from the family page to the DAA product page (§1.2 MOVE).
- **Why:** §5 — the original ask.
- **Preserved:** the one-renderer/five-payloads decision; all eight deep pages; the `?p=` contract.
- **New:** range page, per-product landing, comparison page, type-aware nav.
- **Assumptions:** I will bring you the information architecture — what sits on the range page, the
  landing, and the comparison — **before building it**.
- **Validation:** all five products reachable and complete from a cold start with no prior state.
- **Done:** you can navigate the five as products, not as dropdown options.

### Phase 6 — Restore and deepen the written layer
- **Change:** restore the §2.4 narratives, adapted to five products; sleeve cards regain role,
  rationale, contribution and implementation rather than a label.
- **Why:** §2.4 and your point 2.
- **Preserved:** everything.
- **New:** per-product sleeve write-ups where the v6 sleeve sets differ from v3.8.
- **Assumptions:** for genuinely new sleeves (CHF in Certain, the trend sleeve) I will draft rationale
  from the v6 construction record and mark anything I could not source, rather than inventing it.
- **Validation:** every sleeve at >0.5% weight in every product has role + rationale + contribution.
- **Done:** no sleeve renders as a bare name.

### Phase 7 — Final review
Full 5 × 13 regression; path-diff every book against reference; provenance audit; methodology
traceability audit — every displayed parameter traced to an approved doc or removed; deploy pre-flight.

---

## 7. What I need from you before Phase 1

1. **§3** — confirm the eight unapproved risk budgets come out, and whether Alpha 14% / SAA −22% stay.
2. **§4** — static-weight backtest (labelled) or point-in-time rebuild?
3. **Phase 5** — do you want the IA proposal as a separate document before any build, or inline here?
4. **Sequencing** — Phases 0–4 are restoration and correction and are low-risk; Phase 5 is the design
   work you actually asked for. I propose running 0–4 first so the platform is whole before it is
   extended. Say if you would rather see the architecture first.

Nothing in Phase 1 onward starts without your answer to 1 and 2.

---

# Execution record — all eight phases complete
2026-09-20

## Two corrections to this audit, found while implementing

**1. The volatility budgets were real; I called them invented.** 5.0 / 9.5 / 12.0 / 12.0 / 14.0 are
exactly the `vol_cap` each fund was solved under in `fs6_core.FUNDS6`. The fault was duplication
across three files, not invention. They are now read from `fs6_core`. The *loss* limits were invented
and did contradict the funds' approved drawdown caps — §3 above is corrected in full.

**2. The drawdown caps displayed were the DECLARED caps, not the ones used.** `pc_fs6_build` searches
for the tightest feasible cap at or above the declaration (`fs4_core.solve_fund`). Endowment's
declared 16% CDaR / 22% drawdown was infeasible and was loosened to 20% / 27.5%. The page was showing
"−22%" — a constraint the book was never held to — and reporting Endowment's realised −24.3% as an
overshoot when it was comfortably inside the −27.5% actually used. Now read from the build record,
with the declared figure shown alongside because the loosening is itself information.

Net effect: after Phase 2 **no fund displays a false breach**, and the two genuine ones (Endowment
against its −22% declared cap, SAA against its −22% owner mandate limit, both 2008) are stated openly.

## What each phase delivered

| Phase | Delivered | Verified by |
|---|---|---|
| 0 Harness | `Src/verify_dashboard.py` + `dashboard/module_contract.json` — five contracts | Reproduced all 112 original breaches |
| 1 Restore | `matrix`, `risk_detail`, `stress_forward` built per portfolio; `Equal-Weight` and `PC16 anchor` peers restored | 9 dark tiles now draw; attribution 11 charts, risk 7, stress 5 |
| 2 Parameters | Invented loss limits removed; caps read from `fs6_core` and the build record; `Risk_Limit_Framework_Proposal.md` written, not active | C3 green; no false breach remains |
| 3 Provenance | Provenance contract on every series + visible band; `Src/pit_backtest.py` walk-forward added as a second labelled series | C4 green; all five funds produce a walk-forward |
| 4 Copy | 11 stale tiles + all two-book DAA/SAA copy made portfolio-aware via `.pf-name` | C2 green, widened to catch the whole class |
| 5 Architecture | `portfolios.html` rebuilt as the range; product cards as entry points; comparison; `?p=` carried through nav; Attribution labelled active-only | 45/45 page-portfolio combinations render clean |
| 6 Narrative | `Src/sleeve_registry.py` — thesis, role, risk character per sleeve; role + rationale per vehicle | C5 green; 14 sleeves, 18 vehicles, no stubs |
| 7 Review | Deploy gated on the contracts; pre-flight dry-run passes | Both harnesses green |

## Three further defects found and fixed

- **`portfolios.json` contained literal `NaN` tokens.** Invalid JSON, but valid JavaScript, so the
  page loaded it and compounded it into "Growth of $1: $NaN". The five funds do not exist before
  1997-06; the panel was padded back to 1995-01 and the page then claimed 1995-01–2026-08 as the
  common window. Now `null`, trimmed to the true common window, with the window stated.
- **The walk-forward dropped a decade of history** by `dropna()`-ing across sleeves a fund cannot
  hold — Endowment produced no walk-forward at all. Fixed to consider only holdable sleeves.
- **The sleeve drill-down lost the selected portfolio**, dropping the reader onto another product's
  construction page. `?p=` is now carried.

## Two limitations, stated rather than hidden

1. **The walk-forward is not fully point-in-time.** Risk is re-estimated at each rebalance; the
   expected-return view is not, because `fs3_core.model()` builds its CMA from a current snapshot and
   the platform holds no historical CMA vintages. It answers "how much does the book depend on the
   covariance window?" and not "would we have chosen this in 2008?". Carried in the payload, printed
   by the script, and rendered on the page.
2. **The custom-scenario slider betas are estimates.** The scenario set itself is the approved
   `fund_suite_v6.scenarios_def` and the per-fund impacts match it to 0.1pp. The sleeve×factor
   sensitivities behind the sliders are OLS estimates on sleeve returns, labelled as such on the page.

## Still open for you

- `Risk_Limit_Framework_Proposal.md` — the monitoring layer, not active pending your decision.
- Whether the 1997 backtest should ever become point-in-time on returns as well as risk. It cannot be
  today without historical CMA vintages.
- Endowment's declared CDaR is infeasible at every walk-forward date, not just on the full window.
  That is a fact about the fund's construction worth a decision, not a bug.
