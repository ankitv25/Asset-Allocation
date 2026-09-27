#!/usr/bin/env python3
"""
Summer Funds v6 — Certain · Endowment · SAA (long-horizon growth) · DAA (the SAA book, tilted).

Three strategic books, each solved with its loss limit inside the optimizer, and one tactical fund that
expresses the SAA book through five tilt engines (valuation from a live CMA, trend, relative strength,
regime, diversifier sizing). Writes validation/fund_suite_v6/.
and reports/fund_suite/Summer_Funds_Family_Book.html.
"""
import io
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import fs3_core as V  # noqa: E402
import fs4_core as W4  # noqa: E402
import fs5_core as W5  # noqa: E402
import fs6_core as W6  # noqa: E402
import fs5_signals as SG  # noqa: E402
import fs_core as F  # noqa: E402

BUF = io.StringIO()
REP = os.path.join(os.path.dirname(__file__), '..', 'Research/Portfolio_Construction/reports/fund_suite')
REP = os.path.abspath(REP)


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    BUF.write(s + '\n')


def H(t):
    P('\n' + '=' * 118)
    P(t)
    P('=' * 118)


L = W6.load()
U = V.load(hedged=False)
M = W6.model(L)
W5.MANDATE['room'] = W6.DAA_SLEEVE_ROOM
R, RP = L['R'], L['RP']
mu, EST = M['mu_bl'], M['panel']
IN_M = [m for m in R.index if V.WIN[0] <= m <= V.WIN[1]]
PRE_M = [m for m in RP.index if F.PRE[0] <= m <= F.PRE[1]]
V1 = pd.read_csv(os.path.join(F.OUT, 'phase2_returns.csv'), index_col=0)
V1.index = pd.PeriodIndex(V1.index, freq='M')
cash = V1['Cash']
PL = json.load(open(os.path.join(F.OUT, 'peers', 'peer_landscape.json')))
WINS = {'1997-2007': F.PRE, '2007-2026': V.WIN, '1997-2026': F.LONG}
W6.FUNDS6['Alpha'] = W6.ALPHA_BOOK
W4.SWEEP[:] = W6.SWEEP6
STRAT = list(W6.FUNDS6)
FUNDS = ['Certain', 'Endowment', 'SAA', 'DAA', 'Alpha']
ENG = W5.ENGINES

# ---------------------------------------------------------------- standard benchmarks, from real indices
# MSCI ACWI from the ACWI fund, spliced before its launch to a 63/27/10 world-equity blend; the bond leg is
# the Bloomberg US Aggregate (AGG, spliced to its index fund). Russell is a US domestic index, so it is not
# used to benchmark a global multi-asset family.
_acwi = U['MR']['ACWI'].dropna()
_blend = (0.63 * U['R']['US_EQ'] + 0.27 * U['R']['DM_EQ'] + 0.10 * U['R']['EM_EQ'])
_blend_pre = (0.63 * U['RP']['US_EQ'] + 0.27 * U['RP']['DM_EQ'] + 0.10 * U['RP']['EM_EQ'])
_ov = _acwi.index.intersection(_blend.index)
WORLD = pd.concat([pd.concat([_blend_pre, _blend]).sort_index().loc[:_acwi.index.min() - 1], _acwi]).sort_index()
WORLD = WORLD[~WORLD.index.duplicated()]
_agg = U['MR']['AGG'].dropna()
_aggp = pd.concat([U['bonds_pre'].dropna(), U['bonds'].dropna()]).sort_index()
_aggp = _aggp[~_aggp.index.duplicated()]
AGG = pd.concat([_aggp.loc[:_agg.index.min() - 1], _agg]).sort_index()
AGG = AGG[~AGG.index.duplicated()]
blend = lambda eq: (eq * WORLD + (1 - eq) * AGG.reindex(WORLD.index)).dropna()

H('SUMMER FUNDS v6 — CERTAIN · ENDOWMENT · SAA · DAA · ALPHA')
P(f'  benchmarks: MSCI ACWI (the ACWI fund from {_acwi.index.min()}, spliced to a 63/27/10 world blend before, '
  f'correlation {_acwi.reindex(_ov).corr(_blend.reindex(_ov)):.3f} over {len(_ov)} months), the S&P 500, and '
  f'ACWI/Bloomberg US Aggregate blends at 80/20, 60/40 and 40/60.')

SAA, INFO, CURVE = {}, {}, {}
for f in STRAT:
    spec = W6.FUNDS6[f]
    b = spec['bands']
    curve = {}
    for cd in W4.SWEEP:
        w_, _ = V.solve_cdar(EST, mu, b, cdar=cd, ddcap=cd * (b['ddcap'] / b['cdar']))
        if w_ is None:
            continue
        r_, _ = V.run_static(w_, R, IN_M)
        curve[cd] = dict(mu=V.fwd(w_, M)['mu'], vol=V.fwd(w_, M)['vol'], maxdd=V.dd_stats(r_)['maxdd'],
                         equity=V.classes(w_)['Equity'], weights=w_.to_dict())
    CURVE[f] = curve
    w_raw, cd, dcap, _ = W4.solve_fund(EST, mu, b, M)
    wr, bad = V.round_repair(w_raw, b)
    r_saa, _ = V.run_static(wr, R, IN_M)
    d, fw = V.dd_stats(r_saa), V.fwd(wr, M)
    SAA[f] = wr
    INFO[f] = dict(cdar=cd, ddcap=dcap, declared=b['cdar'], loosened=bool(cd > b['cdar'] + 1e-9), fwd=fw, dd=d,
                   classes=V.classes(wr), bands_ok=not bad, live=wr.to_dict())
    P(f'\n  {f.upper()} — {spec["purpose"]}')
    P(f'    loss limit {100 * cd:.0f}% (declared {100 * b["cdar"]:.0f}%'
      f'{"; loosened to the tightest feasible inside the bands" if cd > b["cdar"] + 1e-9 else ""}) · '
      f'forward return {fw["mu"]:.2f}% · volatility {fw["vol"]:.2f}% · worst loss 2007-26 {d["maxdd"]:.1f}%')
    P('    ' + ' · '.join(f'{c} {100 * v:.1f}' for c, v in V.classes(wr).items()))
    P('    ' + ' '.join(f'{s} {100 * wr[s]:.1f}' for s in W6.S6 if wr[s] > 0.0005))

# ---------------------------------------------------------------- the DAA fund
H('THE DAA FUND — the SAA book, with its diversifiers sized by macro')
X = SG.macro()
E_IN = W5.engines(R, SAA['SAA'], X)
E_PRE = W5.engines(RP, SAA['SAA'], X)
T_IN, D_IN = W5.daa_targets(SAA['SAA'], E_IN, W6.FUNDS6['SAA']['bands'])
T_PRE, D_PRE = W5.daa_targets(SAA['SAA'], E_PRE, W6.FUNDS6['SAA']['bands'])
r_daa_in, W_IN = W5.run_daa5(T_IN, R, IN_M)
r_daa_pre, W_PRE = W5.run_daa5(T_PRE, RP, PRE_M)
W_DAA = pd.concat([W_PRE, W_IN])
live = T_IN.loc[max(T_IN.index)]
SAA['DAA'] = SAA['SAA']
INFO['DAA'] = dict(INFO['SAA'], live=live.to_dict(),
                   classes=V.classes(SAA['SAA']), fwd=V.fwd(SAA['SAA'], M),
                   dd=V.dd_stats(r_daa_in), turnover_yr=float(12 * (W_IN.diff().abs().sum(axis=1) / 2).mean()),
                   live_classes=V.classes(live), state=str(E_IN['_state'].dropna().iloc[-1]),
                   tilt=(live - SAA['SAA']).to_dict())
P(f'  mandate: one-sided tilt budget {W5.MANDATE["budget"]:.0f}pp · per sleeve at most '
  f'max({W5.MANDATE["sleeve_min"]:.0f}pp, {100 * W5.MANDATE["sleeve_cap"]:.0f}% of the strategic weight) · '
  f'never below {100 * W5.MANDATE["floor"]:.0f}% of it · rebalance band {W5.MANDATE["band"]:.1f}pp')
P(f'  engine budgets (one-sided, pp): ' + ' · '.join(f'{k} {W5.MANDATE[v]:.0f}' for k, v in
  [('valuation', 'val'), ('trend', 'trend'), ('relative strength', 'xsec'), ('regime', 'regime'),
   ('diversifier sizing', 'divsize')]))
_mf = E_IN['_mf_target'].dropna()
P(f'  trend sleeve: policy {100 * SAA["SAA"]["MF"]:.0f}% · macro range {T_IN["MF"].min() * 100:.1f}-{T_IN["MF"].max() * 100:.1f}% · '
  + ' · '.join(f'{s} {100 * T_IN["MF"][E_IN["_state"].reindex(T_IN.index) == s].mean():.1f}%'
               for s in SG.MRS_STATES
               if (E_IN['_state'].reindex(T_IN.index) == s).any()))
P(f'  turnover {INFO["DAA"]["turnover_yr"] * 100:.0f}%/yr · average gross tilt '
  f'{100 * (W_IN - SAA["SAA"]).abs().sum(axis=1).mean() / 2:.1f}pp · largest '
  f'{100 * (W_IN - SAA["SAA"]).abs().sum(axis=1).max() / 2:.1f}pp')
P(f'  today: regime "{INFO["DAA"]["state"]}" · ' + ' '.join(
    f'{s}{100 * (live[s] - SAA["SAA"][s]):+.1f}' for s in W6.S6 if abs(live[s] - SAA['SAA'][s]) > 0.002))
P('  all four engines run across the whole record: the yield curve reaches back to 1962 and corporate yields '
  'to 1919. The one gap is the inflation-linked pair (10-year real yield and breakeven), which begins in 2003, '
  'so the TIPS valuation view is dark before then and simply contributes nothing.')

# ---------------------------------------------------------------- record
H('RECORD — net of costs and a 15bp/yr fee')
RET = {}
for f in STRAT:
    ri, _ = V.run_static(SAA[f], R, IN_M)
    rp, _ = V.run_static(SAA[f], RP, PRE_M)
    RET[f] = pd.concat([rp, ri])
RET['SAA book, untilted'] = RET['SAA']
RET['Alpha book, untilted'] = RET['Alpha']
RET['DAA'] = pd.concat([r_daa_pre, r_daa_in])

# Alpha is an actively run portfolio and must be tilted in the backtest too — it was being reported
# static here while fund_nav.py ran it tilted, so the record and the priced book disagreed about what
# Alpha is. Same five engines, on Alpha's own wider mandate.
_saved = {k: W5.MANDATE.get(k) for k in W6.ALPHA_MANDATE}
W5.MANDATE.update(W6.ALPHA_MANDATE)
E_AL, E_AL_PRE = W5.engines(R, SAA['Alpha'], X), W5.engines(RP, SAA['Alpha'], X)
T_AL, _ = W5.daa_targets(SAA['Alpha'], E_AL, W6.FUNDS6['Alpha']['bands'])
T_AL_PRE, _ = W5.daa_targets(SAA['Alpha'], E_AL_PRE, W6.FUNDS6['Alpha']['bands'])
r_al_in, W_AL = W5.run_daa5(T_AL, R, IN_M)
r_al_pre, _ = W5.run_daa5(T_AL_PRE, RP, PRE_M)
for _k, _v in _saved.items():
    if _v is not None:
        W5.MANDATE[_k] = _v
RET['Alpha'] = pd.concat([r_al_pre, r_al_in])
INFO['Alpha'] = dict(INFO['Alpha'], live=T_AL.loc[max(T_AL.index)].to_dict(),
                     live_classes=V.classes(T_AL.loc[max(T_AL.index)]),
                     dd=V.dd_stats(r_al_in),
                     turnover_yr=float(12 * (W_AL.diff().abs().sum(axis=1) / 2).mean()),
                     tilt=(T_AL.loc[max(T_AL.index)] - SAA['Alpha']).to_dict())
P(f'\n  ALPHA tilted: turnover {100 * INFO["Alpha"]["turnover_yr"]:.0f}%/yr · '
  f'worst loss {INFO["Alpha"]["dd"]["maxdd"]:.1f}% (untilted {V.dd_stats(RET["Alpha book, untilted"].dropna())["maxdd"]:.1f}%)')
PEER = {'MSCI ACWI': WORLD, 'S&P 500': V1['US equity (SPY)'],
        'ACWI 80 / Agg 20': blend(0.80), 'ACWI 60 / Agg 40': blend(0.60), 'ACWI 40 / Agg 60': blend(0.40),
        'Bloomberg US Aggregate': AGG}
REFS = {**{f: W6.FUNDS6[f]['ref'] for f in STRAT}, 'DAA': W6.FUNDS6['SAA']['ref']}
ALL = {**{f: RET[f] for f in FUNDS}, **PEER}
TAB = {}
for wn, w in WINS.items():
    P(f'\n  [{wn}]' + ('  — the books were built here' if wn == '2007-2026' else '  — not used in construction'))
    P(f'  {"":28s} {"CAGR":>6s} {"vol":>5s} {"Shp":>5s} {"worst":>7s} {"CDaR5":>6s}')
    for bn, r in ALL.items():
        x = F.sub(r, w).dropna()
        if len(x) == 0 or x.index.min() > w[0]:
            continue
        m, d = F.metrics(x, cash), V.dd_stats(x)
        TAB[(bn, wn)] = dict(m, **d)
        P(f'  {bn:28s} {m["cagr"]:6.2f} {m["vol"]:5.1f} {m["sharpe"]:5.2f} {d["maxdd"]:7.1f} {d["cdar5"]:6.1f}')

H('WHAT THE TILTS ADD — the DAA fund against its own untilted book')
ADDS = {}
for wn, w in WINS.items():
    a, b_ = TAB[('SAA', wn)], TAB[('DAA', wn)]
    ADDS[wn] = dict(cagr=b_['cagr'] - a['cagr'], sharpe=b_['sharpe'] - a['sharpe'], maxdd=b_['maxdd'] - a['maxdd'])
    P(f'  {wn}  return {b_["cagr"] - a["cagr"]:+.2f}pp · Sharpe {a["sharpe"]:.2f} -> {b_["sharpe"]:.2f} · '
      f'worst loss {a["maxdd"]:.1f} -> {b_["maxdd"]:.1f}')

H('EACH ENGINE ON ITS OWN, AND WHAT IS LOST WITHOUT IT (2007-2026)')
ENG_C = {}
for k in ENG:
    only = {x: (E_IN[x] if x == k else E_IN[x] * 0) for x in ENG}
    drop = {x: (E_IN[x] * 0 if x == k else E_IN[x]) for x in ENG}
    row = {}
    for tag, Ek in [('only', only), ('without', drop)]:
        Tk, _ = W5.daa_targets(SAA['SAA'], Ek, W6.FUNDS6['SAA']['bands'])
        rk, Wk = W5.run_daa5(Tk, R, IN_M)
        m, d = F.metrics(rk, cash), V.dd_stats(rk)
        row[tag] = dict(cagr=m['cagr'], sharpe=m['sharpe'], maxdd=d['maxdd'],
                        turnover=float(12 * (Wk.diff().abs().sum(axis=1) / 2).mean()))
    full = TAB[('DAA', '2007-2026')]
    row['adds'] = dict(cagr=full['cagr'] - row['without']['cagr'], sharpe=full['sharpe'] - row['without']['sharpe'],
                       maxdd=full['maxdd'] - row['without']['maxdd'])
    ENG_C[k] = row
    P(f'  {k:18s} alone {row["only"]["cagr"]:5.2f}% / {row["only"]["sharpe"]:.3f} · '
      f'adds to the rest {row["adds"]["cagr"]:+.2f}pp return, {row["adds"]["sharpe"]:+.3f} Sharpe, '
      f'{row["adds"]["maxdd"]:+.1f}pp worst loss')

H('CRISES (cumulative %)')
EP = {'LTCM-98': ('1998-07', '1998-08'), 'Dot-com': ('2000-09', '2002-09'), 'GFC': ('2007-11', '2009-02'),
      'Euro-11': ('2011-05', '2011-09'), 'COVID': ('2020-02', '2020-03'), 'Rates 2022': ('2022-01', '2022-09')}


def cum(r, a, b):
    x = r[(r.index >= pd.Period(a, 'M')) & (r.index <= pd.Period(b, 'M'))].dropna()
    return float(100 * (np.prod(1 + x) - 1)) if len(x) else float('nan')


CRIS = {}
P(f'  {"":24s}' + ''.join(f'{k:>11s}' for k in EP))
for bn in FUNDS + list(PEER):
    r = RET[bn] if bn in RET else PEER[bn]
    CRIS[bn] = {k: cum(r, a, b_) for k, (a, b_) in EP.items()}
    P(f'  {bn:24s}' + ''.join(f'{CRIS[bn][k]:+11.1f}' for k in EP))

H('AGAINST THE BIG-MANAGER FLAGSHIP FUNDS (Sharpe rank, 1997-2026)')
rows = [(t, v['sharpe']) for k, v in PL['table'].items() for t in [k.split('|')[0]] if k.endswith('|Long') and t in PL['peers']]
rows += [(f, TAB[(f, '1997-2026')]['sharpe']) for f in FUNDS]
rows.sort(key=lambda x: -x[1])
RANK = {f: [r[0] for r in rows].index(f) + 1 for f in FUNDS}
P('  ' + ' · '.join(f'{f} #{RANK[f]}/{len(rows)}' for f in FUNDS))
P('  top 6: ' + ' · '.join(f'{n} {s:.2f}' for n, s in rows[:6]))

# ---------------------------------------------------------------- forward outcomes and stress
rng = np.random.default_rng(20260919)
Lc = np.linalg.cholesky(M['cov'].values / 12 + 1e-12 * np.eye(len(W6.S6)))
Z = rng.standard_normal((10000, 120, len(W6.S6))) @ Lc.T + mu / 12
FWD = {}
for f in FUNDS:
    pr = Z @ SAA[f].values - F.FUND_FEE / 12
    g = np.cumprod(1 + pr, axis=1)
    ann = g[:, -1] ** 0.1 - 1
    dd = (g / np.maximum.accumulate(g, axis=1) - 1).min(axis=1)
    FWD[f] = dict(p10=float(100 * np.percentile(ann, 10)), p50=float(100 * np.percentile(ann, 50)),
                  p90=float(100 * np.percentile(ann, 90)), dd_median=float(100 * np.median(dd)),
                  p_loss=float((ann < 0).mean()))
SC = json.load(open(os.path.join(V.OUT, 'phase2_results.json')))['scenarios_def']
SCEN = {}
for nm, sh in SC.items():
    v = pd.Series(sh).reindex(W6.S6).fillna(0.0)   # no currency shock is modelled in these scenarios
    SCEN[nm] = {f: float(SAA[f] @ v) for f in STRAT}
    SCEN[nm]['DAA'] = float(INFO['DAA']['live'] and pd.Series(INFO['DAA']['live'])[W6.S6] @ v)
    eq = 0.63 * sh['US_EQ'] + 0.27 * (sh['DM_EQ'] - 3) + 0.10 * sh['EM_EQ']
    bd = 0.6 * sh['UST'] + 0.2 * sh['USTL'] + 0.2 * sh['IG']
    SCEN[nm]['ACWI 40 / Agg 60'] = 0.4 * eq + 0.6 * bd
    SCEN[nm]['ACWI 60 / Agg 40'] = 0.6 * eq + 0.4 * bd
    SCEN[nm]['ACWI 80 / Agg 20'] = 0.8 * eq + 0.2 * bd
    SCEN[nm]['S&P 500'] = sh['US_EQ']
H('FORWARD 10-YEAR OUTCOMES AND STRESS SCENARIOS')
for f in FUNDS:
    P(f'  {f:12s} poor decade {FWD[f]["p10"]:5.2f}% · median {FWD[f]["p50"]:5.2f}% · good {FWD[f]["p90"]:5.2f}% · '
      f'typical worst loss {FWD[f]["dd_median"]:.1f}% · chance of losing money over ten years {100 * FWD[f]["p_loss"]:.1f}%')
P(f'\n  {"scenario":40s}' + ''.join(f'{f[:14]:>16s}' for f in FUNDS))
for nm in SC:
    P(f'  {nm:40s}' + ''.join(f'{SCEN[nm][f]:16.1f}' for f in FUNDS))

# ---------------------------------------------------------------- attribution, references, risk
H('ATTRIBUTION, REFERENCES AND RISK')
ATTR, RISK, BENCH, TILT_ATTR = {}, {}, {}, {}
WMAP = {}
for f in STRAT:
    Wi = V.run_static(SAA[f], R, IN_M)[1]
    Wp = V.run_static(SAA[f], RP, PRE_M)[1]
    WMAP[f] = pd.concat([Wp, Wi])
WMAP['DAA'] = W_DAA
Rall = pd.concat([RP.loc[PRE_M[0]:PRE_M[-1]], R.loc[IN_M[0]:IN_M[-1]]])
for f in FUNDS:
    W = WMAP[f]
    contrib = W * Rall.reindex(W.index)[W6.S6].fillna(0)
    ATTR[f] = {wn: {s: float(12 * 100 * contrib[(contrib.index >= w[0]) & (contrib.index <= w[1])][s].mean())
                    for s in W6.S6} for wn, w in WINS.items()}
    wv = (pd.Series(INFO['DAA']['live'])[W6.S6] if f == 'DAA' else SAA[f]).values
    tot = float(wv @ M['cov'].values @ wv)
    rc = pd.Series(wv * (M['cov'].values @ wv) / tot, index=W6.S6)
    RISK[f] = dict(by_sleeve=rc.to_dict(),
                   by_class={c: float(sum(rc[s] for s in W6.S6 if W6.CLASS6[s] == c)) for c in W6.CLASSES6},
                   effective_n=float(1 / (rc.clip(lower=0) ** 2).sum()), vol=float(100 * np.sqrt(tot)))
    RISK[f]['weights'] = dict(zip(W6.S6, wv))
    BENCH[f] = {}
    refs = list(dict.fromkeys([REFS[f], 'MSCI ACWI', 'S&P 500']
                              + (['SAA book, untilted'] if f == 'DAA' else [])))
    for rn in refs:
        y_ = RET['SAA'] if rn == 'SAA book, untilted' else PEER[rn]
        x = F.sub(RET[f], F.LONG).dropna()
        y = y_.reindex(x.index).dropna()
        x = x.reindex(y.index)
        act = x - y
        up, dn = y > 0, y <= 0
        BENCH[f][rn] = dict(
            excess=float(100 * (((1 + x).prod() ** (12 / len(x))) - ((1 + y).prod() ** (12 / len(y))))),
            te=float(100 * act.std() * np.sqrt(12)), up=float(x[up].mean() / y[up].mean()),
            down=float(x[dn].mean() / y[dn].mean()), hit=float((act > 0).mean()))
        BENCH[f][rn]['ir'] = BENCH[f][rn]['excess'] / BENCH[f][rn]['te']
    a = ATTR[f]['1997-2026']
    P(f'\n  {f}')
    P('    return from: ' + ' · '.join(f'{k} {v:+.2f}' for k, v in sorted(a.items(), key=lambda kv: -kv[1])[:5]))
    P('    risk from:   ' + ' · '.join(f'{c} {100 * v:.0f}%' for c, v in RISK[f]['by_class'].items() if abs(v) > 0.005)
      + f' · {RISK[f]["effective_n"]:.1f} effective sources')
    for rn, b_ in BENCH[f].items():
        P(f'    vs {rn:22s} excess {b_["excess"]:+.2f}%/yr · tracking error {b_["te"]:5.1f}% · '
          f'up {b_["up"]:.2f} · down {b_["down"]:.2f}')

# what each engine contributed to the DAA's return, by window
for k in ENG:
    dk = E_IN[k].reindex(W_IN.index).fillna(0) / 100
    TILT_ATTR[k] = {wn: float(12 * 100 * (dk * R.reindex(dk.index)[W6.S6].fillna(0))
                              [(dk.index >= w[0]) & (dk.index <= w[1])].sum(axis=1).mean())
                    for wn, w in WINS.items() if w[1] >= V.WIN[0]}

# ---------------------------------------------------------------- outputs
ETF_CAP = 0.20
IMPL_SPLIT = {'US_EQ': ['VOO', 'IVV', 'SPLG', 'VTI'], 'UST': ['VGIT', 'SCHR', 'IEF'], 'USTL': ['VGLT', 'TLT'],
              'DM_EQ': ['DBEF'], 'EM_EQ': ['VWO'], 'TIPS': ['SCHP'], 'IG': ['VCIT', 'VCLT'], 'HY': ['USHY'],
              'REIT': ['VNQ'], 'INFRA': ['GII', 'IGF'], 'CMDTY': ['PDBC', 'DBC'], 'GOLD': ['GLDM', 'IAU'],
              'MF': ['DBMF', 'KMLM'], 'CHF': ['FXF'], 'Cash': ['T-bills']}
CAPS = {}
for f in FUNDS:
    w_ = pd.Series(INFO[f]['live'])[W6.S6]
    hold = {}
    for s in W6.S6:
        if w_[s] < 0.0005:
            continue
        tick = IMPL_SPLIT[s]
        n = max(1, int(np.ceil(w_[s] / ETF_CAP)))
        n = min(n, len(tick))
        for t in tick[:n]:
            hold[t] = w_[s] / n
    over = {t: v for t, v in hold.items() if v > ETF_CAP + 1e-9 and t != 'T-bills'}
    CAPS[f] = dict(holdings=hold, breaches=over, n=len(hold))
P(f'\n  platform caps: ' + ' · '.join(
    f'{f} {CAPS[f]["n"]} holdings, largest {100 * max(v for t, v in CAPS[f]["holdings"].items() if t != "T-bills"):.1f}%'
    + (' BREACH' if CAPS[f]['breaches'] else '') for f in FUNDS))

contract = dict(
    funds={f: dict(purpose=W6.FUNDS6['SAA' if f == 'DAA' else f]['purpose'] if f != 'DAA' else
                   'The SAA book with its diversifiers sized by macro, expressed through five tilt engines',
                   horizon=W6.FUNDS6['SAA' if f == 'DAA' else f]['horizon'],
                   identity=(W6.FUNDS6['SAA'] if f == 'DAA' else W6.FUNDS6[f])['identity'],
                   ref=REFS[f]) for f in FUNDS},
    info={f: dict(INFO[f], saa=SAA[f].to_dict()) for f in FUNDS},
    table={f'{a}|{b}': v for (a, b), v in TAB.items()},
    windows={k: [str(a), str(b)] for k, (a, b) in WINS.items()},
    crises=CRIS, crisis_def={k: [a, b] for k, (a, b) in EP.items()}, forward=FWD, scenarios=SCEN,
    scenarios_def=SC, rank=RANK, n_peers=len(rows), adds=ADDS, engines=ENG_C, tilt_attr=TILT_ATTR,
    attribution=ATTR, risk=RISK, bench=BENCH, caps=CAPS,
    curve={f: [dict(cdar=float(k), mu=v['mu'], vol=v['vol'], maxdd=v['maxdd'], equity=v['equity'])
               for k, v in sorted(CURVE[f].items(), key=lambda kv: float(kv[0]))] for f in STRAT},
    cma=M['cma'].to_dict(orient='index'), mandate={k: v for k, v in W5.MANDATE.items() if k != 'widen'},
    mf_range=[float(T_IN['MF'].min()), float(T_IN['MF'].max())],
    mf_by_state={st: float(T_IN['MF'][E_IN['_state'].reindex(T_IN.index) == st].mean())
                 for st in SG.MRS_STATES
                 if (E_IN['_state'].reindex(T_IN.index) == st).any()},
    regime=dict(state=str(INFO['DAA']['state']),
                history={str(k): v for k, v in E_IN['_state'].dropna().items()},
                source='MRS (Research/MRS) regime_confirmed; tilts from the Playbook regime books',
                states=SG.MRS_STATES,
                tilts={k: {c: round(float(x), 3) for c, x in v.items()}
                       for k, v in W5.REGIME_CLASS_TILT.items()}),
    labels=W6.LABEL6, impl=W6.IMPL6, classes=W6.CLASSES6, class_of=W6.CLASS6,
    peers=[k for k in PEER], strat=STRAT,
    growth={'months': [str(m) for m in F.sub(RET['Certain'], F.LONG).index],
            'series': {**{f: [float(x) for x in F.sub(RET[f], F.LONG).values] for f in FUNDS},
                       **{k: [float(x) for x in F.sub(v, F.LONG).reindex(
                           F.sub(RET['Certain'], F.LONG).index).fillna(0).values] for k, v in PEER.items()}}})
os.makedirs(W6.OUT, exist_ok=True)
json.dump(contract, open(os.path.join(W6.OUT, 'fund_suite_v6.json'), 'w'), indent=1, default=float)
pd.DataFrame({**{f: RET[f] for f in FUNDS},
              **{k: RET[k] for k in RET if k.endswith('untilted')},
              **PEER, 'Cash': cash}).to_csv(os.path.join(W6.OUT, 'returns.csv'))
W_DAA.to_csv(os.path.join(W6.OUT, 'daa_weights.csv'))
open(os.path.join(W6.OUT, 'phase_output.txt'), 'w').write(BUF.getvalue())
P(f'\n  wrote {W6.OUT}')

tpl = open(os.path.join(REP, 'fund_suite_v6_template.html')).read()
out = os.path.join(REP, 'Summer_Funds_Family_Book.html')
open(out, 'w').write(tpl.replace('/*__DATA__*/null', json.dumps(contract, default=float, separators=(',', ':'))))
P(f'  wrote {out}')
