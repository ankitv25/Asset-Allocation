#!/usr/bin/env python3
"""Builds the live fund page from the NAV feed and the v6 strategy contract."""
import json
import os
import sys

import numpy as np
import pandas as pd

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

D = dict(inception=N['inception'], asof=N['dates'][-1], nav0=N['nav0'],
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
