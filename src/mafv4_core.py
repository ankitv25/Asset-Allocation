"""
mafv4_core.py — shared machinery for Multi-Asset Framework v4 (the connected chain).

    CMA + policy ranges + optimization  ->  SAA (Layer 1)
    MRS regime/stance + updated market assumptions  ->  DAA (Layers 2-3)
    risk budget + FX + hedge overlays  ->  implemented book (Layers 4-5)

This module holds data loading, the sleeve definitions, the Capital Market Assumptions, the
risk model, the policy/hard ranges and the optimizers. It performs no printing; the engines
`pc_multiasset_v4.py` (build) and `pc_multiasset_v4_walkforward.py` (validation) import it.

Architecture lineage: Portfolio_Construction_Methodology v1.0 "Framework G" (PC-07: five
layers; PC-09 floors/ceilings; PC-10/11 Black-Litterman SAA; PC-15/16 regime stances; PC-19/20
DCS; PC-24/25/26 risk budgeting) + Multi-Asset Framework v2/v3 estimation discipline (Michaud
resampling, regime shrinkage K=24, tested constraint layers) + the 2026-08 CMA consensus.
"""
import json
import os
import urllib.request

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = os.getcwd()
OUT = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/multiasset_v4')
os.makedirs(OUT, exist_ok=True)

# =====================================================================================
# Data
# =====================================================================================
TICKERS = ['SPY', 'EFA', 'EWC', 'EEM', 'ACWI', 'IWD', 'IWF', 'IWM',
           'GOVT', 'SHY', 'IEF', 'TLT', 'TIP', 'AGG', 'LQD', 'MBB', 'HYG', 'EMB',
           'VNQ', 'DBC', 'GLD', 'DBMF', 'UUP']
FRED_SNAPSHOT = ['DGS3MO', 'DGS1', 'DGS2', 'DGS3', 'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30',
                 'DFII10', 'T10YIE', 'BAMLC0A0CM', 'BAMLC0A0CMEY', 'BAMLH0A0HYM2',
                 'BAMLH0A0HYM2EY', 'CPIAUCSL']
MRS_URL = 'https://raw.githubusercontent.com/ankitv25/Macro-Regime-Score/main/dashboard/data/composite_history.json'


def _fetch(url, path, refresh):
    if refresh or not os.path.exists(path):
        with urllib.request.urlopen(url, timeout=60) as r:
            open(path, 'wb').write(r.read())
    return path


def fred_series(sid, refresh=False):
    p = _fetch(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}',
               os.path.join(OUT, f'fred_{sid}.csv'), refresh)
    d = pd.read_csv(p)
    d.columns = ['date', sid]
    d = d[d[sid].astype(str) != '.']
    d['date'] = pd.to_datetime(d['date'])
    d[sid] = pd.to_numeric(d[sid], errors='coerce')       # FRED marks gaps as '.' or blank
    return d.set_index('date')[sid].dropna()


def load_data(refresh=False):
    """Returns dict with: MR (monthly TR by ticker + Cash), last_complete, snapshot (FRED latest),
    ig_oas (monthly IG credit spread proxy BAA10YM, %), mrs (public MRS composite history, monthly)."""
    daily_f = os.path.join(OUT, 'daily_close.csv')
    if refresh or not os.path.exists(daily_f):
        import yfinance as yf
        px = yf.download(TICKERS, start='2002-07-01', auto_adjust=True, progress=False)['Close']
        px.dropna(how='all').to_csv(daily_f)
    px = pd.read_csv(daily_f, index_col=0, parse_dates=True).sort_index()
    px = px[px.index.dayofweek < 5].dropna(how='all')
    last_obs = px.index.max()
    last_complete = last_obs.to_period('M') - (0 if last_obs >= last_obs + pd.offsets.BMonthEnd(0) else 1)
    mpx = px.resample('ME').last()
    mpx.index = mpx.index.to_period('M')
    MR = mpx.pct_change(fill_method=None).loc[:last_complete]

    tb3 = fred_series('TB3MS', refresh)
    tb3.index = tb3.index.to_period('M')
    MR['Cash'] = (tb3 / 100 / 12).reindex(MR.index)

    # DCS credit input = the platform's own IG spread proxy (process_mrs_inputs.py: ig_spread =
    # Moody's BAA − 10y, FRED BAA10YM, monthly, long history). ICE OAS is used only for today's state.
    ig = fred_series('BAA10YM', refresh)
    ig.index = ig.index.to_period('M')
    ig_oas = ig

    snap_f = os.path.join(OUT, 'fred_snapshot.json')
    if refresh or not os.path.exists(snap_f):
        snap = {}
        for s in FRED_SNAPSHOT:
            p = _fetch(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}',
                       os.path.join(OUT, f'_snap_{s}.csv'), True)
            v = pd.read_csv(p)
            v.columns = ['date', s]
            v[s] = pd.to_numeric(v[s], errors='coerce')          # FRED marks gaps as '.' or blank
            v = v.dropna()
            snap[s] = {'date': str(v['date'].iloc[-1]), 'value': float(v[s].iloc[-1])}
            if s == 'CPIAUCSL':
                snap[s]['yoy'] = float(v[s].iloc[-1] / v[s].iloc[-13] - 1) * 100
            os.remove(p)
        json.dump(snap, open(snap_f, 'w'), indent=1)
    snap = json.load(open(snap_f))

    mrs_f = _fetch(MRS_URL, os.path.join(OUT, 'mrs_composite_history.json'), refresh)
    mrs = pd.DataFrame(json.load(open(mrs_f)))
    mrs['date'] = pd.to_datetime(mrs['date']).dt.to_period('M')
    mrs = mrs.set_index('date')
    MR.to_csv(os.path.join(OUT, 'monthly_tr.csv'))
    return dict(MR=MR, last_complete=last_complete, last_obs=last_obs, snap=snap, ig_oas=ig_oas, mrs=mrs)


# =====================================================================================
# Sleeves — the asset-class level at which SAA/DAA decisions are made
# =====================================================================================
DM_CAN = 0.11            # Canada ≈ 11% of developed ex-US market cap (approx.; EFA/EAFE excludes Canada)
SLEEVES = ['US_EQ', 'DM_EQ', 'EM_EQ', 'UST', 'MBS', 'IG', 'TIPS', 'HY', 'REIT', 'CMDTY', 'GOLD', 'Cash']
CLASS = {'US_EQ': 'Equity', 'DM_EQ': 'Equity', 'EM_EQ': 'Equity',
         'UST': 'Fixed income', 'MBS': 'Fixed income', 'IG': 'Fixed income', 'TIPS': 'Fixed income',
         'HY': 'Fixed income', 'REIT': 'Real assets', 'CMDTY': 'Real assets', 'GOLD': 'Real assets',
         'Cash': 'Cash'}
CLASSES = ['Equity', 'Fixed income', 'Real assets', 'Cash']
LABEL = {'US_EQ': 'US equity', 'DM_EQ': 'Developed ex-US equity', 'EM_EQ': 'Emerging-market equity',
         'UST': 'US Treasuries', 'MBS': 'Agency MBS', 'IG': 'IG corporate credit', 'TIPS': 'TIPS',
         'HY': 'High-yield credit', 'REIT': 'Listed real estate', 'CMDTY': 'Broad commodities',
         'GOLD': 'Gold', 'Cash': 'Cash (T-bills)'}
SERIES = {'US_EQ': 'SPY', 'EM_EQ': 'EEM', 'MBS': 'MBB', 'IG': 'LQD', 'TIPS': 'TIP', 'HY': 'HYG',
          'REIT': 'VNQ', 'CMDTY': 'DBC', 'GOLD': 'GLD', 'Cash': 'Cash'}   # DM_EQ, UST are composites
IMPL = {'US_EQ': 'VOO / IVV', 'DM_EQ': 'VEA (FTSE Developed ex-US, incl. Canada & Korea)',
        'EM_EQ': 'VWO (FTSE EM) — pair with VEA so Korea is held exactly once', 'UST': 'GOVT / VGIT+VGLT+VGSH (duration set internally)',
        'MBS': 'VMBS / MBB', 'IG': 'VCIT+VCLT / LQD', 'TIPS': 'SCHP / TIP', 'HY': 'USHY / HYG',
        'REIT': 'VNQ', 'CMDTY': 'PDBC / DBC', 'GOLD': 'GLDM / IAU', 'Cash': 'T-bills / SGOV'}
FEE_BP = {'US_EQ': 3, 'DM_EQ': 5, 'EM_EQ': 8, 'UST': 4, 'MBS': 4, 'IG': 4, 'TIPS': 4, 'HY': 10,
          'REIT': 13, 'CMDTY': 60, 'GOLD': 10, 'Cash': 0}          # approx. current expense ratios
DUR = {'SHY': 1.9, 'IEF': 7.1, 'TLT': 16.3, 'MBB': 5.8, 'LQD': 8.4, 'TIP': 6.8, 'HYG': 3.2}  # approx. eff. duration


def ust_composite(MR):
    """Treasury sleeve = the broad US Treasury index (GOVT, from 2012). Pre-2012 history is a
    SHY/IEF/TLT composite whose weights are fitted (constrained LS, long-only, sum 1) to GOVT
    over the overlap — duration is a sleeve attribute, not three strategic sleeves."""
    ov = MR[['GOVT', 'SHY', 'IEF', 'TLT']].dropna()
    X, y = ov[['SHY', 'IEF', 'TLT']].values, ov['GOVT'].values
    r = minimize(lambda b: float(((y - X @ b) ** 2).sum()), np.full(3, 1 / 3), method='SLSQP',
                 bounds=[(0, 1)] * 3, constraints=[{'type': 'eq', 'fun': lambda b: b.sum() - 1}])
    b = dict(zip(['SHY', 'IEF', 'TLT'], r.x))
    fit = X @ r.x
    te = float(np.std(y - fit) * np.sqrt(12) * 100)
    corr = float(np.corrcoef(y, fit)[0, 1])
    comp = sum(b[t] * MR[t] for t in b)
    ust = MR['GOVT'].where(MR['GOVT'].notna(), comp)            # observed GOVT where it exists
    dur = sum(b[t] * DUR[t] for t in b)
    return ust, dict(weights=b, te_pct=te, corr=corr, duration=dur, n=len(ov),
                     start=str(ov.index.min()), govt_start=str(MR['GOVT'].first_valid_index()))


def sleeve_returns(MR):
    S = pd.DataFrame(index=MR.index)
    for s, t in SERIES.items():
        S[s] = MR[t]
    S['DM_EQ'] = (1 - DM_CAN) * MR['EFA'] + DM_CAN * MR['EWC']
    ust, ust_info = ust_composite(MR)
    S['UST'] = ust
    return S[SLEEVES], ust_info


# =====================================================================================
# Capital Market Assumptions (strategic, ~10y, geometric, nominal USD)
# =====================================================================================
def load_consensus():
    return json.load(open(os.path.join(
        ROOT, 'Research/Portfolio_Construction/validation/final_audit_2026-08/consensus_cma.json')))


def interp_curve(Y, dur):
    pts = [(1, Y['DGS1']), (2, Y['DGS2']), (3, Y['DGS3']), (5, Y['DGS5']), (7, Y['DGS7']),
           (10, Y['DGS10']), (20, Y['DGS20']), (30, Y['DGS30'])]
    xs, ys = zip(*pts)
    return float(np.interp(dur, xs, ys))


def build_cma(snap, ust_dur):
    """Primary CMA per sleeve with its source and a forecast-error sd (the BL view confidence).
    Equities / real assets / cash: 13-house consensus median (sourced, 2026-08 synthesis).
    Fixed income: yield building blocks from today's observed curve and spreads (the platform's
    own building-block method, PC-11 step 3: 'current yield ± expected spread/rate change'),
    because house vintages were set at a 10y of ~4.1-4.3 vs ~4.9 today."""
    Y = {k: v['value'] for k, v in snap.items()}
    C = load_consensus()
    cons, p25, p75, jpm, nh = C['consensus'], C['pessimistic'], C['optimistic'], C['jpm'], C['n_houses']
    ust_y = interp_curve(Y, ust_dur)
    rows = {
        'US_EQ': (cons['SPY'], 'consensus median', nh['SPY'], 2.5, p25['SPY'], p75['SPY'], jpm['SPY']),
        'DM_EQ': (cons['EFA'], 'consensus median (EAFE view; Canada assumed equal)', nh['EFA'], 2.5, p25['EFA'], p75['EFA'], jpm['EFA']),
        'EM_EQ': (cons['EEM'], 'consensus median', nh['EEM'], 3.0, p25['EEM'], p75['EEM'], jpm['EEM']),
        'UST': (ust_y, f'Treasury curve at sleeve duration {ust_dur:.1f}y (observed)', 'yield', 0.5, cons['IEF'], None, jpm['IEF']),
        'MBS': (interp_curve(Y, DUR['MBB']) + 0.45 - 0.15, 'Treasury @5.8y + MBS OAS ~45bp − prepayment/convexity 15bp (derived)', 'derived', 0.75, None, None, None),
        'IG': (Y['BAMLC0A0CMEY'] - 0.25, 'IG index yield − 25bp downgrade/default drag', 'yield', 0.75, cons['LQD'], None, jpm['LQD']),
        'TIPS': (Y['DFII10'] + Y['T10YIE'] - 0.05, '10y real yield + breakeven − 5bp', 'yield', 0.75, cons['TIP'], None, jpm['TIP']),
        'HY': (Y['BAMLH0A0HYM2EY'] - 2.0, 'HY index yield − ~2%/yr default loss', 'yield', 1.5, cons['HYG'], None, jpm['HYG']),
        'REIT': (cons['VNQ'], 'consensus median', nh['VNQ'], 2.5, p25['VNQ'], p75['VNQ'], jpm['VNQ']),
        'CMDTY': (cons['DBC'], 'consensus median', nh['DBC'], 3.0, p25['DBC'], p75['DBC'], jpm['DBC']),
        'GOLD': (cons['GLD'], 'JPM only (n=1) — low confidence', nh['GLD'], 3.5, None, None, jpm['GLD']),
        'Cash': (cons['Cash'], 'consensus median (10y average bill rate)', nh['Cash'], 0.5, p25['Cash'], p75['Cash'], jpm['Cash']),
    }
    cma = pd.DataFrame(rows, index=['mu', 'source', 'n', 'err_sd', 'p25_or_cons', 'p75', 'jpm']).T
    cma['mu'] = cma['mu'].astype(float)
    cma['err_sd'] = cma['err_sd'].astype(float)
    return cma, Y


# =====================================================================================
# Risk model
# =====================================================================================
RECENT_M = 60          # PC-11 step 2: trailing 5-year window for the stock-bond override
INF_START, INF_END = pd.Period('2021-01', 'M'), pd.Period('2023-12', 'M')   # reporting only (inflation era)


def forward_cov(S, corr_blend=0.5, recent=RECENT_M):
    """PC-11 step 2 (governing spec): full-to-date vols; correlations = 50% full-to-date + 50% trailing
    5-year — the stock-bond override for the documented 2022 structural break. Point-in-time capable:
    pass S truncated at the decision date."""
    vol = S.std() * np.sqrt(12)
    c_full = S.corr()
    c_rec = S.iloc[-recent:].corr()
    c = (1 - corr_blend) * c_full + corr_blend * c_rec
    cov = pd.DataFrame(np.outer(vol, vol) * c.values, index=S.columns, columns=S.columns)
    ev = np.linalg.eigvalsh(cov.values)
    if ev.min() < 1e-10:                                     # keep PSD
        cov = cov + (1e-10 - ev.min()) * np.eye(len(cov))
    return cov


# =====================================================================================
# Ranges — stated BEFORE any optimization (policy = where the SAA may sit;
# hard = where any layer may take the book: PC-09 lineage)
# =====================================================================================
CLASS_POLICY = {'Equity': (0.45, 0.70), 'Fixed income': (0.20, 0.45), 'Real assets': (0.02, 0.15),
                'Cash': (0.02, 0.10)}
CLASS_HARD = {'Equity': (0.20, 0.75), 'Fixed income': (0.15, 0.65), 'Real assets': (0.00, 0.20),
              'Cash': (0.02, 0.25)}
SLEEVE_HARD = {'US_EQ': (0.10, 0.50), 'DM_EQ': (0.03, 0.28), 'EM_EQ': (0.00, 0.15),
               'UST': (0.03, 0.40), 'MBS': (0.00, 0.15), 'IG': (0.00, 0.15), 'TIPS': (0.00, 0.12),
               'HY': (0.00, 0.10), 'REIT': (0.00, 0.06), 'CMDTY': (0.00, 0.08), 'GOLD': (0.00, 0.08),
               'Cash': (0.02, 0.25)}
SLEEVE_POLICY = dict(SLEEVE_HARD)
SLEEVE_POLICY.update({'REIT': (0.00, 0.05), 'CMDTY': (0.00, 0.05), 'GOLD': (0.00, 0.05)})
# shares WITHIN a class (policy): semi-efficient bands around market structure / FI role rules
SHARE_POLICY = {('US_EQ', 'Equity'): (0.45, 0.75), ('DM_EQ', 'Equity'): (0.15, 0.40),
                ('EM_EQ', 'Equity'): (0.05, 0.20),
                ('UST', 'Fixed income'): (0.30, 1.00), ('HY', 'Fixed income'): (0.00, 0.20)}
RANGE_WHY = {
    'Equity (class)': 'floor 45: the IPS growth objective (CPI+5 under 4.5% spending) needs an equity-majority engine; ceiling 70: upper institutional norm (sovereign-style 70/30) and the GFC-class drawdown the IPS can fund through',
    'Fixed income (class)': 'floor 20: ≥4 years of 4.5% spending held in liquid high-quality bonds; ceiling 45: ballast must not dominate a growth book (the IG-30 lesson, stated at class level)',
    'Real assets (class)': '2-15: PC-09 Real Assets floor/ceiling carried unchanged',
    'Cash (class)': 'floor 2: operating liquidity (PC-09); ceiling 10: cash drag in a growth mandate (alts/tail hedges moved to the overlay layer)',
    'US_EQ': 'hard 10-50 (PC-09 15-48, widened for stance room); policy share 45-75% of equity = ACWI cap ~63% ± a semi-efficient band; IPS forbids dependence on US exceptionalism (upper) without a large contrarian bet (lower)',
    'DM_EQ': 'hard 3-28 (PC-09 5-28); policy share 15-40% of equity around cap ~27%',
    'EM_EQ': 'hard 0-15 (PC-09 18 tightened: vol ~21%, concentration/governance risk); policy share 5-20% of equity around cap ~10%',
    'UST': 'hard 3-40; policy: Treasuries ≥30% of fixed income — the only sleeve reliably positive in equity-tail months (liquidity & flight-to-quality anchor)',
    'MBS': 'hard/policy 0-15: government-guaranteed spread sleeve; negative convexity limits it',
    'IG': 'hard/policy 0-15: spread carry with equity-tail correlation (LQD −4.5% in the GFC)',
    'TIPS': 'hard/policy 0-12: inflation-linked real yield',
    'HY': 'hard/policy 0-10 and ≤20% of fixed income: equity-like credit (HY-SPY corr ~0.74), core-plus norm',
    'REIT': 'hard 0-6 / policy 0-5: listed real estate is equity beta (corr ~0.75) with a real-asset label; market weight ~3-4%',
    'CMDTY': 'hard 0-8 / policy 0-5: zero-net-supply futures exposure; role = inflation-regime diversifier',
    'GOLD': 'hard 0-8 / policy 0-5: no cash flows, single-house CMA; above ~5% is rare outside central banks',
    'Cash': 'hard 2-25 (PC-09 Cash & Alts 2-25)',
}


def build_constraints(names, sleeve_rng, class_rng, share_rng=None):
    """Linear constraint list for SLSQP over sleeve weights (sum to 1 always)."""
    idx = {s: i for i, s in enumerate(names)}
    cons = [{'type': 'eq', 'fun': lambda w: w.sum() - 1.0}]
    for c, (lo, hi) in class_rng.items():
        jj = [idx[s] for s in names if CLASS[s] == c]
        cons.append({'type': 'ineq', 'fun': (lambda jj, lo: lambda w: w[jj].sum() - lo)(jj, lo)})
        cons.append({'type': 'ineq', 'fun': (lambda jj, hi: lambda w: hi - w[jj].sum())(jj, hi)})
    for (s, c), (lo, hi) in (share_rng or {}).items():
        jj = [idx[x] for x in names if CLASS[x] == c]
        i = idx[s]
        cons.append({'type': 'ineq', 'fun': (lambda i, jj, lo: lambda w: w[i] - lo * w[jj].sum())(i, jj, lo)})
        cons.append({'type': 'ineq', 'fun': (lambda i, jj, hi: lambda w: hi * w[jj].sum() - w[i])(i, jj, hi)})
    bounds = [sleeve_rng[s] for s in names]
    return cons, bounds


def mv_opt(mu, cov, gamma, cons, bounds, x0=None, nstart=8, seed=0):
    """max w'mu − γ/2 w'Σw subject to linear constraints. mu, cov in decimal annual units."""
    n = len(mu)
    obj = lambda w: -(w @ mu - 0.5 * gamma * (w @ cov @ w))
    jac = lambda w: -(mu - gamma * (cov @ w))
    rng = np.random.default_rng(seed)
    best = None
    starts = [x0] if x0 is not None else []
    for _ in range(nstart):
        x = rng.uniform(0, 1, n)
        starts.append(x / x.sum())
    for x in starts:
        r = minimize(obj, x, jac=jac, method='SLSQP', bounds=bounds, constraints=cons,
                     options={'maxiter': 2000, 'ftol': 1e-13})
        if r.success or r.status == 9:
            viol = max([0.0] + [-c['fun'](r.x) if c['type'] == 'ineq' else abs(c['fun'](r.x)) for c in cons])
            if viol < 1e-6 and (best is None or r.fun < best.fun):
                best = r
    return None if best is None else best.x


# =====================================================================================
# Layer 2 — stance books (optimizer-derived; replaces the hand-set PC-16 matrix)
# =====================================================================================
REGIMES = ['Expansion', 'Neutral', 'Slowdown', 'Contraction']
K_SHRINK = 24                                   # MAv2/v3 regime-confidence prior (gate G5)
STANCES = ['Growth', 'Recovery', 'Neutral', 'Defensive', 'Max Defensive']
STANCE_REGIME = {'Growth': 'Expansion', 'Recovery': 'Neutral', 'Neutral': 'Neutral',
                 'Defensive': 'Slowdown', 'Max Defensive': 'Contraction'}
# The validated risk ladder: structural vol of each PC-16 stance / Neutral (Vol_Budget_Recalibration.md,
# Growth 12.78 · Recovery 11.89 · Neutral 11.52 · Defensive 8.92 · Max Defensive 6.74). The stances keep
# the RISK POSTURE that passed walk-forward (G-7); the optimizer now decides their COMPOSITION.
LADDER = {'Growth': 12.78 / 11.52, 'Recovery': 11.89 / 11.52, 'Neutral': 1.0,
          'Defensive': 8.92 / 11.52, 'Max Defensive': 6.74 / 11.52}


def regime_cov(SRt, labels_t, regime, cov_fwd, K=K_SHRINK):
    """Σ_r = s·Σ_r,sample + (1−s)·Σ_fwd, s = n/(n+K) — MAv3 §4.3 shrinkage, anchored on the PC-11 forward Σ.
    Regime μ is deliberately NOT used (G1: estimated regime means did not survive out of sample)."""
    sub = SRt[labels_t.reindex(SRt.index) == regime]
    n = len(sub)
    if n < 3:
        return cov_fwd.copy(), n, 0.0
    s = n / (n + K)
    c = s * sub.cov().values * 12 + (1 - s) * cov_fwd
    return 0.5 * (c + c.T), n, s


def solve_book(mu, cov_opt, gamma, sleeve_rng, class_rng, share_rng, x0=None, nstart=4, seed=0):
    cons, bnds = build_constraints(SLEEVES, sleeve_rng, class_rng, share_rng)
    return mv_opt(mu, cov_opt, gamma, cons, bnds, x0=x0, nstart=nstart, seed=seed)


def derive_stance_books(SRt, labels_t, saa, mu_bl, mu_bl_x, m_post, cash_mu, rng, draws=40, cal_iter=11):
    """For each stance: re-solve the Layer-1 problem at the stance's vol (SAA vol × LADDER, measured on the
    strategic forward Σ), optimizing on the regime-conditional Σ, within the HARD ranges (+ the policy
    within-class share rules), resampled over the BL posterior. Neutral stance ≡ SAA (PC-16 convention)."""
    cov_fwd = forward_cov(SRt).values
    saa_v = np.array([saa[s] for s in SLEEVES])
    saa_vol = float(np.sqrt(saa_v @ cov_fwd @ saa_v))
    risky_ix = [SLEEVES.index(s) for s in SLEEVES if s != 'Cash']
    mus = []
    for _ in range(draws):
        m = np.full(len(SLEEVES), cash_mu)
        m[risky_ix] = cash_mu + rng.multivariate_normal(mu_bl_x, m_post)
        mus.append(m)
    books, info = {'Neutral': saa_v.copy()}, {}
    for st in STANCES:
        if st == 'Neutral':
            continue
        cov_r, n, s = regime_cov(SRt, labels_t, STANCE_REGIME[st], cov_fwd)
        target = saa_vol * LADDER[st]
        pt_cache = {}

        def avg_at(g):
            pt = solve_book(np.array(mu_bl), cov_r, g, SLEEVE_HARD, CLASS_HARD, SHARE_POLICY, nstart=3)
            W = [solve_book(m, cov_r, g, SLEEVE_HARD, CLASS_HARD, SHARE_POLICY, x0=pt, nstart=1, seed=k)
                 for k, m in enumerate(mus)]
            W = np.array([w for w in W if w is not None])
            return W.mean(axis=0)

        a_, b_ = 0.3, 80.0
        for _ in range(cal_iter):
            g = np.sqrt(a_ * b_)
            w = avg_at(g)
            a_, b_ = (g, b_) if float(np.sqrt(w @ cov_fwd @ w)) > target else (a_, g)
        g = np.sqrt(a_ * b_)
        w = avg_at(g)
        books[st] = w / w.sum()
        info[st] = dict(n=n, s=s, gamma=g, target_vol=target, vol=float(np.sqrt(w @ cov_fwd @ w)))
    info['Neutral'] = dict(n=int((labels_t == 'Neutral').sum()), s=None, gamma=None, target_vol=saa_vol, vol=saa_vol)
    return books, info, cov_fwd


def structural_budgets(books, cov_fwd, buffer=1.20):
    """Layer-4 vol budgets = each stance book's structural vol × 1.20 (audit B1 recalibration rule)."""
    return {st: float(np.sqrt(w @ cov_fwd @ w)) * buffer for st, w in books.items()}


# =====================================================================================
# Layer 3 — the platform's DCS engine, run on the v4 sleeves
# =====================================================================================
ORIENTATION = {'US_EQ': 1, 'DM_EQ': 1, 'EM_EQ': 1, 'HY': 1, 'REIT': 1, 'CMDTY': 1,
               'UST': -1, 'MBS': -1, 'IG': -1, 'TIPS': -1, 'GOLD': -1, 'Cash': -1}
# Legacy mapping (8 sleeves): USEq/IntlDM/EM/HY/RealA = +1 · IG/Govt/Cash = −1. Carried unchanged for every
# sleeve that existed; new split-outs: MBS/TIPS inherit IG/Govt (−1); REIT/CMDTY inherit RealA (+1); GOLD is
# the one reclassification (−1, safe haven: +1.6%/month in S&P worst-decile months) — flagged.


def dcs_tilts_v4(SR_ts, mrs_ts, ig_ts):
    import portfolio_dcs_signal as DCS
    DCS.SLEEVES = SLEEVES
    DCS.RISK_ORIENTATION = pd.Series(ORIENTATION)
    return DCS.dcs_tilts(SR_ts, mrs_ts, ig_ts)


# =====================================================================================
# Layer 4 — the platform's risk-budgeting engine, run on the v4 sleeves
# =====================================================================================
def configure_layer4(stance_vol_budget):
    import portfolio_risk_budgeting as RB
    RB.SLEEVES = SLEEVES
    RB.FLOOR = pd.Series({s: SLEEVE_HARD[s][0] for s in SLEEVES})
    RB.CEILING = pd.Series({s: SLEEVE_HARD[s][1] for s in SLEEVES})
    RB.HAVEN_RAISE = ['UST', 'Cash']          # PC-26: Govt/TIPS + Cash toward Defensive levels
    RB.HAVEN_CUT = ['HY', 'EM_EQ']            # PC-26: HY and EM toward floors
    RB.STANCE_VOL_BUDGET = dict(stance_vol_budget)
    return RB


def clip_class(w):
    """After Layer 4, enforce the HARD class ranges (sleeve clip is done inside RB): scale sleeves within an
    over-weight class down pro-rata, moving the excess to Cash (the defensive direction), iteratively."""
    w = w.copy()
    for _ in range(20):
        moved = False
        for c, (lo, hi) in CLASS_HARD.items():
            if c == 'Cash':
                continue
            members = [s for s in SLEEVES if CLASS[s] == c]
            tot = w[members].sum()
            if tot > hi + 1e-9:
                w[members] *= hi / tot
                w['Cash'] += tot - hi
                moved = True
        if not moved:
            break
    return w / w.sum()
