"""
Portfolio Construction — Dynamic Conviction Score (Layer 3), production engine.

Implements v1.0 Sec 8: a per-asset-class tactical conviction score that drives
band-limited tilts (±3pp/sleeve, Σ|tilt|≤10pp) WITHIN the stance set by Layer
2. Layer 3 is, by the doc's own description (Sec 8.5), "the most fallible
layer" — so it is built to be measured, separately attributed, and switched
off if it does not earn its place. The companion validation
(`pc_dcs_layer3_validation.py`) is the test of whether it does.

Two honest deviations from the PC-19 spec, both forced by available data and
flagged rather than papered over:

  1. CADENCE: PC-19/21 specify a WEEKLY DCS with a 2-consecutive-weekly-
     reading persistence rule. The platform's governed sleeve and macro data
     are MONTHLY (asset universe returns, MRS, FRED inputs are all monthly).
     The DCS is therefore computed MONTHLY here, with the persistence rule
     adapted to 2 consecutive monthly readings. A genuine weekly DCS needs a
     weekly/daily data pipeline that does not yet exist.

  2. COMPONENTS: the PC-19 interim design has 4 live components — momentum
     30%, macro/MRS alignment 30%, valuation 20%, credit 20%. Relative
     valuation (P/E, P/B) is "to be pulled" and not in the pipeline, so it is
     dropped and the remaining three are renormalized
     (momentum 0.375, macro 0.375, credit 0.25). Sentiment and earnings
     components are Phase-2B-deferred per the doc. This matches PC-19's own
     rule: "Deferred components enter only after their data pipelines exist
     and the component demonstrates value in backtest."

All scoring is point-in-time (expanding-window statistics through month M
only) so the engine is usable verbatim in the walk-forward backtest and live.

Inputs (passed in by the caller; this module does no file IO except in main):
    sleeve_returns   monthly, the 8 governed sleeves (momentum)
    mrs              composite + comp_3m_chg (macro alignment)
    ig_spread        monthly IG credit spread (credit conditions)

Tilt mapping (PC-20) and persistence (PC-21) are applied to turn scores into
a signed, self-funding, band-limited tilt vector per month.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Src"))
from portfolio_common import SLEEVES  # noqa: E402

# Renormalized interim component weights (valuation dropped — see docstring).
COMPONENT_WEIGHTS = {"momentum": 0.375, "macro": 0.375, "credit": 0.25}

# Structural risk orientation, pre-committed (not fitted): +1 = risk-on sleeve
# (conviction rises when macro/credit conditions improve), -1 = risk-off
# (conviction rises when conditions deteriorate — flight to quality).
RISK_ORIENTATION = pd.Series({
    "USEq": 1, "IntlDM": 1, "EM": 1, "HY": 1, "RealA": 1,
    "IG": -1, "Govt": -1, "Cash": -1,
})

TILT_BAND = 0.03          # ±3pp per sleeve (PC-20)
TILT_BUDGET = 0.10        # Σ|tilt| ≤ 10pp portfolio-wide (PC-20)
PERSIST_READINGS = 2      # PC-21, adapted to monthly


# ----------------------------------------------------------------------
# Component signals -> signed [-1, +1] per sleeve, point-in-time
# ----------------------------------------------------------------------

def _expanding_z(series, min_periods=24):
    """Expanding-window z-score (mean/std through each point only -> PIT)."""
    mean = series.expanding(min_periods=min_periods).mean()
    std = series.expanding(min_periods=min_periods).std()
    return (series - mean) / std


def momentum_signal(sleeve_returns):
    """Per sleeve: blended 3/6/12m trailing total return, expanding-z, tanh
    -> [-1,1]. High own momentum = positive conviction for that sleeve."""
    out = pd.DataFrame(index=sleeve_returns.index, columns=SLEEVES, dtype=float)
    for s in SLEEVES:
        r = sleeve_returns[s]
        m3 = (1 + r).rolling(3).apply(np.prod, raw=True) - 1
        m6 = (1 + r).rolling(6).apply(np.prod, raw=True) - 1
        m12 = (1 + r).rolling(12).apply(np.prod, raw=True) - 1
        blended = pd.concat([m3, m6, m12], axis=1).mean(axis=1)
        out[s] = np.tanh(_expanding_z(blended))
    return out


def macro_signal(mrs, index):
    """MRS level + direction, mapped per sleeve by risk orientation. A high,
    rising composite is risk-on; risk-off sleeves get the inverse."""
    comp = np.tanh(mrs["composite"].reindex(index))
    direction = np.tanh(mrs["comp_3m_chg"].reindex(index) * 2.0)
    base = 0.7 * comp + 0.3 * direction
    out = pd.DataFrame({s: RISK_ORIENTATION[s] * base for s in SLEEVES}, index=index)
    return out


def credit_signal(ig_spread, index):
    """IG credit-spread level (expanding-z) + 6m change. Tightening/low
    spreads are risk-on; risk-off sleeves get the inverse. Sign is flipped
    because a HIGH spread z is risk-OFF."""
    z = _expanding_z(ig_spread).reindex(index)
    chg6 = ig_spread.diff(6).reindex(index)
    chg6_z = _expanding_z(ig_spread.diff(6)).reindex(index)
    base = -(0.6 * np.tanh(z) + 0.4 * np.tanh(chg6_z))  # high/rising spread -> negative (risk-off)
    out = pd.DataFrame({s: RISK_ORIENTATION[s] * base for s in SLEEVES}, index=index)
    return out


def compute_dcs(sleeve_returns, mrs, ig_spread):
    """Blend the three component signals into a 0-10 DCS panel per sleeve.
    DCS = 5 + 5 * weighted-average-signal, clipped to [0,10]."""
    idx = sleeve_returns.index
    mom = momentum_signal(sleeve_returns)
    mac = macro_signal(mrs, idx)
    cred = credit_signal(ig_spread, idx)

    w = COMPONENT_WEIGHTS
    signal = (w["momentum"] * mom + w["macro"] * mac + w["credit"] * cred)
    dcs = (5 + 5 * signal).clip(0, 10)
    return dcs, {"momentum": mom, "macro": mac, "credit": cred}


# ----------------------------------------------------------------------
# Tier function (PC-20) and persistence (PC-21)
# ----------------------------------------------------------------------

def tier_fraction(dcs_value):
    """PC-20 symmetric tier function -> fraction of the tilt band. A missing
    DCS (e.g. a month without MRS/credit data) is neutral, NOT strong-
    negative — guarding this explicitly because an unguarded NaN silently
    falls through every comparison to the bottom tier."""
    if pd.isna(dcs_value):
        return 0.0
    if dcs_value >= 8.0:
        return 1.0
    if dcs_value >= 6.5:
        return 0.5
    if dcs_value > 4.0:
        return 0.0
    if dcs_value > 2.0:
        return -0.5
    return -1.0


def tier_panel(dcs):
    """Vectorized PC-20 tiers over a DCS panel (NaN -> 0)."""
    v = dcs.values
    out = np.select(
        [v >= 8.0, v >= 6.5, v > 4.0, v > 2.0, v <= 2.0],
        [1.0, 0.5, 0.0, -0.5, -1.0],
        default=0.0,
    )
    out = np.where(np.isnan(v), 0.0, out)
    return pd.DataFrame(out, index=dcs.index, columns=dcs.columns)


def apply_persistence(tier_panel):
    """PC-21: a non-neutral tier acts only after persisting 2 consecutive
    readings; an active tilt is removed after the tier is neutral for 2
    consecutive readings. Returns the persisted (gated) tier panel."""
    gated = pd.DataFrame(0.0, index=tier_panel.index, columns=tier_panel.columns)
    for s in tier_panel.columns:
        active = 0.0
        neutral_run = 0
        col = tier_panel[s]
        for i, (date, raw) in enumerate(col.items()):
            if raw != 0 and i >= 1 and np.sign(col.iloc[i - 1]) == np.sign(raw):
                active = raw            # 2 consecutive same-direction non-neutral readings
                neutral_run = 0
            elif raw == 0:
                neutral_run += 1
                if neutral_run >= PERSIST_READINGS:
                    active = 0.0
            # else: single non-neutral reading or direction flip -> hold prior active
            gated.loc[date, s] = active
    return gated


def self_funding_tilts(gated_tier):
    """Turn gated tier fractions into a signed tilt vector that sums to ~0
    (self-funding) and respects the Σ|tilt| ≤ budget cap. Positive and
    negative legs are balanced by scaling the heavier side down to the
    lighter; if only one side exists, the net is routed to/from Cash."""
    raw = gated_tier * TILT_BAND
    out = pd.DataFrame(0.0, index=raw.index, columns=raw.columns)
    for date, row in raw.iterrows():
        t = row.copy()
        pos = t[t > 0].sum()
        neg = -t[t < 0].sum()
        if pos > 0 and neg > 0:
            if pos > neg:
                t[t > 0] *= neg / pos
            elif neg > pos:
                t[t < 0] *= pos / neg
        elif pos > 0 and neg == 0:        # only longs: fund from Cash
            t["Cash"] -= pos
        elif neg > 0 and pos == 0:        # only shorts: park in Cash
            t["Cash"] += neg
        # Σ|tilt| cap
        gross = t.abs().sum()
        if gross > TILT_BUDGET and gross > 0:
            t *= TILT_BUDGET / gross
        out.loc[date] = t
    return out


def dcs_tilts(sleeve_returns, mrs, ig_spread):
    """End-to-end: returns (tilt_panel, dcs_panel). tilt_panel is the signed,
    persisted, self-funding, band-limited monthly tilt to ADD to the stance
    weights."""
    dcs, _ = compute_dcs(sleeve_returns, mrs, ig_spread)
    tier = tier_panel(dcs)
    gated = apply_persistence(tier)
    tilts = self_funding_tilts(gated)
    return tilts, dcs


# ----------------------------------------------------------------------

def main():
    from portfolio_common import load_sleeve_returns
    sleeve_returns = load_sleeve_returns()
    mrs = pd.read_csv(ROOT / "Research" / "MRS" / "monitoring" / "mrs_composite_history.csv",
                      parse_dates=["date"]).set_index("date")
    mrs.index = mrs.index.to_period("M").to_timestamp("M")
    inp = pd.read_csv(ROOT / "Data" / "Processed" / "mrs_inputs_monthly.csv",
                      index_col=0, parse_dates=True)
    inp.index = inp.index.to_period("M").to_timestamp("M")

    tilts, dcs = dcs_tilts(sleeve_returns, mrs[["composite", "comp_3m_chg"]], inp["ig_spread"])
    latest = dcs.dropna(how="all").index.max()  # latest month with a real DCS
    print(f"Latest DCS month (latest complete macro/credit data): {latest.date()}")
    print("\nCurrent DCS (0-10) per sleeve:")
    print(dcs.loc[latest].round(2))
    print("\nCurrent tactical tilt (pp) per sleeve:")
    print((tilts.loc[latest] * 100).round(2))
    print(f"\nΣ|tilt| = {tilts.loc[latest].abs().sum()*100:.2f}pp (budget 10pp); "
          f"net = {tilts.loc[latest].sum()*100:.2f}pp (should be ~0)")


if __name__ == "__main__":
    main()
