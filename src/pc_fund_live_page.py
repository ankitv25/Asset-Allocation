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
facts = {f: dict(reference=FR.FUNDS[f.lower()]['reference'], horizon=FR.FUNDS[f.lower()]['horizon'],
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
         periods=periods, track=track, facts=facts,
         dates=N['dates'], series=N['series'], stats=stats, rel=rel,
         holdings=N['holdings'], trades=N['trades'], books=N['books'], ticker_sleeve=N['ticker_sleeve'],
         funds={f: S['funds'][f] for f in FUNDS}, labels=S['labels'], class_of=S['class_of'],
         classes=S['classes'], info={f: S['info'][f] for f in FUNDS},
         backtest={f: S['table'][f + '|1997-2026'] for f in FUNDS},
         bench_list=BENCH, fund_list=FUNDS,
         regime=S['regime']['state'], mf_by_state=S['mf_by_state'])
tpl = open(os.path.join(REP, 'fund_live_template.html')).read()
open(os.path.join(REP, 'Summer_Funds_Live.html'), 'w').write(
    tpl.replace('/*__DATA__*/null', json.dumps(D, default=float, separators=(',', ':'))))
os.makedirs(DASH, exist_ok=True)
json.dump(D, open(os.path.join(DASH, 'live_nav.json'), 'w'), default=float)
open(os.path.join(DASH, 'live_nav.js'), 'w').write(
    'window.LIVE_NAV=' + json.dumps(D, default=float, separators=(',', ':')) + ';')
print(f'  wrote {REP}/Summer_Funds_Live.html and the dashboard feed')
