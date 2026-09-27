"""
fs5_core.py — Summer Funds v5: Certain · Endowment · SAA (long-horizon growth) · DAA (SAA, tilted).

Three strategic books, each solved with its loss limit inside the optimizer (the v3/v4 method), and one
tactical fund that expresses the SAA book through four tilt engines. The DAA is a fund, not a layer
bolted onto every book, and it is built to add return rather than to sell down into T-bills.
"""
import json
import os

import numpy as np
import pandas as pd

import fs3_core as V
import fs4_core as W
import fs5_signals as G
import fs_core as F
import fund_registry as FR

OUT = V.OUT.replace('fund_suite_v3', 'fund_suite_v5')
os.makedirs(OUT, exist_ok=True)
S5, RISKY5, CLASS5, CLASSES5 = V.S3, V.RISKY3, V.CLASS3, V.CLASSES3
LABEL5, IMPL5 = V.LABEL3, V.IMPL3
DUR = {'UST': 5.4, 'USTL': 16.3}
VAL_SLEEVES = ['UST', 'USTL', 'TIPS', 'IG', 'HY']       # where forward return is observable

FUNDS5 = {
    'Certain': dict(horizon='3+ years', peer='Paper 30/70', real_peer='AOM (real 40/60)',
                    purpose='Preserve capital and earn a positive real return in every regime',
                    bands=W._bands((0.15, 0.35), (0.50, 0.65), (0.20, 0.35), (0.05, 0.15), (0.12, 0.18),
                                   (0.06, 0.08), (0.02, 0.05), (0.00, 0.04), (0.00, 0.05), (0.08, 0.18),
                                   (0.35, 0.60), (0.00, 0.20), (0.02, 0.15), 0.07, 0.06, 0.08)),
    'Endowment': dict(horizon='10+ years', peer='Paper 60/40', real_peer='AOR (real 60/40)',
                      purpose='Long-horizon compounding on equity, real assets and liquid diversifiers',
                      bands=W._bands((0.38, 0.52), (0.55, 0.70), (0.17, 0.30), (0.05, 0.13), (0.18, 0.23),
                                     (0.06, 0.08), (0.02, 0.05), (0.02, 0.05), (0.03, 0.06), (0.12, 0.18),
                                     (0.15, 0.28), (0.00, 0.15), (0.02, 0.10), 0.11, 0.14, 0.19)),
    'SAA': dict(horizon='20+ years', peer='Paper 80/20', real_peer='AOA (real 80/20)',
                purpose='The house policy portfolio: 20–30 year compounding, growth-led but diversified',
                bands=W._bands((0.48, 0.65), (0.58, 0.75), (0.15, 0.30), (0.05, 0.14), (0.13, 0.18),
                               (0.06, 0.08), (0.02, 0.05), (0.02, 0.05), (0.00, 0.05), (0.08, 0.15),
                               (0.10, 0.25), (0.00, 0.15), (0.02, 0.08), 0.13, 0.20, 0.26)),
}

# --------------------------------------------------------------- the DAA fund's mandate
# The philosophy sets the SAA. The DAA fund's mandate is a declared tactical range around it: it may
# lean, it may not rebuild the portfolio. Caps are in percentage points of the fund.
MANDATE = dict(
    # Each engine gets a one-sided budget: the sum of everything it wants to buy, in points of the fund.
    val=6.0,          # valuation — the CMA rebuilt from today's market, on the sleeves that carry a yield
    trend=6.0,        # trend — rotation between sleeves, with a bounded de-risk only when breadth collapses
    xsec=4.0,         # relative strength inside each class, sums to zero so the class structure is untouched
    regime=3.0,       # the regime vector, set from economics before any backtest
    divsize=6.0,      # diversifier sizing — how big the trend sleeve should be given the macro state
    derisk=8.0,       # the most the trend engine may move to T-bills when everything is falling
    sleeve_cap=0.35,  # per-sleeve deviation: max(3pp, 35% of the strategic weight)
    sleeve_min=3.0,
    floor=0.50,       # never below half the strategic weight — a tilt, never an overwrite
    ceil=1.75,
    div_lo=0.45,      # the trend sleeve may fall to this fraction of its policy weight in calm disinflation
    div_hi=1.90,      # and rise to this in inflationary stress
    cash_max=10.0,    # T-bills are the residual: the fund may raise this much cash, band permitting
    budget=12.0,      # total one-sided deviation from the SAA book
    band=0.60,        # no-trade band per sleeve, pp
    widen=dict(Equity=0.10, Defensive=0.10, **{'Real assets': 0.05, 'Diversifiers': 0.05, 'Cash': 0.10}),
)

# The regime view is NOT invented here. The platform already answers "what does this regime imply for
# allocation": Research/Portfolio_Construction — the four regime-optimised books in the Playbook
# (dashboard/data/playbook.json), each with class weights against the static base, plus a per-regime
# shrink factor. This reads that evidence and uses the book-minus-base delta as the regime tilt, so the
# portfolios express the house playbook rather than a second opinion.
PLAYBOOK_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'Research/Portfolio_Construction/dashboard/data/playbook.json')


def regime_class_tilts(path=PLAYBOOK_JSON):
    """{MRS state: {platform class: tilt in pp}} from the Playbook's own regime books."""
    with open(path) as f:
        pb = json.load(f)
    base = pb['static']['classes']
    out = {}
    for state, book in pb['books'].items():
        shrink = float(pb['regime_defs'].get(state, {}).get('shrink', 1.0))
        out[state] = {c: 100.0 * (book['classes'].get(c, 0.0) - base.get(c, 0.0)) * shrink
                      for c in base}
    return out


def _zero(d):
    v = pd.Series(d, index=S5).fillna(0.0)
    return v - v.mean()


REGIME_CLASS_TILT = regime_class_tilts()
ENGINES = ['Valuation', 'Trend', 'Relative strength', 'Regime', 'Diversifier sizing']


def _scale(t, cap):
    """Scale a tilt vector so its largest single move is `cap` percentage points."""
    m = t.abs().max()
    return t * (cap / m) if m > 1e-9 else t


def _budget(T, cap):
    """Scale each month's tilt vector down to a one-sided budget: what it buys totals at most `cap` pp."""
    gross = T.clip(lower=0).sum(axis=1)
    k = (cap / gross.replace(0, np.nan)).clip(upper=1.0).fillna(1.0)
    return T.mul(k, axis=0)


def engines(R, w_saa, X=None):
    """The four tilt engines, monthly, each already in percentage points of the fund.

    Every input is lagged: `R` is realised returns, and a signal stamped on month t is built only from
    months up to t-1, so the weight held through month t was knowable before month t began."""
    X = G.macro() if X is None else X
    idx = R.index
    w_saa = w_saa.reindex(S5).fillna(0.0)
    E = {}

    # 1. valuation — what today's market pays for duration and credit, against what it has paid before.
    # The quantity judged is the premium over T-bills, which is what the CMA is built on and what decides
    # whether the risk is worth owning; the yield level itself drifts for decades and says little.
    y = G.live_cma(X, DUR).reindex(idx)
    prem = pd.DataFrame({s: y[s] - y['Cash'] for s in VAL_SLEEVES}, index=idx)
    z = pd.DataFrame({s: G._ez(prem[s]) for s in VAL_SLEEVES}, index=idx)
    val = pd.DataFrame(0.0, index=idx, columns=S5)
    for s in VAL_SLEEVES:
        val[s] = (z[s] / 1.5).clip(-1, 1) * 4.0
    # what the view funds, or is funded by, is the rest of the book pro rata — not a cash park
    rest = [s for s in S5 if s not in VAL_SLEEVES]
    wr = w_saa.reindex(rest).fillna(0.0)
    wr = wr / wr.sum() if wr.sum() > 0 else wr
    val[rest] = -np.outer(val[VAL_SLEEVES].sum(axis=1).values, wr.values)
    E['Valuation'] = _budget(val.fillna(0.0), MANDATE['val'])

    # 2. trend — rotation first, de-risking only when breadth collapses
    e1 = W.e1(R).shift(1)                                             # 3/6/12-month ensemble, lagged
    e1['MF'], e1['Cash'] = np.nan, np.nan                             # managed futures is already a trend fund
    rot = e1[[s for s in RISKY5 if s != 'MF']]
    breadth = rot.mean(axis=1)
    dm = rot.sub(rot.mean(axis=1), axis=0)
    trend = pd.DataFrame(0.0, index=idx, columns=S5)
    trend[dm.columns] = dm.div(dm.abs().max(axis=1).replace(0, np.nan), axis=0) * MANDATE['trend']
    derisk = ((0.5 - breadth).clip(lower=0) * 2 * MANDATE['derisk'])  # 0 at half breadth, full at none
    risky = [s for s in RISKY5 if s != 'MF']
    trend[risky] = trend[risky].sub(derisk / len(risky), axis=0)
    trend['Cash'] = derisk
    E['Trend'] = _budget(trend.fillna(0.0), MANDATE['trend'])

    # 3. relative strength inside each class — sums to zero per class, so the class structure is policy
    mom = (R.shift(1).rolling(12).sum() - R.shift(1))                 # 12-1 momentum
    xs = pd.DataFrame(0.0, index=idx, columns=S5)
    for c in ['Equity', 'Defensive', 'Real assets']:
        mem = [s for s in S5 if CLASS5[s] == c]
        r = mom[mem].rank(axis=1, pct=True) - 0.5
        xs[mem] = r.sub(r.mean(axis=1), axis=0) * (MANDATE['xsec'] / 0.5)
    E['Relative strength'] = _budget(xs.fillna(0.0), MANDATE['xsec'])

    # 4. regime — the MRS state, expressed through the Playbook's own regime books
    rg = G.mrs().reindex(idx)
    reg = pd.DataFrame(0.0, index=idx, columns=S5)
    wl = w_saa[w_saa > 0.0005]
    cls_w = {}
    for sl, wv in wl.items():
        cls_w.setdefault(FR.PLATFORM_CLASS.get(sl, 'Cash'), []).append(sl)
    for state, ct in REGIME_CLASS_TILT.items():
        m = (rg['state'] == state)
        if not m.any():
            continue
        vec = pd.Series(0.0, index=S5)
        for c, tilt in ct.items():
            mem = cls_w.get(c, [])
            tot = sum(wl[x] for x in mem)
            if not mem or tot <= 0:
                continue                      # the portfolio does not hold this class: no tilt to place
            for x in mem:
                vec[x] += tilt * (wl[x] / tot)
        vec = vec - vec.mean()
        reg.loc[m] = np.tile(vec.values, (int(m.sum()), 1))
    E['Regime'] = _budget(reg.fillna(0.0), MANDATE['regime'])

    # 5. diversifier sizing — the trend sleeve is the one holding whose size is a macro decision rather
    # than a policy weight. Trend pays in volatile, trending, inflationary regimes and costs carry in
    # calm disinflation, so it is scaled on stress and inflation and funded from the rest of the book.
    base_mf = float(w_saa.get('MF', 0.0)) * 100
    dv = pd.DataFrame(0.0, index=idx, columns=S5)
    if base_mf > 0.05:
        # MRS composite is positive in expansion and negative as conditions deteriorate; trend pays
        # when conditions deteriorate, so the sleeve scales inversely to the score.
        z = (-rg['composite'].clip(-1.5, 1.5) / 1.5).fillna(0.0)
        mult = (1 + 0.9 * z).clip(MANDATE['div_lo'], MANDATE['div_hi'])
        dv['MF'] = base_mf * (mult - 1)
        rest2 = [s for s in S5 if s != 'MF']
        wr2 = w_saa.reindex(rest2).fillna(0.0)
        wr2 = wr2 / wr2.sum() if wr2.sum() > 0 else wr2
        dv[rest2] = -np.outer(dv['MF'].values, wr2.values)
    E['Diversifier sizing'] = _budget(dv.fillna(0.0), MANDATE['divsize'])
    E['_state'] = rg['state']
    E['_mf_target'] = dv['MF'] + base_mf
    return E


def mandate_bands(b):
    """The DAA fund's declared range: the SAA's own bands, widened by the amounts in MANDATE."""
    w = MANDATE['widen']
    cls = {c: (max(0.0, lo - w[c]), min(1.0, hi + w[c])) for c, (lo, hi) in b['cls'].items()}
    sl = {s: (max(0.0, lo - 0.04), min(1.0, hi + 0.04)) for s, (lo, hi) in b['sleeve'].items()}
    sh = {k: (max(0.0, lo - 0.08), min(1.0, hi + 0.08)) for k, (lo, hi) in b['share'].items()}
    return dict(b, sleeve=sl, cls=cls, share=sh)


def _project(w, b, n=60):
    """Nearest book inside the mandate: clip sleeves, pull each class back into its range, T-bills absorb."""
    w = w.clip(lower=0.0)
    for _ in range(n):
        for s, (lo, hi) in b['sleeve'].items():
            w[s] = min(max(w[s], lo), hi)
        for c, (lo, hi) in b['cls'].items():
            mem = [s for s in S5 if CLASS5[s] == c and s != 'Cash']
            if not mem:
                continue
            tot = w[mem].sum()
            if tot > hi + 1e-9 and tot > 0:
                w[mem] *= hi / tot
            elif tot < lo - 1e-9 and tot > 0:
                w[mem] *= lo / tot
        for (s, c), (lo, hi) in b['share'].items():
            mem = [x for x in S5 if CLASS5[x] == c]
            tot = w[mem].sum()
            if tot <= 0:
                continue
            w[s] = min(max(w[s], lo * tot), hi * tot)
        w = w / w.sum()
        if V.violations(w, b) == []:
            break
    return w


def daa_targets(w_saa, E, b):
    """Strategic book plus the four engines, held inside the mandate. Returns monthly target weights."""
    idx = E['Trend'].index
    base = w_saa.reindex(S5).fillna(0.0) * 100
    D = sum(E[k] for k in ENGINES).reindex(idx)[S5]
    cap = np.maximum(MANDATE['sleeve_min'], MANDATE['sleeve_cap'] * base)
    for k, v in MANDATE.get('room', {}).items():                  # sleeves whose size is a macro call
        if k in S5:
            cap[S5.index(k)] = max(cap[S5.index(k)], v)
    lo = np.maximum(MANDATE['floor'] * base - base, -cap)
    hi = np.minimum(MANDATE['ceil'] * base - base, cap)
    # T-bills are the residual, not a position: what the fund may hold in cash is set by the mandate band,
    # not by a fraction of a 2% strategic weight, which would make the cash lever unusable by construction.
    i = S5.index('Cash')
    lo[i], hi[i] = -base['Cash'], MANDATE['cash_max']
    D = D.clip(lower=pd.Series(lo, index=S5), upper=pd.Series(hi, index=S5), axis=1)
    D = _budget(D, MANDATE['budget'])
    mb = mandate_bands(b)
    T = {}
    for t in idx:
        T[t] = _project((base + D.loc[t]) / 100, mb)
    return pd.DataFrame(T).T[S5], D


def run_daa5(T, R, months, cost=V.COST, fee=V.FEE_YR, band=None):
    """Hold the book; rebalance to target only when a sleeve has drifted past the no-trade band."""
    band = (MANDATE['band'] if band is None else band) / 100
    idx = pd.PeriodIndex(months)
    Rm = R.reindex(idx)[S5].fillna(0.0)
    w = T.reindex(idx).ffill().bfill()
    held, rows, rets = w.iloc[0].copy(), [], []
    for i, t in enumerate(idx):
        tgt = w.loc[t]
        trade = 0.0
        if i == 0 or (tgt - held).abs().max() > band:
            trade = (tgt - held).abs().sum()
            held = tgt.copy()
        rows.append(held.copy())
        r = float((held * Rm.loc[t]).sum()) - trade * cost - fee / 12
        rets.append(r)
        held = held * (1 + Rm.loc[t])
        held = held / held.sum()
    return pd.Series(rets, index=idx), pd.DataFrame(rows, index=idx)
