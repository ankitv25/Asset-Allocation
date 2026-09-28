# Updating the platform

Two different things get updated, and only one of them happens in this repository.

| | Where it runs | What it does |
|---|---|---|
| **Refresh** | private research repo | re-prices the NAV, rebuilds the five payloads |
| **Deploy** | private research repo, one script | pushes pages + payloads + `src/` + docs here |
| **Verify** | **either repo** | the five contracts, and the render check |

This mirror is written by the deploy script. Editing a page or a payload here is overwritten on the
next deploy — change it in the private repo.

## Refresh (private repo)

Order matters: `pit_backtest.py` and `style_box.py` write JSON that `build_portfolio_books_data.py`
reads, and it degrades gracefully (prints a note) if either is absent.

```
/usr/bin/python3 Src/pc_fs6_build.py                    # books + backtest (only if the strategy changed)
/usr/bin/python3 Src/fund_nav.py                        # daily NAV from market closes
/usr/bin/python3 Src/vehicle_data.py                    # per-vehicle yield and category
/usr/bin/python3 Src/factor_attrib.py                   # factor attribution of the live NAV
/usr/bin/python3 Src/pit_backtest.py                    # walk-forward series (slow-ish, cacheable)
/usr/bin/python3 Src/style_box.py                       # 3x3 style box (fetches 9 ETFs, cached)
/usr/bin/python3 Src/build_portfolios_dashboard_data.py # Portfolios page payload
/usr/bin/python3 Src/build_portfolio_books_data.py      # the five deep-page payloads
/usr/bin/python3 Src/pc_fund_live_page.py               # Live NAV page + feed
python3 Src/verify_dashboard.py                         # must pass
bash Research/Portfolio_Construction/dashboard/deploy_dashboard_public.sh   # owner-run; gated on the above
```

`/usr/bin/python3` is the interpreter with pandas — the homebrew `python3` does not have it.
`verify_dashboard.py` is stdlib-only and runs on either.

### NAV refresh only

The common case. Two steps:

```
/usr/bin/python3 Src/fund_nav.py
/usr/bin/python3 Src/factor_attrib.py
/usr/bin/python3 Src/pc_fund_live_page.py
```

The Live NAV page's equity style box keeps its position from the last `style_box.py` run — it only
moves when the US equity vehicles change, so the daily refresh does not need it. Run `style_box.py`
before `pc_fund_live_page.py` after any change to the equity vehicles.

**What the ingestion guarantees.** It rebuilds all five books from the CMAs and the optimiser first, so
the NAV is never computed against stale weights. It pulls dividend-adjusted daily closes for every
vehicle held plus SPY / ACWI / AGG, and **refuses to run on partial data** — if any vehicle is missing
or has under 20 prints it exits rather than pricing a fund that is quietly under-invested, and it
re-checks that every day's target weights sum to 1. That is not theoretical: the first run silently
dropped SPLG, which left Alpha 17% in cash and understated both its return and its volatility. **SPLG
must not be reintroduced** — ITOT and SCHX are the substitutes in the US equity split. The whole series
is recomputed from inception every run, so a bad print cannot persist once the source is fixed. A 15bp
annual fee is charged daily and 10bp per side whenever a fund deals.

**Dealing rules.** Certain / Endowment / SAA hold policy weights and deal only when a holding drifts
1pp from target. DAA / Alpha re-read the five engines at each month end, same 1pp band on execution.

## Verify (either repo)

```
python3 src/verify_dashboard.py --dash .        # in this mirror
python3 Src/verify_dashboard.py                 # in the private repo
```

Five contracts, no browser, and it gates the deploy: **C1** module presence · **C2** stale page copy ·
**C3** parameter provenance · **C4** series provenance · **C5** sleeve narrative. Exit 0 is clean; every
breach is printed with its page, portfolio and payload path. See [HANDOFF.md](HANDOFF.md) for why the
older "no uncaught errors + count SVGs" standard reported clean on pages rendering nothing.

The second layer is a render check in a headless browser over the 45 page × portfolio combinations —
also in HANDOFF.md.

## Running the build chain from this mirror

Mostly you cannot, and that is deliberate.

`src/` is published to be **read and audited**. The chain resolves its inputs relative to the repo
root, and the inputs themselves are not redistributed here:

| Stage | Needs | Shipped? |
|---|---|---|
| `fs2_core`, `fs3_core` | daily price panel, World Bank commodity file, Fama-French factors | no — third-party |
| `fs5_signals`, `portfolio_dcs_signal` | MRS composite history | via [Macro-Regime-Score](https://github.com/ankitv25/Macro-Regime-Score) |
| `pc_fs6_build` | upstream solver output, peer landscape | no |
| `build_portfolio_books_data` | `validation/fund_suite_v6/`, `validation/fund_nav/` | no |
| `vehicle_data` | a public market-data feed, for per-vehicle yield | no |
| `factor_attrib` | the live NAV feed, plus long price history for the factor legs | no |
| `verify_dashboard` | this repo's pages, `module_contract.json`, `data/portfolio_books.json` | **yes** |

External data the chain reaches for at runtime: FRED CSV endpoints (keyless), Yahoo daily closes via
`yfinance`, and the MRS composite from the public Macro-Regime-Score repo. No credentials are used
anywhere in `src/`, and none are needed.

## Requirements

```
pip install -r requirements.txt
```

`numpy`, `pandas`, `scipy` for the solvers, `yfinance` for prices, `openpyxl` to read the commodity
workbook. `verify_dashboard.py` needs none of them.
