#!/usr/bin/env python3
"""
fund_nav.py — daily NAV for the five Summer funds, from actual market prices.

Inception 15 July 2026 at NAV 100.00. The books are the v6 books; the strategic funds hold their launch
weights and rebalance on a 1pp band, the DAA and Alpha re-read their engines at each month end. Prices
are dividend-adjusted daily closes, so the NAV is a total-return series net of a 15bp annual fee and
10bp per side of trading.

Re-runnable: it re-pulls prices, rebuilds the books, recomputes the whole NAV series and rewrites the
dashboard feed. Nothing is appended in place, so a bad print cannot silently persist.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import fs3_core as V  # noqa: E402
import fs4_core as W4  # noqa: E402
import fs5_core as W5  # noqa: E402
import fs5_signals as SG  # noqa: E402
import fs6_core as W6  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(ROOT, 'Research/Portfolio_Construction/dashboard/data')
OUT = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_nav')
os.makedirs(OUT, exist_ok=True)
INCEPTION = pd.Timestamp('2026-07-15')
NAV0 = 100.0
FEE_YR = 0.0015
COST = 0.0010
BAND = 0.01

# how each sleeve is actually held, and across how many vehicles (the platform caps a single fund at 20%)
IMPL = {'US_EQ': ['VOO', 'IVV', 'ITOT', 'SCHX'], 'DM_EQ': ['DBEF'], 'EM_EQ': ['VWO'],
        'UST': ['VGIT', 'SCHR', 'IEF'], 'USTL': ['VGLT', 'TLT'], 'TIPS': ['SCHP', 'TIP'],
        'IG': ['VCIT', 'VCLT'], 'HY': ['USHY'], 'REIT': ['VNQ'], 'INFRA': ['GII', 'IGF'],
        'CMDTY': ['PDBC', 'DBC'], 'GOLD': ['GLDM', 'IAU'], 'MF': ['DBMF', 'KMLM'],
        'CHF': ['FXF'], 'Cash': ['SGOV']}
BENCH = {'S&P 500': 'SPY', 'MSCI ACWI': 'ACWI', 'Bloomberg US Aggregate': 'AGG'}
CAP = 0.20


TICKER_SLEEVE = {t: s for s, ts in IMPL.items() for t in ts}


def to_etf(w):
    """Spread a sleeve across as few vehicles as the 20% single-fund cap allows."""
    h = {}
    for s, v in w.items():
        if v < 0.0005:
            continue
        tick = IMPL[s]
        n = min(len(tick), max(1, int(np.ceil(v / CAP))))
        for t in tick[:n]:
            h[t] = h.get(t, 0.0) + v / n
    return pd.Series(h)


def prices(tickers, start='2026-06-25'):
    """Daily dividend-adjusted closes. Every requested vehicle must come back with a usable history —
    a silently missing ticker would leave the fund under-invested and the NAV quietly wrong."""
    import yfinance as yf
    want = sorted(set(tickers))
    px = yf.download(want, start=start, auto_adjust=True, progress=False)['Close']
    px = px.dropna(how='all').ffill()
    missing = [t for t in want if t not in px.columns or px[t].notna().sum() < 20]
    if missing:
        raise SystemExit(f'price feed incomplete for {missing} — refusing to compute a NAV on partial data')
    return px[want]


def build_books():
    """The five books, plus the monthly target weights for the two actively run funds."""
    L = W6.load()
    M = W6.model(L)
    R = L['R']
    W4.SWEEP[:] = W6.SWEEP6
    W6.FUNDS6['Alpha'] = W6.ALPHA_BOOK
    X = SG.macro()
    books, monthly = {}, {}
    for f, spec in W6.FUNDS6.items():
        w, cd, dcap, _ = W4.solve_fund(M['panel'], M['mu_bl'], spec['bands'], M)
        w, _ = V.round_repair(w, spec['bands'])
        books[f] = w
    for nm, base, mand in [('DAA', 'SAA', dict(room=W6.DAA_SLEEVE_ROOM)),
                           ('Alpha', 'Alpha', W6.ALPHA_MANDATE)]:
        saved = {k: W5.MANDATE.get(k) for k in mand}
        W5.MANDATE.update(mand)
        E = W5.engines(R, books[base], X)
        T, _ = W5.daa_targets(books[base], E, W6.FUNDS6[base]['bands'])
        monthly[nm] = T
        books[nm] = T.loc[max(T.index)]
        for k, v in saved.items():
            if v is not None:
                W5.MANDATE[k] = v
    return books, monthly, R


def run():
    books, monthly, R = build_books()
    funds = ['Certain', 'Endowment', 'SAA', 'DAA', 'Alpha']
    tick = sorted({t for f in funds for t in to_etf(books[f]).index} | set(BENCH.values()))
    px = prices(tick)
    px = px.loc[px.index >= INCEPTION]
    ret = px.pct_change(fill_method=None).fillna(0.0)
    days = ret.index
    out, holdings, trades, bridge, daily_w = {}, {}, {}, {}, {}
    for f in funds:
        # the weight the fund targets on each day
        if f in monthly:
            tgt_m = monthly[f]
            tgt = {d: to_etf(tgt_m.loc[min(tgt_m.index, key=lambda p: abs((p.to_timestamp() - d).days))])
                   for d in days}
        else:
            base = to_etf(books[f])
            tgt = {d: base for d in days}
        w0 = tgt[days[0]]
        if abs(w0.sum() - 1) > 0.005:
            raise SystemExit(f'{f}: launch weights sum to {w0.sum():.4f}, not 1')
        held = w0.reindex(px.columns).fillna(0.0)
        nav, rows, tr = [], [], []
        # What actually moved the NAV. Each day's contribution is scaled by the NAV level it was
        # earned on, so the pieces reconcile to the NAV exactly rather than approximately:
        #   sum(contribution) - dealing - fee == NAV_end - NAV0
        contrib = pd.Series(0.0, index=px.columns)
        cost_pts = fee_pts = 0.0
        for i, d in enumerate(days):
            t = tgt[d].reindex(px.columns).fillna(0.0)
            if abs(t.sum() - 1) > 0.005:
                raise SystemExit(f'{f} on {d.date()}: target weights sum to {t.sum():.4f}, not 1')
            turn = 0.0
            if i == 0 or (t - held).abs().max() > BAND:
                turn = float((t - held).abs().sum())
                held = t.copy()
            r = float((held * ret.loc[d]).sum()) - turn * COST - FEE_YR / 252
            prev = nav[-1] if nav else NAV0
            contrib += prev * held * ret.loc[d]
            cost_pts += prev * turn * COST
            fee_pts += prev * FEE_YR / 252
            nav.append(prev * (1 + r))
            rows.append(held.copy())
            if turn > 1e-9:
                tr.append(dict(date=str(d.date()), turnover=round(100 * turn, 2)))
            held = held * (1 + ret.loc[d])
            held = held / held.sum()
        s = pd.Series(nav, index=days)
        out[f] = s
        holdings[f] = {k: float(v) for k, v in rows[-1].items() if v > 0.0005}
        trades[f] = tr
        # The weight actually held on each day. Attribution that uses today's weights for a window
        # in which the book was rebalanced attributes the return to a book that was not held.
        W = pd.DataFrame(rows, index=days)
        daily_w[f] = {c: [round(float(x), 6) for x in W[c]] for c in W.columns if W[c].abs().max() > 5e-4}
        bridge[f] = dict(holdings={k: float(v) for k, v in contrib.items() if abs(v) > 1e-9},
                         dealing=-float(cost_pts), fee=-float(fee_pts),
                         total=float(s.iloc[-1] - NAV0))
        chk = sum(bridge[f]['holdings'].values()) + bridge[f]['dealing'] + bridge[f]['fee']
        if abs(chk - bridge[f]['total']) > 1e-6:
            raise SystemExit(f'{f}: NAV bridge does not reconcile ({chk:.8f} vs '
                             f'{bridge[f]["total"]:.8f}) — do not publish an attribution that does '
                             f'not add up to the NAV')
    for bn, t in BENCH.items():
        out[bn] = NAV0 * (1 + ret[t]).cumprod()
    nav = pd.DataFrame(out)
    nav.index = [str(d.date()) for d in nav.index]
    return nav, holdings, trades, books, bridge, daily_w


if __name__ == '__main__':
    nav, holdings, trades, books, bridge, daily_w = run()
    print(f'  inception {INCEPTION.date()} · {len(nav)} trading days through {nav.index[-1]}')
    for c in nav.columns:
        s = nav[c]
        r = s.pct_change().dropna()
        print(f'  {c:24s} NAV {s.iloc[-1]:7.2f}  since inception {s.iloc[-1] / NAV0 - 1:+7.2%}  '
              f'vol {100 * r.std() * np.sqrt(252):5.1f}%  best day {100 * r.max():+.2f}%  worst {100 * r.min():+.2f}%')
    nav.to_csv(os.path.join(OUT, 'fund_nav.csv'))
    json.dump(dict(inception=str(INCEPTION.date()), nav0=NAV0, dates=list(nav.index),
                   series={c: [round(float(x), 4) for x in nav[c]] for c in nav.columns},
                   holdings=holdings, trades=trades, bridge=bridge, daily_weights=daily_w,
                   books={f: {k: float(v) for k, v in books[f].items() if v > 0.0005} for f in books},
                   ticker_sleeve=TICKER_SLEEVE),
              open(os.path.join(OUT, 'fund_nav.json'), 'w'), indent=1)
    print(f'  wrote {OUT}')
