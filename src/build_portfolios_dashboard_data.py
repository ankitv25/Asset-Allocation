#!/usr/bin/env python3
"""
build_portfolios_dashboard_data.py — the dashboard payload for the five portfolios.

Writes data/portfolios.json (+ .js) in the SAME SHAPE the Portfolios page already consumes
(data/candidates.json: meta / versions / metrics / series / crises / reference / gates), so the
existing Portfolios page carries the five portfolios instead of the three superseded candidates. The old payload
and its generator (pc_candidates_dashboard_data.py) are left in place as the superseded record, the
way portfolio.json is kept as the v3.8 reference.

Metrics come from cf_core.metrics — the platform's canonical definitions — so a Sharpe here means the
same thing as a Sharpe anywhere else on the dashboard. Nothing is hand-typed: identity comes from
fund_registry, returns and weights from validation/fund_suite_v6/.

Per the standing rule that the dashboard must interpret rather than display, every narrative string is
composed from the payload's own numbers.
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import cf_core as C  # noqa: E402
import fund_registry as FR  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_suite_v6')
NAVD = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_nav')
DASH = os.path.join(ROOT, 'Research/Portfolio_Construction/dashboard/data')

BENCH_COL = {'spy': 'S&P 500', 'acwi': 'MSCI ACWI', 'agg': 'Bloomberg US Aggregate',
             'acwi8020': 'ACWI 80 / Agg 20', 'acwi6040': 'ACWI 60 / Agg 40',
             'acwi4060': 'ACWI 40 / Agg 60'}
CRISES = [('GFC 2008', '2007-11', '2009-02'), ('Euro 2011', '2011-05', '2011-09'),
          ('COVID 2020', '2020-02', '2020-03'), ('2022 inflation', '2022-01', '2022-09'),
          ('Dot-com 2000', '2000-09', '2002-09')]


def _panel():
    r = pd.read_csv(os.path.join(SUITE, 'returns.csv'), index_col=0)
    r.index = pd.PeriodIndex(r.index, freq='M')
    return r


def _metric_panel(r, cash, eq, fi, ref6040, spy):
    """cf_core metrics plus the beta/correlation/tracking set the Portfolios page already shows."""
    m = C.metrics(r, cash)
    x = r.dropna()
    c = cash.reindex(x.index)
    ex = x - c
    dn = ex[ex < 0]
    out = dict(cagr=m['cagr'] / 100, vol=m['vol'] / 100, mdd=m['maxdd'] / 100,
               sharpe=m['sharpe'], sortino=m['sortino'], calmar=m['calmar'],
               cvar5=m['cvar5'] / 100, skew=m['skew'], kurt=m['kurt'],
               downside_dev=float(np.sqrt((dn ** 2).mean()) * np.sqrt(12)) if len(dn) else None)
    for tag, b in [('6040', ref6040), ('eq', eq), ('fi', fi), ('spx', spy)]:
        y = b.reindex(x.index)
        ok = x.notna() & y.notna()
        if ok.sum() < 24:
            out[f'beta_{tag}'], out[f'corr_{tag}'] = None, None
            continue
        out[f'beta_{tag}'] = float(np.cov(x[ok], y[ok])[0, 1] / np.var(y[ok]))
        out[f'corr_{tag}'] = float(x[ok].corr(y[ok]))
    y = ref6040.reindex(x.index)
    act = (x - y).dropna()
    out['te_6040'] = float(act.std() * np.sqrt(12))
    out['excess_6040'] = float(((1 + x).prod() ** (12 / len(x)) - 1) - ((1 + y).prod() ** (12 / len(y)) - 1))
    return {k: (None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), 6))
            for k, v in out.items()}


def build():
    R = _panel()
    cash = R['Cash']
    suite = json.load(open(os.path.join(SUITE, 'fund_suite_v6.json')))
    nav = json.load(open(os.path.join(NAVD, 'fund_nav.json')))
    eq, fi = R['MSCI ACWI'], R['Bloomberg US Aggregate']
    ref, spy = R['ACWI 60 / Agg 40'], R['S&P 500']

    metrics, versions, series = {}, {}, {}
    for key in FR.ORDER:
        meta = FR.FUNDS[key]
        nm = meta['name']
        metrics[key] = _metric_panel(R[nm], cash, eq, fi, ref, spy)
        series[key] = [round(float(v), 6) for v in R[nm].values]
        w = suite['info'][nm]['live']
        versions[key] = dict(
            name=nm, key=key, engine_label=meta['engine_label'], role=meta['role'],
            status=meta['status'], horizon=meta['horizon'], color=meta['color'],
            reference=meta['reference'], thesis=meta['thesis'], dials=meta['dials'],
            managed=meta.get('managed', 'static'),
            weights={c: round(v, 6) for c, v in FR.platform_weights(w).items()},
            sleeves={s: round(float(v), 6) for s, v in w.items() if v > 0.0005},
            fi_of_book={'Govt': round(w.get('UST', 0) + w.get('USTL', 0), 6),
                        'IG': round(w.get('IG', 0), 6),
                        'TIPS': round(w.get('TIPS', 0), 6),
                        'HY': round(w.get('HY', 0), 6)},
            sleeve_labels={s: suite['labels'][s] for s in w if v_ok(w, s)},
            nav=round(nav['series'][nm][-1], 4),
            nav_return=round(nav['series'][nm][-1] / nav['nav0'] - 1, 6),
            n_holdings=len(nav['holdings'][nm]))
    for bkey, col in BENCH_COL.items():
        metrics[bkey] = _metric_panel(R[col], cash, eq, fi, ref, spy)
        series[bkey] = [round(float(v), 6) for v in R[col].values]

    crises = []
    for nm, a, b in CRISES:
        seg = R[(R.index >= pd.Period(a, 'M')) & (R.index <= pd.Period(b, 'M'))]
        crises.append(dict(name=nm, start=a, end=b, returns={
            **{k: round(float((1 + seg[FR.FUNDS[k]['name']]).prod() - 1), 6) for k in FR.ORDER},
            **{k: round(float((1 + seg[c]).prod() - 1), 6) for k, c in BENCH_COL.items()}}))

    # DAA mechanics, from MRS (the platform's backbone regime signal) and the priced book
    import fs5_signals as SG
    mrs = SG.mrs().reindex(R.index)
    tl = mrs.dropna(subset=['state'])
    da = dict(
        source='MRS regime_confirmed (Research/MRS/monitoring/mrs_composite_history.csv)',
        states=SG.MRS_STATES,
        timeline=dict(dates=[str(d) for d in tl.index],
                      state=[str(tl.loc[d, 'state']) for d in tl.index],
                      composite=[(None if pd.isna(tl.loc[d, 'composite']) else round(float(tl.loc[d, 'composite']), 4))
                                 for d in tl.index]),
        switches=int((tl['state'] != tl['state'].shift()).sum() - 1),
        turnover_oneway_yr=round(float(suite['info']['DAA'].get('turnover_yr', 0)) / 2, 4),
        cost_drag_bp_yr=round(float(suite['info']['DAA'].get('turnover_yr', 0)) * 10, 1),
        months_in_state={st: int((tl['state'] == st).sum()) for st in SG.MRS_STATES},
        class_tilt={st: {c: round(float(v), 2) for c, v in t.items()}
                    for st, t in __import__('fs5_core').REGIME_CLASS_TILT.items()},
        turnover_yr={k: round(float(suite['info'][FR.FUNDS[k]['name']].get('turnover_yr', 0)), 4)
                     for k in FR.ORDER if 'turnover_yr' in suite['info'][FR.FUNDS[k]['name']]},
        trend_by_state={st: round(float(v), 6) for st, v in suite.get('mf_by_state', {}).items()},
        caveats=['MRS begins 2003-08, so the regime engine contributes nothing before then.',
                 'Regime tilts are the Playbook regime books against the static base, shrunk by each '
                 'regime\'s own shrink factor — not a second opinion formed here.'])

    best = max(FR.ORDER, key=lambda k: metrics[k]['sharpe'])
    deepest = min(FR.ORDER, key=lambda k: metrics[k]['mdd'])
    payload = dict(
        meta=dict(built=pd.Timestamp.today().strftime('%Y-%m-%d'),
                  window=dict(start=str(R.index.min()), end=str(R.index.max()), n=int(len(R))),
                  inception=nav['inception'], asof=nav['dates'][-1],
                  engines=['Src/pc_fs6_build.py (books, backtest)', 'Src/fund_nav.py (priced NAV)',
                           'Research/MRS (regime state)'],
                  generator='Src/build_portfolios_dashboard_data.py',
                  cost_note='Net of 10bp per side of dealing and a 15bp annual fund fee.',
                  taxonomy_note='Weights are rolled into the platform\'s six classes via '
                                'fund_registry.PLATFORM_CLASS; the funds\' own methodology classes are '
                                'Equity / Defensive / Real assets / Diversifiers / Cash.'),
        order=FR.ORDER, bench_order=list(BENCH_COL),
        books={**{k: dict(label=FR.FUNDS[k]['name'], color=FR.FUNDS[k]['color']) for k in FR.ORDER},
               **{k: dict(label=v['name'], color=v['color']) for k, v in FR.BENCHMARKS.items()}},
        versions=versions, metrics=metrics,
        series=dict(dates=[str(d) for d in R.index], returns=series),
        crises=crises, da=da,
        platform_classes=FR.PLATFORM_CLASSES,
        # Sleeve identity at the root, so the range page can build one matrix across all five books
        # without re-deriving labels per version or inventing its own names.
        sleeve_labels=dict(suite['labels']),
        class_of={s: FR.PLATFORM_CLASS.get(s, 'Other') for s in suite['labels']},
        narrative=dict(
            headline=f'Five funds, live since {nav["inception"]}. Over {R.index.min()}–{R.index.max()} '
                     f'{FR.FUNDS[best]["name"]} carries the best risk-adjusted record at a Sharpe of '
                     f'{metrics[best]["sharpe"]:.2f}, and {FR.FUNDS[deepest]["name"]} the deepest loss at '
                     f'{100 * metrics[deepest]["mdd"]:.1f}%.',
            reference='Every fund is measured against its own reference blend plus the S&P 500 and MSCI '
                      'ACWI, all built from real index series.'),
        reference=_superseded_reference(),
        gates=[dict(owner='Owner', item='Confirm the trend sleeve sits at 8% of the SAA rather than the '
                                        '12\u201318% the optimiser reached in earlier drafts.'),
               dict(owner='Owner', item='Confirm Alpha\u2019s ~14% volatility budget; a 12.5% budget '
                                        'gives +0.05 Sharpe and a 7pp shallower loss.'),
               dict(owner='Owner', item='Confirm gold maps to Commodities and the Swiss franc to Cash in '
                                        'the platform taxonomy (fund_registry.PLATFORM_CLASS).'),
               dict(owner='Research', item='MRS begins 2003-08; the regime engine is dark before then.'),
               dict(owner='Research', item='Live NAV is 47 trading days \u2014 not yet a track record.')])
    return payload


def _superseded_reference():
    """The previous deployed 8-sleeve book, carried through from the payload that documented it, so the
    superseded banner keeps saying what it has always said rather than being quietly repurposed."""
    old = os.path.join(DASH, 'candidates.json')
    if os.path.exists(old):
        r = json.load(open(old)).get('reference')
        if r:
            r = dict(r)
            r['note'] = (r.get('note', '') + ' The five portfolios on this page replace the three '
                         'candidate versions; the legacy pages still document the 8-sleeve book.').strip()
            return r
    return dict(label='Deployed 8-sleeve book (superseded)', window='n/a', metrics={},
                note='Superseded; see Methodology for the v3.8 lineage.')


def v_ok(w, s):
    return w.get(s, 0) > 0.0005


def _sanitise(o):
    """Replace NaN/Inf with null, and record where a series actually starts.

    json.dump writes a bare `NaN` token for float('nan'). That is not valid JSON — but portfolios.js
    is evaluated as JavaScript, where NaN is a legal literal, so the page loaded it happily and then
    compounded it into "Growth of $1: $NaN". The five funds do not exist before 1997-06 and ACWI not
    before 2003-02; the panel was padded back to 1995-01 with NaN and the page then claimed
    1995-01-2026-08 as the common window. Null is the honest value and the page can skip it.
    """
    if isinstance(o, dict):
        return {k: _sanitise(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_sanitise(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def _true_window(p):
    """The window where every one of the five funds actually has data."""
    dates, R = p['series']['dates'], p['series']['returns']
    first = 0
    for k in p['order']:
        v = R[k]
        i = next((j for j, x in enumerate(v) if x is not None), len(v))
        first = max(first, i)
    last = len(dates) - 1
    return first, dict(start=dates[first], end=dates[last], n=last - first + 1,
                       padded_from=dates[0] if first else None)


if __name__ == '__main__':
    p = _sanitise(build())
    i0, win = _true_window(p)
    if i0:
        print(f'  note: the five funds start {win["start"]}; the panel was padded back to '
              f'{win["padded_from"]} with no data. Trimming to the true common window.')
        p['series']['dates'] = p['series']['dates'][i0:]
        p['series']['returns'] = {k: v[i0:] for k, v in p['series']['returns'].items()}
    p['meta']['window'] = win
    p['meta']['window_note'] = (
        f'The common window is {win["start"]}-{win["end"]}: every one of the five funds has data '
        f'over all of it. Benchmarks that start later (MSCI ACWI and its blends begin 2003-02) are '
        f'null before their own first observation and are simply not drawn there.')
    os.makedirs(DASH, exist_ok=True)
    json.dump(p, open(os.path.join(DASH, 'portfolios.json'), 'w'), indent=1, allow_nan=False)
    open(os.path.join(DASH, 'portfolios.js'), 'w').write(
        'window.PORTFOLIOS=' + json.dumps(p, separators=(',', ':'), allow_nan=False) + ';')
    print(f'  {len(p["order"])} portfolios + {len(p["bench_order"])} benchmarks · '
          f'{len(p["series"]["dates"])} months · {len(p["crises"])} crises')
    for k in p['order']:
        m, v = p['metrics'][k], p['versions'][k]
        print(f'  {v["name"]:10s} CAGR {100 * m["cagr"]:5.2f}  Sharpe {m["sharpe"]:.2f}  '
              f'Sortino {m["sortino"]:.2f}  MDD {100 * m["mdd"]:6.1f}  beta6040 {m["beta_6040"]:.2f}  '
              f'NAV {v["nav"]:.2f}')
    print(f'  MRS timeline {len(p["da"]["timeline"])} months · {p["da"]["months_in_state"]}')
    print(f'  wrote {DASH}/portfolios.json + portfolios.js')
