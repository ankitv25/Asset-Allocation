"""
fs5_signals.py — the market and macro signal panel behind the DAA fund.

Every series is built so that the value stamped on month t uses only information that existed at the
end of month t-1: prices are lagged one month, macro releases two (a CPI print for month m is published
in month m+1, so it is usable from m+2).
"""
import os

import numpy as np
import pandas as pd

import mafv4_core as K

FRED = os.path.join(K.ROOT, 'Data/Raw/Fred')
INFL_CMA = 2.30          # the inflation assumption inside our CMAs — what a breakeven is judged against
IG_DRAG = 0.25           # downgrade/default drag on IG, as in the CMA
HY_DRAG = 2.40           # long-run credit loss on high yield, as in the CMA


def _m(df):
    return df.groupby(pd.PeriodIndex(df.index, freq='M')).last()


def macro(refresh=False):
    """Monthly macro panel, publication-lagged: month t carries what a desk knew on the last day of t-1.

    Pulled from FRED so the record reaches back to the start of the return panel; the yield curve runs
    from 1962, corporate yields from 1919, the VIX from 1990. The two inflation-linked series (the 10-year
    real yield and the breakeven) only begin in 2003, so the TIPS valuation view is dark before then."""
    D = {s: K.fred_series(s, refresh) for s in
         ['DGS2', 'DGS10', 'DGS20', 'DGS30', 'DFII10', 'T10YIE', 'DTB3', 'VIXCLS', 'NFCI',
          'BAA', 'AAA', 'BAA10YM', 'CPIAUCSL', 'CPILFESL', 'PAYEMS', 'INDPRO', 'UNRATE']}
    mk = pd.DataFrame({k: _m(D[k].to_frame())[k] for k in
                       ['DGS2', 'DGS10', 'DGS20', 'DGS30', 'DFII10', 'T10YIE', 'DTB3', 'VIXCLS', 'NFCI',
                        'BAA', 'AAA', 'BAA10YM']}).sort_index()
    mk['DGS30'] = mk['DGS30'].fillna(mk['DGS20'])          # the 30-year was not issued 2002-2006
    mk = mk.ffill(limit=3).shift(1)                        # month t sees month t-1's close
    mc = pd.DataFrame({k: _m(D[k].to_frame())[k] for k in
                       ['CPIAUCSL', 'CPILFESL', 'PAYEMS', 'INDPRO', 'UNRATE']}).sort_index()
    M = pd.DataFrame(index=mc.index)
    M['CPI_YOY'] = (mc['CPIAUCSL'] / mc['CPIAUCSL'].shift(12) - 1) * 100
    M['CORE_YOY'] = (mc['CPILFESL'] / mc['CPILFESL'].shift(12) - 1) * 100
    M['PAY_6M'] = (mc['PAYEMS'] / mc['PAYEMS'].shift(6) - 1) * 100
    M['IP_YOY'] = (mc['INDPRO'] / mc['INDPRO'].shift(12) - 1) * 100
    M['UNRATE_12M'] = mc['UNRATE'] - mc['UNRATE'].rolling(12).min()
    M = M.shift(2)                                         # released with a month's lag, usable the next
    X = mk.join(M, how='outer')
    X['FEDFUNDS'] = X['DTB3']                              # T-bill yield is what our cash sleeve earns
    return X


def _ez(x, minp=36):
    """Expanding z-score — uses only history up to and including each point, so it never looks forward."""
    mu = x.expanding(min_periods=minp).mean()
    sd = x.expanding(min_periods=minp).std()
    return ((x - mu) / sd.replace(0, np.nan)).clip(-2.5, 2.5)


def live_cma(X, dur):
    """Expected return rebuilt each month from what the market is actually paying — the CMA, dialled to today.

    Only the sleeves where forward return is observable: the curve prices the Treasuries, the breakeven
    prices TIPS against our own inflation assumption, corporate yields price credit net of loss.
    Equities and real assets have no yield we trust, so they carry no valuation view (see fs5_core)."""
    y = pd.DataFrame(index=X.index)
    # curve interpolation on the 2s/10s/30s grid at each sleeve's duration
    for s, d in dur.items():
        if d <= 10:
            y[s] = X['DGS2'] + (X['DGS10'] - X['DGS2']) * (d - 2) / 8
        else:
            y[s] = X['DGS10'] + (X['DGS30'] - X['DGS10']) * (d - 10) / 20
    y['TIPS'] = X['DFII10'] + INFL_CMA                 # real yield + what WE assume inflation is
    y['IG'] = 0.5 * (X['AAA'] + X['BAA']) - IG_DRAG
    y['HY'] = X['BAA'] + 1.6 * X['BAA10YM'] - HY_DRAG  # no long high-yield yield series; Baa spread scaled
    y['Cash'] = X['FEDFUNDS']
    return y


def regime(X):
    """Four states from growth, inflation and stress — the labels are economics, not a fitted classifier."""
    g = (_ez(X['PAY_6M']) + _ez(X['IP_YOY']) - _ez(X['UNRATE_12M'])) / 3
    i = (_ez(X['CPI_YOY']) + _ez(X['CPI_YOY'] - X['CPI_YOY'].shift(6))) / 2
    st = (_ez(X['VIXCLS']) + _ez(X['NFCI']) + _ez(X['BAA10YM'])) / 3
    lab = pd.Series(index=X.index, dtype=object)
    lab[(g >= 0) & (i < 0)] = 'Goldilocks'
    lab[(g >= 0) & (i >= 0)] = 'Reflation'
    lab[(g < 0) & (i >= 0)] = 'Stagflation'
    lab[(g < 0) & (i < 0)] = 'Disinflationary slowdown'
    lab[st > 1.0] = 'Stress'                           # stress overrides: it is the state that matters most
    return pd.DataFrame(dict(growth=g, inflation=i, stress=st, state=lab))


# =====================================================================================
# MRS — the platform's backbone regime signal.
# The Macro Regime Score is the house regime framework (Research/MRS). The portfolios read their
# regime state FROM it rather than classifying the macro themselves, so there is one regime
# vocabulary on the platform: Expansion / Neutral / Slowdown / Contraction.
# =====================================================================================
MRS_HISTORY = os.path.join(K.ROOT, 'Research/MRS/monitoring/mrs_composite_history.csv')
MRS_STATES = ['Expansion', 'Neutral', 'Slowdown', 'Contraction']


def mrs():
    """Monthly MRS state and composite, lagged one month so a portfolio only ever acts on a score
    that was published before the month began. `regime_confirmed` is used, not `regime_raw`: the
    confirmed state is the one MRS itself treats as actionable."""
    d = pd.read_csv(MRS_HISTORY, parse_dates=['date'])
    d.index = pd.PeriodIndex(d['date'], freq='M')
    out = pd.DataFrame(index=d.index)
    out['state'] = d['regime_confirmed'].where(d['regime_confirmed'].isin(MRS_STATES))
    out['composite'] = pd.to_numeric(d['composite'], errors='coerce')
    out['trend'] = pd.to_numeric(d.get('comp_trend_6m'), errors='coerce')
    out = out[~out.index.duplicated(keep='last')].sort_index()
    return out.shift(1)                      # month t acts on the score published for t-1
