#!/usr/bin/env python3
"""
pit_backtest.py — walk-forward books, re-solved on information available at each rebalance date.

WHY THIS EXISTS
The 1997-2026 series the dashboard calls "Growth of $1" applies TODAY'S weights to all of history.
That is a legitimate object — it shows what this book would have done — but it is not a track record
and it is not a walk-forward. It cannot tell you whether the *construction process* would have chosen
these weights at the time. This builds the series that can.

METHOD
At each annual rebalance date t (30 June), the book is re-solved with the same optimiser, the same
bands and the same objective, but with the covariance estimated only on sleeve returns available up
to t. Those weights are then held for the following twelve months, net of the same dealing cost and
fee as everywhere else. Nothing after t touches the weights held from t.

THE LIMITATION, STATED PLAINLY
The expected-return vector is NOT point-in-time. `fs3_core.model()` builds its CMA from
`mafv4_core.load_data()`, which is a CURRENT snapshot of yields and valuations — the platform holds no
historical CMA vintages, so there is nothing to reconstruct a 2008 view from. This series therefore
re-estimates RISK point-in-time and holds the RETURN view fixed at today's.

That is a real look-ahead channel and it is not hidden: it is carried in the payload as
`basis.limitation`, printed by this script, and rendered on the page next to the chart. What the
series does isolate is how much of the book depends on which window the covariance was measured over
— which is the question the static-weight series cannot answer at all.

Output: Research/Portfolio_Construction/validation/fund_suite_v6/pit_backtest.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import fs3_core as V           # noqa: E402
import fs4_core as W4          # noqa: E402
import fs6_core as W6          # noqa: E402
import fund_registry as FR     # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'Research/Portfolio_Construction/validation/fund_suite_v6')
MIN_MONTHS = 60          # no solve until five years of sleeve history exists
REBAL_MONTH = 6          # 30 June
COST = 0.0010            # 10bp per side, as everywhere else on the platform
FEE_YR = 0.0015          # 15bp annual


def _specs():
    W6.FUNDS6.setdefault('alpha', W6.ALPHA_BOOK)
    out = {}
    for key in FR.ORDER:
        nm = FR.FUNDS[key]['name']
        spec = W6.FUNDS6.get(nm)
        if spec is None and key == 'alpha':
            spec = W6.ALPHA_BOOK
        if spec is None and key == 'daa':
            spec = W6.FUNDS6.get('SAA')      # the DAA runs the SAA book
        if spec is not None:
            out[key] = spec
    return out


def walk_forward(key, spec, panel, mu, M):
    """Re-solve at each June with an expanding covariance window; hold for twelve months.

    Only the sleeves the fund can actually hold decide how much history is usable. A fund bounded to
    zero in INFRA must not lose a decade of history because INFRA's series starts late — the earlier
    version dropped any month with a NaN anywhere in the panel, which is why Endowment produced no
    walk-forward at all and SAA could not solve before 2017.
    """
    bands = spec['bands']['sleeve']
    holdable = [s for s in panel.columns if bands.get(s, (0.0, 0.0))[1] > 0]
    idx = panel.index
    dates = [d for d in idx if d.month == REBAL_MONTH]
    rows, w_prev, seg_returns, held = [], None, [], []
    infeasible = 0
    for t in dates:
        win = panel.loc[:t]
        ok = win[holdable].notna().all(axis=1)
        hist = win.loc[ok].fillna(0.0)          # unheld sleeves are bounded to zero; 0 is inert
        if len(hist) < MIN_MONTHS:
            continue
        # Use the platform's own solver, not a bare solve_cdar: fs4_core.solve_fund searches for the
        # tightest feasible CDaR budget at or above the declared one and then applies the volatility
        # cap. That loosening step is how the live books were built (Endowment's declared 16% CDaR was
        # loosened to 20%), so a walk-forward that skipped it would be testing a different process.
        w, cd, dcap, _tried = W4.solve_fund(hist, mu, spec['bands'], M)
        loosened = bool(cd > spec['bands']['cdar'] + 1e-9)
        if w is None:
            infeasible += 1
            if w_prev is None:
                continue
            w, loosened = w_prev, None
        w = w.clip(lower=0)
        w = w / w.sum()
        turn = float(np.abs(w - w_prev).sum()) if w_prev is not None else float(w.sum())
        fwd = panel.loc[(idx > t) & (idx <= t + 12)].fillna(0.0)
        if not len(fwd):
            break
        seg = (fwd[w.index].fillna(0) * w.values).sum(axis=1)
        seg.iloc[0] -= turn * COST                       # dealing cost on the rebalance
        seg = seg - FEE_YR / 12                          # fee accrues monthly
        seg_returns.append(seg)
        rows.append(dict(date=str(t), turnover=round(100 * turn, 1),
                         n_months_used=int(len(hist)), cdar_used=round(100 * cd, 1),
                         dd_used=round(100 * dcap, 1), loosened=loosened,
                         weights={s: round(float(v), 4) for s, v in w.items() if v > 0.0005}))
        held.append(w)
        w_prev = w
    if not seg_returns:
        return None
    r = pd.concat(seg_returns).sort_index()
    r = r[~r.index.duplicated(keep='first')]
    W = pd.DataFrame([h for h in held], index=[pd.Period(x['date'], freq='M') for x in rows])
    drift = W.diff().abs().sum(axis=1).dropna()
    return dict(returns=r, rebalances=rows, infeasible=infeasible, holdable=len(holdable),
                avg_turnover=round(float(np.mean([x['turnover'] for x in rows[1:]] or [0])), 1),
                weight_drift=round(100 * float(drift.mean()) if len(drift) else 0.0, 1))


def main():
    L = W6.load()
    M = W6.model(L)
    mu = M['mu'] if hasattr(M['mu'], 'index') else pd.Series(M['mu_bl'], index=W6.S6)
    panel = L['R'].dropna(how='all')
    print(f'sleeve panel {panel.index.min()} — {panel.index.max()}  ({len(panel)} months)')

    static = json.load(open(os.path.join(OUT, 'fund_suite_v6.json')))
    out = {}
    for key, spec in _specs().items():
        nm = FR.FUNDS[key]['name']
        res = walk_forward(key, spec, panel, mu, M)
        if res is None:
            print(f'  {nm:10s} no walk-forward (insufficient history)')
            continue
        r = res['returns']
        nav = (1 + r).cumprod()
        dd = (nav / nav.cummax() - 1)
        yrs = len(r) / 12
        cagr = 100 * (float(nav.iloc[-1]) ** (1 / yrs) - 1)
        vol = 100 * float(r.std() * np.sqrt(12))
        out[key] = dict(
            name=nm, start=str(r.index.min()), end=str(r.index.max()),
            n_rebalances=len(res['rebalances']), n_infeasible=res['infeasible'],
            n_loosened=sum(1 for x in res['rebalances'] if x['loosened']),
            n_holdable_sleeves=res['holdable'], avg_turnover_pct=res['avg_turnover'],
            avg_weight_change_pp=res['weight_drift'],
            cagr=round(cagr, 2), vol=round(vol, 1), maxdd=round(100 * float(dd.min()), 1),
            sharpe=round(cagr / vol, 2) if vol else None,
            series=[dict(date=str(d.to_timestamp(how='end').date()), v=round(float(v), 4))
                    for d, v in nav.items()],
            returns=[dict(date=str(d.to_timestamp(how='end').date()), v=round(float(v), 6))
                     for d, v in r.items()],
            rebalances=res['rebalances'])
        st = static['info'][nm]
        print(f'  {nm:10s} {out[key]["start"]}..{out[key]["end"]}  '
              f'CAGR {cagr:5.2f}%  vol {vol:4.1f}%  maxDD {100 * float(dd.min()):6.1f}%  '
              f'{len(res["rebalances"])} rebalances  turnover {res["avg_turnover"]:.0f}%/yr'
              + (f'  [{res["infeasible"]} infeasible]' if res['infeasible'] else '')
              + (f'  [{out[key]["n_loosened"]} loosened]' if out[key]['n_loosened'] else ''))

    payload = dict(
        generated=str(pd.Timestamp.today().date()),
        method=dict(
            rebalance='annual, 30 June',
            covariance='expanding window, point-in-time — only returns available at the rebalance date',
            minimum_history_months=MIN_MONTHS,
            expected_returns='NOT point-in-time — held at the current CMA snapshot (see limitation)',
            costs=f'{COST * 1e4:.0f}bp per side on rebalance turnover, {FEE_YR * 1e4:.0f}bp annual fee',
            optimiser='fs4_core.solve_fund — the same objective, bands, loosening search and '
                      'volatility cap as the live books'),
        limitation=(
            'Risk is re-estimated point-in-time; the expected-return view is not. fs3_core.model() '
            'builds its CMA from a current snapshot of yields and valuations and the platform holds '
            'no historical CMA vintages, so a 2008 return view cannot be reconstructed. This series '
            'therefore answers "how much does the book depend on the covariance window?" and does '
            'NOT answer "would we have picked these weights in 2008?". It is not a track record.'),
        funds=out)
    f = os.path.join(OUT, 'pit_backtest.json')
    json.dump(payload, open(f, 'w'), indent=1)
    print(f'\nwrote {f} ({os.path.getsize(f) // 1024} KB)')
    print('LIMITATION:', payload['limitation'][:150], '...')


if __name__ == '__main__':
    main()
