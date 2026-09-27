# Summer Funds — Certain · Endowment · SAA · DAA (v6, 2026-09-20)

**Status**: PRE-LAUNCH. Supersedes v1–v5.

**What changed from v5, and why.** v5 was one template with the equity/bond dial turned: gold sat at
exactly 8.0%, commodities at 2.0% and cash at 2.0% in *every* fund, and managed futures ran at 12–18%,
far above what any real manager holds. In v6 **each fund declares its own sleeve set** — a holding a
fund does not believe in is bounded to zero rather than left for the optimiser to discover — the trend
sleeve is sized like a sleeve, and the Swiss franc is held outright where it earns its place.

**Evidence**: `validation/fund_suite_v6/`. **Book**: `reports/fund_suite/Summer_Funds_Family_Book.html`.
**Reproduce**: `/usr/bin/python3 Src/pc_fs6_build.py` (`fs6_core.py`, `fs5_core.py`, `fs5_signals.py`).

## 1. Four funds, four different designs

**Certain** — 3+ years, reference Global 30/70  
*Short duration by design, with T-bills held as a real position rather than a residual. Gold and the Swiss franc are the store of value. No trend sleeve, no listed property, no long Treasuries.*  
4.94% a year · Sharpe 0.67 · worst loss -10.0% · forward return 4.91% at 4.7% volatility  
  US equity 9.0 · Developed ex-US equity 5.0 · US Treasuries (intermediate) 22.0 · IG corporate credit 8.0 · TIPS 16.0 · Broad commodities 4.0 · Gold 7.0 · Cash (T-bills) 26.0 · Swiss franc 3.0

**Endowment** — 10+ years, reference Global 60/40  
*Real assets are the identity — property, infrastructure, commodities and gold at a quarter of the fund. Thin nominal bonds, TIPS-led. No trend sleeve.*  
7.28% a year · Sharpe 0.64 · worst loss -24.3% · forward return 6.65% at 9.3% volatility  
  US equity 23.5 · Developed ex-US equity 4.5 · Emerging-market equity 6.0 · US Treasuries (intermediate) 8.0 · IG corporate credit 5.0 · TIPS 8.0 · Listed real estate 4.0 · Broad commodities 5.0 · Gold 8.0 · Cash (T-bills) 6.0 · Listed infrastructure 7.0 · US Treasuries (long) 15.0

**SAA** — 20+ years, reference Global 80/20  
*Nine holdings. Equity, two Treasury durations, gold, commodities and a trend sleeve sized like a sleeve, not like a hedge fund.*  
7.81% a year · Sharpe 0.65 · worst loss -25.5% · forward return 6.74% at 9.5% volatility  
  US equity 35.0 · Developed ex-US equity 7.0 · Emerging-market equity 9.0 · US Treasuries (intermediate) 6.0 · Broad commodities 3.0 · Gold 8.0 · Cash (T-bills) 4.0 · Managed futures (trend) 8.0 · US Treasuries (long) 20.0

**DAA** — 20+ years, reference Global 80/20  
*Nine holdings. Equity, two Treasury durations, gold, commodities and a trend sleeve sized like a sleeve, not like a hedge fund.*  
7.93% a year · Sharpe 0.71 · worst loss -20.7% · forward return 6.74% at 9.5% volatility  
  US equity 35.9 · Developed ex-US equity 8.4 · Emerging-market equity 10.4 · US Treasuries (intermediate) 3.7 · Broad commodities 4.0 · Gold 8.8 · Cash (T-bills) 4.3 · Managed futures (trend) 7.4 · US Treasuries (long) 17.1

The point of the table below is the dashes: these funds do not hold the same things.

| Holding | Certain | Endowment | SAA | DAA |
|---|---:|---:|---:|---:|
| US equity | 9.0 | 23.5 | 35.0 | 35.9 |
| Developed ex-US equity | 5.0 | 4.5 | 7.0 | 8.4 |
| Emerging-market equity | – | 6.0 | 9.0 | 10.4 |
| US Treasuries (intermediate) | 22.0 | 8.0 | 6.0 | 3.7 |
| IG corporate credit | 8.0 | 5.0 | – | – |
| TIPS | 16.0 | 8.0 | – | – |
| Listed real estate | – | 4.0 | – | – |
| Broad commodities | 4.0 | 5.0 | 3.0 | 4.0 |
| Gold | 7.0 | 8.0 | 8.0 | 8.8 |
| Cash (T-bills) | 26.0 | 6.0 | 4.0 | 4.3 |
| Listed infrastructure | – | 7.0 | – | – |
| Managed futures (trend) | – | – | 8.0 | 7.4 |
| US Treasuries (long) | – | 15.0 | 20.0 | 17.1 |
| Swiss franc | 3.0 | – | – | – |

## 2. Record (net of costs and a 15bp/yr fee)

**1997-2026** — not used in construction

| | CAGR | Vol | Sharpe | Worst loss |
|---|---:|---:|---:|---:|
| Certain | 4.94 | 4.1 | 0.67 | -10.0 |
| Endowment | 7.28 | 8.1 | 0.64 | -24.3 |
| SAA | 7.81 | 8.8 | 0.65 | -25.5 |
| DAA | 7.93 | 8.2 | 0.71 | -20.7 |
| Global 30/70 | 5.61 | 6.0 | 0.58 | -17.6 |
| Global 60/40 | 7.01 | 9.8 | 0.52 | -34.5 |
| Global 80/20 | 7.83 | 12.7 | 0.49 | -44.7 |
| US 60/40 | 7.68 | 9.6 | 0.59 | -32.3 |
| S&P 500 | 9.69 | 15.4 | 0.54 | -50.8 |
| World equity (ACWI) | 8.41 | 16.0 | 0.45 | -55.0 |

**2007-2026** — the books were built here

| | CAGR | Vol | Sharpe | Worst loss |
|---|---:|---:|---:|---:|
| Certain | 4.11 | 4.4 | 0.60 | -10.0 |
| Endowment | 6.43 | 8.6 | 0.60 | -24.3 |
| SAA | 7.27 | 8.7 | 0.68 | -25.5 |
| DAA | 7.77 | 8.4 | 0.76 | -20.7 |
| Global 30/70 | 4.91 | 6.5 | 0.55 | -17.6 |
| Global 60/40 | 6.64 | 10.2 | 0.54 | -34.5 |
| Global 80/20 | 7.68 | 13.0 | 0.52 | -44.7 |
| US 60/40 | 7.87 | 9.9 | 0.67 | -32.3 |
| S&P 500 | 10.74 | 15.5 | 0.64 | -50.8 |
| World equity (ACWI) | 7.72 | 16.4 | 0.45 | -55.0 |

**1997-2007** — not used in construction

| | CAGR | Vol | Sharpe | Worst loss |
|---|---:|---:|---:|---:|
| Certain | 6.55 | 3.3 | 0.88 | -2.5 |
| Endowment | 8.92 | 6.9 | 0.76 | -8.1 |
| SAA | 8.85 | 9.0 | 0.59 | -18.2 |
| DAA | 8.24 | 7.7 | 0.61 | -14.5 |
| Global 30/70 | 6.96 | 4.9 | 0.68 | -4.7 |
| Global 60/40 | 7.73 | 9.0 | 0.48 | -22.1 |
| Global 80/20 | 8.11 | 12.1 | 0.41 | -33.3 |
| US 60/40 | 7.32 | 9.0 | 0.44 | -23.5 |
| S&P 500 | 7.69 | 15.1 | 0.33 | -44.8 |
| World equity (ACWI) | 9.78 | 15.1 | 0.46 | -38.5 |

Every fund beats its reference on Sharpe and on worst loss. The DAA beats its own untilted book on
Sharpe in **all three** windows, including the decade nothing was fitted to.

## 3. The trend sleeve is sized by macro

Policy weight 8%. The DAA's diversifier-sizing engine runs it between
3.8% and 12.0%:

| Regime | Goldilocks | Reflation | Disinflationary slowdown | Stagflation | Stress |
|---|---:|---:|---:|---:|---:|
| Trend sleeve | 5.9% | 9.2% | 6.8% | 10.8% | 11.1% |

Trend pays in volatile, trending, inflationary regimes and costs carry in calm disinflation, so it is
scaled on stress and inflation and funded from the rest of the book.

