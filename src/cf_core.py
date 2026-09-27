"""
cf_core.py — shared machinery for the Competitive Fund study (pre-registration:
Research/Portfolio_Construction/docs/methodology/Competitive_Fund_PreRegistration_2026-09-19.md).

Builds on mafv4_core (v4 sleeves, CMA, ranges). Adds: daily sleeve returns, extra instruments
(min-vol equity, hedged EAFE, peer funds), a monthly backtest engine with costs and an FX overlay,
and the statistics the pre-registration requires (bootstrap CI of Sharpe differences, Deflated Sharpe).
"""
import json
import os

import numpy as np
import pandas as pd
from scipy.stats import norm

import mafv4_core as K

OUT = os.path.join(K.ROOT, 'Research/Portfolio_Construction/validation/competitive_fund')
os.makedirs(OUT, exist_ok=True)
EXTRA = ['USMV', 'EFAV', 'EEMV', 'DBEF', 'AOR', 'AOA', 'AOM', 'DBMF']
DESIGN = (pd.Period('2007-06', 'M'), pd.Period('2016-12', 'M'))
HOLDOUT = (pd.Period('2017-01', 'M'), pd.Period('2026-08', 'M'))
COST = 0.0010                    # 10bp per side traded (pre-registered); 25bp sensitivity


def load(refresh=False):
    D = K.load_data(refresh)
    MR = D['MR']
    SR, ust = K.sleeve_returns(MR)
    SR = SR.dropna()
    # extra instruments (daily closes cached separately)
    f = os.path.join(OUT, 'extra_daily_close.csv')
    if refresh or not os.path.exists(f):
        import yfinance as yf
        px = yf.download(EXTRA, start='2005-01-01', auto_adjust=True, progress=False)['Close']
        px.dropna(how='all').to_csv(f)
    ex = pd.read_csv(f, index_col=0, parse_dates=True).sort_index()
    ex = ex[ex.index.dayofweek < 5]
    mex = ex.resample('ME').last()
    mex.index = mex.index.to_period('M')
    XR = mex.pct_change(fill_method=None).loc[:D['last_complete']]
    # daily sleeve returns (for volatility targeting)
    dpx = pd.read_csv(os.path.join(K.OUT, 'daily_close.csv'), index_col=0, parse_dates=True).sort_index()
    dpx = dpx[dpx.index.dayofweek < 5]
    dr = dpx.pct_change(fill_method=None)
    b = ust['weights']
    DS = pd.DataFrame(index=dr.index)
    for s, t in K.SERIES.items():
        if t != 'Cash':
            DS[s] = dr[t]
    DS['DM_EQ'] = (1 - K.DM_CAN) * dr['EFA'] + K.DM_CAN * dr['EWC']
    comp = sum(b[t] * dr[t] for t in b)
    DS['UST'] = dr['GOVT'].where(dr['GOVT'].notna(), comp)
    tb = K.fred_series('TB3MS')
    daily_cash = (tb / 100 / 252).reindex(DS.index, method='ffill')
    DS['Cash'] = daily_cash
    DS = DS[K.SLEEVES]
    return dict(D=D, MR=MR, SR=SR, XR=XR, DS=DS, ust=ust, uup_d=dr['UUP'])


def sub(r, win):
    return r[(r.index >= win[0]) & (r.index <= win[1])]


def metrics(r, cash):
    r = r.dropna()
    c = cash.reindex(r.index)
    g = (1 + r).cumprod()
    n = len(r)
    ex = r - c
    dn = ex[ex < 0]
    mdd = float((g / g.cummax() - 1).min())
    cagr = float(g.iloc[-1] ** (12 / n) - 1)
    return dict(n=n, cagr=100 * cagr, vol=100 * r.std() * np.sqrt(12),
                sharpe=float(ex.mean() / r.std() * np.sqrt(12)),
                sortino=float(ex.mean() / np.sqrt((dn ** 2).mean()) * np.sqrt(12)) if len(dn) else np.nan,
                maxdd=100 * mdd, calmar=cagr / abs(mdd) if mdd < 0 else np.nan,
                cvar5=100 * float(np.sort(r.values)[:max(1, n // 20)].mean()),
                skew=float(r.skew()), kurt=float(r.kurt()))


def sharpe_diff_ci(ra, rb, cash, reps=2000, block=12, seed=7):
    """Stationary-block bootstrap 90% CI of Sharpe(ra) − Sharpe(rb) on paired months."""
    idx = ra.dropna().index.intersection(rb.dropna().index)
    xa = (ra - cash).reindex(idx).values
    xb = (rb - cash).reindex(idx).values
    pa, pb = ra.reindex(idx).values, rb.reindex(idx).values
    n = len(idx)
    rng = np.random.default_rng(seed)
    out = []
    p = 1.0 / block
    for _ in range(reps):
        ii = np.empty(n, dtype=int)
        ii[0] = rng.integers(n)
        for k in range(1, n):
            ii[k] = rng.integers(n) if rng.random() < p else (ii[k - 1] + 1) % n
        sa = xa[ii].mean() / pa[ii].std(ddof=1)
        sb = xb[ii].mean() / pb[ii].std(ddof=1)
        out.append((sa - sb) * np.sqrt(12))
    out = np.array(out)
    return float(np.percentile(out, 5)), float(np.percentile(out, 95)), float((out > 0).mean())


def deflated_sharpe(r, cash, n_trials, sr_trials_var=None):
    """Bailey & López de Prado (2014) DSR: P(true SR > SR0), SR0 = expected max SR of n_trials
    zero-skill trials. Monthly units internally; sr_trials_var = variance of the trials' monthly SRs."""
    x = (r - cash.reindex(r.index)).dropna()
    T = len(x)
    sr = x.mean() / r.reindex(x.index).std(ddof=1)
    g3, g4 = float(r.skew()), float(r.kurt()) + 3
    v = sr_trials_var if sr_trials_var is not None else (1.0 / T)
    emc = 0.5772156649
    sr0 = np.sqrt(v) * ((1 - emc) * norm.ppf(1 - 1 / n_trials) + emc * norm.ppf(1 - 1 / (n_trials * np.e))) if n_trials > 1 else 0.0
    z = (sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return float(norm.cdf(z)), float(sr0 * np.sqrt(12))


def run_book(weights_fn, SR, MR, months, fx_hedge=True, cost=COST):
    """Monthly backtest. weights_fn(d) -> pd.Series of sleeve weights decided at end of month d
    (information <= d), held through month d+1. FX overlay: DM exposure actually held is 100% hedged
    via (UUP − T-bill). Costs: `cost` per side on sleeve-weight changes (drift ignored — monthly
    rebalance to target, same convention as v4) and on hedge-notional changes. Returns (returns, weights)."""
    h = (MR['UUP'] - MR['Cash'])
    out, W, prev_w, prev_h = [], [], None, 0.0
    for m in months:
        d = m - 1
        w = weights_fn(d).reindex(K.SLEEVES).fillna(0.0)
        r = float(w.values @ SR.loc[m, K.SLEEVES].values)
        hn = float(w['DM_EQ']) if fx_hedge else 0.0
        r += hn * float(h.loc[m]) - hn * 0.0010 / 12
        if prev_w is not None:
            r -= cost * float((w - prev_w).abs().sum())
        r -= cost * abs(hn - prev_h)
        prev_w, prev_h = w, hn
        out.append(r)
        W.append(w)
    return pd.Series(out, index=pd.PeriodIndex(months)), pd.DataFrame(W, index=pd.PeriodIndex(months))


def load_saa():
    st = json.load(open(os.path.join(K.OUT, 'saa_v4.json')))
    return pd.Series(st['saa'])[K.SLEEVES], st


# =====================================================================================
# D2 — time-series momentum overlay (Moskowitz-Ooi-Pedersen 2012), the Phase-3 survivor
# =====================================================================================
def tsmom_signals(MR, lookback=12):
    """Per sleeve at month-end d: 1 if the trailing `lookback`-month total return beats T-bills
    over the same months, else 0. Uses only returns <= d. Sleeves with < lookback months of own
    history return 1 (hold the SAA weight)."""
    SRF, _ = K.sleeve_returns(MR)
    g = (1 + SRF.fillna(0)).rolling(lookback).apply(np.prod, raw=True)
    gc = (1 + SRF['Cash'].fillna(0)).rolling(lookback).apply(np.prod, raw=True)
    enough = SRF.notna().rolling(lookback).sum() >= lookback
    sig = (g.sub(gc, axis=0) > 0).astype(float).where(enough, 1.0)
    sig['Cash'] = 1.0
    return sig


def overlay(base, sig_row):
    """Apply per-sleeve exposure e in [0,1] to the base weights; switched-out weight goes to T-bills."""
    w = base.copy()
    for s in K.SLEEVES:
        if s == 'Cash':
            continue
        e = float(sig_row.get(s, 1.0))
        w['Cash'] += w[s] * (1 - e)
        w[s] *= e
    return w


# =====================================================================================
# SAA at a given forward-vol dial point (v4 machinery, resampled; for Amendment 1)
# =====================================================================================
def dial_saa(st, SR, target_vol, draws=200, cal_draws=40, seed=20260919):
    from scipy.optimize import minimize  # noqa: F401
    S_ = K.SLEEVES
    risky_ix = [S_.index(s) for s in S_ if s != 'Cash']
    mu_bl, mu_x, mpost, cash_mu = np.array(st['mu_bl']), np.array(st['mu_bl_excess']), np.array(st['m_post']), st['cash_mu']
    covf = np.array(st['cov_fwd'])
    cons, bnds = K.build_constraints(S_, K.SLEEVE_POLICY, K.CLASS_POLICY, K.SHARE_POLICY)
    rng = np.random.default_rng(seed)
    Rv = SR[S_].values
    Rrec = Rv[-K.RECENT_M:]
    D = []
    for _ in range(draws):
        idx = rng.integers(0, len(Rv) - 11, size=len(Rv) // 12 + 1)
        boot = np.vstack([Rv[i:i + 12] for i in idx])[:len(Rv)]
        brec = Rrec[rng.integers(0, len(Rrec), size=len(Rrec))]
        v = boot.std(axis=0, ddof=1) * np.sqrt(12)
        c = 0.5 * np.corrcoef(boot.T) + 0.5 * np.corrcoef(brec.T)
        cov = np.outer(v, v) * c
        ev = np.linalg.eigvalsh(cov)
        if ev.min() < 1e-10:
            cov += (1e-10 - ev.min()) * np.eye(len(S_))
        mu = np.full(len(S_), cash_mu)
        mu[risky_ix] = cash_mu + rng.multivariate_normal(mu_x, mpost)
        D.append((mu, cov))

    def avg(g, dr):
        pt = K.mv_opt(mu_bl, covf, g, cons, bnds, nstart=4)
        W = [K.mv_opt(m, c, g, cons, bnds, x0=pt, nstart=1, seed=k) for k, (m, c) in enumerate(dr)]
        W = np.array([w for w in W if w is not None])
        return W.mean(axis=0)

    a, b = 0.1, 60.0
    for _ in range(12):
        g = np.sqrt(a * b)
        w = avg(g, D[:cal_draws])
        a, b = (g, b) if float(np.sqrt(w @ covf @ w)) > target_vol else (a, g)
    g = float(np.sqrt(a * b))
    w = avg(g, D)
    return pd.Series(w / w.sum(), index=S_), g, float(np.sqrt(w @ covf @ w))
