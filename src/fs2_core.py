"""
fs2_core.py — shared machinery for the Summer Fund Suite v2 (pre-registration:
Research/Portfolio_Construction/docs/methodology/Fund_Suite_v2_PreRegistration_2026-09-19.md).

Philosophy first: each fund's weight BANDS are declared policy; the v4 machinery (CMA -> Black-Litterman ->
resampled mean-variance) chooses weights inside them. v2 universe = the v4 sleeves minus MBS, plus listed
infrastructure (GII) and managed futures (an equal-weight composite of every real MF fund alive that month).
Everything is parameterised by the v2 sleeve list; the v4/v1 modules are reused unchanged underneath.
"""
import json
import os

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import cf_core as C
import fs_core as F
import mafv4_core as K

VARIANT = os.environ.get('FS2_VARIANT', 'v2')   # 'v2' · 'v2.1' · 'v2.2' · 'v2.3' (readiness corrections: no quality tilt, Endowment differentiated)
V21 = VARIANT in ('v2.1', 'v2.2', 'v2.3')
V22 = VARIANT in ('v2.2', 'v2.3')
V23 = VARIANT == 'v2.3'
OUT = os.path.join(K.ROOT, 'Research/Portfolio_Construction/validation/' +
                   {'v2': 'fund_suite_v2', 'v2.1': 'fund_suite_v2_1', 'v2.2': 'fund_suite_v2_2', 'v2.3': 'fund_suite_v2_3'}[VARIANT])
DATA = os.path.join(K.ROOT, 'Research/Portfolio_Construction/validation/fund_suite_v2/data')
os.makedirs(OUT, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

S2 = ['US_EQ', 'DM_EQ', 'EM_EQ', 'UST', 'TIPS', 'IG', 'HY', 'REIT', 'INFRA', 'CMDTY', 'GOLD', 'MF', 'Cash']
RISKY2 = [s for s in S2 if s != 'Cash']
CLASS2 = {'US_EQ': 'Equity', 'DM_EQ': 'Equity', 'EM_EQ': 'Equity', 'UST': 'Defensive', 'TIPS': 'Defensive',
          'IG': 'Defensive', 'HY': 'Defensive', 'REIT': 'Real assets', 'INFRA': 'Real assets', 'CMDTY': 'Real assets',
          'GOLD': 'Real assets', 'MF': 'Diversifiers', 'Cash': 'Cash'}
CLASSES2 = ['Equity', 'Defensive', 'Real assets', 'Diversifiers', 'Cash']
LABEL2 = dict(K.LABEL, INFRA='Listed infrastructure', MF='Managed futures (trend)')
IMPL2 = dict(K.IMPL, INFRA='GII / IGF (S&P Global Infrastructure)', MF='DBMF / KMLM (managed futures)',
             DM_EQ='DBEF (hedged EAFE) + hedged Canada, or VEA + FX forwards', GOLD='GLDM / IAU')
FEE2 = dict(K.FEE_BP, INFRA=40, MF=85)
MF_FUNDS = ['RYMFX', 'AQMIX', 'ASFYX', 'PQTIX', 'DBMF', 'KMLM']
EXTRA2 = ['GII'] + MF_FUNDS
TRIALS_PRIOR = 43


# =====================================================================================
# Data
# =====================================================================================
def _extra_monthly(refresh=False):
    f = os.path.join(DATA, 'v2_daily_close.csv')
    if refresh or not os.path.exists(f):
        import yfinance as yf
        px = yf.download(EXTRA2, start='2005-01-01', auto_adjust=True, progress=False)['Close']
        px.dropna(how='all').to_csv(f)
    px = pd.read_csv(f, index_col=0, parse_dates=True).sort_index()
    px = px[px.index.dayofweek < 5]
    m = px.resample('ME').last()
    m.index = m.index.to_period('M')
    return m.pct_change(fill_method=None)


def mf_composite(xr):
    """Equal weight of every real managed-futures fund with a return that month (no selection by result)."""
    return xr[MF_FUNDS].mean(axis=1, skipna=True).where(xr[MF_FUNDS].notna().any(axis=1))


def load_insample(refresh=False):
    I = F.load_insample(refresh)
    xr = _extra_monthly(refresh)
    # FULL sleeve history (from 2002), not the window-trimmed panel: the trend signals need their 12-month look-back
    # at the start of the Design window (the v1 engines use the same full series for signals)
    R = K.sleeve_returns(I['MR'])[0].drop(columns=['MBS']).copy()
    R['INFRA'] = xr['GII'].reindex(R.index)
    R['MF'] = mf_composite(xr).reindex(R.index)
    return dict(R=R[S2], hedge=I['hedge'], bonds=I['bonds'], XR=I['XR'], MR=I['MR'], xr2=xr)


def wb_gold():
    """World Bank CMO monthly gold price ($/troy oz, monthly AVERAGE) -> monthly returns. Used only before 2000-09."""
    x = pd.read_excel(os.path.join(DATA, 'CMO.xlsx'), sheet_name='Monthly Prices', header=None)
    hdr = x.iloc[4].astype(str)
    col = [i for i, h in enumerate(hdr) if h.strip().lower() == 'gold'][0]
    s = x.iloc[6:, [0, col]].dropna()
    s.columns = ['m', 'p']
    s = s[s['m'].astype(str).str.match(r'^\d{4}M\d{2}$')]
    s.index = pd.PeriodIndex([f'{m[:4]}-{m[5:]}' for m in s['m']], freq='M')
    return pd.to_numeric(s['p']).pct_change()


def load_presample(refresh=False, cmdty_collateral=True):
    P = F.load_presample(refresh, cmdty_collateral)
    R = P['R'].drop(columns=['MBS']).copy()
    # Amendment v2-0: World Bank monthly-AVERAGE gold failed the proxy QA (corr 0.60 with GLD month-end returns, vol
    # 13.1% vs 16.7%), so it is NOT used; gold before 2000-09 falls back to the v1 pro-rata missing-sleeve rule.
    R['INFRA'] = np.nan
    R['MF'] = np.nan
    return dict(R=R[S2], hedge=P['hedge'], bonds=P['bonds'], info=P['info'])


# =====================================================================================
# CMA, risk model, Black-Litterman on the v2 universe
# =====================================================================================
NEW_CMA = {  # sleeve: (mu geo %, source, n houses, view sd)
    'GOLD': (5.75, 'median of J.P. Morgan 2026 LTCMA 5.5 and Amundi 2026 CMA 6.0', 2, 3.0),
    'INFRA': (7.7, 'median of Northern Trust 2026 (6.7), Amundi 2026 (7.7), Verus 2026 S&P Global Infrastructure (8.2)', 3, 3.0),
    'MF': (5.35, '8-house consensus "hedge funds / trend" (hedge-fund proxies; mapping imperfect — flagged)', 8, 2.0),
}
if V21:  # C1: the DM sleeve is held USD-hedged, so it is priced hedged (Verus 2026, MSCI EAFE hedged)
    NEW_CMA['DM_EQ'] = (float(os.environ.get('FS2_DM_CMA', 6.8)), 'Verus 2026 MSCI EAFE hedged (only house publishing a hedged DM figure)', 1, 3.0)
DM_HEDGE_COST = 0.0010 / 12
W_MKT2 = {'US_EQ': 31.5, 'DM_EQ': 13.5, 'EM_EQ': 5.0, 'UST': 15.0 + 8.0 * 15 / 24, 'IG': 9.0 + 8.0 * 9 / 24,
          'TIPS': 2.0, 'HY': 2.0, 'REIT': 4.0, 'INFRA': 1.5, 'CMDTY': 0.0, 'GOLD': 2.0, 'MF': 0.0}


def build_model(I):
    """Returns the v2 model: panel, CMA table, forward cov, BL posterior (excess + total), draws helper inputs."""
    D = K.load_data()
    _, ust = K.sleeve_returns(D['MR'])
    cma4, Y = K.build_cma(D['snap'], ust['duration'])
    rows = {}
    for s in S2:
        if s in NEW_CMA:
            mu, src, n, sd = NEW_CMA[s]
        else:
            mu, src, n, sd = cma4.loc[s, 'mu'], cma4.loc[s, 'source'], cma4.loc[s, 'n'], cma4.loc[s, 'err_sd']
        rows[s] = dict(mu=float(mu), source=src, n=n, err_sd=float(sd))
    cma = pd.DataFrame(rows).T
    panel = I['R'].loc[F.DESIGN[0]:F.HOLDOUT[1], S2].dropna().copy()
    if V21:  # C1: risk-model the DM sleeve as held — USD-hedged (the same hedge the backtest applies)
        panel['DM_EQ'] = panel['DM_EQ'] + I['hedge'].reindex(panel.index) - DM_HEDGE_COST
    cov = K.forward_cov(panel)
    mu_tot = np.array([(cma.loc[s, 'mu'] + 50 * cov.loc[s, s] - FEE2[s] / 100) / 100 for s in S2])
    cash_mu = cma.loc['Cash', 'mu'] / 100
    ri = [S2.index(s) for s in RISKY2]
    Sr = cov.values[np.ix_(ri, ri)]
    wm = np.array([W_MKT2[s] for s in RISKY2])
    wm = wm / wm.sum()
    delta = 0.30 / float(np.sqrt(wm @ Sr @ wm))
    tau = 0.05
    q = mu_tot[ri] - cash_mu
    om = np.diag([(cma.loc[s, 'err_sd'] / 100) ** 2 for s in RISKY2])
    pi = delta * Sr @ wm
    A = np.linalg.inv(tau * Sr)
    Mp = np.linalg.inv(A + np.linalg.inv(om))
    mux = Mp @ (A @ pi + np.linalg.inv(om) @ q)
    mu_bl = np.full(len(S2), cash_mu)
    mu_bl[ri] = mux + cash_mu
    return dict(cma=cma, panel=panel, cov=cov, mu_tot=mu_tot, cash_mu=cash_mu, pi=pi, q=q, mu_bl=mu_bl,
                mu_bl_x=mux, m_post=Mp, delta=delta, tau=tau, wm=dict(zip(RISKY2, wm)), yields=Y)


def draws(M, n=200, seed=20260919):
    rng = np.random.default_rng(seed)
    Rv = M['panel'][S2].values
    Rrec = Rv[-K.RECENT_M:]
    ri = [S2.index(s) for s in RISKY2]
    out = []
    for _ in range(n):
        idx = rng.integers(0, len(Rv) - 11, size=len(Rv) // 12 + 1)
        boot = np.vstack([Rv[i:i + 12] for i in idx])[:len(Rv)]
        brec = Rrec[rng.integers(0, len(Rrec), size=len(Rrec))]
        v = boot.std(axis=0, ddof=1) * np.sqrt(12)
        c = 0.5 * np.corrcoef(boot.T) + 0.5 * np.corrcoef(brec.T)
        cov = np.outer(v, v) * c
        ev = np.linalg.eigvalsh(cov)
        if ev.min() < 1e-10:
            cov += (1e-10 - ev.min()) * np.eye(len(S2))
        mu = np.full(len(S2), M['cash_mu'])
        mu[ri] = M['cash_mu'] + rng.multivariate_normal(M['mu_bl_x'], M['m_post'])
        out.append((mu, cov))
    return out


# =====================================================================================
# Funds — declared bands (pre-registration §3)
# =====================================================================================
SHARES = {('US_EQ', 'Equity'): (0.45, 0.75), ('DM_EQ', 'Equity'): (0.15, 0.40), ('EM_EQ', 'Equity'): (0.05, 0.20),
          ('UST', 'Defensive'): (0.30, 1.00), ('HY', 'Defensive'): (0.00, 0.20)}
# C2 (v2.1): regional equity mix declared as policy, anchored on MSCI ACWI (~64 US / 26 DM / 10 EM)
REGION_V21 = {'default': {('US_EQ', 'Equity'): (0.55, 0.70), ('DM_EQ', 'Equity'): (0.20, 0.30), ('EM_EQ', 'Equity'): (0.05, 0.12)},
              'Long-Horizon Growth': {('US_EQ', 'Equity'): (0.60, 0.75), ('DM_EQ', 'Equity'): (0.17, 0.27), ('EM_EQ', 'Equity'): (0.05, 0.12)}}


# v2.2 owner scope correction: the US tilt applies ONLY to Endowment and Long-Horizon Growth; Absolute Return and
# Balanced stay globally diversified around their v2 mix (bands needed because hedged-DM pricing would otherwise drift them)
REGION_V22 = {'Absolute Return': {('US_EQ', 'Equity'): (0.50, 0.60), ('DM_EQ', 'Equity'): (0.25, 0.35), ('EM_EQ', 'Equity'): (0.10, 0.15)},
              'Balanced': {('US_EQ', 'Equity'): (0.50, 0.60), ('DM_EQ', 'Equity'): (0.25, 0.35), ('EM_EQ', 'Equity'): (0.10, 0.15)},
              'Endowment': REGION_V21['default'], 'Long-Horizon Growth': REGION_V21['Long-Horizon Growth']}


def shares_for(fund):
    if not V21:
        return SHARES
    if V22:
        return {**SHARES, **REGION_V22[fund]}
    return {**SHARES, **REGION_V21.get(fund, REGION_V21['default'])}


def _bands(eq, ra, gold, cmdty, reit, infra, mf, dfn, cash):
    cls = {'Equity': eq, 'Real assets': ra, 'Diversifiers': mf, 'Defensive': dfn, 'Cash': cash}
    sl = {'US_EQ': (0.0, 1.0), 'DM_EQ': (0.0, 1.0), 'EM_EQ': (0.0, 1.0), 'UST': (0.0, 1.0), 'TIPS': (0.0, 0.12),
          'IG': (0.0, 0.15), 'HY': (0.0, 1.0), 'REIT': reit, 'INFRA': infra, 'CMDTY': cmdty, 'GOLD': gold, 'MF': mf,
          'Cash': cash}
    return sl, cls


FUNDS2 = {
    'Absolute Return': dict(objective='maxsharpe', target=None, floor=0.0,
                            bands=_bands((0.25, 0.45), (0.12, 0.16), (0.07, 0.08), (0.03, 0.05), (0.01, 0.03), (0, 0), (0, 0), (0.40, 0.60), (0.02, 0.15))),
    'Balanced': dict(objective='vol', target=0.11, floor=0.5,
                     bands=_bands((0.45, 0.60), (0.13, 0.17), (0.07, 0.08), (0.03, 0.05), (0.03, 0.05), (0, 0), (0, 0), (0.25, 0.40), (0.02, 0.10))),
    # v2.3 C2: differentiated so the Endowment is not a clone of Balanced (readiness audit: correlation 1.00)
    'Endowment': dict(objective='vol', target=0.11, floor=0.5,
                      bands=_bands((0.38, 0.48), (0.18, 0.23), (0.07, 0.08), (0.03, 0.05), (0.03, 0.05), (0.03, 0.06), (0.12, 0.18), (0.15, 0.30), (0.02, 0.10))),
    'Long-Horizon Growth': dict(objective='vol', target=0.14, floor=0.5,
                                bands=_bands((0.65, 0.75), (0.13, 0.17), (0.06, 0.08), (0.03, 0.05), (0.03, 0.05), (0, 0.03), (0, 0), (0.10, 0.20), (0.02, 0.05))),
}
for _f, _spec in FUNDS2.items():
    _spec['shares'] = shares_for(_f)
PEERS2 = {'Absolute Return': ('AOM (real 40/60)', 0.3), 'Balanced': ('AOR (real 60/40)', 0.6),
          'Endowment': ('AOR (real 60/40)', 0.6), 'Long-Horizon Growth': ('AOA (real 80/20)', 0.8)}


def constraints(bands, shares=None):
    shares = shares or SHARES
    sl, cls = bands
    idx = {s: i for i, s in enumerate(S2)}
    cons = [{'type': 'eq', 'fun': lambda w: w.sum() - 1.0}]
    for c, (lo, hi) in cls.items():
        jj = [idx[s] for s in S2 if CLASS2[s] == c]
        cons.append({'type': 'ineq', 'fun': (lambda jj, lo: lambda w: w[jj].sum() - lo)(jj, lo)})
        cons.append({'type': 'ineq', 'fun': (lambda jj, hi: lambda w: hi - w[jj].sum())(jj, hi)})
    for (s, c), (lo, hi) in shares.items():
        jj = [idx[x] for x in S2 if CLASS2[x] == c]
        i = idx[s]
        cons.append({'type': 'ineq', 'fun': (lambda i, jj, lo: lambda w: w[i] - lo * w[jj].sum())(i, jj, lo)})
        cons.append({'type': 'ineq', 'fun': (lambda i, jj, hi: lambda w: hi * w[jj].sum() - w[i])(i, jj, hi)})
    return cons, [sl[s] for s in S2]


def check_bands(w, bands, tol=1e-6, shares=None):
    shares = shares or SHARES
    sl, cls = bands
    bad = []
    for s in S2:
        lo, hi = sl[s]
        if w[s] < lo - tol or w[s] > hi + tol:
            bad.append(f'{s} {100 * w[s]:.2f} outside {100 * lo:.0f}-{100 * hi:.0f}')
    for c, (lo, hi) in cls.items():
        t = sum(w[s] for s in S2 if CLASS2[s] == c)
        if t < lo - tol or t > hi + tol:
            bad.append(f'{c} {100 * t:.2f} outside {100 * lo:.0f}-{100 * hi:.0f}')
    for (s, c), (lo, hi) in shares.items():
        t = sum(w[x] for x in S2 if CLASS2[x] == c)
        if t > 1e-9 and (w[s] < lo * t - tol or w[s] > hi * t + tol):
            bad.append(f'{s} share of {c} {100 * w[s] / t:.1f}% outside {100 * lo:.0f}-{100 * hi:.0f}%')
    return bad


def _max_sharpe(mu, cov, cash_mu, cons, bnds, x0):
    f = lambda w: -((w @ mu - cash_mu) / np.sqrt(w @ cov @ w))
    r = minimize(f, x0, method='SLSQP', bounds=bnds, constraints=cons, options={'maxiter': 2000, 'ftol': 1e-12})
    if not (r.success or r.status == 9):
        return None
    viol = max([0.0] + [-c['fun'](r.x) if c['type'] == 'ineq' else abs(c['fun'](r.x)) for c in cons])
    return r.x if viol < 1e-6 else None


def solve_fund(M, spec, D_):
    """Resampled solve inside the fund's bands. vol objective: γ bisected on ALL draws (v1 Correction 1)."""
    cons, bnds = constraints(spec['bands'], spec.get('shares'))
    covf, mu = M['cov'].values, M['mu_bl']
    x0 = np.array([np.mean(b) for b in bnds])
    x0 = x0 / x0.sum()
    if spec['objective'] == 'maxsharpe':
        pt = _max_sharpe(mu, covf, M['cash_mu'], cons, bnds, x0)
        W = [_max_sharpe(m, c, M['cash_mu'], cons, bnds, pt) for m, c in D_]
        W = np.array([w for w in W if w is not None])
        return pd.Series(W.mean(axis=0) / W.mean(axis=0).sum(), index=S2), None, len(W)

    def avg(g):
        pt = K.mv_opt(mu, covf, g, cons, bnds, nstart=4)
        W = [K.mv_opt(m, c, g, cons, bnds, x0=pt, nstart=1, seed=k) for k, (m, c) in enumerate(D_)]
        W = np.array([w for w in W if w is not None])
        return W.mean(axis=0), len(W)

    a, b = 0.05, 80.0
    for _ in range(14):
        g = float(np.sqrt(a * b))
        w, _ = avg(g)
        a, b = (g, b) if float(np.sqrt(w @ covf @ w)) > spec['target'] else (a, g)
    g = float(np.sqrt(a * b))
    w, n = avg(g)
    return pd.Series(w / w.sum(), index=S2), g, n


def _violation(w, bands, shares):
    """Total size of all band / share breaches (0 = compliant)."""
    shares = shares or SHARES
    sl, cls = bands
    v = sum(max(0.0, sl[s][0] - w[s]) + max(0.0, w[s] - sl[s][1]) for s in S2)
    for c, (lo, hi) in cls.items():
        t = sum(w[s] for s in S2 if CLASS2[s] == c)
        v += max(0.0, lo - t) + max(0.0, t - hi)
    for (s, c), (lo, hi) in shares.items():
        t = sum(w[x] for x in S2 if CLASS2[x] == c)
        v += max(0.0, lo * t - w[s]) + max(0.0, w[s] - hi * t)
    return v


def round_weights(w, bands, step=0.005, shares=None):
    """Judgment step, mechanised: round to 0.5%, restore the 100% total, then REPAIR any band/share breach the
    rounding created by moving single 0.5% steps between sleeves (the move closest to the unrounded weights wins).
    Returns (rounded weights, remaining breaches — must be empty)."""
    r = (w / step).round() * step
    gap = round(1.0 - r.sum(), 10)
    while abs(gap) > 1e-9:                                   # fix the total on the sleeves with the largest residuals
        resid = (w - r) * np.sign(gap)
        s = resid.idxmax()
        r[s] += step * np.sign(gap)
        gap = round(1.0 - r.sum(), 10)
    for _ in range(100):
        v0 = _violation(r, bands, shares)
        if v0 < 1e-9:
            break
        best = None
        for a in S2:                                         # move one step from a to b
            if r[a] < step - 1e-12:
                continue
            for b in S2:
                if a == b:
                    continue
                c = r.copy()
                c[a] -= step
                c[b] += step
                v = _violation(c, bands, shares)
                dist = float(((c - w) ** 2).sum())
                if v < v0 - 1e-12 and (best is None or (v, dist) < best[0]):
                    best = ((v, dist), c)
        if best is None:
            break
        r = best[1]
    return r.clip(lower=0), check_bands(r, bands, tol=1e-9, shares=shares)


def classes(w):
    return {c: float(sum(w[s] for s in S2 if CLASS2[s] == c)) for c in CLASSES2}


def fwd_stats(w, M):
    v = w.reindex(S2).values
    m, s = float(v @ M['mu_bl']), float(np.sqrt(v @ M['cov'].values @ v))
    return dict(mu=100 * m, vol=100 * s, sharpe=(m - M['cash_mu']) / s)


# =====================================================================================
# Dynamic layer and backtest
# =====================================================================================
def e1(R):
    """E1 ensemble (TSMOM 3/6/12) on the v2 sleeves; MF is never switched (it is itself a trend strategy)."""
    s = (F.tsmom(R, 3) + F.tsmom(R, 6) + F.tsmom(R, 12)) / 3
    s['MF'] = 1.0
    return s


def with_floor(sig, floor):
    out = floor + (1 - floor) * sig
    out['Cash'] = 1.0
    return out


def run(base, R, hedge, months, sig=None, cost=F.COST, fx=True, lag=0):
    """fs_core.run generalised to the v2 sleeve list (same conventions, same missing-sleeve rule)."""
    idx = pd.PeriodIndex(months)
    Rm = R.reindex(idx)[S2]
    avail = Rm.notna()
    W = pd.DataFrame(np.outer(np.ones(len(idx)), base.reindex(S2).fillna(0).values), index=idx, columns=S2)
    W = W.where(avail, 0.0)
    W = W.div(W.sum(axis=1), axis=0)
    if sig is not None:
        S = sig.reindex(idx - 1 - lag).fillna(1.0)
        S.index = idx
        for s in RISKY2:
            W['Cash'] += W[s] * (1 - S[s])
            W[s] *= S[s]
    r = (W * Rm.fillna(0)).sum(axis=1)
    tc = W.diff().abs().sum(axis=1).fillna(0) * cost
    if fx:
        r += W['DM_EQ'] * (hedge.reindex(idx) - 0.0010 / 12)
        tc += W['DM_EQ'].diff().abs().fillna(0) * cost
    return r - tc, W


# =====================================================================================
# B1 — French factor data
# =====================================================================================
def _french(fname, section='Value Weight Returns -- Monthly'):
    lines = open(os.path.join(DATA, fname), encoding='latin-1').read().splitlines()
    i0 = [i for i, l in enumerate(lines) if section in l and 'Equal' not in l][0]
    hdr = [h.strip() for h in lines[i0 + 1].split(',')]
    rows = []
    for l in lines[i0 + 2:]:
        p = [x.strip() for x in l.split(',')]
        if len(p) < 2 or not p[0].isdigit() or len(p[0]) != 6:
            break
        rows.append(p)
    df = pd.DataFrame(rows, columns=['m'] + hdr[1:]).set_index('m').astype(float) / 100
    df.index = pd.PeriodIndex([f'{m[:4]}-{m[4:]}' for m in df.index], freq='M')
    return df


def french_factors():
    op = _french('Portfolios_Formed_on_OP.csv')
    bm = _french('Portfolios_Formed_on_BE-ME.csv')
    lines = open(os.path.join(DATA, 'F-F_Research_Data_Factors.csv'), encoding='latin-1').read().splitlines()
    i0 = [i for i, l in enumerate(lines) if l.strip().startswith(',Mkt-RF')][0]
    rows = []
    for l in lines[i0 + 1:]:
        p = [x.strip() for x in l.split(',')]
        if len(p) < 2 or not p[0].isdigit() or len(p[0]) != 6:
            break
        rows.append(p)
    ff = pd.DataFrame(rows, columns=['m', 'MktRF', 'SMB', 'HML', 'RF']).set_index('m').astype(float) / 100
    ff.index = pd.PeriodIndex([f'{m[:4]}-{m[4:]}' for m in ff.index], freq='M')
    mkt = ff['MktRF'] + ff['RF']
    return pd.DataFrame({'Mkt': mkt, 'HiOP': op['Hi 30'], 'HiBM': bm['Hi 30']})
