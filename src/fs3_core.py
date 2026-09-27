"""
fs3_core.py — Summer Funds v3: two static funds with the drawdown budget inside the optimizer.
Pre-registration: docs/methodology/Fund_Suite_v3_PreRegistration_2026-09-19.md.

What is different from v2.x, and why:
  * NO dynamic layer. The products are static books, rebalanced quarterly with a 1pp no-trade band.
  * Drawdown is a CONSTRAINT, not a hope: conditional drawdown-at-risk (CDaR, Chekhlov-Uryasev) and a hard
    worst-drawdown cap, both linear in the weights, solved as a linear program.
  * Managed futures is a strategic sleeve (real funds), so crisis protection is an asset we own rather than
    a signal we have to trade.
  * Treasuries are split into intermediate (GOVT ≈5.4y) and long (TLT ≈16y) so the optimizer can choose the
    duration it wants for crisis protection.
  * The developed-market sleeve is priced, risk-modelled and held USD-hedged (the v2.1 fix).
"""
import json
import os

import numpy as np
import pandas as pd
from scipy.optimize import linprog

import fs2_core as G
import fs_core as F
import mafv4_core as K

OUT = os.path.join(K.ROOT, 'Research/Portfolio_Construction/validation/fund_suite_v3')
os.makedirs(OUT, exist_ok=True)
S3 = ['US_EQ', 'DM_EQ', 'EM_EQ', 'UST', 'USTL', 'TIPS', 'IG', 'HY', 'REIT', 'INFRA', 'CMDTY', 'GOLD', 'MF', 'Cash']
RISKY3 = [s for s in S3 if s != 'Cash']
CLASS3 = dict(G.CLASS2, USTL='Defensive')
CLASSES3 = G.CLASSES2
LABEL3 = dict(G.LABEL2, UST='US Treasuries (intermediate)', USTL='US Treasuries (long)')
IMPL3 = dict(G.IMPL2, UST='VGIT / GOVT (≈5y)', USTL='VGLT / TLT (≈16y)', US_EQ='VOO / IVV')
FEE3 = dict(G.FEE2, USTL=4)
_BASE_S3 = list(S3)
_EXTENDED = []


def extend_universe(sleeves, class_map, labels=None, impl=None, fee=None):
    """Add sleeves to the shared universe, in place, for the whole process.

    The solver, the band checks, the backtest and the tilt engines all read S3/RISKY3/CLASS3 as module
    globals, so a later universe (v6 adds the Swiss franc) has to extend them rather than shadow them.
    Doing that through this function instead of assigning to the globals directly keeps the change
    greppable, guards it, and makes the requirements explicit:

      * the new universe must be a SUPERSET of the base one, so nothing already built disappears;
      * 'Cash' stays last, which several routines rely on for indexing;
      * it may only be called once per process, and calling it twice with the same universe is a no-op.

    Callers that do not call this see the original 14-sleeve universe and are unaffected.
    """
    sleeves = list(sleeves)
    missing = [x for x in _BASE_S3 if x not in sleeves]
    if missing:
        raise ValueError(f'extend_universe would drop {missing}; it may only add sleeves')
    if sleeves[-1] != 'Cash':
        raise ValueError("extend_universe requires 'Cash' to remain the last sleeve")
    if _EXTENDED:
        if _EXTENDED[0] == sleeves:
            return
        raise RuntimeError(f'universe already extended to {_EXTENDED[0]}; refusing to change it again')
    S3[:] = sleeves
    RISKY3[:] = [x for x in sleeves if x != 'Cash']
    CLASS3.update(class_map)
    if labels:
        LABEL3.update(labels)
    if impl:
        IMPL3.update(impl)
    if fee:
        FEE3.update(fee)
    missing_cls = [x for x in S3 if x not in CLASS3]
    if missing_cls:
        raise ValueError(f'no class mapping for {missing_cls}')
    _EXTENDED.append(list(sleeves))
WIN = (F.DESIGN[0], F.HOLDOUT[1])            # 2007-06..2026-08: the estimation window (GFC, COVID, 2022)
COST, FEE_YR, BAND = F.COST, F.FUND_FEE, 0.01


# =====================================================================================
# Data
# =====================================================================================
def _long_ust():
    f = os.path.join(G.DATA, 'longust_daily.csv')
    px = pd.read_csv(f, index_col=0, parse_dates=True).sort_index()
    px = px[px.index.dayofweek < 5]
    m = px.resample('ME').last()
    m.index = m.index.to_period('M')
    r = m.pct_change(fill_method=None)
    return r['TLT'].where(r['TLT'].notna(), r['VUSTX']), r['VUSTX']     # TLT from 2002-08, VUSTX before


def load(hedged=True):
    """In-sample and pre-sample sleeve panels, with DM held hedged and long Treasuries added."""
    I = G.load_insample()
    P = G.load_presample()
    tlt, vustx = _long_ust()
    R = I['R'].copy()
    R['USTL'] = tlt.reindex(R.index)
    RP = P['R'].copy()
    RP['USTL'] = vustx.reindex(RP.index)
    if hedged:
        R['DM_EQ'] = R['DM_EQ'] + I['hedge'].reindex(R.index) - 0.0010 / 12
        RP['DM_EQ'] = RP['DM_EQ'] + P['hedge'].reindex(RP.index) - 0.0010 / 12
    return dict(R=R[S3], RP=RP[S3], hedge=I['hedge'], hedge_pre=P['hedge'], MR=I['MR'], XR=I['XR'], bonds=I['bonds'],
                bonds_pre=P['bonds'])


def model(L):
    """CMA + Black-Litterman posterior on the v3 universe (v2 machinery; adds long Treasuries)."""
    D = K.load_data()
    _, ust = K.sleeve_returns(D['MR'])
    cma4, Y = K.build_cma(D['snap'], ust['duration'])
    panel = L['R'].loc[WIN[0]:WIN[1]].dropna()
    cov = K.forward_cov(panel)
    rows = {}
    for s in S3:
        if s == 'USTL':
            mu, src, n, sd = K.interp_curve(Y, K.DUR['TLT']), f'Treasury curve at {K.DUR["TLT"]:.1f}y (observed)', 'yield', 0.5
        elif s in G.NEW_CMA:
            mu, src, n, sd = G.NEW_CMA[s]
        else:
            mu, src, n, sd = cma4.loc[s, 'mu'], cma4.loc[s, 'source'], cma4.loc[s, 'n'], cma4.loc[s, 'err_sd']
        rows[s] = dict(mu=float(mu), source=src, n=n, err_sd=float(sd))
    cma = pd.DataFrame(rows).T
    mu_tot = np.array([(cma.loc[s, 'mu'] + 50 * cov.loc[s, s] - FEE3[s] / 100) / 100 for s in S3])
    cash_mu = cma.loc['Cash', 'mu'] / 100
    ri = [S3.index(s) for s in RISKY3]
    Sr = cov.values[np.ix_(ri, ri)]
    wm0 = dict(G.W_MKT2)
    tre = wm0.pop('UST')
    wm0['UST'], wm0['USTL'] = tre * 0.75, tre * 0.25          # the Treasury market by duration bucket (approx.)
    wm = np.array([wm0[s] for s in RISKY3])
    wm = wm / wm.sum()
    delta, tau = 0.30 / float(np.sqrt(wm @ Sr @ wm)), 0.05
    q = mu_tot[ri] - cash_mu
    om = np.diag([(cma.loc[s, 'err_sd'] / 100) ** 2 for s in RISKY3])
    pi = delta * Sr @ wm
    A = np.linalg.inv(tau * Sr)
    Mp = np.linalg.inv(A + np.linalg.inv(om))
    mux = Mp @ (A @ pi + np.linalg.inv(om) @ q)
    mu_bl = np.full(len(S3), cash_mu)
    mu_bl[ri] = mux + cash_mu
    return dict(cma=cma, cov=cov, panel=panel, mu_bl=mu_bl, mu_bl_x=mux, m_post=Mp, cash_mu=cash_mu, pi=pi, q=q,
                delta=delta, tau=tau, wm=dict(zip(RISKY3, wm)), yields=Y)


# =====================================================================================
# Funds — declared bands (pre-registration §4)
# =====================================================================================
def _b(eq, us, dm, em, ra, gold, cmdty, reit, infra, mf, dfn, ustl, hy, cash, vol_cap, cdar, ddcap):
    sl = {'US_EQ': (0, 1), 'DM_EQ': (0, 1), 'EM_EQ': (0, 1), 'UST': (0, 1), 'USTL': ustl, 'TIPS': (0, 0.12),
          'IG': (0, 0.15), 'HY': hy, 'REIT': reit, 'INFRA': infra, 'CMDTY': cmdty, 'GOLD': gold, 'MF': mf, 'Cash': cash}
    cls = {'Equity': eq, 'Defensive': dfn, 'Real assets': ra, 'Diversifiers': mf, 'Cash': cash}
    sh = {('US_EQ', 'Equity'): us, ('DM_EQ', 'Equity'): dm, ('EM_EQ', 'Equity'): em,
          ('UST', 'Defensive'): (0.20, 1.0)}
    return dict(sleeve=sl, cls=cls, share=sh, vol_cap=vol_cap, cdar=cdar, ddcap=ddcap)


FUNDS3 = {
    'Stable': dict(purpose='Protect capital and earn a modest real return through every regime', horizon='3+ years',
                   bands=_b((0.15, 0.35), (0.50, 0.65), (0.20, 0.35), (0.05, 0.15), (0.12, 0.18), (0.06, 0.08),
                            (0.02, 0.05), (0.00, 0.04), (0.00, 0.04), (0.08, 0.18), (0.35, 0.60), (0.00, 0.20),
                            (0.00, 0.05), (0.02, 0.15), 0.07, 0.06, 0.08)),
    'Fundamental': dict(purpose='Compound long-horizon wealth through cycles without depending on timing', horizon='10+ years',
                        bands=_b((0.40, 0.65), (0.60, 0.75), (0.17, 0.30), (0.05, 0.15), (0.13, 0.20), (0.06, 0.08),
                                 (0.02, 0.05), (0.02, 0.05), (0.02, 0.06), (0.10, 0.20), (0.12, 0.30), (0.00, 0.15),
                                 (0.00, 0.05), (0.02, 0.08), 0.12, 0.18, 0.24)),   # v3-1(b): equity floor 40%, CDaR 18%, LP cap 24% (uncompounded)
}


def lin_constraints(b):
    """Band constraints as (A_ub, b_ub, A_eq, b_eq, bounds) over the sleeve weights."""
    n = len(S3)
    A, bb = [], []
    for c, (lo, hi) in b['cls'].items():
        row = np.array([1.0 if CLASS3[s] == c else 0.0 for s in S3])
        A.append(-row)
        bb.append(-lo)
        A.append(row)
        bb.append(hi)
    for (s, c), (lo, hi) in b['share'].items():
        mem = np.array([1.0 if CLASS3[x] == c else 0.0 for x in S3])
        one = np.array([1.0 if x == s else 0.0 for x in S3])
        A.append(lo * mem - one)
        bb.append(0.0)
        A.append(one - hi * mem)
        bb.append(0.0)
    return np.array(A), np.array(bb), np.ones((1, n)), np.array([1.0]), [b['sleeve'][s] for s in S3]


# =====================================================================================
# CDaR optimisation (Chekhlov-Uryasev): maximise μ'w s.t. CDaR_5 ≤ budget, maxDD ≤ cap, bands
# =====================================================================================
def solve_cdar(R, mu, b, alpha=0.95, cdar=None, ddcap=None):
    """R: T×n monthly returns (estimation window). Variables: w (n), u_t (running max of cumulative, T),
    zeta (1), z_t (T). Cumulative returns are uncompounded (the standard CDaR formulation)."""
    Rm = R[S3].values
    T, n = Rm.shape
    C = np.cumsum(Rm, axis=0)                     # cumulative asset returns; portfolio cum = C @ w
    cdar = b['cdar'] if cdar is None else cdar
    ddcap = b['ddcap'] if ddcap is None else ddcap
    nv = n + T + 1 + T
    iw, iu, iz, izt = 0, n, n + T, n + T + 1
    A, bb = [], []
    Ab, bbb, Aeq0, beq0, bounds = lin_constraints(b)
    for r, v in zip(Ab, bbb):                     # band constraints on w
        row = np.zeros(nv)
        row[iw:iw + n] = r
        A.append(row)
        bb.append(v)
    for t in range(T):                            # u_t >= cum_t  ->  cum_t - u_t <= 0
        row = np.zeros(nv)
        row[iw:iw + n] = C[t]
        row[iu + t] = -1
        A.append(row)
        bb.append(0.0)
    for t in range(1, T):                         # u_{t-1} - u_t <= 0 (non-decreasing running max)
        row = np.zeros(nv)
        row[iu + t - 1] = 1
        row[iu + t] = -1
        A.append(row)
        bb.append(0.0)
    for t in range(T):                            # drawdown cap: u_t - cum_t <= ddcap
        row = np.zeros(nv)
        row[iu + t] = 1
        row[iw:iw + n] = -C[t]
        A.append(row)
        bb.append(ddcap)
    for t in range(T):                            # z_t >= u_t - cum_t - zeta
        row = np.zeros(nv)
        row[iu + t] = 1
        row[iw:iw + n] = -C[t]
        row[iz] = -1
        row[izt + t] = -1
        A.append(row)
        bb.append(0.0)
    row = np.zeros(nv)                            # CDaR: zeta + 1/((1-a)T) * sum z_t <= budget
    row[iz] = 1
    row[izt:izt + T] = 1.0 / ((1 - alpha) * T)
    A.append(row)
    bb.append(cdar)
    Aeq = np.zeros((1, nv))
    Aeq[0, iw:iw + n] = 1.0
    c = np.zeros(nv)
    c[iw:iw + n] = -mu                            # maximise expected return
    bnds = list(bounds) + [(None, None)] * T + [(None, None)] + [(0, None)] * T
    res = linprog(c, A_ub=np.array(A), b_ub=np.array(bb), A_eq=Aeq, b_eq=np.array([1.0]), bounds=bnds, method='highs')
    if not res.success:
        return None, res.message
    return pd.Series(res.x[iw:iw + n], index=S3), res


def resampled_cdar(R, mu, b, draws=200, seed=20260919, block=12, **kw):
    """Michaud-style: re-solve the CDaR program on block-bootstrap resamples and average the weights."""
    rng = np.random.default_rng(seed)
    Rv = R[S3]
    T = len(Rv)
    W, fails = [], 0
    for _ in range(draws):
        idx = np.concatenate([np.arange(s, s + block) % T for s in rng.integers(0, T, T // block + 1)])[:T]
        w, _ = solve_cdar(Rv.iloc[idx], mu, b, **kw)
        if w is None:
            fails += 1
        else:
            W.append(w.values)
    W = np.array(W)
    return pd.Series(W.mean(axis=0), index=S3), len(W), fails


# =====================================================================================
# Static backtest: quarterly rebalance to target with a 1pp no-trade band, 10bp/side, 15bp/yr fee
# =====================================================================================
def run_static(w_target, R, months, cost=COST, band=BAND, fee=FEE_YR):
    idx = pd.PeriodIndex(months)
    Rm = R.reindex(idx)[S3]
    w = None
    out, W = [], []
    for m in idx:
        av = Rm.loc[m].notna()
        tgt = w_target.where(av, 0.0)
        tgt = tgt / tgt.sum()
        if w is None:
            w, tc = tgt.copy(), 0.0
        else:
            w = w.where(av, 0.0)
            w = w / w.sum()
            if m.month in (1, 4, 7, 10) and (w - tgt).abs().max() > band:
                tc = cost * float((w - tgt).abs().sum())
                w = tgt.copy()
            else:
                tc = 0.0
        r = float((w * Rm.loc[m].fillna(0)).sum()) - tc - fee / 12
        out.append(r)
        W.append(w.copy())
        gr = (1 + Rm.loc[m].fillna(0)) * w
        w = gr / gr.sum()
    return pd.Series(out, index=idx), pd.DataFrame(W, index=idx)


def dd_stats(r):
    g = (1 + r.dropna()).cumprod()
    dd = g / g.cummax() - 1
    return dict(maxdd=float(100 * dd.min()), cdar5=float(-100 * dd.sort_values().iloc[:max(1, len(dd) // 20)].mean()),
                ulcer=float(100 * np.sqrt((dd ** 2).mean())))


def violations(w, b, tol=1e-9):
    """Every band / class / within-class-share breach, as text."""
    bad = []
    for s in S3:
        lo, hi = b['sleeve'][s]
        if w[s] < lo - tol or w[s] > hi + tol:
            bad.append(f'{s} {100 * w[s]:.1f} outside {100 * lo:.0f}-{100 * hi:.0f}')
    for c, (lo, hi) in b['cls'].items():
        t = sum(w[s] for s in S3 if CLASS3[s] == c)
        if t < lo - tol or t > hi + tol:
            bad.append(f'{c} {100 * t:.1f} outside {100 * lo:.0f}-{100 * hi:.0f}')
    for (s, c), (lo, hi) in b['share'].items():
        t = sum(w[x] for x in S3 if CLASS3[x] == c)
        if t > tol and (w[s] < lo * t - tol or w[s] > hi * t + tol):
            bad.append(f'{s} share of {c} {100 * w[s] / t:.1f}% outside {100 * lo:.0f}-{100 * hi:.0f}%')
    return bad


def _viol_size(w, b):
    v = 0.0
    for s in S3:
        lo, hi = b['sleeve'][s]
        v += max(0.0, lo - w[s]) + max(0.0, w[s] - hi)
    for c, (lo, hi) in b['cls'].items():
        t = sum(w[s] for s in S3 if CLASS3[s] == c)
        v += max(0.0, lo - t) + max(0.0, t - hi)
    for (s, c), (lo, hi) in b['share'].items():
        t = sum(w[x] for x in S3 if CLASS3[x] == c)
        v += max(0.0, lo * t - w[s]) + max(0.0, w[s] - hi * t)
    return v


def round_repair(w, b, step=0.005):
    """Round to 0.5%, restore the 100% total, then repair any band breach the rounding created with single
    0.5% moves (the move that stays closest to the unrounded book wins). Same routine as v2.3."""
    r = (w / step).round() * step
    while abs(round(1 - r.sum(), 10)) > 1e-9:
        g = round(1 - r.sum(), 10)
        r[((w - r) * np.sign(g)).idxmax()] += step * np.sign(g)
    for _ in range(200):
        v0 = _viol_size(r, b)
        if v0 < 1e-9:
            break
        best = None
        for a in S3:
            if r[a] < step - 1e-12:
                continue
            for c in S3:
                if a == c:
                    continue
                cand = r.copy()
                cand[a] -= step
                cand[c] += step
                v = _viol_size(cand, b)
                dist = float(((cand - w) ** 2).sum())
                if v < v0 - 1e-12 and (best is None or (v, dist) < best[0]):
                    best = ((v, dist), cand)
        if best is None:
            break
        r = best[1]
    return r.clip(lower=0), violations(r, b)


def classes(w):
    return {c: float(sum(w[s] for s in S3 if CLASS3[s] == c)) for c in CLASSES3}


def fwd(w, M):
    v = w.reindex(S3).values
    m, s = float(v @ M['mu_bl']), float(np.sqrt(v @ M['cov'].values @ v))
    return dict(mu=100 * m, vol=100 * s, sharpe=(m - M['cash_mu']) / s)
