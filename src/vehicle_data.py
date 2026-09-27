#!/usr/bin/env python3
"""
vehicle_data.py — per-vehicle reference data for the five portfolios' look-through.

WHY THIS EXISTS
The five books are multi-asset: equity, two bond durations, real assets, trend, cash. What separates
them is not the sector split of one equity sleeve — it is how much income they throw off and how much
rate risk they carry. Neither was on the platform, because neither can be derived from prices.

WHAT IT COLLECTS, AND WHAT IT REFUSES TO
  yield     trailing 12-month distribution yield, per vehicle. Available for all vehicles held.
  category  the vehicle's own fund category, for the look-through table.

  DURATION IS NOT COLLECTED. The obvious field is empty for every one of the eighteen vehicles, and
  an effective duration invented from a maturity guess would be a number with no source on a page
  whose whole contract is that displayed figures trace to one. Rate sensitivity is reported instead
  from the factor model (Rates + Curve exposure in factor_attrib.py), which is measured.

Cached: the figures move slowly and the page should not depend on a live fetch to render.
Output: Research/Portfolio_Construction/validation/fund_nav/vehicle_data.json
"""
import json
import os
import sys
import warnings

warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAVD = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_nav')
OUT = os.path.join(NAVD, 'vehicle_data.json')


def main():
    nav = json.load(open(os.path.join(NAVD, 'fund_nav.json')))
    vehicles = sorted({v for f in nav['daily_weights'] for v in nav['daily_weights'][f]})

    import yfinance as yf
    data, missing = {}, []
    for t in vehicles:
        try:
            info = yf.Ticker(t).info or {}
        except Exception:
            info = {}
        y, cat = info.get('yield'), info.get('category')
        if y is None:
            missing.append(t)
            continue
        data[t] = dict(yield_=float(y), category=cat or '')

    # A portfolio yield computed over only the vehicles that reported would silently understate a
    # book holding one that did not. Better to fail than to publish a weighted average of a subset.
    if missing:
        raise SystemExit('vehicle_data: no yield for %s — a portfolio yield built on the rest would '
                         'understate every book holding them' % ', '.join(missing))

    json.dump(dict(vehicles=data, n=len(data)), open(OUT, 'w'), indent=1)
    print(f'  vehicle data · {len(data)} vehicles · yield and category')
    return 0


if __name__ == '__main__':
    sys.exit(main())
