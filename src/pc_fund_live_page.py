#!/usr/bin/env python3
"""Builds the live fund page from the NAV feed and the v6 strategy contract."""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fund_nav as FN  # noqa: E402  fee, dealing cost and rebalance band — read, never re-typed
import fund_registry as FR  # noqa: E402  identity: reference, horizon, how each fund is run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REP = os.path.join(ROOT, 'Research/Portfolio_Construction/reports/fund_suite')
NAVD = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_nav')
SUITE = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_suite_v6')
DASH = os.path.join(ROOT, 'Research/Portfolio_Construction/dashboard/data')

N = json.load(open(os.path.join(NAVD, 'fund_nav.json')))
S = json.load(open(os.path.join(SUITE, 'fund_suite_v6.json')))
FUNDS = ['Certain', 'Endowment', 'SAA', 'DAA', 'Alpha']
BENCH = ['S&P 500', 'MSCI ACWI', 'Bloomberg US Aggregate']
nav = pd.DataFrame(N['series'], index=pd.to_datetime(N['dates']))

stats = {}
for c in nav.columns:
    s = nav[c]
    r = s.pct_change().dropna()
    dd = s / s.cummax() - 1
    stats[c] = dict(nav=float(s.iloc[-1]), ret=float(s.iloc[-1] / N['nav0'] - 1),
                    vol=float(r.std() * np.sqrt(252)), maxdd=float(dd.min()),
                    best=float(r.max()), worst=float(r.min()),
                    up=int((r > 0).sum()), n=int(len(r)))
# excess vs each fund's own reference, and vs every benchmark
rel = {}
for f in FUNDS:
    rel[f] = {}
    for b in BENCH:
        x, y = nav[f].pct_change().dropna(), nav[b].pct_change().dropna()
        rel[f][b] = dict(excess=float(stats[f]['ret'] - stats[b]['ret']),
                         te=float((x - y).std() * np.sqrt(252)),
                         beta=float(np.cov(x, y)[0, 1] / np.var(y)))

# ---- each portfolio's own reference ------------------------------------------------------------
# A fund is measured against its own benchmark, not against whichever index is handy. The registry
# declares references like "ACWI 40 / Agg 60"; ACWI and the Aggregate are both priced here, so the
# blend is built from them and rebalanced daily. Alpha's reference is the S&P 500, already priced.
_IDX = {'ACWI': 'MSCI ACWI', 'Agg': 'Bloomberg US Aggregate', 'S&P 500': 'S&P 500'}


def reference_series(spec):
    if spec in nav.columns:
        return nav[spec]
    parts = [q.strip().split() for q in spec.split('/')]
    legs = [(_IDX[' '.join(q[:-1])], float(q[-1]) / 100.0) for q in parts]
    if abs(sum(w for _, w in legs) - 1) > 1e-9:
        raise SystemExit('reference %r does not weight to 100' % spec)
    r = sum(nav[c].pct_change().fillna(0.0) * w for c, w in legs)
    return N['nav0'] * (1 + r).cumprod()


REF_OF = {f: FR.FUNDS[f.lower()]['reference'] for f in FUNDS}
for _spec in sorted(set(REF_OF.values())):
    if _spec not in nav.columns:
        nav[_spec] = reference_series(_spec)

# ---- standard period returns -------------------------------------------------------------------
# Factsheet convention: discrete CUMULATIVE returns over calendar lookbacks, and no annualisation
# under twelve months. A period the fund did not exist for is omitted, not shown part-filled — a
# "3M" cell quietly holding 2 months of history is the way a short record gets overstated.
LOOKBACKS = [('1M', 1), ('3M', 3), ('6M', 6), ('12M', 12)]


def period_returns(s):
    out, end = {}, s.index[-1]
    for lbl, m in LOOKBACKS:
        start = end - pd.DateOffset(months=m)
        out[lbl] = None if s.index[0] > start else float(s.iloc[-1] / s.asof(start) - 1)
    out['SI'] = float(s.iloc[-1] / N['nav0'] - 1)
    return out


periods = {c: period_returns(nav[c]) for c in nav.columns}

# Calendar-month returns. The first and last months are partial — the fund launched mid-July and
# today is mid-month — so each is flagged rather than silently presented as a full month.
_mk = nav.index.to_period('M')
monthly = {}
for c in nav.columns:
    out = []
    for per in sorted(set(_mk)):
        seg = nav[c][_mk == per]
        first = seg.index[0]
        base = N['nav0'] if first == nav.index[0] else float(nav[c][nav.index < first].iloc[-1])
        out.append(dict(month=str(per), ret=float(seg.iloc[-1] / base - 1),
                        partial=bool(per == sorted(set(_mk))[0] or per == sorted(set(_mk))[-1]),
                        days=int(len(seg))))
    monthly[c] = out

# Drawdown from the running high, and the latest one-day move — the two things a NAV page is asked
# for that the table did not carry.
drawdown = {c: [float(x) for x in (nav[c] / nav[c].cummax() - 1)] for c in nav.columns}
day = {c: dict(chg=float(nav[c].iloc[-1] / nav[c].iloc[-2] - 1),
               pts=float(nav[c].iloc[-1] - nav[c].iloc[-2]),
               dd=float(nav[c].iloc[-1] / nav[c].max() - 1)) for c in nav.columns}

# Factor attribution, if factor_attrib.py has run. It is optional the same way pit_backtest and
# style_box are: the page degrades to the holdings bridge alone rather than failing.
_fa = os.path.join(NAVD, 'factor_attrib.json')
factor = json.load(open(_fa)) if os.path.exists(_fa) else None
if factor is None:
    print('  note: factor_attrib.json absent — the exposure view will not render')

# ---- exposure, on the platform's own taxonomies -------------------------------------------------
# Two class views, because the platform deliberately keeps two and the crosswalk between them is an
# owner-confirmed decision (fund_registry.PLATFORM_CLASS): the portfolios' methodology classes drive
# the optimiser, the platform's six drive the shared components. Both are built from the LIVE
# holdings, not the policy weights, so the page shows what is actually held today.
#
# Geography is given for the EQUITY sleeves only. US / developed ex-US / emerging is unambiguous
# there. Assigning a geography to gold, broad commodities or a trend sleeve would be inventing a
# mapping that appears in no approved document, so it is not done.
GEO = {'US_EQ': 'United States', 'DM_EQ': 'Developed ex-US', 'EM_EQ': 'Emerging markets'}
SLEEVE_OF = N['ticker_sleeve']
exposure = {}
for f in FUNDS:
    h = N['holdings'][f]
    tot = sum(h.values()) or 1.0
    by_sleeve = {}
    for t, w in h.items():
        sl = SLEEVE_OF.get(t, t)
        by_sleeve[sl] = by_sleeve.get(sl, 0.0) + w / tot
    meth, plat = {}, {}
    for sl, w in by_sleeve.items():
        meth[S['class_of'].get(sl, 'Other')] = meth.get(S['class_of'].get(sl, 'Other'), 0.0) + w
        plat[FR.PLATFORM_CLASS[sl]] = plat.get(FR.PLATFORM_CLASS[sl], 0.0) + w
    eq = {GEO[sl]: w for sl, w in by_sleeve.items() if sl in GEO}
    eq_tot = sum(eq.values())
    exposure[f] = dict(
        methodology={k: round(100 * v, 2) for k, v in meth.items()},
        platform={k: round(100 * v, 2) for k, v in plat.items()},
        sleeves={S['labels'].get(k, k): round(100 * v, 2)
                 for k, v in sorted(by_sleeve.items(), key=lambda kv: -kv[1])},
        equity_geography={k: round(100 * v / eq_tot, 2) for k, v in eq.items()} if eq_tot else {},
        equity_weight=round(100 * eq_tot, 2))

# ---- what separates five multi-asset books -----------------------------------------------------
# Income yield, weighted from what each book actually holds today, and its sensitivity to the two
# things that drive a multi-asset portfolio: equity direction and rates. The sensitivities come from
# the factor model, so they are measured rather than declared. Effective duration is deliberately
# absent — see vehicle_data.py; the rate exposure is the sourced answer to the same question.
_vd = os.path.join(NAVD, 'vehicle_data.json')
chars = None
if os.path.exists(_vd):
    VD = json.load(open(_vd))['vehicles']
    chars = {}
    for f in FUNDS:
        h = N['holdings'][f]
        tot = sum(h.values())
        missing = [t for t in h if t not in VD]
        if missing:
            raise SystemExit('%s holds %s with no reference data — rerun Src/vehicle_data.py'
                             % (f, ', '.join(missing)))
        ytm = sum(w * VD[t]['yield_'] for t, w in h.items()) / tot
        fx = (factor or {}).get('funds', {}).get(f)
        gx = (lambda n: next((x['exposure'] for x in fx['factors'] if x['name'] == n), None))             if fx else (lambda n: None)
        chars[f] = dict(
            income_yield=float(ytm),
            equity_beta=gx('Equity'), rate_beta=(None if not fx else
                                                 round(gx('Rates') + gx('Curve'), 3)),
            gold=gx('Gold'), trend=gx('Trend'),
            n_holdings=len(h), vol=stats[f]['vol'], maxdd=stats[f]['maxdd'],
            # CONSTRUCTION CONSTRAINT — the cap the optimiser was actually held to, read from the
            # build record. Not a mandate limit and not a "budget": where a declared cap was
            # infeasible, pc_fs6_build loosened it and recorded what it used, and that is what is
            # shown. Endowment's declared 16% CDaR / 22% drawdown was solved at 20% / 27.5%.
            dd_cap=-abs(float(S['info'][f]['ddcap'])) if S['info'][f].get('ddcap') else None,
            # `declared` in the build record is the declared CDaR, not a declared drawdown — pairing
            # it with the drawdown cap would put a mislabelled parameter on the page.
            cdar_cap=abs(float(S['info'][f]['cdar'])) if S['info'][f].get('cdar') else None,
            cdar_declared=abs(float(S['info'][f]['declared'])) if S['info'][f].get('declared') else None,
            dd_loosened=bool(S['info'][f].get('loosened')),
            categories=sorted({VD[t]['category'] for t in h if VD[t]['category']}))
else:
    print('  note: vehicle_data.json absent — characteristics will not render')

# The 3x3 style box: where each portfolio's US equity sleeve sits on size and style, and — priced
# over the live window by style_box.py — what each of the nine boxes actually paid.
_sb = os.path.join(SUITE, 'style_box.json')
stylebox = json.load(open(_sb)) if os.path.exists(_sb) else None
if stylebox is None:
    print('  note: style_box.json absent — the style box will not render')

# What the page shows of it: the Morningstar-style box per portfolio — where the US equity sleeve
# sits, and how much of the book that sleeve is. The full analysis (active vs the total market, what
# each box paid) stays on Attribution, which owns it; this is the product-page summary, same source.
style = None
if stylebox:
    _key = {FR.FUNDS[k]['name']: k for k in FR.ORDER}
    style = dict(sizes=stylebox['sizes'], styles=stylebox['styles'], window=stylebox['window'],
                 n_months=stylebox['n_months'], method=stylebox['method'],
                 market=dict(name=stylebox['market']['name'], grid=stylebox['market']['grid']),
                 funds={f: {k: stylebox['funds'][_key[f]][k]
                            for k in ('grid', 'dominant', 'r2', 'us_equity_weight',
                                      'size_active', 'style_active', 'vehicles')}
                        for f in FUNDS if _key.get(f) in stylebox['funds']})

# The NAV bridge, rolled from vehicles up to sleeves. fund_nav.py already proved it reconciles.
SLEEVE = N['ticker_sleeve']
bridge = {}
for f in FUNDS:
    b = N['bridge'][f]
    by_sleeve = {}
    for tk, v in b['holdings'].items():
        by_sleeve[SLEEVE.get(tk, tk)] = by_sleeve.get(SLEEVE.get(tk, tk), 0.0) + v
    bridge[f] = dict(vehicles=b['holdings'], sleeves=by_sleeve, dealing=b['dealing'],
                     fee=b['fee'], total=b['total'])

# How long the record actually is, so the page can state its own limits instead of the renderer
# hard-coding a judgement. Twelve months is the floor for annualising a return; risk statistics are
# conventionally quoted on thirty-six.
_months = (nav.index[-1] - nav.index[0]).days / 365.25 * 12
track = dict(trading_days=int(len(nav)), months=round(float(_months), 1),
             annualise_returns=bool(_months >= 12), risk_stats_meaningful=bool(_months >= 36),
             min_months_to_annualise=12, min_months_for_risk_stats=36,
             note=('Returns are cumulative, not annualised: the record is %.1f months long and the '
                   'convention is not to annualise under twelve.' % _months))

# ---- fund facts ---------------------------------------------------------------------------------
# The identity panel a factsheet leads with. Every value is read from the registry or the pricing
# constants. There is deliberately no fund size, units in issue or ISIN: these funds are notional,
# priced from market closes, and inventing a subscription record would be inventing a fund.
facts = {f: dict(color=FR.FUNDS[f.lower()]['color'],
                 reference=FR.FUNDS[f.lower()]['reference'], horizon=FR.FUNDS[f.lower()]['horizon'],
                 role=FR.FUNDS[f.lower()]['role'], managed=FR.FUNDS[f.lower()]['managed'],
                 fee_bps=round(FN.FEE_YR * 1e4), dealing_bps=round(FN.COST * 1e4),
                 band_bps=round(FN.BAND * 1e4), vehicle_cap=FN.CAP,
                 currency='USD', pricing='Dividend-adjusted market closes, daily',
                 distribution='Accumulating — income is reinvested in the NAV',
                 dealing=('Month-end signal, executed on a %.0fbp drift band' % (FN.BAND * 1e4))
                 if FR.FUNDS[f.lower()]['managed'] == 'active'
                 else 'Policy weights held, dealt on a %.0fbp drift band' % (FN.BAND * 1e4))
         for f in FUNDS}

D = dict(inception=N['inception'], asof=N['dates'][-1], nav0=N['nav0'],
         periods=periods, track=track, facts=facts, monthly=monthly, ref_of=REF_OF,
         ref_series={r: [round(float(x), 4) for x in nav[r]]
                     for r in sorted(set(REF_OF.values())) if r not in N['series']},
         ref_stats={f: dict(name=REF_OF[f],
                            ret=float(nav[REF_OF[f]].iloc[-1] / N['nav0'] - 1),
                            # Arithmetic, matching the `rel` table's "Excess". The two were
                            # different conventions — a NAV ratio here, a difference of cumulative
                            # returns there — so one page showed one word with two meanings.
                            excess=float((nav[f].iloc[-1] / N['nav0'] - 1)
                                         - (nav[REF_OF[f]].iloc[-1] / N['nav0'] - 1)))
                    for f in FUNDS},
         day=day, bridge=bridge, factor=factor,
         chars=chars, exposure=exposure, style=style,
         # Colour is a portfolio's identity across the whole platform. It is published from the
         # registry rather than re-typed in the renderer: the hand-copied map had drifted so far that
         # Certain was drawn in SAA's colour, SAA in DAA's, and DAA in a benchmark's.
         bench_colors={b['name']: b['color'] for b in FR.BENCHMARKS.values()},
         methodology_classes=S['classes'], platform_classes=FR.PLATFORM_CLASSES,
         dates=N['dates'], series=N['series'], stats=stats, rel=rel,
         holdings=N['holdings'], trades=N['trades'], books=N['books'], ticker_sleeve=N['ticker_sleeve'],
         funds={f: S['funds'][f] for f in FUNDS}, labels=S['labels'], class_of=S['class_of'],
         classes=S['classes'],
         backtest={f: S['table'][f + '|1997-2026'] for f in FUNDS},
         bench_list=BENCH, fund_list=FUNDS,
         regime=S['regime']['state'])
tpl = open(os.path.join(REP, 'fund_live_template.html')).read()
open(os.path.join(REP, 'Summer_Funds_Live.html'), 'w').write(
    tpl.replace('/*__DATA__*/null', json.dumps(D, default=float, separators=(',', ':'))))
os.makedirs(DASH, exist_ok=True)
json.dump(D, open(os.path.join(DASH, 'live_nav.json'), 'w'), default=float)
open(os.path.join(DASH, 'live_nav.js'), 'w').write(
    'window.LIVE_NAV=' + json.dumps(D, default=float, separators=(',', ':')) + ';')
print(f'  wrote {REP}/Summer_Funds_Live.html and the dashboard feed')
