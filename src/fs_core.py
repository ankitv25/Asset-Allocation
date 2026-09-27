"""
fs_core.py — shared machinery for the Summer Fund Suite v1 (pre-registration:
Research/Portfolio_Construction/docs/methodology/Fund_Suite_PreRegistration_2026-09-19.md).

Builds on mafv4_core (sleeves, BL posterior, optimizer) and cf_core (TSMOM overlay, metrics, the
bootstrap and deflated-Sharpe statistics). Adds: the suite constraint set and its resampled frontier,
the never-examined 1997-2007 pre-sample built from long-history index-fund proxies, a vectorised
backtest that works on either sample, and the fund-fee convention.
"""
import os

import numpy as np
import pandas as pd

import cf_core as C
import mafv4_core as K

OUT = os.path.join(K.ROOT, 'Research/Portfolio_Construction/validation/fund_suite')
os.makedirs(OUT, exist_ok=True)
S_ = K.SLEEVES
RISKY = [s for s in S_ if s != 'Cash']

# ------------------------------------------------------------------ windows (pre-registration §4)
PRE = (pd.Period('1997-06', 'M'), pd.Period('2007-05', 'M'))
DESIGN, HOLDOUT = C.DESIGN, C.HOLDOUT
FULL = (C.DESIGN[0], C.HOLDOUT[1])
LONG = (PRE[0], C.HOLDOUT[1])
WINDOWS = {'Pre-sample': PRE, 'Design': DESIGN, 'Holdout': HOLDOUT, 'Full': FULL, 'Long': LONG}
COST = C.COST                      # 10bp per side
FUND_FEE = 0.0015                  # 15bp/yr fund fee (pre-registration §6)

# ------------------------------------------------------------------ suite ranges (pre-registration §2)
SUITE_CLASS = {'Equity': (0.10, 0.95), 'Fixed income': (0.03, 0.85), 'Real assets': (0.02, 0.15),
               'Cash': (0.02, 0.15)}
SUITE_SLEEVE = {'US_EQ': (0.05, 0.70), 'DM_EQ': (0.02, 0.35), 'EM_EQ': (0.00, 0.17),
                'UST': (0.01, 0.60), 'MBS': (0.00, 0.15), 'IG': (0.00, 0.15), 'TIPS': (0.00, 0.12),
                'HY': (0.00, 0.10), 'REIT': (0.00, 0.05), 'CMDTY': (0.00, 0.05), 'GOLD': (0.00, 0.05),
                'Cash': (0.02, 0.15)}
SUITE_SHARE = dict(K.SHARE_POLICY)
V4_RANGES = (K.SLEEVE_POLICY, K.CLASS_POLICY, K.SHARE_POLICY)
SUITE_RANGES = (SUITE_SLEEVE, SUITE_CLASS, SUITE_SHARE)


# =====================================================================================
# Resampled frontier point (cf_core.dial_saa generalised to any constraint set)
# =====================================================================================
def _draws(st, SR, draws, seed):
    """The v4 resampling draws: μ ~ BL posterior, Σ from 12-month block bootstraps (full + trailing)."""
    mu_x, mpost, cash_mu = np.array(st['mu_bl_excess']), np.array(st['m_post']), st['cash_mu']
    risky_ix = [S_.index(s) for s in RISKY]
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
    return D


def frontier_saa(st, SR, target_vol, ranges=SUITE_RANGES, draws=200, cal_draws=40, seed=20260919):
    """Resampled MV book at a forward-vol target inside `ranges`; γ bisected on the first `cal_draws`
    draws exactly as cf_core.dial_saa (which this reproduces bit-for-bit with V4_RANGES).
    Returns (weights, gamma, forward vol, n_valid_draws)."""
    mu_bl = np.array(st['mu_bl'])
    covf = np.array(st['cov_fwd'])
    cons, bnds = K.build_constraints(S_, *ranges)
    D = _draws(st, SR, draws, seed)

    def avg(g, dr):
        pt = K.mv_opt(mu_bl, covf, g, cons, bnds, nstart=4)
        W = [K.mv_opt(m, c, g, cons, bnds, x0=pt, nstart=1, seed=k) for k, (m, c) in enumerate(dr)]
        W = np.array([w for w in W if w is not None])
        return W.mean(axis=0), len(W)

    a, b = 0.1, 60.0
    for _ in range(12):
        g = np.sqrt(a * b)
        w, _ = avg(g, D[:cal_draws])
        a, b = (g, b) if float(np.sqrt(w @ covf @ w)) > target_vol else (a, g)
    g = float(np.sqrt(a * b))
    w, n = avg(g, D)
    return pd.Series(w / w.sum(), index=S_), g, float(np.sqrt(w @ covf @ w)), n


def max_return_vol(st, ranges=SUITE_RANGES):
    """Forward vol of the maximum-forward-return book inside `ranges` (the frontier's top end)."""
    mu = np.array(st['mu_bl'])
    covf = np.array(st['cov_fwd'])
    cons, bnds = K.build_constraints(S_, *ranges)
    w = K.mv_opt(mu, covf, 1e-4, cons, bnds, nstart=8)
    return float(np.sqrt(w @ covf @ w)), pd.Series(w, index=S_)


def fwd_stats(w, st):
    mu = np.array(st['mu_bl'])
    covf = np.array(st['cov_fwd'])
    v = w.reindex(S_).values
    m, s = float(v @ mu), float(np.sqrt(v @ covf @ v))
    return dict(mu=100 * m, vol=100 * s, sharpe=(m - st['cash_mu']) / s)


def classes(w):
    return {c: float(sum(w[s] for s in S_ if K.CLASS[s] == c)) for c in K.CLASSES}


# =====================================================================================
# Signals — generic on any sleeve-return frame (reproduces cf_core.tsmom_signals in-sample)
# =====================================================================================
def tsmom(SRF, lookback=12):
    g = (1 + SRF.fillna(0)).rolling(lookback).apply(np.prod, raw=True)
    gc = (1 + SRF['Cash'].fillna(0)).rolling(lookback).apply(np.prod, raw=True)
    enough = SRF.notna().rolling(lookback).sum() >= lookback
    sig = (g.sub(gc, axis=0) > 0).astype(float).where(enough, 1.0)
    sig['Cash'] = 1.0
    return sig


def ensemble(SRF, lookbacks=(3, 6, 12)):
    """Lever E1: mean of the TSMOM switches over several lookbacks (exposure 0, 1/3, 2/3, 1)."""
    return sum(tsmom(SRF, L) for L in lookbacks) / len(lookbacks)


# =====================================================================================
# Backtest — vectorised, either sample
# =====================================================================================
def run(base, R, hedge, months, sig=None, cost=COST, fx=True, lag=0):
    """Weights decided at month-end d (signal from d − lag), held through d+1 = m.
    Missing-sleeve rule (pre-registration §5): a sleeve with no return in month m gets weight 0 and its
    weight is spread pro-rata over the available sleeves — before the overlay, in every book alike.
    FX: the DM weight actually held is hedged with `hedge` (hedge excess return over bills), with
    10bp/yr running cost and `cost` per side on hedge-notional changes (cf_core.run_book convention).
    Returns (gross-of-fund-fee monthly returns, weights)."""
    idx = pd.PeriodIndex(months)
    Rm = R.reindex(idx)[S_]
    avail = Rm.notna()
    W = pd.DataFrame(np.outer(np.ones(len(idx)), base.reindex(S_).fillna(0).values), index=idx, columns=S_)
    W = W.where(avail, 0.0)
    W = W.div(W.sum(axis=1), axis=0)
    if sig is not None:
        S = sig.reindex(idx - 1 - lag).fillna(1.0)
        S.index = idx
        for s in RISKY:
            W['Cash'] += W[s] * (1 - S[s])
            W[s] *= S[s]
    r = (W * Rm.fillna(0)).sum(axis=1)
    tc = W.diff().abs().sum(axis=1).fillna(0) * cost
    if fx:
        h = hedge.reindex(idx)
        r += W['DM_EQ'] * (h - 0.0010 / 12)
        tc += W['DM_EQ'].diff().abs().fillna(0) * cost
    return r - tc, W


def net(r):
    """Net of the 15bp/yr fund fee."""
    return r - FUND_FEE / 12


def sub(r, win):
    return C.sub(r, win)


def metrics(r, cash):
    return C.metrics(r, cash)


# =====================================================================================
# Pre-sample data (1996-2007) — long-history index-fund proxies (pre-registration §5)
# =====================================================================================
LONG_TICKERS = ['VFINX', 'VGTSX', 'VTMGX', 'EWC', 'VEIEX', 'VFITX', 'VFIIX', 'VFICX', 'VIPSX', 'VWEHX',
                'VGSIX', '^SPGSCI', 'GC=F', 'DX-Y.NYB', 'VBMFX']
DXY_W = {'EZ': 0.576, 'JP': 0.136, 'GB': 0.119, 'CA': 0.091, 'SE': 0.042, 'CH': 0.036}


def load_presample(refresh=False, cmdty_collateral=True):
    """Monthly sleeve returns (with Cash) from long-history proxies, the FX-hedge excess return and the
    paper-peer bond series. Returns dict(R, hedge, bonds, info)."""
    f = os.path.join(OUT, 'long_daily_close.csv')
    if refresh or not os.path.exists(f):
        import yfinance as yf
        px = yf.download(LONG_TICKERS, start='1995-01-01', end='2007-07-15', auto_adjust=True, progress=False)['Close']
        px.dropna(how='all').to_csv(f)
    px = pd.read_csv(f, index_col=0, parse_dates=True).sort_index()
    px = px[px.index.dayofweek < 5]
    m = px.resample('ME').last()
    m.index = m.index.to_period('M')
    r = m.pct_change(fill_method=None)
    tb = K.fred_series('TB3MS', refresh)
    tb.index = tb.index.to_period('M')
    cash = (tb / 100 / 12).reindex(r.index)
    R = pd.DataFrame(index=r.index)
    R['US_EQ'] = r['VFINX']
    dm = r['VTMGX'].where(r['VTMGX'].notna(), r['VGTSX'])
    R['DM_EQ'] = (1 - K.DM_CAN) * dm + K.DM_CAN * r['EWC']
    R['EM_EQ'] = r['VEIEX']
    R['UST'] = r['VFITX']
    R['MBS'] = r['VFIIX']
    R['IG'] = r['VFICX']
    R['TIPS'] = r['VIPSX']
    R['HY'] = r['VWEHX']
    R['REIT'] = r['VGSIX']
    R['CMDTY'] = r['^SPGSCI'] + (cash if cmdty_collateral else 0.0)
    R['GOLD'] = r['GC=F']
    R['Cash'] = cash
    R = R[S_]
    # FX hedge excess return: DXY spot + (US bill − DXY-weighted foreign 3m) − UUP's fee
    fr = {}
    for k, sid in {'EZ': 'IR3TIB01EZM156N', 'DE': 'IR3TIB01DEM156N', 'JP': 'IR3TIB01JPM156N',
                   'GB': 'IR3TIB01GBM156N', 'CA': 'IR3TIB01CAM156N', 'SE': 'IR3TIB01SEM156N',
                   'CH': 'IR3TIB01CHM156N'}.items():
        s = K.fred_series(sid, refresh)
        s.index = s.index.to_period('M')
        # Amendment 0b: where the OECD 3-month series starts late (JP 2002, CH 1999), fall back to the
        # OECD immediate (call-money / interbank overnight) rate for the same country
        imm = K.fred_series(sid.replace('IR3TIB01', 'IRSTCI01'), refresh)
        imm.index = imm.index.to_period('M')
        fr[k] = s.combine_first(imm)
    fr = pd.DataFrame(fr).reindex(r.index)
    fr['EZ'] = fr['EZ'].where(fr['EZ'].notna(), fr['DE'])            # pre-1999: Germany
    foreign = sum(DXY_W[k] * fr[k] for k in DXY_W)
    hedge = r['DX-Y.NYB'] + (tb.reindex(r.index) - foreign) / 100 / 12 - 0.0075 / 12
    info = {'first': {s: str(R[s].first_valid_index()) for s in S_},
            'foreign_rate_missing_months': int(foreign.loc[PRE[0]:PRE[1]].isna().sum())}
    return dict(R=R, hedge=hedge, bonds=r['VBMFX'], info=info)


def load_insample(refresh=False):
    """In-sample sleeve returns, FX hedge (UUP − bill), paper-peer bonds (AGG) and real peers."""
    L = C.load(refresh)
    MR, SR, XR = L['MR'], L['SR'], L['XR']
    return dict(R=SR, hedge=(MR['UUP'] - MR['Cash']), bonds=MR['AGG'].reindex(SR.index), XR=XR, MR=MR)


def paper_peer(R, bonds, eq_share):
    """Paper peer: eq_share × (63% US / 27% DM / 10% EM, unhedged) + (1 − eq_share) × total bond index."""
    eq = 0.63 * R['US_EQ'] + 0.27 * R['DM_EQ'] + 0.10 * R['EM_EQ']
    return eq_share * eq + (1 - eq_share) * bonds.reindex(R.index)
