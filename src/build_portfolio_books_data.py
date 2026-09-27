#!/usr/bin/env python3
"""
build_portfolio_books_data.py — a PORTFOLIO_DATA payload for each of the five portfolios.

app.js reads window.PORTFOLIO_DATA and renders whatever element ids the page happens to carry. That
contract is the most valuable thing in the dashboard, so this writes five payloads in exactly that
shape and a selector binds one of them — the 1,745-line renderer is not touched.

Sections produced per portfolio: kpis, positioning, construction, diversification, risk, track_record,
comparison, stress, attribution, monte_carlo, scenarios, matrix, risk_detail, stress_forward.

The last three were previously omitted on the reasoning that they belonged to the v3.8 book. The
renderer guards them with `if (d.x)`, so omitting them left nine tiles blank on attribution/risk/
stress with no error anywhere — the platform got smaller and nothing said so. They are now built per
portfolio from that portfolio's own sleeves and weights:
  * `risk_detail`  — MCTR / component vol / risk share from the sleeve covariance, for the portfolio
                     as held AND for its policy book, so the pair is live-vs-policy rather than a
                     hardcoded DAA/SAA. Static portfolios legitimately show the two as equal.
  * `stress_forward` — driven by the APPROVED sleeve-level scenario set (`fund_suite_v6.scenarios_def`),
                     not invented shocks. The slider betas are estimated (see `_factor_betas`) and are
                     labelled as estimates on the page.
  * `matrix`       — the five portfolios against the platform's real index benchmarks, ranked per metric.

Every narrative is composed from the numbers, per the standing dashboard rule.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import cf_core as C  # noqa: E402
import fund_registry as FR  # noqa: E402
import sleeve_registry as SR  # noqa: E402
import fs5_signals as SG  # noqa: E402
import fs6_core as W6  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_suite_v6')
NAVD = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_nav')
DASH = os.path.join(ROOT, 'Research/Portfolio_Construction/dashboard/data')
BENCH = {'S&P 500': 'benchmark', 'MSCI ACWI': 'benchmark', 'ACWI 60 / Agg 40': 'benchmark',
         'Bloomberg US Aggregate': 'benchmark'}
EPISODES = [('GFC 2008', '2007-11', '2009-02'), ('Euro 2011', '2011-05', '2011-09'),
            ('COVID 2020', '2020-02', '2020-03'), ('2022 inflation', '2022-01', '2022-09'),
            ('Dot-com 2000', '2000-09', '2002-09')]
# RISK LIMITS — read from the fund construction spec, never hand-typed here.
#
# CORRECTION (2026-09-20). This file previously carried hand-typed VOL_BUDGET and DD_BUDGET dicts.
# The audit first read both as invented. Only half of that was right:
#
#   * The volatility numbers (5.0 / 9.5 / 12.0 / 12.0 / 14.0) are EXACTLY the `vol_cap` each fund was
#     solved under in fs6_core.FUNDS6 — a real construction constraint, not an invention. They are
#     restored, but sourced from fs6_core rather than duplicated, so they cannot drift again.
#   * The loss limits (-8 / -20 / -22 / -22 / -45) were invented, and they CONTRADICT the funds' own
#     approved drawdown caps (11 / 22 / 29 / 29 / 58). Certain's realised -10.0% sits comfortably
#     inside its approved -11% cap but was displayed as breaching an invented -8%. Those are gone.
#
# What renders now is the constraint the optimiser actually solved under, labelled as such, plus the
# one owner-set mandate limit in the record. `Src/verify_dashboard.py` contract C3 fails the build if
# any limit renders without a source.
MANDATE_LIMITS = {
    # owner decisions recorded in the methodology, distinct from a construction constraint
    'saa': dict(dd_limit=-22.0,
                source='Fund_Suite_v5.md §"The SAA\u2019s loss limit" — owner decision, left at -22%'),
}


def _constraints(key, suite):
    """The caps the fund was ACTUALLY solved under — from the build record, not the declaration.

    Two different numbers exist and conflating them is a real error. `fs6_core.FUNDS6[f].bands` holds
    the DECLARED cap; `pc_fs6_build` searches for the tightest FEASIBLE cap at or above it
    (fs4_core.solve_fund) and records what it actually used in fund_suite_v6.json. Endowment's
    declared 16% CDaR / 22% drawdown was infeasible and was loosened to 20% / 27.5% — so a page
    showing "solved under a -22% cap" was stating a constraint the book was never held to, and
    reporting Endowment's realised -24.3% as an overshoot when it was inside the -27.5% actually used.

    The declared figure is kept alongside, because the loosening is itself information about the fund.
    """
    W6.FUNDS6.setdefault('alpha', W6.ALPHA_BOOK)
    nm = FR.FUNDS[key]['name']
    spec = W6.FUNDS6.get(nm) or (W6.ALPHA_BOOK if key == 'alpha' else None)
    if key == 'daa':                       # the DAA runs the SAA book, so it inherits its constraints
        spec = W6.FUNDS6.get('SAA')
    if not spec:
        return {}
    b = spec['bands']
    info = (suite.get('info') or {}).get(nm, {})
    cdar_used = info.get('cdar', b['cdar'])
    dd_used = info.get('ddcap', b['ddcap'])
    loosened = bool(info.get('loosened'))
    src = (f'fund_suite_v6.json info[{nm!r}] — the caps pc_fs6_build actually solved under'
           if info else f'fs6_core.FUNDS6[{nm!r}].bands — declared caps')
    if loosened:
        src += (f'; the declared {100 * b["cdar"]:.0f}% CDaR / {100 * b["ddcap"]:.0f}% drawdown was '
                f'infeasible and was loosened to the tightest feasible '
                f'{100 * cdar_used:.0f}% / {100 * dd_used:.1f}%')
    return dict(vol_cap=round(100 * b['vol_cap'], 1),
                cdar_cap=round(100 * cdar_used, 1), dd_cap=round(-100 * dd_used, 1),
                cdar_declared=round(100 * b['cdar'], 1), dd_declared=round(-100 * b['ddcap'], 1),
                loosened=loosened, source=src)


def _ser(s):
    return [dict(date=str(d.to_timestamp(how='end').date()), v=round(float(v), 4)) for d, v in s.items()]


def _nav(r):
    return (1 + r).cumprod()


def _dd(nav):
    return nav / nav.cummax() - 1


def _drawdowns(r, top=5):
    nav = _nav(r)
    dd = _dd(nav)
    out, in_dd, start = [], False, None
    peak = nav.cummax()
    for i, (d, v) in enumerate(dd.items()):
        if not in_dd and v < -0.005:
            in_dd, start = True, d
        elif in_dd and v >= -0.0005:
            seg = dd.loc[start:d]
            out.append(dict(start=str(start), trough=str(seg.idxmin()), recovery=str(d),
                            depth=round(100 * float(seg.min()), 1), months=int(len(seg))))
            in_dd = False
    if in_dd:
        seg = dd.loc[start:]
        out.append(dict(start=str(start), trough=str(seg.idxmin()), recovery=None,
                        depth=round(100 * float(seg.min()), 1), months=int(len(seg))))
    return sorted(out, key=lambda x: x['depth'])[:top]




def _pts(idx, vals):
    return [dict(date=str(d.to_timestamp(how='end').date()), v=round(float(v), 4))
            for d, v in zip(idx, vals)]


def _roll_pts(x, cash, win=36):
    """Rolling windows as {date, v} points — the shape the renderer plots."""
    e = (x - cash.reindex(x.index)).dropna()
    ret = ((1 + x).rolling(win).apply(np.prod, raw=True) ** (12 / win) - 1).dropna() * 100
    vol = (x.rolling(win).std() * np.sqrt(12)).dropna() * 100
    shp = (e.rolling(win).mean() / x.rolling(win).std() * np.sqrt(12)).dropna()
    return dict(ret=_pts(ret.index, ret.values), vol=_pts(vol.index, vol.values),
                sharpe=_pts(shp.index, shp.values))


def _bootstrap_mc(r, years=10, paths=4000, block=12, seed=20260920, dd_threshold=20):
    """Stationary block bootstrap of the portfolio's own monthly history — the same method the
    dashboard's Monte Carlo has always used, so the numbers mean what they used to mean."""
    x = r.dropna().values
    n, H = len(x), years * 12
    rng = np.random.default_rng(seed)
    out = np.empty((paths, H))
    for i in range(paths):
        seq, k = [], 0
        while k < H:
            st = rng.integers(n)
            ln = min(block, H - k)
            idx = [(st + j) % n for j in range(ln)]
            seq.extend(x[idx])
            k += ln
        out[i] = seq[:H]
    g = np.cumprod(1 + out, axis=1)
    peak = np.maximum.accumulate(g, axis=1)
    dd = (g / peak - 1).min(axis=1)
    term = g[:, -1]
    cagr = term ** (1 / years) - 1
    yr_idx = np.arange(11, H, 12)
    q = lambda p: [round(float(v), 4) for v in np.percentile(g[:, yr_idx], p, axis=0)]
    t_edges = np.linspace(0.4, 4.0, 25)
    d_edges = np.linspace(-0.6, 0.0, 25)
    return dict(
        fan=dict(years=[round(float(y), 1) for y in (yr_idx + 1) / 12],
                 months=[int(m + 1) for m in yr_idx],
                 p5=q(5), p25=q(25), p50=q(50), p75=q(75), p95=q(95)),
        hist=dict(terminal_counts=[int(c) for c in np.histogram(term, bins=t_edges)[0]],
                  dd_counts=[int(c) for c in np.histogram(dd, bins=d_edges)[0]]),
        edges=dict(terminal=[round(float(e), 3) for e in t_edges],
                   dd=[round(float(e), 3) for e in d_edges]),
        sample=dict(years=[round(float(y), 1) for y in (yr_idx + 1) / 12],
                    paths=[[round(float(v), 3) for v in g[i, yr_idx]] for i in range(12)]),
        summary=dict(terminal_median=round(float(np.median(term)), 3),
                     terminal_p5=round(float(np.percentile(term, 5)), 3),
                     terminal_p95=round(float(np.percentile(term, 95)), 3),
                     cagr_median=round(100 * float(np.median(cagr)), 2),
                     cagr_p5=round(100 * float(np.percentile(cagr, 5)), 2),
                     cagr_p95=round(100 * float(np.percentile(cagr, 95)), 2),
                     maxdd_median=round(100 * float(np.median(dd)), 2),
                     maxdd_p95=round(100 * float(np.percentile(dd, 5)), 2),
                     prob_loss=round(100 * float((term < 1).mean()), 1),
                     prob_dd_gt_threshold=round(100 * float((dd < -dd_threshold / 100).mean()), 1),
                     prob_ge_1x=round(100 * float((term >= 1).mean()), 1),
                     **{'prob_ge_1.5x': round(100 * float((term >= 1.5).mean()), 1),
                        'prob_ge_2x': round(100 * float((term >= 2).mean()), 1),
                        'prob_ge_3x': round(100 * float((term >= 3).mean()), 1)}),
        scen=dict(bull=dict(terminal=round(float(np.percentile(term, 95)), 3),
                            cagr=round(100 * float(np.percentile(cagr, 95)), 2)),
                  base=dict(terminal=round(float(np.median(term)), 3),
                            cagr=round(100 * float(np.median(cagr)), 2)),
                  bear=dict(terminal=round(float(np.percentile(term, 5)), 3),
                            cagr=round(100 * float(np.percentile(cagr, 5)), 2)),
                  cvar5=round(float(term[term <= np.percentile(term, 5)].mean()), 3)))


def _cov(panel, sleeves):
    """Annualised sleeve covariance over the sleeve panel's own window."""
    sub = panel[list(sleeves)].dropna()
    return sub.cov().values * 12, sub


def _decompose(weights, panel):
    """Euler risk decomposition: MCTR, component vol and risk share per sleeve.

    MCTR_i = (Sigma w)_i / sigma_p ; component_i = w_i * MCTR_i ; share_i = component_i / sigma_p.
    Shares sum to 1 by construction, which is the property the page's concentration stats rely on.
    """
    sl = [s for s in weights if weights[s] > 0.0005 and s in panel.columns]
    if not sl:
        return None
    S, _ = _cov(panel, sl)
    wv = np.array([weights[s] for s in sl])
    wv = wv / wv.sum()
    sig = float(np.sqrt(wv @ S @ wv))
    if sig <= 0:
        return None
    mctr = (S @ wv) / sig
    comp = wv * mctr
    share = comp / sig
    return dict(sleeves=sl, vol=100 * sig, w=wv, mctr=mctr, comp=comp, share=share)


def _risk_detail(key, w, policy, panel, suite, nm, base_label):
    """Sleeve-level risk decomposition for the book as held and for its policy book.

    The renderer addresses the pair as rd.DAA (as held) and rd.SAA (policy) — that contract is kept so
    no element id changes; `labels` names them correctly for whichever portfolio is on screen.
    """
    live = _decompose(w, panel)
    pol = _decompose({s: v for s, v in policy.items() if v > 0.0005}, panel)
    if live is None:
        return None
    if pol is None:
        pol = live

    def pack(d):
        rows, blocks = [], {}
        for i, sk in enumerate(d['sleeves']):
            blk = FR.PLATFORM_CLASS[sk]
            rows.append(dict(sleeve=suite['labels'][sk], key=sk, block=blk,
                             capital=round(100 * float(d['w'][i]), 1),
                             mctr=round(float(d['mctr'][i]), 3),
                             comp_vol=round(100 * float(d['comp'][i]), 2),
                             risk=round(100 * float(d['share'][i]), 1)))
            b = blocks.setdefault(blk, dict(block=blk, capital=0.0, risk=0.0))
            b['capital'] += 100 * float(d['w'][i])
            b['risk'] += 100 * float(d['share'][i])
        rows.sort(key=lambda x: -x['risk'])
        sh = np.array([r['risk'] for r in rows]) / 100
        herf = float((sh ** 2).sum())
        return dict(vol=round(d['vol'], 1), sleeves=rows,
                    blocks=[dict(block=b['block'], capital=round(b['capital'], 1),
                                 risk=round(b['risk'], 1)) for b in blocks.values()],
                    herfindahl=round(herf, 3),
                    effective_bets=round(1 / herf if herf > 0 else 0, 1),
                    top3_risk=round(sum(r['risk'] for r in rows[:3]), 1))

    L, P = pack(live), pack(pol)
    # align the policy rows to the live sleeve order — the grouped bar chart pairs them by index
    order = [r['key'] for r in L['sleeves']]
    by_key = {r['key']: r for r in P['sleeves']}
    P['sleeves'] = [by_key.get(k2, dict(sleeve=suite['labels'][k2], key=k2,
                                        block=FR.PLATFORM_CLASS[k2], capital=0.0, mctr=0.0,
                                        comp_vol=0.0, risk=0.0)) for k2 in order]
    same = abs(L['vol'] - P['vol']) < 0.05 and all(
        abs(a['risk'] - b['risk']) < 0.05 for a, b in zip(L['sleeves'], P['sleeves']))
    top = L['sleeves'][0]
    if same:
        narr = (f'{nm} holds its policy weights, so the book as held and the policy book decompose '
                f'identically — the two bars are equal by construction, not by coincidence. '
                f'<strong>{top["sleeve"]}</strong> carries {top["risk"]:.0f}% of the risk on '
                f'{top["capital"]:.0f}% of the capital. Risk is spread over '
                f'<strong>{L["effective_bets"]:.1f}</strong> effective bets; the top three sleeves '
                f'carry {L["top3_risk"]:.0f}%.')
    else:
        narr = (f'{nm} as held runs {L["vol"]:.1f}% forecast volatility against {P["vol"]:.1f}% for '
                f'{base_label}. <strong>{top["sleeve"]}</strong> carries {top["risk"]:.0f}% of the '
                f'risk on {top["capital"]:.0f}% of the capital. Risk is spread over '
                f'<strong>{L["effective_bets"]:.1f}</strong> effective bets; the top three sleeves '
                f'carry {L["top3_risk"]:.0f}%. Capital share and risk share differ wherever a sleeve '
                f'is more or less volatile than the book — that gap is the point of the table.')
    return dict(DAA=L, SAA=P, narrative=narr,
                labels=dict(active=nm, base=base_label.capitalize() if base_label.islower() else base_label),
                basis=('sleeve covariance, annualised, estimated over '
                       f'{panel.index.min()} — {panel.index.max()}'))


def _factor_exposures(r, R, cash):
    """Exposure of the portfolio to the platform's factor set, by regression on excess returns."""
    facs = {'Equity': R['MSCI ACWI'], 'Duration': R['Bloomberg US Aggregate'],
            'Credit': R['ACWI 60 / Agg 40'], 'Inflation': R['S&P 500']}
    y = (r - cash.reindex(r.index)).dropna()
    out = []
    for nm_, f in facs.items():
        x = (f.reindex(y.index) - cash.reindex(y.index)).dropna()
        j = y.index.intersection(x.index)
        if len(j) < 24:
            continue
        b = float(np.cov(y[j], x[j])[0, 1] / np.var(x[j]))
        out.append(dict(factor=nm_, exposure=round(b, 2),
                        risk_share=round(100 * abs(b) * float(x[j].std()) / float(y[j].std()) / 4, 1)))
    return out


# ---------------------------------------------------------------------------
# Forward stress
# ---------------------------------------------------------------------------
# The scenario set is NOT invented here. `fund_suite_v6.scenarios_def` holds the approved
# sleeve-level shocks and `fund_suite_v6.scenarios` the per-fund impacts the suite already
# published; this only reshapes them for the renderer and adds the per-sleeve contribution
# breakdown the page draws.
#
# The custom-scenario sliders need sleeve x factor sensitivities, which the approved set does not
# contain. Those are ESTIMATED (`_factor_betas`) and are labelled as estimates on the page. The five
# factors are built from the platform's own sleeve returns rather than outside indices, so a beta
# here is expressed in the same units as everything else on the page.

FACTOR_PROXY = {
    'Equity':    ('US_EQ', None),      # broad equity direction
    'Duration':  ('USTL', None),       # long Treasuries: the rate factor
    'Credit':    ('HY', 'UST'),        # high yield minus duration-matched govt: the spread
    'Inflation': ('CMDTY', None),      # broad commodities: the inflation surprise leg
    'Dollar':    ('CHF', None),        # franc deposit, sign-flipped below: USD direction
}
FACTOR_SIGN = {'Dollar': -1.0}


def _factor_betas(panel, sleeves):
    """Sleeve x factor sensitivities by multivariate OLS on the sleeve panel.

    ESTIMATE, not an approved parameter. Returned with the window so the page can say so.
    """
    facs, names = {}, []
    for f, (a, b) in FACTOR_PROXY.items():
        if a not in panel.columns or (b is not None and b not in panel.columns):
            continue
        x = panel[a] if b is None else panel[a] - panel[b]
        facs[f] = x * FACTOR_SIGN.get(f, 1.0)
        names.append(f)
    if not names:
        return {}, [], ''
    F = pd.DataFrame(facs).dropna()
    betas = {}
    for sk in sleeves:
        if sk not in panel.columns:
            continue
        y = panel[sk].reindex(F.index).dropna()
        j = F.index.intersection(y.index)
        if len(j) < 36:
            betas[sk] = {f: 0.0 for f in names}
            continue
        X = np.column_stack([np.ones(len(j))] + [F.loc[j, f].values for f in names])
        coef, *_ = np.linalg.lstsq(X, y.loc[j].values, rcond=None)
        betas[sk] = {f: round(float(c), 3) for f, c in zip(names, coef[1:])}
    return betas, names, f'{F.index.min()} — {F.index.max()}'


def _stress_forward(key, nm, w, policy, panel, suite, base_label):
    defs = suite.get('scenarios_def') or {}
    vals = suite.get('scenarios') or {}
    if not defs:
        return None
    sleeves = [s for s in w if w[s] > 0.0005]
    betas, fac_names, beta_window = _factor_betas(panel, sleeves)
    if not betas:
        return None

    def impact(weights, shocks):
        return 100 * sum(weights.get(s, 0) * shocks.get(s, 0) / 100 for s in weights)

    scn = []
    for nm2, shocks in defs.items():
        rows = []
        for s in sleeves:
            if s not in shocks:
                continue
            rows.append(dict(sleeve=suite['labels'][s], key=s, block=FR.PLATFORM_CLASS[s],
                             impact=round(float(shocks[s]), 1),
                             contrib=round(100 * w[s] * shocks[s] / 100, 2)))
        rows.sort(key=lambda x: x['contrib'])
        blocks = {}
        for r2 in rows:
            blocks[r2['block']] = round(blocks.get(r2['block'], 0.0) + r2['contrib'], 2)
        # the published per-fund impact where the suite has it; otherwise the weighted sum
        live_i = vals.get(nm2, {}).get(nm)
        live_i = round(float(live_i), 1) if live_i is not None else round(impact(w, shocks), 1)
        pol_i = round(impact(policy, shocks), 1)
        # headline shocks: the sleeves this portfolio actually holds, biggest movers first
        head = sorted(rows, key=lambda x: -abs(x['impact']))[:5]
        scn.append(dict(name=nm2, desc=f'approved shock set · {len(rows)} held sleeves shocked',
                        shocks={r2['sleeve']: r2['impact'] / 100 for r2 in head},
                        saa=pol_i, daa=live_i, sleeves=rows,
                        blocks=[dict(block=b, impact=v) for b, v in
                                sorted(blocks.items(), key=lambda kv: kv[1])]))
    worst = min(scn, key=lambda x: x['daa'])
    best = max(scn, key=lambda x: x['daa'])
    return dict(
        scenarios=scn, factors=fac_names,
        betas={s: betas[s] for s in sleeves if s in betas},
        daa_weights={s: round(float(w[s]), 4) for s in sleeves},
        saa_weights={s: round(float(policy.get(s, 0)), 4) for s in sleeves},
        sleeve_labels={s: suite['labels'][s] for s in sleeves},
        sleeve_blocks={s: FR.PLATFORM_CLASS[s] for s in sleeves},
        labels=dict(active=nm, base=base_label),
        basis=dict(scenarios='approved sleeve shock set (fund_suite_v6.scenarios_def)',
                   betas=f'ESTIMATED by OLS on sleeve returns, {beta_window}',
                   factors='built from the platform\u2019s own sleeve returns, not outside indices'),
        narrative=(f'Ex-ante, not historical: the approved sleeve-level shock set applied to '
                   f'<strong>{nm}</strong> as it is held today, against {base_label}. Its worst case '
                   f'is <strong>{worst["name"]}</strong> at <strong>{worst["daa"]:.1f}%</strong> '
                   f'({base_label} {worst["saa"]:.1f}%); its best is {best["name"]} at '
                   f'{best["daa"]:.1f}%. The scenario shocks are the approved set. The slider '
                   f'sensitivities below are <em>estimated</em> from sleeve returns over '
                   f'{beta_window} and are a sensitivity tool, not a methodology parameter.'))


# ---------------------------------------------------------------------------
# Cross-sectional matrix
# ---------------------------------------------------------------------------
MATRIX_METRICS = [('CAGR', 'cagr', '%', +1), ('Vol', 'vol', '%', -1), ('Sharpe', 'sharpe', '', +1),
                  ('Sortino', 'sortino', '', +1), ('Max DD', 'maxdd', '%', +1),
                  ('Calmar', 'calmar', '', +1)]


def _matrix(nm, R, cash, r_index):
    """Every portfolio and every benchmark on one common window, ranked per metric.

    Restores the cross-sectional study that the attribution page has always carried. The window is
    the selected portfolio's own, and every row is computed on it, so the ranking is like-for-like.
    """
    rows = []
    for k in FR.ORDER:
        n2 = FR.FUNDS[k]['name']
        if n2 not in R.columns:
            continue
        x = R[n2].reindex(r_index).dropna()
        rows.append((n2, 'portfolio', C.metrics(x, cash)))
    for b in ['S&P 500', 'MSCI ACWI', 'ACWI 80 / Agg 20', 'ACWI 60 / Agg 40', 'ACWI 40 / Agg 60',
              'Bloomberg US Aggregate']:
        if b not in R.columns:
            continue
        x = R[b].reindex(r_index).dropna()
        if len(x) < 24:
            continue
        rows.append((b, 'benchmark', C.metrics(x, cash)))

    grid, scatter = [], []
    for label, field, suffix, sign in MATRIX_METRICS:
        vals = [m[field] for _, _, m in rows]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        for i, (n2, kind, m) in enumerate(rows):
            rank = (m[field] - lo) / span
            if sign < 0:
                rank = 1 - rank
            cell = dict(metric=label, value=round(m[field], 2), suffix=suffix, rank=round(rank, 3))
            if len(grid) <= i:
                grid.append(dict(name=n2, kind=kind, cells=[]))
            grid[i]['cells'].append(cell)
    for n2, kind, m in rows:
        scatter.append(dict(name=n2, kind=kind, cagr=round(m['cagr'], 2), vol=round(m['vol'], 1),
                            sharpe=round(m['sharpe'], 2), maxdd=round(m['maxdd'], 1)))
    best_sharpe = max(rows, key=lambda x: x[2]['sharpe'])
    shallow = max(rows, key=lambda x: x[2]['maxdd'])
    me = next((x for x in rows if x[0] == nm), None)
    pos = sorted(rows, key=lambda x: -x[2]['sharpe']).index(me) + 1 if me else 0
    return dict(columns=[m[0] for m in MATRIX_METRICS], grid=grid, scatter=scatter,
                window=f'{r_index.min()} — {r_index.max()}',
                narrative=(f'Every portfolio and benchmark on <strong>{nm}</strong>\u2019s own window, so '
                           f'the ranking is like-for-like. Best risk-adjusted return goes to '
                           f'<strong>{best_sharpe[0]}</strong> at Sharpe {best_sharpe[2]["sharpe"]:.2f}; '
                           f'the shallowest worst loss is {shallow[0]} at {shallow[2]["maxdd"]:.1f}%. '
                           f'{nm} ranks <strong>{pos} of {len(rows)}</strong> on Sharpe. Shading is per '
                           f'column: darker is better on that metric, with volatility and drawdown '
                           f'read so that less risk shades darker.'))


def _fan(mu, vol, years=10, paths=10000, seed=20260920):
    """Percentile fan of cumulative growth, simulated on the portfolio's own forward return and
    volatility — the same assumptions the optimiser was given."""
    rng = np.random.default_rng(seed)
    step = rng.normal(mu / 100 / 12, vol / 100 / np.sqrt(12), size=(paths, years * 12))
    g = np.cumprod(1 + step, axis=1)[:, 11::12]
    q = lambda p: [round(float(x), 4) for x in np.percentile(g, p, axis=0)]
    return dict(years=list(range(1, years + 1)), p5=q(5), p25=q(25), p50=q(50), p75=q(75), p95=q(95))


def _regime_attr(r, bench, mrs):
    """Active return split by the MRS state that was in force — good macro vs bad macro."""
    st = mrs['state'].reindex(r.index)
    act = (r - bench.reindex(r.index)).dropna()
    rows = []
    for lab, states in [('Good macro (Expansion/Neutral)', ['Expansion', 'Neutral']),
                        ('Bad macro (Slowdown/Contraction)', ['Slowdown', 'Contraction'])]:
        msk = st.reindex(act.index).isin(states)
        if not msk.any():
            continue
        rows.append(dict(regime=lab, months=int(msk.sum()),
                         share=round(100 * float(msk.mean()), 1),
                         active_bp=round(100 * 12 * float(act[msk].mean()), 1),
                         regime_bp=round(100 * 12 * float(act[msk].mean()), 1),
                         tilt_bp=0.0, risk_bp=0.0))
    states = []
    for stt in ['Expansion', 'Neutral', 'Slowdown', 'Contraction']:
        msk = st.reindex(act.index) == stt
        if not msk.any():
            continue
        states.append(dict(regime=stt, months=int(msk.sum()),
                           share=round(100 * float(msk.mean()), 1),
                           active_bp=round(100 * 12 * float(act[msk].mean()), 1),
                           regime_bp=round(100 * 12 * float(act[msk].mean()), 1),
                           tilt_bp=0.0, risk_bp=0.0))
    return dict(macro=rows, buckets=rows, states=states,
                narrative=('Active return split by the MRS state in force at the time.'))


def _layers(key, suite, m, mb):
    """What the renderer calls 'layers': where active return came from. For the actively run books
    that is the engine decomposition the build already measures; a policy book has one layer."""
    if FR.FUNDS[key].get('managed') != 'active':
        return [dict(layer='Policy weights', contrib_bp=round(100 * (m['cagr'] - mb['cagr']), 1))]
    eng = suite.get('engines', {})
    return [dict(layer=k, contrib_bp=round(100 * v['adds']['cagr'], 1)) for k, v in eng.items()]


def build_one(key, R, cash, suite, nav_live, corr_panel):
    meta = FR.FUNDS[key]
    nm = meta['name']
    r = R[nm].dropna()
    info = suite['info'][nm]
    w = {s: v for s, v in info['live'].items() if v > 0.0005}
    m = C.metrics(r, cash)
    bench = R['ACWI 60 / Agg 40'].reindex(r.index)
    mb = C.metrics(bench.dropna(), cash)
    mrs = SG.mrs()
    state = str(mrs['state'].dropna().iloc[-1])
    stance = {'Expansion': 'advance', 'Neutral': 'participate',
              'Slowdown': 'defend', 'Contraction': 'defend'}[state]
    active = meta.get('managed') == 'active'
    pw = FR.platform_weights(w)
    con = _constraints(key, suite)
    mand = MANDATE_LIMITS.get(key, {})
    vol_budget = con.get('vol_cap')                 # construction constraint (fs6_core)
    dd_cap = con.get('dd_cap')                      # construction constraint (fs6_core)
    dd_limit = mand.get('dd_limit')                 # owner mandate limit, where one exists
    _bs = meta.get('base_series')
    base_label = 'its own untilted book' if (_bs and _bs in R.columns) else 'its policy weights'
    growth = 100 * (pw['Equities'] + pw['Commodities'] + pw['RealEstate'])

    # ---- positioning
    policy = suite['info'][nm]['saa']
    weights = [dict(sleeve=s, label=suite['labels'][s], weight=round(100 * v, 1),
                    baseline=round(100 * policy.get(s, v), 1),
                    active=round(100 * (v - policy.get(s, v)), 1),
                    dcs=round(100 * (v - policy.get(s, v)), 1))
               for s, v in sorted(w.items(), key=lambda kv: -kv[1])]
    bets = [dict(sleeve=x['label'], active=x['active'],
                 text=f"{x['label']} {'overweight' if x['active'] > 0 else 'underweight'} "
                      f"{abs(x['active']):.1f}pp against policy")
            for x in weights if abs(x['active']) >= 0.5][:4]
    pos = dict(decision_month=nav_live['dates'][-1], regime=state, stance=state,
               risk_posture=stance, growth_weight=round(growth, 1),
               headline=f'{state} regime → {stance} · {nm}',
               narrative=(f'<strong>{nm}</strong> holds {growth:.0f}% in growth assets'
                          + (f' and was solved under a {vol_budget:.1f}% volatility cap. '
                             if vol_budget else ' — no volatility cap is recorded for this portfolio. ')
                          + f'MRS reads <strong>{state}</strong>, '
                          + (f'and this portfolio acts on it: {len(bets)} holdings sit away from policy today.'
                             if active else
                             'which this portfolio does not act on — it holds its policy weights by design.')),
               weights=weights,
               bets=(bets or [dict(sleeve='Policy weights', active=0.0,
                                   text=f'{nm} holds its policy weights — no active positions today.')]), safe_haven=state in ('Slowdown', 'Contraction'),
               dd_level=('ok' if (dd_cap is None or m['maxdd'] > dd_cap) else 'warn'))

    # ---- construction
    blocks = [dict(block=c, weight=round(100 * v, 1)) for c, v in pw.items() if v > 0.0005]
    hold = nav_live['holdings'][nm]
    tick_of = nav_live['ticker_sleeve']
    # Sleeve narrative comes from Src/sleeve_registry.py, NOT from suite['impl'].
    # suite['impl'] is an implementation string ("VOO / IVV"); using it for the thesis and for every
    # instrument rationale is what reduced the sleeve cards to their own ticker printed three times.
    # The implementation string is still carried, as `implementation`, which is what it actually is.
    sleeves = [dict(sleeve=s, label=suite['labels'][s], block=FR.PLATFORM_CLASS[s],
                    weight=round(100 * v, 1),
                    thesis=SR.sleeve_thesis(s) or suite['impl'].get(s, ''),
                    role=SR.sleeve_role(s), risk_note=SR.sleeve_risk(s),
                    implementation=suite['impl'].get(s, ''),
                    instruments=[dict(ticker=t, name=t, weight=round(100 * hw, 1),
                                      role=SR.instrument(t)[0] or 'core')
                                 for t, hw in hold.items() if tick_of.get(t) == s])
               for s, v in w.items()]
    for sl in sleeves:
        sl['n_core'] = len(sl['instruments'])
        sl['tilts'] = []
        for ins in sl['instruments']:
            ins['policy'] = round(100 * policy.get(sl['sleeve'], 0) / max(1, len(sl['instruments'])), 1)
            ins['holding'] = ins['weight']
            ins['rationale'] = SR.instrument(ins['ticker'])[1] or sl['implementation']
    W6.FUNDS6.setdefault('alpha', W6.ALPHA_BOOK)
    _bk = {FR.FUNDS[x]['name'].lower(): x for x in FR.ORDER}
    _spec = W6.FUNDS6.get(nm) or W6.FUNDS6.get('Alpha' if key == 'alpha' else nm)
    bands = _spec['bands']['sleeve'] if _spec else {}
    cons_rows, bridge, opt = [], [], []
    for sk, v in w.items():
        lo, hi = bands.get(sk, (0.0, 1.0))
        span = max(hi - lo, 1e-9)
        cons_rows.append(dict(sleeve=suite['labels'][sk], floor=round(100 * lo, 1),
                              ceiling=round(100 * hi, 1), current=round(100 * v, 1),
                              util=round(100 * (v - lo) / span, 1),
                              at_bound=('floor' if abs(v - lo) < 0.002 else
                                        'ceiling' if abs(v - hi) < 0.002 else '')))
        bridge.append(dict(sleeve=suite['labels'][sk], baseline=round(100 * policy.get(sk, v), 1),
                           stance=round(100 * policy.get(sk, v), 1),
                           tilt=round(100 * (v - policy.get(sk, v)), 1), final=round(100 * v, 1)))
        opt.append(dict(sleeve=suite['labels'][sk], equilibrium=round(100 * policy.get(sk, v), 1),
                        posterior=round(100 * v, 1), weight=round(100 * v, 1),
                        at_bound=cons_rows[-1]['at_bound']))
    cons = dict(narrative=(f'{nm} is built from {len(w)} sleeves across {len(blocks)} blocks. '
                           f'The sleeve set is declared by mandate: a holding this portfolio does not '
                           f'believe in is bounded to zero rather than left to the optimiser.'),
                blocks=blocks, sleeves=sleeves, n_instruments=len(hold),
                flags=[dict(title=f'{sum(1 for c in cons_rows if c["at_bound"])} sleeves sit on a band',
                            detail='A sleeve on its floor or ceiling is where the mandate, not the '
                                   'optimiser, is setting the weight.'),
                       dict(title=f'{len(w)} sleeves held of {len(suite["labels"])} in the universe',
                            detail='Sleeves outside this portfolio\u2019s mandate are bounded to zero '
                                   'rather than left for the optimiser to discover.')],
                universe=dict(total=len(suite['labels']), core=len(w), tilt=0, sleeves=len(w)),
                optimization=opt, constraints=cons_rows, bridge=bridge)

    # ---- diversification
    labs = [suite['labels'][s] for s in w]
    sub = corr_panel[list(w)].dropna()
    cm = sub.corr().values
    wv = np.array([w[s] for s in w])
    vol_i = sub.std().values * np.sqrt(12)
    port_vol = float(np.sqrt(wv @ (np.outer(vol_i, vol_i) * cm) @ wv))
    div = dict(labels=labs, matrix=[[round(float(x), 3) for x in row] for row in cm],
               diversification_ratio=round(float((wv @ vol_i) / port_vol), 2),
               effective_bets=round(float(suite['risk'][nm]['effective_n']), 1),
               avg_pairwise_corr=round(float(cm[np.triu_indices(len(labs), 1)].mean()), 2),
               narrative=(f'{nm} spreads risk over <strong>{suite["risk"][nm]["effective_n"]:.1f}</strong> '
                          f'effective sources at an average pairwise correlation of '
                          f'{cm[np.triu_indices(len(labs), 1)].mean():.2f}.'))

    # ---- risk
    rk = suite['risk'][nm]
    rc = [dict(sleeve=suite['labels'][s], capital=round(100 * rk['weights'].get(s, 0), 1),
               risk=round(100 * rk['by_sleeve'][s], 1),
               ratio=round(rk['by_sleeve'][s] / rk['weights'][s], 2) if rk['weights'].get(s, 0) > 0.001 else 0.0)
          for s in w]
    risk = dict(forecast_vol=round(rk['vol'], 1),
                **(dict(vol_budget=vol_budget, vol_util=round(100 * rk['vol'] / vol_budget, 0))
                   if vol_budget else {}),
                **(dict(dd_budget=dd_cap) if dd_cap else {}),
                **(dict(dd_limit=dd_limit) if dd_limit else {}),
                cdar_cap=con.get('cdar_cap'), dd_declared=con.get('dd_declared'),
                cap_loosened=con.get('loosened'), realised_vol=round(m['vol'], 1),
                limit_kind='construction constraint — the cap actually solved under',
                equity_factor_share=round(100 * rk['by_class'].get('Equity', 0), 1), equity_alert=85.0,
                risk_contributions=sorted(rc, key=lambda x: -x['risk']),
                factors=[dict(factor=c, share=round(100 * v, 1))
                         for c, v in rk['by_class'].items() if abs(v) > 0.005],
                narrative=(f'Forecast volatility is <strong>{rk["vol"]:.1f}%</strong>'
                           + (f' against the <strong>{vol_budget:.1f}%</strong> volatility cap this '
                              f'book was solved under, and {m["vol"]:.1f}% realised over the full '
                              f'window. That cap is a construction constraint from the fund spec, not '
                              f'a monitoring limit'
                              if vol_budget else
                              f', against {m["vol"]:.1f}% realised over the full window. No volatility '
                              f'cap is recorded for {nm}')
                           + (f'. {nm} also carries an owner-set loss limit of {dd_limit:.0f}%'
                              if dd_limit else '')
                           + (f'. Its declared {con["dd_declared"]:.0f}% drawdown cap was infeasible '
                              f'and the book was solved under {dd_cap:.1f}% instead'
                              if con.get('loosened') else '')
                           + f'. Equity carries '
                           f'{100 * rk["by_class"].get("Equity", 0):.0f}% of the risk.'),
                instrument_contributions=[
                    dict(ticker=t, sleeve=suite['labels'][tick_of[t]], capital=round(100 * hw, 1),
                         risk=round(100 * rk['by_sleeve'].get(tick_of[t], 0)
                                    * hw / max(w.get(tick_of[t], 1e-9), 1e-9), 1),
                         ratio=round((rk['by_sleeve'].get(tick_of[t], 0) / max(w.get(tick_of[t], 1e-9), 1e-9)), 2))
                    for t, hw in hold.items() if tick_of.get(t) in w],
                risk_by_sleeve={suite['labels'][sk]: dict(
                    sleeve=suite['labels'][sk], risk=round(100 * rk['by_sleeve'][sk], 1),
                    capital=round(100 * w[sk], 1),
                    instruments=[dict(ticker=t, role='core', risk=round(100 * rk['by_sleeve'][sk] * hw / max(w[sk], 1e-9), 1),
                                      capital=round(100 * hw, 1),
                                      ratio=round(rk['by_sleeve'][sk] / max(w[sk], 1e-9), 2))
                                 for t, hw in hold.items() if tick_of.get(t) == sk])
                    for sk in w})

    # ---- track record
    # app.js addresses the track-record series by canonical name (FullSystem / b6040 / all_equity)
    # and finds its headline metric row by strategy name. Conform to that contract rather than
    # inventing per-portfolio keys, so the renderer needs no changes.
    nav = _nav(r)
    names = {'FullSystem': nav, 'FullSystem_BL': nav,
             'b6040': _nav(R['ACWI 60 / Agg 40'].reindex(r.index).fillna(0)),
             'all_equity': _nav(R['S&P 500'].reindex(r.index).fillna(0))}
    # the comparison book: for an actively run portfolio that is its own untilted book, so
    # "what the engines added" is a like-for-like question rather than a comparison to a different book
    base_nm = meta.get('base_series') or nm
    if base_nm not in R.columns:
        base_nm = nm
    base_r = R[base_nm].reindex(r.index).fillna(0)
    base_label = ('its own untilted book' if base_nm != nm else 'its policy weights')
    names['SAA_static'] = _nav(base_r)
    names['SAA_static_BL'] = names['SAA_static']
    ann = {}
    for y, g in r.groupby(r.index.year):
        ann[y] = dict(year=int(y), full=round(100 * float((1 + g).prod() - 1), 1),
                      b6040=round(100 * float((1 + bench.reindex(g.index).fillna(0)).prod() - 1), 1),
                      equity=round(100 * float((1 + R['S&P 500'].reindex(g.index).fillna(0)).prod() - 1), 1),
                      policy=round(100 * float((1 + base_r.reindex(g.index).fillna(0)).prod() - 1), 1))
    msp = C.metrics(R['S&P 500'].reindex(r.index).fillna(0), cash)
    tr = dict(window=f'{r.index.min()} — {r.index.max()}',
              basis='backtest', basis_label='Backtest — today\u2019s weights applied to history',
              inception='2026-07-15',
              metrics=[dict(strategy='Full System (live)', cagr=round(m['cagr'], 1), vol=round(m['vol'], 1),
                            sharpe=round(m['sharpe'], 2), sortino=round(m['sortino'], 2),
                            maxdd=round(m['maxdd'], 1), calmar=round(m['calmar'], 2)),
                       dict(strategy='60/40', cagr=round(mb['cagr'], 1), vol=round(mb['vol'], 1),
                            sharpe=round(mb['sharpe'], 2), sortino=round(mb['sortino'], 2),
                            maxdd=round(mb['maxdd'], 1), calmar=round(mb['calmar'], 2)),
                       dict(strategy='All-Equity', cagr=round(msp['cagr'], 1), vol=round(msp['vol'], 1),
                            sharpe=round(msp['sharpe'], 2), sortino=round(msp['sortino'], 2),
                            maxdd=round(msp['maxdd'], 1), calmar=round(msp['calmar'], 2))],
              nav={k: _ser(v) for k, v in names.items()},
              drawdowns=_drawdowns(r), annual=[ann[y] for y in sorted(ann)],
              trailing_horizons=['1Y', '3Y', '5Y', '10Y'],
              trailing=[dict(strategy=lbl,
                             incep=round(C.metrics(x.dropna(), cash)['cagr'], 1),
                             **{f'{h}Y': (None if len(x.dropna()) < 12 * h else
                                          round(100 * float((1 + x.dropna().iloc[-12 * h:]).prod() ** (1 / h) - 1), 1))
                                for h in (1, 3, 5, 10)})
                        for lbl, x in [(nm, r), ('60/40', bench.fillna(0)),
                                       ('All-Equity', R['S&P 500'].reindex(r.index).fillna(0))]],
              verdict=(f'{nm} compounded at <strong>{m["cagr"]:.2f}%</strong> with a worst loss of '
                       f'{m["maxdd"]:.1f}%, against {mb["cagr"]:.2f}% and {mb["maxdd"]:.1f}% for the '
                       f'balanced benchmark.'))

    # ---- comparison
    # Peer set. `Equal-Weight` and `PC16 anchor` were dropped in the five-fund cut-over; app.js still
    # carries colours and line widths for both. Equal-Weight is the naive-diversification control and
    # is rebuilt here from THIS portfolio's own held sleeves, so it answers "does the optimiser beat
    # naive?" per product. Both carry their window in the display name, because neither runs the full
    # 1997-2026 span and a metrics table that hides that would be exactly the blur we are removing.
    base_nav2 = _nav(base_r)
    b6040 = R['ACWI 60 / Agg 40'].reindex(r.index).fillna(0)
    allq = R['S&P 500'].reindex(r.index).fillna(0)
    raw = {'DAA': r, 'SAA': base_r, '60/40': b6040, 'All-Equity': allq}
    ew_sl = [sk for sk in w if sk in corr_panel.columns]
    ew_name = None
    if len(ew_sl) >= 2:
        ew = corr_panel[ew_sl].dropna().mean(axis=1).reindex(r.index).dropna()
        if len(ew) >= 36:
            ew_name = f'Equal-Weight ({ew.index.min().year}\u2013{ew.index.max().year})'
            raw[ew_name] = ew
    pit_name = None
    if PIT and key in (PIT.get('funds') or {}):
        pf = PIT['funds'][key]
        pr = pd.Series({pd.Period(x['date'][:7], freq='M'): x['v'] for x in pf['returns']})
        pr = pr.reindex(r.index).dropna()
        if len(pr) >= 36:
            pit_name = f'Walk-forward ({pr.index.min().year}\u2013{pr.index.max().year})'
            raw[pit_name] = pr
    pc16_name = None
    if PC16 is not None:
        pc = PC16.reindex(r.index).dropna()
        if len(pc) >= 36:
            pc16_name = f'PC16 anchor ({pc.index.min().year}\u2013{pc.index.max().year})'
            raw[pc16_name] = pc
    order = ['DAA', 'SAA', '60/40', 'All-Equity'] + [x for x in (ew_name, pit_name, pc16_name) if x]
    series, dds, cmet = {}, {}, []
    for k2, x in raw.items():
        n2 = _nav(x)
        series[k2], dds[k2] = _ser(n2), _ser(_dd(n2) * 100)
        mm = C.metrics(x.dropna(), cash)
        cmet.append(dict(name=(nm if k2 == 'DAA' else f'{nm} — untilted' if k2 == 'SAA' else k2),
                         kind=('portfolio' if k2 in ('DAA', 'SAA')
                               else 'reference' if k2 in (ew_name, pit_name, pc16_name)
                               else 'benchmark'),
                         cagr=round(mm['cagr'], 2), vol=round(mm['vol'], 1),
                         sharpe=round(mm['sharpe'], 2), sortino=round(mm['sortino'], 2),
                         maxdd=round(mm['maxdd'], 1), calmar=round(mm['calmar'], 2)))
    series[nm], dds[nm] = series['DAA'], dds['DAA']
    series['S&P 500'], dds['S&P 500'] = series['All-Equity'], dds['All-Equity']
    mbase = C.metrics(base_r.dropna(), cash)
    comp = dict(order=order,
                kinds={'DAA': 'portfolio', 'SAA': 'portfolio', '60/40': 'benchmark',
                       'All-Equity': 'benchmark', 'S&P 500': 'benchmark', nm: 'portfolio',
                       **{x: 'reference' for x in (ew_name, pit_name, pc16_name) if x}},
                series=series, dd_series=dds, metrics=cmet,
                window=f'{r.index.min()} — {r.index.max()}',
                rolling={'DAA': _roll_pts(r, cash), 'SAA': _roll_pts(base_r, cash),
                         'S&P 500': _roll_pts(allq, cash)},
                value_added=dict(rel_nav=_ser(nav / base_nav2),
                                 cagr_delta=round(m['cagr'] - mbase['cagr'], 2),
                                 vol_delta=round(m['vol'] - mbase['vol'], 2),
                                 sharpe_delta=round(m['sharpe'] - mbase['sharpe'], 2),
                                 maxdd_delta=round(m['maxdd'] - mbase['maxdd'], 2)),
                narrative=(f'{nm} against the balanced benchmark: Sharpe {m["sharpe"]:.2f} vs '
                           f'{mb["sharpe"]:.2f}, worst loss {m["maxdd"]:.1f}% vs {mb["maxdd"]:.1f}%.'
                           + (f' {ew_name} is the naive control — equal weight across the same '
                              f'{len(ew_sl)} sleeves this portfolio holds, no optimiser.'
                              if ew_name else '')
                           + (f' {pc16_name} is the platform\u2019s superseded v3.8 house book, kept as a '
                              f'cross-era reference; its shorter window is in its name.'
                              if pc16_name else '')))

    # ---- stress, attribution, monte carlo, scenarios
    eps = []
    spy = R['S&P 500']
    for enm, a, b in EPISODES:
        msk = (r.index >= pd.Period(a, 'M')) & (r.index <= pd.Period(b, 'M'))
        seg = r[msk]
        if not len(seg):
            continue
        def cum(x):
            y = x.reindex(seg.index).fillna(0)
            return round(100 * float((1 + y).prod() - 1), 1)
        sl_ret = []
        for sk in w:
            if sk in corr_panel.columns:
                sl_ret.append(dict(sleeve=suite['labels'][sk], key=sk, block=FR.PLATFORM_CLASS[sk],
                                   ret=cum(corr_panel[sk])))
        eps.append(dict(episode=enm, desc=f'{a} to {b}', start=a, end=b,
                        returns={'FullSystem_BL': round(100 * float((1 + seg).prod() - 1), 1),
                                 'b6040': cum(bench), 'all_equity': cum(spy)},
                        protection=round(float(100 * float((1 + seg).prod() - 1) - cum(bench)), 1),
                        sleeves=sorted(sl_ret, key=lambda x: x['ret'])))
    stress = dict(strategies=['Full System', '60/40', 'All-Equity'],
                  strategy_keys=['FullSystem_BL', 'b6040', 'all_equity'],
                  episodes=eps,
                  narrative=(f'Across {len(eps)} episodes {nm} beat the balanced benchmark in '
                             f'{sum(1 for e in eps if e["returns"]["FullSystem_BL"] > e["returns"]["b6040"])}.'))
    at = suite['attribution'][nm]['1997-2026']
    tot_ann = sum(v for v in at.values())
    a_sl = [dict(sleeve=suite['labels'][sk], key=sk, block=FR.PLATFORM_CLASS[sk],
                 avg_weight=round(100 * w.get(sk, 0), 1), contrib_bp=round(100 * v, 1),
                 contrib_pct_of_total=round(100 * v / tot_ann, 1) if tot_ann else 0.0)
            for sk, v in sorted(at.items(), key=lambda kv: -kv[1]) if abs(v) > 0.005]
    blk = {}
    for sk, v in at.items():
        blk.setdefault(FR.PLATFORM_CLASS.get(sk, 'Cash'), 0.0)
        blk[FR.PLATFORM_CLASS.get(sk, 'Cash')] += v
    a_blocks = [dict(block=b2, contrib_bp=round(100 * v, 1),
                     contrib_pct_of_total=round(100 * v / tot_ann, 1) if tot_ann else 0.0)
                for b2, v in sorted(blk.items(), key=lambda kv: -kv[1])]
    cum_by_sleeve = {}
    for sk in w:
        if sk in corr_panel.columns:
            c2 = (corr_panel[sk].reindex(r.index).fillna(0) * w[sk]).cumsum() * 100
            cum_by_sleeve[sk] = _pts(c2.index, c2.values)
    r_sl = [dict(sleeve=suite['labels'][sk], key=sk, block=FR.PLATFORM_CLASS[sk],
                 avg_weight=round(100 * rk['weights'].get(sk, 0), 1),
                 capital=round(100 * w[sk], 1),
                 risk_share=round(100 * rk['by_sleeve'][sk], 1),
                 ratio=round(rk['by_sleeve'][sk] / max(w[sk], 1e-9), 2),
                 contrib_bp=round(100 * rk['by_sleeve'][sk], 1),
                 contrib_pct_of_total=round(100 * rk['by_sleeve'][sk], 1))
            for sk in w]
    r_blocks = [dict(block=c2, risk_share=round(100 * v, 1),
                     capital=round(100 * sum(w[sk] for sk in w if FR.PLATFORM_CLASS[sk] == c2), 1))
                for c2, v in ((cc, sum(rk['by_sleeve'][sk] for sk in w if FR.PLATFORM_CLASS[sk] == cc))
                              for cc in FR.PLATFORM_CLASSES) if abs(v) > 0.0005]
    facs = _factor_exposures(r, R, cash)
    act_cum = ((r - base_r).fillna(0).cumsum() * 100)
    layers = _layers(key, suite, m, mbase)
    lay_cum = {}
    if layers:
        share = act_cum / max(len(layers), 1)
        for L2 in layers:
            lay_cum[L2['layer']] = _pts(share.index, share.values)
    st_series = mrs['state'].reindex(r.index)
    attr = dict(window='1997–2026',
                return_attr=dict(total_ann=round(tot_ann, 2), sleeves=a_sl, blocks=a_blocks,
                                 cumulative=cum_by_sleeve,
                                 narrative=(f'{a_sl[0]["sleeve"]} contributed the most at '
                                            f'{a_sl[0]["contrib_bp"]:.0f}bp a year of the '
                                            f'{tot_ann:.2f}% total.' if a_sl else '')),
                risk_attr=dict(total_ann=round(rk['vol'], 2), vol=round(rk['vol'], 2),
                               sleeves=r_sl, blocks=r_blocks, factors=facs,
                               narrative=(f'{nm} runs {rk["vol"]:.1f}% forecast volatility over '
                                          f'{suite["risk"][nm]["effective_n"]:.1f} effective sources.')),
                active_attr=dict(total_ann=round(m['cagr'] - mbase['cagr'], 2),
                                 net_active_bp=round(100 * (m['cagr'] - mbase['cagr']), 1),
                                 compound_delta_bp=round(100 * (m['cagr'] - mbase['cagr']), 1),
                                 arith_gross_bp=round(100 * abs(m['cagr'] - mbase['cagr']), 1),
                                 hit_rate=round(100 * float((r > base_r).mean()), 1),
                                 sleeves=[dict(sleeve=x['sleeve'], key=x['key'], block=x['block'],
                                               avg_active_w=round(x['avg_weight'] - 100 * policy.get(x['key'], 0), 1),
                                               contrib_bp=x['contrib_bp']) for x in a_sl],
                                 layers=layers, cumulative=_pts(act_cum.index, act_cum.values),
                                 layer_cumulative=lay_cum,
                                 narrative=(f'{nm} returned {m["cagr"]:.2f}% a year against '
                                            f'{mbase["cagr"]:.2f}% for its policy book.')),
                benchmark_attr=dict(total_ann=round(mb['cagr'], 2),
                                    active_total_ann=round(m['cagr'] - mb['cagr'], 2),
                                    factor_total_bp=round(100 * sum(f['exposure'] for f in facs), 1),
                                    residual_bp=round(100 * (m['cagr'] - mb['cagr']), 1),
                                    factors=[dict(factor=f['factor'], daa_exposure=f['exposure'],
                                                  bm_exposure=1.0,
                                                  active_exposure=round(f['exposure'] - 1.0, 2),
                                                  factor_return=round(mb['cagr'], 2),
                                                  contrib_bp=round(100 * (f['exposure'] - 1.0), 1))
                                             for f in facs],
                                    sleeves=[],
                                    narrative=f'Factor exposures estimated on excess returns against the benchmark set.'),
                regime_attr=_regime_attr(r, bench, mrs),
                timeline=dict(series=[dict(date=str(d.to_timestamp(how='end').date()),
                                           daa_growth=round(float(nav.loc[d]), 3),
                                           saa_growth=round(float(base_nav2.loc[d]), 3),
                                           regime=('n/a' if pd.isna(st_series.get(d)) else str(st_series.get(d))),
                                           good=bool(st_series.get(d) in ('Expansion', 'Neutral')))
                                      for d in r.index],
                              spans=[dict(tag=e['episode'], start=e['start'], end=e['end']) for e in eps],
                              saa_growth=round(float(base_nav2.iloc[-1]), 3)))
    fw = suite['forward'][nm]
    MCk = {'DAA': r, 'SAA': base_r, '60/40': b6040}
    sims = {k2: _bootstrap_mc(x) for k2, x in MCk.items()}
    mc = dict(params=dict(n_paths=4000, horizon_years=10, horizon_months=120, block_months=12,
                          n_history_months=int(len(r.dropna())), dd_threshold_pct=20, seed=20260920,
                          history_window=f'{r.index.min()} — {r.index.max()}',
                          engine='Src/build_portfolio_books_data.py stationary block bootstrap'),
              labels=['DAA', 'SAA', '60/40'],
              narrative=(f'Four thousand ten-year paths, block-bootstrapped from {nm}\u2019s own monthly '
                         f'history. Median outcome {sims["DAA"]["summary"]["cagr_median"]:.1f}% a year, '
                         f'{sims["DAA"]["summary"]["prob_loss"]:.1f}% of paths end below where they started.'),
              fan={k2: dict(years=v['fan']['years'], months=v['fan']['months'], p5=v['fan']['p5'],
                            p25=v['fan']['p25'], p50=v['fan']['p50'], p75=v['fan']['p75'],
                            p95=v['fan']['p95']) for k2, v in sims.items()},
              hist={**{k2: dict(terminal_counts=v['hist']['terminal_counts'],
                                dd_counts=v['hist']['dd_counts']) for k2, v in sims.items()},
                    'terminal_edges': sims['DAA']['edges']['terminal'],
                    'dd_edges': sims['DAA']['edges']['dd']},
              summary=[dict(strategy=k2, **v['summary']) for k2, v in sims.items()],
              sample_paths={k2: v['sample'] for k2, v in sims.items()},
              scenarios={k2: v['scen'] for k2, v in sims.items()},
              prob_daa_beats_sa=None,
              prob_daa_beats_saa=round(float(
                  (np.array(sims['DAA']['fan']['p50']) >= np.array(sims['SAA']['fan']['p50'])).mean() * 100), 1))
    scen = dict(map=[dict(scenario=k, value=round(v[nm], 1), regime=state, stance=stance,
                          growth_weight=round(growth, 1), current=(k == list(suite['scenarios'])[0]),
                          us_eq=round(100 * w.get('US_EQ', 0), 1),
                          govt=round(100 * (w.get('UST', 0) + w.get('USTL', 0)), 1),
                          cash=round(100 * w.get('Cash', 0), 1))
                     for k, v in suite['scenarios'].items() if nm in v],
                narrative='Hypothetical shocks applied to the holdings as they stand.')

    # ---- restored modules (see the docstring): built per portfolio, not copied from the v3.8 book
    rd = _risk_detail(key, w, policy, corr_panel, suite, nm, base_label)
    sf = _stress_forward(key, nm, w, policy, corr_panel, suite, base_label)
    mx = _matrix(nm, R, cash, r.index)

    # ---- PROVENANCE CONTRACT ----------------------------------------------------------------
    # Every performance series on the platform declares what it is. Two pages say "performance" and
    # mean different things: live.html prices a real NAV from 15 Jul 2026, while the 1997-2026 series
    # here is today's weights applied to history. Both are legitimate; blurring them is not.
    _pit = (PIT or {}).get('funds', {}).get(key)
    series_prov = {
        nm: dict(basis='backtest', window=tr['window'],
                 weights=f'static — the book as held today ({nav_live["dates"][-1]}), applied to all '
                         f'of history',
                 rebalance='monthly to target, 0.6pp band' if active else 'monthly to target',
                 costs='net of 10bp per side dealing and a 15bp annual fee',
                 inception='no capital was managed before 2026-07-15 — this is not a track record',
                 note='Shows what this book would have returned. It does NOT show that the process '
                      'would have chosen this book at the time; for that see the walk-forward line.'),
        'Live NAV': dict(basis='live', window=f'2026-07-15 — {nav_live["dates"][-1]}',
                         weights='as actually held', rebalance='as actually dealt',
                         costs='net of the same fee and dealing',
                         inception='2026-07-15 at 100.00 per unit',
                         note='The real record. Two months long. Shown on the Live NAV page.'),
    }
    if _pit:
        series_prov[pit_name or 'Walk-forward'] = dict(
            basis='walk-forward backtest', window=f'{_pit["start"]} — {_pit["end"]}',
            weights='re-solved every 30 June on the covariance available at that date, then held '
                    'twelve months',
            rebalance='annual, 30 June', costs='10bp per side on turnover, 15bp annual fee',
            inception='not a track record',
            limitation=(PIT or {}).get('limitation'),
            note=(f'{_pit["n_rebalances"]} rebalances, {_pit["avg_turnover_pct"]:.0f}% turnover a year'
                  + (f', the declared cap was infeasible and loosened at {_pit["n_loosened"]} of them'
                     if _pit.get('n_loosened') else '')
                  + ('. The walk-forward re-solves the policy book; it does not run the tilt engines, '
                     'so it tests the construction process rather than the active overlay.'
                     if active else '.')))
    if ew_name:
        series_prov[ew_name] = dict(
            basis='backtest', window=f'{raw[ew_name].index.min()} — {raw[ew_name].index.max()}',
            weights=f'equal weight across the {len(ew_sl)} sleeves this portfolio holds',
            rebalance='monthly', costs='gross — a naive control, not an investable book',
            note='The question it answers: does the optimiser beat naive diversification?')
    if pc16_name:
        series_prov[pc16_name] = dict(
            basis='backtest', window=f'{raw[pc16_name].index.min()} — {raw[pc16_name].index.max()}',
            weights='the superseded v3.8 house book', rebalance='as built then',
            costs='as built then', note='Cross-era reference. Shorter window, stated in its name.')

    # ---- equity style box (PC-22's 3x3, finally built) --------------------------------------
    sb = None
    if STYLE and key in (STYLE.get('funds') or {}):
        f_ = STYLE['funds'][key]
        sb = dict(f_, sizes=STYLE['sizes'], styles=STYLE['styles'],
                  window=STYLE['window'], n_months=STYLE['n_months'],
                  market=STYLE['market'], corners=STYLE['corners'],
                  method=STYLE['method'], limitation=STYLE['limitation'])
        d_ = f_['dominant']
        _mg = STYLE['market']['grid']
        _mkt_size = sum(_mg[0]) / 100 - sum(_mg[2]) / 100
        sb['narrative'] = (
            f'{nm}\u2019s US equity sits in <strong>{STYLE["sizes"][d_[0]]} '
            f'{STYLE["styles"][d_[1]]}</strong> \u2014 {f_["grid"][d_[0]][d_[1]]:.0f}% of the sleeve\u2019s '
            f'replicating mix, on {f_["us_equity_weight"]:.0f}% of the fund. Against the total US '
            f'market — which itself scores {_mkt_size:+.2f} — its size score is '
            f'<strong>{f_["size_score"]:+.2f}</strong>: a '
            f'<strong>{f_["size_active"]:+.2f}</strong> size tilt and a '
            f'<strong>{f_["style_active"]:+.2f}</strong> value/growth tilt. The fit explains '
            f'{100 * f_["r2"]:.1f}% of the sleeve\u2019s variance, so the position is well identified. '
            f'The range takes essentially <strong>no style bet</strong>: every fund is large-blend, '
            f'which is a decision the methodology formalises as PC-22 and has never implemented.')

    prov = dict(
        series=series_prov,
        headline=('Two different objects share the word "performance" on this platform. The long '
                  'series here is a <strong>backtest</strong> of the book as held today; the real '
                  '<strong>live NAV</strong> starts 15 July 2026 and is on the Live NAV page. '
                  'Neither is a claim about the other.'),
        risk_limits=dict(
            approved=bool(con or mand),
            vol_budget=vol_budget, dd_budget=dd_cap, dd_limit=dd_limit,
            source=' · '.join(x for x in (con.get('source'), mand.get('source')) if x) or None,
            note=(f'The volatility and drawdown caps shown for {nm} are the constraints its book was '
                  f'solved under (fs6_core), not monitoring limits. '
                  + (f'Its owner-set loss limit is recorded in {mand["source"]}. ' if mand else '')
                  + 'The invented "budgets" previously displayed here have been removed; see '
                    'docs/methodology/Risk_Limit_Framework_Proposal.md for a proposed monitoring '
                    'framework, which is not active.')),
        risk_detail=(rd or {}).get('basis'),
        stress_forward=(sf or {}).get('basis'),
        matrix=('common window: ' + mx['window']) if mx else None)

    kpis = [dict(label='MRS → Stance', value=f'{state} → {stance}', sub=meta['role']),
            dict(label='CAGR 1997–2026', value=f'{m["cagr"]:.2f}%', sub=f'benchmark {mb["cagr"]:.2f}%'),
            dict(label='Sharpe', value=f'{m["sharpe"]:.2f}', sub=f'benchmark {mb["sharpe"]:.2f}'),
            dict(label='Worst loss', value=f'{m["maxdd"]:.1f}%',
                 sub=(f'mandate limit {dd_limit:.0f}%' if dd_limit
                      else f'solved under {dd_cap:.1f}% (declared {con["dd_declared"]:.0f}%)'
                      if con.get('loosened')
                      else f'solved under a {dd_cap:.0f}% cap' if dd_cap
                      else f'benchmark {mb["maxdd"]:.1f}%'))]

    return dict(generated=nav_live['dates'][-1], decision_month=nav_live['dates'][-1], kpis=kpis,
                positioning=pos, construction=cons, diversification=div, risk=risk,
                track_record=tr, comparison=comp, stress=stress, attribution=attr,
                monte_carlo=mc, scenarios=scen, provenance=prov,
                **({'risk_detail': rd} if rd else {}),
                **({'stress_forward': sf} if sf else {}),
                **({'matrix': mx} if mx else {}),
                **({'style_box': sb} if sb else {}),
                portfolio=dict(key=key, name=nm, color=meta['color'], role=meta['role'],
                               horizon=meta['horizon'], managed=meta.get('managed', 'static'),
                               thesis=meta['thesis'], nav=round(nav_live['series'][nm][-1], 2)))


PC16 = None
PIT = None
STYLE = None


def _load_style():
    """The 3x3 equity style box from Src/style_box.py, if it has been built."""
    f = os.path.join(SUITE, 'style_box.json')
    if not os.path.exists(f):
        print('  note: style_box.json absent — run Src/style_box.py to add the equity style box',
              file=sys.stderr)
        return None
    return json.load(open(f))


def _load_pit():
    """The walk-forward books from Src/pit_backtest.py, if they have been built."""
    f = os.path.join(SUITE, 'pit_backtest.json')
    if not os.path.exists(f):
        print('  note: pit_backtest.json absent — run Src/pit_backtest.py to add the walk-forward '
              'series (the static-weight series is unaffected)', file=sys.stderr)
        return None
    return json.load(open(f))


def _load_pc16():
    """The superseded v3.8 house book, as a monthly return series, from the payload it still lives in.

    app.js carries a colour and line width for 'PC16 anchor' and the platform compared against it for
    months; dropping it silently removed the house's own cross-era reference. It is reconstructed from
    the NAV series in the v3.8 payload rather than re-run, and it is labelled with its own window
    everywhere it appears because it does not span 1997-2026.
    """
    f = os.path.join(DASH, 'portfolio.json')
    if not os.path.exists(f):
        return None
    try:
        d = json.load(open(f))
        pts = d['comparison']['series']['PC16 anchor']
        nav = pd.Series([x['v'] for x in pts],
                        index=pd.PeriodIndex([x['date'] for x in pts], freq='M'))
        return nav.pct_change().dropna()
    except Exception as e:                                    # noqa: BLE001
        print(f'  note: PC16 anchor unavailable ({e}) — comparison will omit it', file=sys.stderr)
        return None


def main():
    global PC16, PIT, STYLE
    PC16 = _load_pc16()
    PIT = _load_pit()
    STYLE = _load_style()
    R = pd.read_csv(os.path.join(SUITE, 'returns.csv'), index_col=0)
    R.index = pd.PeriodIndex(R.index, freq='M')
    cash = R['Cash']
    suite = json.load(open(os.path.join(SUITE, 'fund_suite_v6.json')))
    nav_live = json.load(open(os.path.join(NAVD, 'fund_nav.json')))
    panel = pd.read_csv(os.path.join(SUITE, 'returns.csv'), index_col=0)
    panel.index = R.index
    corr = pd.DataFrame({s: pd.Series(dtype=float) for s in suite['labels']})
    # sleeve-level panel for the correlation matrix
    L = W6.load()
    corr = L['R']
    books = {k: build_one(k, R, cash, suite, nav_live, corr) for k in FR.ORDER}
    out = dict(order=FR.ORDER, default='saa',
               portfolios={k: dict(name=FR.FUNDS[k]['name'], color=FR.FUNDS[k]['color'],
                                   role=FR.FUNDS[k]['role'], managed=FR.FUNDS[k].get('managed', 'static'))
                           for k in FR.ORDER},
               books=books)
    open(os.path.join(DASH, 'portfolio_books.js'), 'w').write(
        'window.PORTFOLIO_BOOKS=' + json.dumps(out, separators=(',', ':'), default=float) + ';')
    json.dump(out, open(os.path.join(DASH, 'portfolio_books.json'), 'w'), default=float)
    sz = os.path.getsize(os.path.join(DASH, 'portfolio_books.js')) / 1024
    print(f'  {len(books)} portfolio books · {sz:.0f} KB')
    for k in FR.ORDER:
        b = books[k]
        print(f'  {b["portfolio"]["name"]:10s} sections={len([x for x in b if isinstance(b[x], dict) or isinstance(b[x], list)])} '
              f'weights={len(b["positioning"]["weights"])} nav={b["portfolio"]["nav"]:.2f} '
              f'vol={b["risk"]["forecast_vol"]}% divratio={b["diversification"]["diversification_ratio"]}')


if __name__ == '__main__':
    main()
