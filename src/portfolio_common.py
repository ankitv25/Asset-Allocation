"""
Portfolio Construction — shared foundation (single source of truth).

Institutional-standard hygiene: the governed sleeve set, canonical paths,
the transaction-cost model, annualization/metrics, and the nearest-PSD
repair were being redefined ad hoc across modules (SLEEVES alone appeared in
five files). This module centralizes them so every layer computes returns,
Sharpe, drawdown, and costs identically and there is one place to change a
convention. New modules (Layers 3-4, the waterfall integrator, the audit
fixes) import from here; the already-frozen Bricks 1-2 keep their own
local copies to avoid disturbing committed, validated outputs, but the
definitions here are byte-identical to theirs.

Nothing in here is a methodology decision -- these are conventions and
numerical utilities. Methodology lives in the layer modules and their
validation notes.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Data" / "Processed"
RESEARCH = ROOT / "Research" / "Portfolio_Construction"

# Canonical governed sleeve order. Every matrix, weight vector, and return
# panel in the portfolio-construction pipeline uses exactly this order.
SLEEVES = ["USEq", "IntlDM", "EM", "IG", "HY", "Govt", "RealA", "Cash"]

# Canonical production file locations (produced by the frozen bricks).
SLEEVE_RETURNS_FILE = DATA / "portfolio_sleeve_returns.csv"
CORR_FILE = DATA / "portfolio_correlation_matrix.csv"
VOL_FILE = DATA / "portfolio_volatility_annualized.csv"
COV_FILE = DATA / "portfolio_covariance_matrix.csv"

MONTHS_PER_YEAR = 12

# Round-trip transaction cost assumption, basis points of traded notional
# per unit of turnover (one side). 25 bps is a deliberately conservative
# all-in estimate for liquid multi-asset ETFs (spread + commission + a
# modest market-impact allowance) -- institutional desks typically realize
# less on names this liquid, so this biases reported net performance
# downward, which is the prudent direction for a go/no-go validation.
DEFAULT_COST_BPS = 25.0


# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------

def load_sleeve_returns(path=SLEEVE_RETURNS_FILE):
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = df.index.to_period("M").to_timestamp("M")
    return df


def to_month_end(idx):
    return pd.DatetimeIndex(idx).to_period("M").to_timestamp("M")


# ----------------------------------------------------------------------
# Turnover and transaction cost
# ----------------------------------------------------------------------

def turnover(weights_df):
    """Per-period one-side turnover = 0.5 * sum |Δw|. The 0.5 makes it a
    genuine one-side traded fraction (a full switch from one sleeve to
    another is 100% turnover, not 200%), so multiplying by a one-side cost
    in bps gives the correct round-trip-free cost."""
    return 0.5 * weights_df.diff().abs().sum(axis=1)


def apply_costs(gross_returns, weights_df, cost_bps=DEFAULT_COST_BPS):
    """Net monthly returns after charging `cost_bps` (one side) on each
    period's turnover. Aligns on the weights index; the first period has no
    prior weights so no cost is charged."""
    t = turnover(weights_df).reindex(gross_returns.index).fillna(0.0)
    return gross_returns - t * (cost_bps / 10000.0)


# ----------------------------------------------------------------------
# Performance metrics (one definition, used everywhere)
# ----------------------------------------------------------------------

def ann_return(returns):
    return (1 + returns).prod() ** (MONTHS_PER_YEAR / len(returns)) - 1


def ann_vol(returns):
    return returns.std() * np.sqrt(MONTHS_PER_YEAR)


def max_drawdown(returns):
    cum = (1 + returns).cumprod()
    return (cum / cum.cummax() - 1).min()


def realized_rf(cash_returns, index):
    """Annualized realized cash return over the given index -- the honest
    risk-free rate for an OOS Sharpe (not a fixed forward CMA assumption,
    per the bug fixed in the correlation-validation work)."""
    cash = cash_returns.reindex(index)
    return (1 + cash).prod() ** (MONTHS_PER_YEAR / len(cash)) - 1


def perf_stats(returns, cash_returns):
    ar = ann_return(returns)
    av = ann_vol(returns)
    rf = realized_rf(cash_returns, returns.index)
    mdd = max_drawdown(returns)
    return {
        "ann_return": ar,
        "ann_vol": av,
        "sharpe": (ar - rf) / av if av > 0 else np.nan,
        "max_drawdown": mdd,
        "calmar": ar / abs(mdd) if mdd != 0 else np.nan,
        "n_months": len(returns),
    }


# ----------------------------------------------------------------------
# Covariance / risk utilities
# ----------------------------------------------------------------------

def nearest_psd(matrix, epsilon=0.0):
    """Higham-style nearest positive-semidefinite repair via eigenvalue
    clipping, then rescale the diagonal back to the original variances so a
    covariance stays a covariance (and a correlation keeps unit diagonal).
    Returns the input unchanged (up to float noise) when it is already PSD,
    so it is a safe no-op on well-formed matrices.

    Pairwise correlation/covariance built from differing overlap windows is
    not guaranteed PSD; an optimizer or risk forecast on a non-PSD matrix is
    silently invalid. This is the defensive repair, applied only when the
    minimum eigenvalue is below `epsilon`."""
    a = np.asarray(matrix, dtype=float)
    a = 0.5 * (a + a.T)
    vals, vecs = np.linalg.eigh(a)
    if vals.min() >= epsilon:
        repaired = a
    else:
        vals_clipped = np.clip(vals, epsilon, None)
        repaired = (vecs * vals_clipped) @ vecs.T
        repaired = 0.5 * (repaired + repaired.T)
        # restore original diagonal (variances / unit correlation diagonal)
        d_orig = np.sqrt(np.clip(np.diag(a), 0, None))
        d_new = np.sqrt(np.clip(np.diag(repaired), 1e-300, None))
        scale = np.divide(d_orig, d_new, out=np.ones_like(d_new), where=d_new > 0)
        repaired = repaired * np.outer(scale, scale)
    if isinstance(matrix, pd.DataFrame):
        return pd.DataFrame(repaired, index=matrix.index, columns=matrix.columns)
    return repaired


def is_psd(matrix, tol=1e-10):
    vals = np.linalg.eigvalsh(np.asarray(matrix, dtype=float))
    return bool(vals.min() >= -tol), float(vals.min())


def portfolio_vol(weights, cov):
    """Annualized portfolio volatility from a weight vector and an annualized
    covariance matrix, both aligned to SLEEVES."""
    w = weights.reindex(cov.index).values
    return float(np.sqrt(w @ cov.values @ w))


def risk_contribution(weights, cov):
    """Fractional contribution to portfolio variance per sleeve (sums to 1)."""
    w = weights.reindex(cov.index).values
    port_var = w @ cov.values @ w
    if port_var <= 0:
        return pd.Series(np.nan, index=cov.index)
    mctr = cov.values @ w
    return pd.Series(w * mctr / port_var, index=cov.index)
