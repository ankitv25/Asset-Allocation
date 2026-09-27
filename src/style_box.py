#!/usr/bin/env python3
"""
style_box.py — the 3x3 equity style box (size x value/growth) for each portfolio.

WHY THIS EXISTS
The methodology formalises sectors and styles as living INSIDE the equity sleeves -- "PC-22, the 3x3
style box" (Multi_Asset_Framework_v4 s64) -- and the waterfall handoff records it as NOT BUILT. So the
platform has always said equity style is part of the design and has never shown it. Nothing on any
page told you whether the range is large-blend, where it sits against the market, or whether any of
the five takes a size or value bet at all. This builds it.

METHOD -- returns-based style analysis (Sharpe 1992)
Each portfolio's US equity sleeve is the actual weighted mix of the vehicles it holds. That series is
regressed on the nine Russell style-box corners with weights constrained to be non-negative and to sum
to one, so the result reads as "the passive style mix that best replicates this sleeve" rather than as
unconstrained betas. R-squared is reported: a low R-squared means the style mix does not explain the
sleeve and the position in the box should not be trusted.

Size score maps large/mid/small to +1/0/-1 and style score maps value/blend/growth to -1/0/+1, so a
portfolio's coordinates in the box are a weighted average of its corner weights. The active tilt is
measured against the TOTAL US market (ITOT), not against a large-cap index -- benchmarking a
large-cap book to a large-cap index reports no size bet and hides the stance actually being taken.

HONEST BOUNDS
 * The nine corners share a common start of 2001-08 (IWP/IWR/IWS inception), so this analysis runs
   from 2001-09. It is shorter than the 1997-2026 backtest and is labelled with its own window.
 * Returns-based style analysis infers style from behaviour, not from looking through to holdings.
   For index funds that is a very good approximation; it would be weaker for an active manager.
 * This is DESCRIPTIVE. It introduces no target, no band and no limit. PC-22 remains unbuilt: the
   point of showing the box is to make visible that the size/style dimension is currently unused.

Output: Research/Portfolio_Construction/validation/fund_suite_v6/style_box.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(__file__))
import fund_registry as FR  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_suite_v6')
NAVD = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_nav')
PX = os.path.join(OUT, 'style_box_prices.csv')

# The nine corners, plus the market reference and the vehicles the funds actually hold.
CORNERS = [('Large', 'Value', 'IWD'), ('Large', 'Blend', 'IWB'), ('Large', 'Growth', 'IWF'),
           ('Mid', 'Value', 'IWS'), ('Mid', 'Blend', 'IWR'), ('Mid', 'Growth', 'IWP'),
           ('Small', 'Value', 'IWN'), ('Small', 'Blend', 'IWM'), ('Small', 'Growth', 'IWO')]
HELD = ['VOO', 'IVV', 'ITOT', 'SCHX']
# The market reference is the TOTAL US market, not the Russell 1000. IWB is itself a large-cap index,
# so measuring a large-cap book against it reports ~zero active size bet and hides the actual stance.
# Against the total market, holding only S&P 500 trackers IS a size decision, and that is the point.
MARKET = 'ITOT'
SIZES, STYLES = ['Large', 'Mid', 'Small'], ['Value', 'Blend', 'Growth']
SIZE_SCORE = {'Large': 1.0, 'Mid': 0.0, 'Small': -1.0}
STYLE_SCORE = {'Value': -1.0, 'Blend': 0.0, 'Growth': 1.0}


def prices(refresh=False):
    tick = sorted({t for _, _, t in CORNERS} | set(HELD))
    if refresh or not os.path.exists(PX):
        import yfinance as yf
        px = yf.download(tick, start='1995-01-01', auto_adjust=True, progress=False)['Close']
        px.dropna(how='all').to_csv(PX)
    px = pd.read_csv(PX, index_col=0, parse_dates=True).sort_index()
    m = px.resample('ME').last()
    m.index = m.index.to_period('M')
    return m.pct_change(fill_method=None)


def style_fit(y, X):
    """Non-negative weights summing to one that best replicate y from the corners X."""
    n = X.shape[1]
    A, b = X.values, y.values

    def sse(w):
        r = b - A @ w
        return float(r @ r)

    res = minimize(sse, np.full(n, 1.0 / n), method='SLSQP',
                   bounds=[(0.0, 1.0)] * n,
                   constraints=[{'type': 'eq', 'fun': lambda w: w.sum() - 1.0}],
                   options={'maxiter': 500, 'ftol': 1e-12})
    w = np.clip(res.x, 0, None)
    w = w / w.sum()
    resid = b - A @ w
    r2 = 1.0 - float(resid @ resid) / float(((b - b.mean()) ** 2).sum())
    te = float(np.std(resid) * np.sqrt(12))
    return w, r2, te


def main():
    R = prices()
    nav = json.load(open(os.path.join(NAVD, 'fund_nav.json')))
    ts = nav['ticker_sleeve']
    corner_t = [t for _, _, t in CORNERS]
    panel = R[corner_t + HELD].dropna()
    print(f'style-box window {panel.index.min()} — {panel.index.max()} ({len(panel)} months)')

    X = panel[corner_t]
    mkt_w, mkt_r2, _ = style_fit(panel[MARKET], X)     # the market reference, fitted the same way

    out = {}
    for key in FR.ORDER:
        nm = FR.FUNDS[key]['name']
        hold = nav['holdings'][nm]
        us = {t: w for t, w in hold.items() if ts.get(t) == 'US_EQ' and t in HELD}
        if not us:
            continue
        tot = sum(us.values())
        sleeve = sum(panel[t] * (w / tot) for t, w in us.items())
        w, r2, te = style_fit(sleeve, X)

        grid = [[0.0] * 3 for _ in range(3)]
        act = [[0.0] * 3 for _ in range(3)]
        for i, (sz, st, _t) in enumerate(CORNERS):
            grid[SIZES.index(sz)][STYLES.index(st)] = round(100 * float(w[i]), 1)
            act[SIZES.index(sz)][STYLES.index(st)] = round(100 * float(w[i] - mkt_w[i]), 1)
        size = float(sum(w[i] * SIZE_SCORE[c[0]] for i, c in enumerate(CORNERS)))
        style = float(sum(w[i] * STYLE_SCORE[c[1]] for i, c in enumerate(CORNERS)))
        m_size = float(sum(mkt_w[i] * SIZE_SCORE[c[0]] for i, c in enumerate(CORNERS)))
        m_style = float(sum(mkt_w[i] * STYLE_SCORE[c[1]] for i, c in enumerate(CORNERS)))

        out[key] = dict(
            name=nm, grid=grid, active=act, r2=round(r2, 3), tracking_error=round(100 * te, 2),
            size_score=round(size, 3), style_score=round(style, 3),
            size_active=round(size - m_size, 3), style_active=round(style - m_style, 3),
            us_equity_weight=round(100 * tot, 1),
            vehicles={t: round(100 * w2 / tot, 1) for t, w2 in sorted(us.items(), key=lambda kv: -kv[1])},
            dominant=max(((SIZES.index(c[0]), STYLES.index(c[1]), w[i]) for i, c in enumerate(CORNERS)),
                         key=lambda x: x[2])[:2])
        d = out[key]['dominant']
        print(f'  {nm:10s} US eq {out[key]["us_equity_weight"]:5.1f}%  '
              f'{SIZES[d[0]]}/{STYLES[d[1]]:6s} {grid[d[0]][d[1]]:5.1f}%  '
              f'size {size:+.2f} (mkt {m_size:+.2f})  style {style:+.2f} (mkt {m_style:+.2f})  '
              f'R2 {r2:.3f}')

    # ---- what each box PAID over the live window -------------------------------------------------
    # The box says where the equity sleeve sits. On its own that is positioning. Priced over the live
    # NAV window it becomes attribution: each corner's return since inception, and the contribution of
    # holding that corner at that weight. Daily corner prices are already cached here.
    live_grid, live_meta = None, None
    navf = os.path.join(NAVD, 'fund_nav.json')
    if os.path.exists(navf):
        nv = json.load(open(navf))
        dpx = pd.read_csv(PX, index_col=0, parse_dates=True).sort_index()
        d0, d1 = pd.Timestamp(nv['dates'][0]), pd.Timestamp(nv['dates'][-1])
        seg = dpx.loc[(dpx.index >= d0) & (dpx.index <= d1)]
        cret = {f'{c[0]}/{c[1]}': float(seg[c[2]].iloc[-1] / seg[c[2]].iloc[0] - 1)
                for c in CORNERS if c[2] in seg.columns and seg[c[2]].notna().sum() > 2}
        mret = float(seg[MARKET].iloc[-1] / seg[MARKET].iloc[0] - 1)
        live_grid = [[round(100 * cret.get(f'{sz}/{st}', float('nan')), 3) for st in STYLES]
                     for sz in SIZES]
        live_meta = dict(start=str(d0.date()), end=str(d1.date()), market=round(100 * mret, 3))
        for key in out:
            g = out[key]['grid']
            contrib = [[round(out[key]['us_equity_weight'] / 100 * g[i][j] / 100
                              * 100 * cret.get(f'{SIZES[i]}/{STYLES[j]}', 0.0), 3)
                        for j in range(3)] for i in range(3)]
            out[key]['live_contrib'] = contrib
            out[key]['live_total'] = round(sum(sum(r) for r in contrib), 3)

    payload = dict(
        generated=str(pd.Timestamp.today().date()),
        live=dict(meta=live_meta, corner_returns=live_grid) if live_grid else None,
        window=f'{panel.index.min()} — {panel.index.max()}',
        n_months=len(panel),
        sizes=SIZES, styles=STYLES,
        corners={f'{c[0]}/{c[1]}': c[2] for c in CORNERS},
        market=dict(ticker=MARKET, name='Total US market (S&P Total Market)',
                    grid=[[round(100 * float(mkt_w[[i for i, c in enumerate(CORNERS)
                                                   if c[0] == sz and c[1] == st][0]]), 1)
                           for st in STYLES] for sz in SIZES],
                    r2=round(mkt_r2, 3)),
        method=('Returns-based style analysis (Sharpe 1992): non-negative corner weights summing to '
                'one, fitted on monthly returns of each portfolio’s US equity sleeve.'),
        limitation=('Descriptive only — it sets no target, band or limit. The nine corners share a '
                    'common start of 2001-08, so this window is shorter than the 1997-2026 backtest. '
                    'Style is inferred from returns, not from looking through to holdings; for index '
                    'vehicles that is a close approximation. PC-22, the style/sector tilt layer the '
                    'methodology formalises, remains unbuilt — showing the box is what makes that '
                    'visible.'),
        funds=out)
    f = os.path.join(OUT, 'style_box.json')
    json.dump(payload, open(f, 'w'), indent=1)
    print(f'wrote {f}')


if __name__ == '__main__':
    main()
