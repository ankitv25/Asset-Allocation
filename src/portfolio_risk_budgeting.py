"""
Portfolio Construction — Risk Budgeting (Layer 4), production rule engine.

Implements v1.0 Sec 9: the risk envelope that scales the output of Layers
1-3 toward safety but never toward more risk (Sec 11.6 rule 3). Four
mechanisms, applied in a fixed, auditable order:

  1. Safe-haven trigger (PC-26, FORMALIZED): MRS composite < -1.00, OR
     (MRS 3-month change < -0.50 AND composite < -0.30) -> raise Govt+Cash
     to their Defensive-stance levels and cut HY+EM to their floors,
     without waiting for the 2-month regime confirmation. The one deliberate
     exception to confirmation: accept false-alarm cost to cap tail risk.
  2. Drawdown-budget breach protocol (PC-24, FORMALIZED): track running
     drawdown vs the stance's budget; at >=100% consumed, de-risk one stance
     step regardless of the regime signal, and hold until drawdown recovers
     to 50% of budget. (80% consumed raises a review flag but does not move
     weights.) A breach can only ever make the portfolio MORE defensive.
  3. Volatility-budget scaling (PC-25, PROPOSED): forecast annualized vol
     from the 36-month covariance of the current weights; if it exceeds the
     stance budget, blend toward Max Defensive,
     w = lambda*w_target + (1-lambda)*w_MaxDef, with lambda the largest
     value <=1 for which the forecast meets the budget (closed-form below).
  4. Factor-concentration limit (PC-23, FORMALIZED): no single factor
     (equity, duration, credit, ...) may exceed 40% of total portfolio risk
     contribution. Measured and flagged here (returns-based, Sec 15.1);
     correction is a flag for the next rebalance, not an automatic reweight,
     because the corrective action (which sleeve to trim) is a governance
     decision, not a mechanical one.

Stance budgets (Sec 9.2 / 9.3), keyed by the five stances Layer 2 produces:

  Stance         Vol budget   Max-DD budget
  Growth            12%          -15%
  Neutral           11%          -14%   (Neutral DD is PROPOSED)
  Recovery          10%          -12%
  Defensive          8%          -10%
  Max Defensive      6%           -8%

This module is a pure function of its inputs (current stance, target
weights, point-in-time covariance, MRS state, running drawdown) -- it holds
no state. The caller (the waterfall integrator or the live monitor) supplies
the running drawdown and the breach-latch state; the walk-forward validation
(`pc_risk_budgeting_validation.py`) threads that state through history.

Floors/ceilings used here are the FORMALIZED Sec 6.2 (PC-09) bounds, NOT the
illustrative v2.1 bounds in the BL solver (Brick 2). See the pipeline audit
note: the formalized Sec 6.2 floors/ceilings should govern the constraint
and risk layers; reconciling Brick 2's optimizer bounds to them is an open
item pending the house CMA (G-2).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Src"))
from portfolio_common import SLEEVES, portfolio_vol, risk_contribution  # noqa: E402

# Volatility budgets. The PROPOSED PC-25 values (Growth 12 / Recovery 10 /
# Neutral 11 / Defensive 8 / Max Defensive 6 %) were found miscalibrated
# (audit finding B1): they sit at/below the stances' structural vol, so the
# scaler bound ~always. RECALIBRATED to structural vol * 1.20 (derived in
# Src/pc_vol_budget_recalibration.py; see Vol_Budget_Recalibration.md). With
# these, the scaler binds during genuine vol elevation only: Growth 0% /
# Recovery 17% / Neutral 10% / Defensive 80% (by design — held during stress)
# / Max Defensive 0% of months over 2008-2026.
STANCE_VOL_BUDGET = {"Growth": 0.155, "Recovery": 0.145, "Neutral": 0.140,
                     "Defensive": 0.105, "Max Defensive": 0.080}
STANCE_VOL_BUDGET_PROPOSED = {"Growth": 0.12, "Recovery": 0.10, "Neutral": 0.11,
                              "Defensive": 0.08, "Max Defensive": 0.06}
STANCE_DD_BUDGET = {"Growth": -0.15, "Recovery": -0.12, "Neutral": -0.14,
                    "Defensive": -0.10, "Max Defensive": -0.08}

# Risk ordering, most aggressive -> most defensive. "De-risk one step" moves
# one position toward Max Defensive. Recovery sits just above Neutral (it is
# slightly more risk-on per the PC-16 matrix: 34.5% vs 33.3% US equity).
STANCE_RISK_ORDER = ["Growth", "Recovery", "Neutral", "Defensive", "Max Defensive"]

# FORMALIZED Sec 6.2 (PC-09) floors/ceilings, aligned to SLEEVES.
FLOOR = pd.Series({"USEq": 0.15, "IntlDM": 0.05, "EM": 0.00, "IG": 0.08,
                   "HY": 0.00, "Govt": 0.00, "RealA": 0.02, "Cash": 0.02})
CEILING = pd.Series({"USEq": 0.48, "IntlDM": 0.28, "EM": 0.18, "IG": 0.30,
                     "HY": 0.14, "Govt": 0.25, "RealA": 0.15, "Cash": 0.25})

# Safe-haven sleeves to raise / cut (PC-26).
HAVEN_RAISE = ["Govt", "Cash"]
HAVEN_CUT = ["HY", "EM"]

# Factor-concentration governance (audit finding B2). PC-23's 40% single-
# factor risk limit is structurally UNACHIEVABLE for an unlevered long-only
# multi-asset book — equity-factor risk share runs 0.7-0.9 even at ~60%
# equity capital weight (the standard equity-risk-dominance result). Resolved
# as a MONITORING metric, not an enforced constraint: report the equity-factor
# share every period and ALERT above a realistic threshold; do not auto-
# reweight (the corrective action is a governance decision). The 0.40 ideal is
# retained only as a reference for non-equity factors (duration, credit),
# which a 60/40-style book CAN keep under 40%.
FACTOR_CONCENTRATION_IDEAL = 0.40          # PC-23 ideal; achievable for non-equity factors
EQUITY_FACTOR_ALERT = 0.80                 # realistic monitoring alert for the equity factor


# ----------------------------------------------------------------------
# Constraint clip (PC-23 / Sec 11.6 rule 1)
# ----------------------------------------------------------------------

def clip_to_bounds(weights):
    """Clip to Sec 6.2 floors/ceilings, then redistribute the residual
    pro-rata across sleeves that still have room, so the vector stays
    long-only and sums to 1. Iterates because a redistribution can push
    another sleeve through a bound."""
    w = weights.reindex(SLEEVES).clip(lower=FLOOR, upper=CEILING)
    for _ in range(100):
        residual = 1.0 - w.sum()
        if abs(residual) < 1e-12:
            break
        if residual > 0:  # need to add weight: distribute to sleeves below ceiling
            room = (CEILING - w).clip(lower=0)
        else:             # need to remove weight: take from sleeves above floor
            room = (w - FLOOR).clip(lower=0)
        total_room = room.sum()
        if total_room < 1e-12:
            break
        w = w + residual * room / total_room
        w = w.clip(lower=FLOOR, upper=CEILING)
    return w


# ----------------------------------------------------------------------
# 1. Safe-haven trigger (PC-26)
# ----------------------------------------------------------------------

def safe_haven_fires(mrs_composite, mrs_3m_change):
    return (mrs_composite < -1.00) or (mrs_3m_change < -0.50 and mrs_composite < -0.30)


def apply_safe_haven(weights, defensive_weights):
    """Raise Govt+Cash to (at least) their Defensive-stance levels, cut
    HY+EM to their floors, fund the net change pro-rata from the remaining
    sleeves, then clip to bounds."""
    w = weights.copy()
    for s in HAVEN_RAISE:
        w[s] = max(w[s], defensive_weights[s])
    for s in HAVEN_CUT:
        w[s] = FLOOR[s]
    others = [s for s in SLEEVES if s not in HAVEN_RAISE + HAVEN_CUT]
    gap = 1.0 - w.sum()  # negative if we added net weight -> take from others
    other_w = w[others]
    if other_w.sum() > 0:
        w[others] = other_w + gap * other_w / other_w.sum()
    return clip_to_bounds(w)


# ----------------------------------------------------------------------
# 2. Drawdown-budget breach protocol (PC-24)
# ----------------------------------------------------------------------

def step_down_stance(stance):
    i = STANCE_RISK_ORDER.index(stance)
    return STANCE_RISK_ORDER[min(i + 1, len(STANCE_RISK_ORDER) - 1)]


def drawdown_budget_status(running_dd, stance):
    """Fraction of the stance's drawdown budget consumed (0..1+), and the
    discrete protocol level: 'ok' / 'review' (>=80%) / 'breach' (>=100%)."""
    budget = STANCE_DD_BUDGET[stance]
    consumed = running_dd / budget if budget != 0 else 0.0  # both negative -> positive ratio
    if consumed >= 1.0:
        level = "breach"
    elif consumed >= 0.80:
        level = "review"
    else:
        level = "ok"
    return consumed, level


# ----------------------------------------------------------------------
# 3. Volatility-budget scaling (PC-25) -- closed form
# ----------------------------------------------------------------------

def vol_scale_lambda(w_target, w_maxdef, cov, budget):
    """Largest lambda in [0,1] with vol(lambda*w_target + (1-lambda)*w_maxdef)
    <= budget. vol^2(lambda) is a convex quadratic in lambda along the segment
    from w_maxdef (lambda=0) to w_target (lambda=1); solve exactly.

    Returns (lambda, forecast_vol_at_lambda, budget_binds: bool)."""
    a = w_target.reindex(cov.index).values
    b = w_maxdef.reindex(cov.index).values
    d = a - b
    S = cov.values
    A = float(d @ S @ d)          # lambda^2 coefficient
    B = float(2 * (d @ S @ b))    # lambda^1 coefficient
    C = float(b @ S @ b) - budget ** 2  # constant (vol^2 - budget^2 at lambda=0)

    vol_at = lambda lam: float(np.sqrt(max((b + lam * d) @ S @ (b + lam * d), 0.0)))

    # If the full target already meets the budget, no scaling.
    if vol_at(1.0) <= budget + 1e-12:
        return 1.0, vol_at(1.0), False
    # If even Max Defensive breaches the budget, clamp to lambda=0 (best we can do).
    if C > 0:
        return 0.0, vol_at(0.0), True
    # Solve A*lam^2 + B*lam + C = 0 for the root in [0,1].
    if abs(A) < 1e-15:
        lam = -C / B if abs(B) > 1e-15 else 0.0
    else:
        disc = max(B * B - 4 * A * C, 0.0)
        r1 = (-B + np.sqrt(disc)) / (2 * A)
        r2 = (-B - np.sqrt(disc)) / (2 * A)
        roots = [r for r in (r1, r2) if -1e-9 <= r <= 1 + 1e-9]
        lam = max(roots) if roots else 0.0
    lam = float(np.clip(lam, 0.0, 1.0))
    return lam, vol_at(lam), True


# ----------------------------------------------------------------------
# 4. Factor-concentration measurement (PC-23) -- returns-based
# ----------------------------------------------------------------------

def factor_risk_contributions(weights, sleeve_returns, factor_returns, window=36):
    """Returns-based factor risk decomposition (Sec 15.1): regress each
    sleeve's trailing `window`-month returns on the factor proxies, build a
    factor-model covariance of the sleeves, and report each factor's share
    of total portfolio risk. Returns a Series of factor risk fractions
    (may not sum to 1: the residual idiosyncratic share is the remainder)."""
    # Join sleeves and factors and drop any row with a missing value so the
    # trailing regression window never contains a NaN (early sleeve history
    # or a factor proxy that starts late would otherwise break lstsq).
    joined = pd.concat([sleeve_returns[SLEEVES], factor_returns], axis=1).dropna()
    if len(joined) < window:
        return None
    joined = joined.iloc[-window:]
    sr = joined[SLEEVES]
    fr = joined[factor_returns.columns]
    X = np.column_stack([np.ones(len(fr)), fr.values])
    betas = {}
    resid_var = {}
    for s in SLEEVES:
        y = sr[s].values
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        betas[s] = coef[1:]
        resid_var[s] = float(np.var(y - X @ coef, ddof=1))
    B = np.array([betas[s] for s in SLEEVES])            # sleeves x factors
    F = np.cov(fr.values, rowvar=False) * 12             # factor covariance, annualized
    D = np.diag([resid_var[s] * 12 for s in SLEEVES])    # idiosyncratic, annualized
    w = weights.reindex(SLEEVES).values
    total_var = float(w @ (B @ F @ B.T + D) @ w)
    if total_var <= 0:
        return None
    # Portfolio factor exposure wp = w'B (1 x factors). Each factor k's share
    # of total variance is wp_k * (F @ wp)_k / total_var; these sum to the
    # systematic (factor) share, with the remainder being idiosyncratic.
    wp = w @ B
    Fwp = F @ wp
    out = {fac: float(wp[k] * Fwp[k] / total_var)
           for k, fac in enumerate(factor_returns.columns)}
    return pd.Series(out)


# ----------------------------------------------------------------------
# Top-level Layer 4 application
# ----------------------------------------------------------------------

def apply_layer4(w_target, stance, cov, w_maxdef, defensive_weights,
                 mrs_composite, mrs_3m_change, running_dd, breach_latched=False):
    """Apply the full Layer 4 envelope in order. Returns (final_weights,
    diagnostics dict). `breach_latched` carries the drawdown-breach hold
    state from the prior period (the caller threads it through time)."""
    diag = {"stance_in": stance}

    w = w_target.copy()

    # 1. Safe-haven trigger
    sh = safe_haven_fires(mrs_composite, mrs_3m_change)
    diag["safe_haven_fired"] = bool(sh)
    if sh:
        w = apply_safe_haven(w, defensive_weights)

    # 2. Drawdown breach -> step the stance down (affects the vol budget used
    # below and latches a hold). The actual de-risking is expressed by
    # tightening the vol budget to the stepped-down stance's budget and
    # blending toward Max Defensive via the vol-scaler.
    consumed, dd_level = drawdown_budget_status(running_dd, stance)
    diag["dd_budget_consumed"] = consumed
    diag["dd_level"] = dd_level
    effective_stance = stance
    if dd_level == "breach" or breach_latched:
        effective_stance = step_down_stance(stance)
        diag["dd_stepped_to"] = effective_stance
    diag["breach_latched_out"] = bool(dd_level == "breach" or breach_latched)

    # 3. Volatility-budget scaling against the effective stance's budget
    budget = STANCE_VOL_BUDGET[effective_stance]
    forecast_vol_pre = portfolio_vol(w, cov)
    lam, forecast_vol_post, binds = vol_scale_lambda(w, w_maxdef, cov, budget)
    w = lam * w.reindex(SLEEVES) + (1 - lam) * w_maxdef.reindex(SLEEVES)
    diag.update({"vol_budget": budget, "forecast_vol_pre": forecast_vol_pre,
                 "lambda": lam, "forecast_vol_post": forecast_vol_post,
                 "vol_budget_binds": bool(binds)})

    # 4. Final constraint clip (defensive; the blends above stay in bounds
    # already, but a safe-haven + step-down combination can drift).
    w = clip_to_bounds(w)
    diag["final_vol"] = portfolio_vol(w, cov)

    return w, diag
