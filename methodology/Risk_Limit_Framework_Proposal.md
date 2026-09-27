# Risk Limits — What Is Real, and a Proposed Monitoring Layer
**Status: the "what is real" part is implemented. The proposed monitoring layer is NOT ACTIVE.**
2026-09-20

## 1. What was wrong, and the correction

`Src/build_portfolio_books_data.py` carried hand-typed `VOL_BUDGET` and `DD_BUDGET` dictionaries whose
numbers appeared in no methodology document. The first audit read both as invented. **Only half of
that was right**, and the correction matters:

**The volatility numbers were real.** 5.0 / 9.5 / 12.0 / 12.0 / 14.0 are exactly the `vol_cap` each
fund was solved under in `fs6_core.FUNDS6` — a genuine construction constraint. The fault was
duplication, not invention: the same number hand-typed in three places (`fs6_core`, the generator,
`fund_registry`), free to drift apart. They are now **read from `fs6_core`** and cannot drift.

**The loss limits were invented, and they contradicted the funds' own approved caps:**

| Fund | Displayed "budget" | Approved `ddcap` (fs6_core) | Realised worst loss | What the page said | What was true |
|---|---|---|---|---|---|
| Certain | −8% | **−11%** | −10.0% | breach | **within its approved cap** |
| Endowment | −20% | **−22%** | −24.3% | breach | exceeded, by 2.3pp not 4.3pp |
| SAA | −22% | **−29%** | −25.5% | breach | within the construction cap; exceeds the owner's −22% mandate limit |
| DAA | −22% | **−29%** | −20.8% | within | within |
| Alpha | −45% | **−58%** | −44.0% | within | within, with far more headroom |

Certain is the clearest case: a fund comfortably inside its approved −11% drawdown cap was displaying
a breach against a number nobody had set.

## 2. What the platform shows now

Three distinct objects, never merged into one word "budget":

- **Construction constraint** — the `vol_cap`, `cdar` and `ddcap` the optimiser actually solved
  under, read live from `fs6_core.FUNDS6`. Labelled as a constraint, not a monitoring limit. Present
  for all five funds.
- **Mandate limit** — an owner decision in the record. One exists: **SAA −22%**
  (`Fund_Suite_v5.md`). It is tighter than SAA's −29% construction cap, which is the correct
  relationship: the mandate promises more than the solver was required to deliver.
- **Measured** — forecast and realised volatility, realised worst loss. No frame, no comparison.

Where a fund's realised loss exceeds a constraint, the page now says so honestly — Endowment (−24.3%
against a −22% cap) and SAA against its −22% mandate limit both did, in 2008. Those are real
disclosures about approved numbers, not artefacts of an invented one.

`Src/verify_dashboard.py` contract C3 fails the build if any limit renders without a source.

## 3. Proposed — a monitoring layer (NOT ACTIVE)

A construction constraint is not a monitoring limit. It bound the solver once, at build time; it says
nothing about what should happen if a *live* fund starts running hot. The platform has no monitoring
layer, and adding one needs three things it does not yet have:

1. **A basis** — forecast vol, trailing realised vol, or live peak-to-trough? Different tests.
2. **A measurement convention** — which series (live NAV or backtest), what window, what frequency.
   A monthly backtest drawdown and a daily live drawdown are not comparable.
3. **A consequence** — de-risk, review, notify, or nothing. A limit with no consequence is
   decoration, and decoration that reads as a breach is worse than no limit at all.

### Proposed bands, derived from each fund's own modelled tail

From the block bootstrap already behind the Monte Carlo page (4,000 ten-year paths, each fund's own
monthly history):

| Fund | Modelled median DD | Modelled 95th-pct DD | Proposed monitoring band | Construction cap | Realised |
|---|---|---|---|---|---|
| Certain | −6.4% | −12.0% | −12% | −11% | −10.0% |
| Endowment | −15.3% | −26.8% | −27% | −22% | −24.3% |
| SAA | −15.6% | −28.8% | −29% | −29% | −25.5% |
| DAA | −15.6% | −24.0% | −24% | −29% | −20.8% |
| Alpha | −24.3% | −47.9% | −48% | −58% | −44.0% |

Note what this surfaces: for **Certain and Endowment the modelled tail is wider than the construction
cap** (−12.0% vs −11%, −26.8% vs −22%). The solver's drawdown constraint is estimated on its own
covariance model; the bootstrap resamples realised history including 2008. The gap is not an error in
either — it is the difference between a model-implied cap and a resampled empirical tail, and it is
worth knowing before any monitoring band is set. Endowment's realised −24.3% sits between the two.

### Recommendation

Adopt the bands above as **surfaced monitoring only, no consequence**, displayed as a third labelled
category alongside the construction constraint — never merged with it. Revisit consequences once
there is enough live NAV history for a live-basis test to mean anything (today: two months).

## 4. What activating this would touch

`Src/build_portfolio_books_data.py` (`MANDATE_LIMITS` and a new `MONITORING_BANDS`),
`Src/fund_registry.py` (`dials` — which still carries hand-typed limit strings and should read from
`fs6_core` the same way), the Risk page vol gauge, the KPI ribbon, and contract C3 in
`Src/verify_dashboard.py`, which would need to treat a band as a third category rather than as an
approved limit.

**Decision required before any of this becomes visible.**
