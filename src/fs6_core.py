"""
fs6_core.py — Summer Funds v6: four funds that are different by construction, not by dial setting.

  Certain    — preserve purchasing power. TIPS-led, gold and Swiss franc as the store of value.
               No managed futures, no commodities, no listed property, no long duration.
  Endowment  — the endowment model made liquid. Real assets are the identity; thin nominal bonds.
               No managed futures.
  SAA        — the policy portfolio. Lean, equity-led, nine holdings, a properly sized trend sleeve.
  DAA        — the SAA book with its diversifiers sized by macro, plus the four tilt engines.

Each fund declares its own sleeve set. A sleeve a fund does not believe in is bounded to zero, not
left to the optimiser to discover.
"""
import os

import numpy as np
import pandas as pd

import fs3_core as V
import fs4_core as W4
import fs5_core as W5
import mafv4_core as K

OUT = V.OUT.replace('fund_suite_v3', 'fund_suite_v6')
os.makedirs(OUT, exist_ok=True)

S6 = V.S3[:-1] + ['CHF', 'Cash'] if 'Cash' in V.S3 else V.S3 + ['CHF']
S6 = [s for s in V.S3 if s != 'Cash'] + ['CHF', 'Cash']
RISKY6 = [s for s in S6 if s != 'Cash']
CLASS6 = dict(V.CLASS3, CHF='Real assets')          # a store of value, not a diversifier strategy
CLASSES6 = V.CLASSES3
LABEL6 = dict(V.LABEL3, CHF='Swiss franc')
IMPL6 = dict(V.IMPL3, CHF='FXF / CHF deposit')
CHF_CMA = 1.50          # Swiss short rate plus PPP drift at the long-run Swiss–US inflation gap
CHF_W_MKT = 0.015


def chf_returns():
    """Swiss franc held by a dollar investor: the spot move plus the Swiss short rate."""
    sp = K.fred_series('DEXSZUS')                               # CHF per USD
    m = sp.groupby(pd.PeriodIndex(sp.index, freq='M')).last()
    r3 = K.fred_series('IR3TIB01CHM156N')
    rc = K.fred_series('IRSTCI01CHM156N')
    r3 = r3.groupby(pd.PeriodIndex(r3.index, freq='M')).last()
    rc = rc.groupby(pd.PeriodIndex(rc.index, freq='M')).last()
    rate = r3.reindex(m.index).fillna(rc.reindex(m.index)).ffill()
    return ((m.shift(1) / m - 1) + rate.shift(1) / 1200).dropna()


def load():
    L = V.load()
    c = chf_returns()
    L['R'] = L['R'].assign(CHF=c.reindex(L['R'].index))[S6]
    L['RP'] = L['RP'].assign(CHF=c.reindex(L['RP'].index))[S6]
    return L


_PATCHED = [False]


def _patch():
    """Extend the shared sleeve universe in place, so the solver, the band checks and the tilt engines
    all see the franc. Done after the Black-Litterman step, which has no prior for a currency."""
    if _PATCHED[0]:
        return
    V.extend_universe(S6, CLASS6, LABEL6, IMPL6, {'CHF': 0})
    W5.S5, W5.RISKY5 = V.S3, V.RISKY3
    W5.VAL_SLEEVES = [x for x in W5.VAL_SLEEVES if x in S6]
    # the regime tilt is class-level (the Playbook's regime books) and is mapped onto whatever sleeves
    # a portfolio actually holds at build time, so there is no per-universe vector to reindex here.
    _PATCHED[0] = True


def model(L):
    """The v3 model, extended with the franc. A currency has no market-capitalisation prior, so it
    enters with its capital-market assumption directly rather than through the Black-Litterman blend."""
    L14 = dict(L, R=L['R'][[c for c in L['R'].columns if c != 'CHF']])
    M = V.model(L14)
    _patch()
    panel = L['R'].loc[V.WIN[0]:V.WIN[1]].dropna()
    cov = K.forward_cov(panel)
    cma = M['cma'].copy()
    cma.loc['CHF'] = dict(mu=CHF_CMA, source='Swiss 3m rate + PPP drift (Swiss–US inflation gap)',
                          n='house', err_sd=1.5)
    mu = pd.Series(M['mu_bl'], index=[x for x in S6 if x != 'CHF']).reindex(S6)
    mu['CHF'] = CHF_CMA / 100
    return dict(M, cma=cma.reindex(S6), cov=cov.reindex(index=S6, columns=S6), panel=panel,
                mu_bl=mu.values, mu=mu)


def bands(sleeves, cls, share, vol_cap, cdar, ddcap):
    """Explicit per-fund sleeve set: anything not named is bounded to zero."""
    sl = {s: tuple(sleeves.get(s, (0.0, 0.0))) for s in S6}
    return dict(sleeve=sl, cls=cls, share=share, vol_cap=vol_cap, cdar=cdar, ddcap=ddcap)


FUNDS6 = {
    'Certain': dict(
        horizon='3+ years', ref='ACWI 40 / Agg 60',
        purpose='Preserve purchasing power. Real yield, high-grade nominal bonds, and a store-of-value pocket.',
        identity='Short duration by design, with T-bills held as a real position rather than a residual. '
                 'Gold and the Swiss franc are the store of value. No trend sleeve, no listed property, '
                 'no long Treasuries.',
        bands=bands({'US_EQ': (0.08, 0.14), 'DM_EQ': (0.02, 0.05), 'UST': (0.12, 0.22), 'TIPS': (0.10, 0.18),
                     'IG': (0.02, 0.08), 'GOLD': (0.05, 0.07), 'CMDTY': (0.00, 0.04), 'CHF': (0.03, 0.05),
                     'Cash': (0.12, 0.28)},
                    {'Equity': (0.10, 0.16), 'Defensive': (0.30, 0.46), 'Real assets': (0.08, 0.14),
                     'Diversifiers': (0.0, 0.0), 'Cash': (0.12, 0.28)},
                    {('US_EQ', 'Equity'): (0.62, 0.80)},
                    0.05, 0.08, 0.11)),
    'Endowment': dict(
        horizon='10+ years', ref='ACWI 60 / Agg 40',
        purpose='The endowment model, made liquid: real assets and equity compounding purchasing power.',
        identity='Real assets are the identity — property, infrastructure, commodities and gold at a quarter '
                 'of the fund. Thin nominal bonds, TIPS-led. No trend sleeve.',
        bands=bands({'US_EQ': (0.17, 0.26), 'DM_EQ': (0.04, 0.09), 'EM_EQ': (0.03, 0.07),
                     'UST': (0.04, 0.12), 'USTL': (0.08, 0.15), 'TIPS': (0.08, 0.15), 'IG': (0.0, 0.05),
                     'REIT': (0.04, 0.07), 'INFRA': (0.04, 0.07), 'CMDTY': (0.05, 0.07), 'GOLD': (0.07, 0.08),
                     'Cash': (0.02, 0.06)},
                    {'Equity': (0.30, 0.38), 'Defensive': (0.26, 0.36), 'Real assets': (0.21, 0.27),
                     'Diversifiers': (0.0, 0.0), 'Cash': (0.02, 0.06)},
                    {('US_EQ', 'Equity'): (0.55, 0.70)},
                    0.095, 0.16, 0.22)),
    'SAA': dict(
        horizon='20+ years', ref='ACWI 80 / Agg 20',
        purpose='The house policy portfolio: 20-30 year compounding, growth-led and deliberately lean.',
        identity='Nine holdings. Equity, two Treasury durations, gold, commodities and a trend sleeve sized '
                 'like a sleeve, not like a hedge fund.',
        bands=bands({'US_EQ': (0.33, 0.44), 'DM_EQ': (0.07, 0.13), 'EM_EQ': (0.04, 0.09),
                     'UST': (0.02, 0.08), 'USTL': (0.10, 0.20), 'GOLD': (0.06, 0.08), 'CMDTY': (0.03, 0.05),
                     'MF': (0.04, 0.08), 'Cash': (0.02, 0.04)},
                    {'Equity': (0.50, 0.60), 'Defensive': (0.16, 0.26), 'Real assets': (0.09, 0.13),
                     'Diversifiers': (0.04, 0.08), 'Cash': (0.02, 0.04)},
                    {('US_EQ', 'Equity'): (0.62, 0.78)},
                    0.12, 0.22, 0.29)),
}

# The DAA is the alpha fund and carries its own risk budget — roughly the volatility of the S&P 500 —
# rather than inheriting the policy portfolio's. Same philosophy, same sleeve family, more of it.
ALPHA_BOOK = dict(
    horizon='10+ years', ref='S&P 500',
    purpose='Equity-level risk, run actively: the index\'s volatility budget, spent better.',
    identity='Carries its own ~14% volatility budget rather than the policy portfolio\'s. Equity-led, '
             'with gold, long Treasuries and a macro-sized trend sleeve doing the defending. '
             'Five engines and a wider tilt budget.',
    bands=bands({'US_EQ': (0.45, 0.80), 'DM_EQ': (0.06, 0.16), 'EM_EQ': (0.04, 0.13),
                 'USTL': (0.00, 0.12), 'GOLD': (0.05, 0.08), 'CMDTY': (0.02, 0.05),
                 'MF': (0.02, 0.06), 'Cash': (0.01, 0.03)},
                {'Equity': (0.80, 0.90), 'Defensive': (0.00, 0.14), 'Real assets': (0.05, 0.11),
                 'Diversifiers': (0.02, 0.06), 'Cash': (0.01, 0.03)},
                {('US_EQ', 'Equity'): (0.66, 0.82)},
                0.14, 0.45, 0.58))

# On the alpha fund the engines are allowed to speak louder, and the trend sleeve gets room the policy
# weights do not: its size is a macro decision, not an allocation.
ALPHA_MANDATE = dict(budget=20.0, sleeve_cap=0.42, sleeve_min=4.0, room={'MF': 8.0, 'CMDTY': 4.0, 'GOLD': 3.0})
DAA_SLEEVE_ROOM = {'MF': 7.0, 'CMDTY': 4.0, 'GOLD': 3.0}
SWEEP6 = W4.SWEEP + [0.32, 0.36, 0.40, 0.45]
