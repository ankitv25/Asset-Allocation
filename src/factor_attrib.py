#!/usr/bin/env python3
"""
factor_attrib.py — what the live NAV was EXPOSED to, and what each exposure paid.

WHY THIS EXISTS
The Live NAV page could say which holding moved the NAV (fund_nav's bridge) but not what the book was
exposed to. "VGLT cost 0.98 points" is a line item; "you were long 0.34 of duration and duration fell"
is a reason. The methodology already treats size and value as live dimensions -- PC-22's 3x3 box --
and style_box.py shows where the equity sleeve SITS, but nothing said what that positioning EARNED.

METHOD -- holdings-based factor attribution, not a fund-level regression
A fund-level regression on 51 daily observations would be noise: ten factors on fifty-one points
estimates nothing. But the actual daily weights are known, so the exposure does not have to be
estimated at all -- only the VEHICLES' betas do, and those are estimated on years of daily history
where they are stable:

  1. Estimate each vehicle's factor betas by OLS on a long daily window (LOOKBACK below).
  2. The book's exposure on day t is the weight-weighted sum of its vehicles' betas -- the real
     weights fund_nav recorded, so a rebalance inside the window is respected.
  3. Contribution of factor f = sum over days of (exposure_f,t x factor return_f,t), each scaled by
     the NAV level it was earned on, so contributions are in points of NAV like the holdings bridge.
  4. Whatever the factors do not explain is reported as a RESIDUAL, not spread silently over the
     factors. Residual + factors + costs == the NAV move, exactly.

THE FACTOR SET is tradeable and long/short where a spread is the point, so a beta reads as a position
rather than as an artefact of two correlated indices:

  Equity      ACWI            the market leg
  Size        IWM - IWB       small minus big
  Value       IWD - IWF       value minus growth
  Rates       IEF - SGOV      the level of rates: intermediate Treasuries over cash
  Curve       VGLT - IEF      the slope: long over intermediate — one rate factor cannot span a curve,
                              and with only VGLT-SGOV the bond-heavy books' return fell into the
                              residual (Certain -0.86 on a +0.14 total)
  Credit      LQD - IEF       investment grade over duration-matched govt
  Inflation   TIP - IEF       breakeven: linkers over nominals
  Commodity   DBC             broad commodity
  Gold        GLDM            gold, which is not a commodity trade in these books
  Dollar      UUP             the dollar

HONEST BOUNDS
 * Betas are estimated, not declared. They come from a long window and are reported with R-squared.
 * A factor set is a choice. These nine span what the five books actually take positions in; a book
   holding something outside them shows up in the residual, which is why the residual is published.
 * The live window is 2.4 months. The ATTRIBUTION is exact -- it reconciles to the NAV -- but the
   factor returns it attributes to are themselves two months long and prove nothing about the future.

Output: Research/Portfolio_Construction/validation/fund_nav/factor_attrib.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAVD = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_nav')
PX = os.path.join(NAVD, 'factor_prices.csv')

CASH = 'SGOV'   # the risk-free leg: every book earns it on 100% of its money, by construction

# factor -> (long leg, short leg). Everything is a SPREAD over cash or over its natural comparator,
# so a beta reads as a position rather than as an artefact of two correlated indices. The set is
# chosen to span what these five books actually hold — an empirical check, not taste: with the first
# nine, cash (R2 0.005), trend (0.21), property (0.65) and EM (0.73) were left unexplained and their
# return fell into the residual, which is not attribution, it is a shrug.
FACTORS = [
    ('Equity',    'ACWI', CASH),
    ('Size',      'IWM',  'IWB'),
    ('Value',     'IWD',  'IWF'),
    ('Emerging',  'VWO',  'ACWI'),
    ('Rates',     'IEF',  CASH),
    ('Curve',     'VGLT', 'IEF'),
    ('Credit',    'LQD',  'IEF'),
    ('Inflation', 'TIP',  'IEF'),
    ('RealAsset', ('VNQ', 'IGF'), 'ACWI'),
    ('Commodity', 'DBC',  CASH),
    ('Gold',      'GLDM', CASH),
    ('Trend',     'DBMF', CASH),
    ('Dollar',    'UUP',  CASH),
]
BLURB = {
    'Equity': 'global equity over cash', 'Size': 'small minus big',
    'Value': 'value minus growth', 'Emerging': 'emerging over global equity',
    'Rates': 'intermediate Treasuries over cash', 'Curve': 'long over intermediate Treasuries',
    'Credit': 'investment grade over govt',
    'Inflation': 'linkers over nominals', 'RealAsset': 'listed property and infrastructure over equity',
    'Commodity': 'broad commodity over cash', 'Gold': 'gold over cash',
    'Trend': 'managed futures over cash', 'Dollar': 'the US dollar',
}
LOOKBACK = '2018-01-01'   # long enough for a stable beta, short enough to be this vehicle's behaviour
MIN_OBS = 250             # a year of daily data before a beta is quoted


def prices(tickers):
    """Daily dividend-adjusted closes, cached — the betas do not change between runs."""
    want = sorted(set(tickers))
    if os.path.exists(PX):
        have = pd.read_csv(PX, index_col=0, parse_dates=True)
        if not set(want) - set(have.columns):
            return have[want]
    import yfinance as yf
    px = yf.download(want, start=LOOKBACK, auto_adjust=True, progress=False)['Close']
    px = px.dropna(how='all').ffill()
    missing = [t for t in want if t not in px.columns or px[t].notna().sum() < MIN_OBS]
    if missing:
        raise SystemExit('factor_attrib: no usable history for %s — a factor or vehicle with no '
                         'prices would be silently dropped from the attribution' % ', '.join(missing))
    px.to_csv(PX)
    return px[want]


def main():
    nav = json.load(open(os.path.join(NAVD, 'fund_nav.json')))
    funds = list(nav['daily_weights'])
    vehicles = sorted({v for f in funds for v in nav['daily_weights'][f]})
    legs = sorted({t for _, a, b in FACTORS
                   for leg in (a, b) if leg
                   for t in ((leg,) if isinstance(leg, str) else leg)} | {CASH})

    px = prices(vehicles + legs)
    ret = px.pct_change(fill_method=None).dropna(how='all').fillna(0.0)

    def leg(x):
        return ret[x] if isinstance(x, str) else ret[list(x)].mean(axis=1)

    F = pd.DataFrame({nm: leg(a) - (leg(b) if b else 0.0) for nm, a, b in FACTORS}).dropna()
    names = [nm for nm, _, _ in FACTORS]

    # ---- 1. vehicle betas, on the long window -------------------------------------------------
    betas, r2 = {}, {}
    X = np.column_stack([np.ones(len(F))] + [F[n].values for n in names])
    rf = ret[CASH].reindex(F.index).fillna(0.0)
    for v in vehicles:
        y = (ret[v].reindex(F.index).fillna(0.0) - rf).values   # excess of cash
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        fit = X @ coef
        ss = float(((y - y.mean()) ** 2).sum())
        betas[v] = {n: float(c) for n, c in zip(names, coef[1:])}
        r2[v] = float(1 - ((y - fit) ** 2).sum() / ss) if ss > 0 else 0.0

    # ---- 2 & 3. exposures through the live window, and what they paid -------------------------
    dates = pd.to_datetime(nav['dates'])
    Flive = F.reindex(dates).fillna(0.0)
    rflive = ret[CASH].reindex(dates).fillna(0.0)
    out = {}
    for f in funds:
        W = pd.DataFrame(nav['daily_weights'][f], index=dates)
        navser = pd.Series(nav['series'][f], index=dates)
        prev = navser.shift(1).fillna(nav['nav0'])

        expo = pd.DataFrame({n: sum(W[v] * betas[v][n] for v in W.columns) for n in names},
                            index=dates)
        # day 0 has no return to attribute; the exposure that earns day t is the one held on day t
        contrib = {n: float((prev * expo[n] * Flive[n]).iloc[1:].sum()) for n in names}

        # Every book holds 100% of its money, so it earns the cash rate on all of it whatever it is
        # invested in. Attributing that to a factor would be wrong; leaving it in the residual made
        # Certain's 26% T-bill position look like unexplained return.
        cash_c = float((prev * rflive).iloc[1:].sum())

        br = nav['bridge'][f]
        total = br['total']
        costs = br['dealing'] + br['fee']
        resid = total - sum(contrib.values()) - costs - cash_c
        wavg = {n: float((W.mul(pd.Series({v: betas[v][n] for v in W.columns}), axis=1)
                          .sum(axis=1)).mean()) for n in names}
        out[f] = dict(
            factors=[dict(name=n, blurb=BLURB[n], exposure=round(wavg[n], 3),
                          fret=float(Flive[n].iloc[1:].sum()), contrib=contrib[n]) for n in names],
            residual=resid, costs=costs, total=total, cash=cash_c,
            explained=float(sum(contrib.values())))

        chk = sum(contrib.values()) + costs + resid + cash_c
        if abs(chk - total) > 1e-8:
            raise SystemExit(f'{f}: factor attribution does not reconcile to the NAV')

    payload = dict(
        asof=nav['dates'][-1], inception=nav['inception'],
        window=dict(beta_start=LOOKBACK, beta_obs=int(len(F)), live_days=len(dates)),
        factor_defs=[dict(name=n, blurb=BLURB[n], long=a, short=b) for n, a, b in FACTORS],
        vehicle_r2={v: round(r2[v], 3) for v in vehicles},
        vehicle_betas={v: {n: round(b, 3) for n, b in betas[v].items()} for v in vehicles},
        funds=out)
    json.dump(payload, open(os.path.join(NAVD, 'factor_attrib.json'), 'w'), indent=1)
    print(f'  factor attribution · {len(names)} factors · betas on {len(F)} days from {LOOKBACK}')
    for f in funds:
        o = out[f]
        print(f'    {f:10s} total {o["total"]:+6.3f} = cash {o["cash"]:+6.3f} '
              f'+ factors {o["explained"]:+6.3f} + costs {o["costs"]:+6.3f} '
              f'+ residual {o["residual"]:+6.3f}')


if __name__ == '__main__':
    main()
