"""
fs4_core.py — Summer Funds v4: the four-fund architecture (Absolute Return, SAA, Endowment, Long-Horizon Growth),
each an SAA book built with the drawdown limit inside the optimizer (v3 method) plus a DAA expression on top.
Pre-registration: docs/methodology/Fund_Suite_v4_PreRegistration_2026-09-19.md.
"""
import os

import numpy as np
import pandas as pd

import fs2_core as G
import fs3_core as V
import fs_core as F

OUT = os.path.join(V.OUT.replace('fund_suite_v3', 'fund_suite_v4'))
os.makedirs(OUT, exist_ok=True)
S4, RISKY4, CLASS4, CLASSES4 = V.S3, V.RISKY3, V.CLASS3, V.CLASSES3
LABEL4, IMPL4 = V.LABEL3, V.IMPL3


def _bands(eq, us, dm, em, ra, gold, cmdty, reit, infra, mf, dfn, ustl, cash, vol_cap, cdar, ddcap):
    sl = {'US_EQ': (0, 1), 'DM_EQ': (0, 1), 'EM_EQ': (0, 1), 'UST': (0, 1), 'USTL': ustl, 'TIPS': (0, 0.12),
          'IG': (0, 0.15), 'HY': (0, 0.05), 'REIT': reit, 'INFRA': infra, 'CMDTY': cmdty, 'GOLD': gold, 'MF': mf,
          'Cash': cash}
    cls = {'Equity': eq, 'Defensive': dfn, 'Real assets': ra, 'Diversifiers': mf, 'Cash': cash}
    sh = {('US_EQ', 'Equity'): us, ('DM_EQ', 'Equity'): dm, ('EM_EQ', 'Equity'): em, ('UST', 'Defensive'): (0.20, 1.0)}
    return dict(sleeve=sl, cls=cls, share=sh, vol_cap=vol_cap, cdar=cdar, ddcap=ddcap)


FUNDS4 = {
    'Absolute Return': dict(floor=0.0, horizon='3+ years', peer='Paper 30/70', real_peer='AOM (real 40/60)',
                            purpose='Preserve capital and generate positive returns across regimes',
                            bands=_bands((0.15, 0.35), (0.50, 0.65), (0.20, 0.35), (0.05, 0.15), (0.12, 0.18),
                                         (0.06, 0.08), (0.02, 0.05), (0.00, 0.04), (0.00, 0.05), (0.08, 0.18),
                                         (0.35, 0.60), (0.00, 0.20), (0.02, 0.15), 0.07, 0.06, 0.08)),
    'SAA': dict(floor=0.5, horizon='7+ years', peer='Paper 60/40', real_peer='AOR (real 60/40)',
                purpose='The central investable reference portfolio — long-term policy weights',
                bands=_bands((0.40, 0.60), (0.50, 0.65), (0.20, 0.35), (0.05, 0.15), (0.13, 0.18), (0.06, 0.08),
                             (0.02, 0.05), (0.02, 0.05), (0.00, 0.05), (0.05, 0.12), (0.22, 0.38), (0.00, 0.18),
                             (0.02, 0.10), 0.11, 0.12, 0.16)),
    'Endowment': dict(floor=0.5, horizon='10+ years', peer='Paper 60/40', real_peer='AOR (real 60/40)',
                      purpose='Long-horizon compounding with real assets and liquid diversifiers',
                      bands=_bands((0.38, 0.52), (0.55, 0.70), (0.17, 0.30), (0.05, 0.13), (0.18, 0.23), (0.06, 0.08),
                                   (0.02, 0.05), (0.02, 0.05), (0.03, 0.06), (0.12, 0.18), (0.15, 0.28), (0.00, 0.15),
                                   (0.02, 0.10), 0.11, 0.14, 0.19)),
    'Long-Horizon Growth': dict(floor=0.5, horizon='20+ years', peer='Paper 80/20', real_peer='AOA (real 80/20)',
                                purpose='20–30 year compounding, growth-led but diversified',
                                # equity floor set at 48% by judgment: at 55% the only feasible book loses 32%,
                                # and the extra 7pp of equity buys just 0.45pp of expected return
                                bands=_bands((0.48, 0.72), (0.60, 0.75), (0.17, 0.28), (0.05, 0.13), (0.13, 0.18),
                                             (0.06, 0.08), (0.02, 0.05), (0.02, 0.05), (0.00, 0.04), (0.08, 0.15),
                                             (0.08, 0.22), (0.00, 0.14), (0.02, 0.08), 0.13, 0.22, 0.29)),
}
SWEEP = [0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.25, 0.28]


def solve_fund(R, mu, b, M):
    """Tightest feasible budget at or above the declared one (pre-registration §2), then the volatility cap."""
    cd, dcap = b['cdar'], b['ddcap']
    tried = []
    for _ in range(14):
        w, _ = V.solve_cdar(R, mu, b, cdar=cd, ddcap=dcap)
        tried.append((cd, w is not None))
        if w is None:                                  # infeasible: loosen to the next budget on the grid
            nxt = [x for x in SWEEP if x > cd + 1e-9]
            if not nxt:
                return None, cd, dcap, tried
            cd, dcap = nxt[0], nxt[0] * (b['ddcap'] / b['cdar'])
            continue
        if V.fwd(w, M)['vol'] <= 100 * b['vol_cap'] + 1e-9:
            return w, cd, dcap, tried
        cd, dcap = cd - 0.01, dcap - 0.01              # volatility cap binds: tighten
    return None, cd, dcap, tried


def e1(R):
    s = (F.tsmom(R, 3) + F.tsmom(R, 6) + F.tsmom(R, 12)) / 3
    s['MF'] = 1.0
    s['Cash'] = 1.0
    return s


def run_daa(w_target, R, months, floor, sig, cost=V.COST, fee=V.FEE_YR):
    """SAA book with the DAA expression on top: exposure = floor + (1-floor)*E1, rebalanced monthly to that
    target (the DAA is a monthly expression by construction); switched-out weight goes to T-bills."""
    idx = pd.PeriodIndex(months)
    Rm = R.reindex(idx)[S4]
    S = sig.reindex(idx - 1).fillna(1.0)
    S.index = idx
    W = pd.DataFrame(np.outer(np.ones(len(idx)), w_target.reindex(S4).values), index=idx, columns=S4)
    W = W.where(Rm.notna(), 0.0)
    W = W.div(W.sum(axis=1), axis=0)
    e = floor + (1 - floor) * S
    for s in RISKY4:
        W['Cash'] += W[s] * (1 - e[s])
        W[s] *= e[s]
    r = (W * Rm.fillna(0)).sum(axis=1) - W.diff().abs().sum(axis=1).fillna(0) * cost - fee / 12
    return r, W
