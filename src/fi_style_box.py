#!/usr/bin/env python3
"""
fi_style_box.py — the fixed-income 3x3 (interest-rate sensitivity x credit quality) per portfolio.

WHY THIS EXISTS
The equity style box (style_box.py) places each portfolio's US equity sleeve. For Certain, Endowment
and the SAA, bonds are 25-45% of the book, so a product page showing only the equity box describes
half of them. Morningstar shows both boxes for allocation funds. This builds the second one.

WHY IT WAS NOT BUILT BEFORE
vehicle_data.py deliberately collects no duration: nothing on the platform's data feed reports it, and
a duration invented from a maturity guess would be a number with no source. The inputs here are
transcribed from named issuer documents with their as-of dates (bond_vehicle_data.json), which meets
the platform's rule that a displayed figure traces to a source.

METHOD — Morningstar Fixed-Income Style Box methodology (effective 31 July 2019)
  Interest-rate sensitivity, from the asset-weighted effective duration of the bond holdings:
      Limited    below 75% of the reference duration
      Moderate   75% to 125%
      Extensive  125% and above
  Morningstar's reference is its Core Bond Index (MCBI), set monthly and not published openly; the
  Bloomberg US Aggregate (via AGG) stands in for it. See bond_vehicle_data.json 'reference_duration'.

  Credit quality, NOT a linear average of letter grades — Morningstar maps each grade to a relative
  default rate (Exhibit 1), averages the default rates by weight, and maps the average back to a grade
  (Exhibit 4). A 90% AAA / 10% CCC portfolio averages to BB this way, where a linear average says AA.
      High    average AA or better
      Medium  A or BBB
      Low     below BBB
  US Treasuries: Morningstar gives unrated US government bonds the rating of other US government debt
  from two of the three major agencies. S&P (2011) and Fitch (2023) rate the US AA+ and Moody's Aa1
  (2025), so Treasuries grade AA here — still High quality.

SCOPE — what is and is not in the box
  The bond sleeves only: intermediate and long Treasuries, TIPS, investment-grade credit. The T-bill
  position (SGOV) is the platform's Cash class and Morningstar treats instruments under 92 days as
  cash, so it is shown alongside the box, not averaged into it — otherwise Certain's 26% T-bills would
  drag its bond duration to near zero and describe cash, not bonds.

Refuses to run if a held bond vehicle has no sourced entry.
Output: Research/Portfolio_Construction/validation/fund_suite_v6/fi_style_box.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fund_registry as FR  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_suite_v6')
NAVD = os.path.join(ROOT, 'Research/Portfolio_Construction/validation/fund_nav')

BOND_SLEEVES = {'UST', 'USTL', 'TIPS', 'IG', 'HY', 'MBS'}
CASH_SLEEVES = {'Cash'}

# Exhibit 1, relative default rate (%) by Morningstar grade; GOVT is graded AA (see docstring).
REL_DEFAULT = {'AAA': 0.00, 'AA': 0.56, 'A': 2.22, 'BBB': 5.00, 'BB': 17.78, 'B': 49.44, 'BELOW_B': 100.0,
               'NR': 49.44}
GOVT_GRADE = 'AA'
# Exhibit 4, average relative default rate -> grade (upper bounds, exclusive).
GRADE_BANDS = [(0.13889, 'AAA'), (1.25, 'AA'), (3.47223, 'A'), (9.02778, 'BBB'),
               (31.25, 'BB'), (72.36112, 'B'), (float('inf'), 'Below B')]
QUALITY = {'AAA': 'High', 'AA': 'High', 'A': 'Medium', 'BBB': 'Medium',
           'BB': 'Low', 'B': 'Low', 'Below B': 'Low'}
MIN_BOND_WEIGHT = 5.0     # % of the book; below it the box is labelled not meaningful
SENS = ['Limited', 'Moderate', 'Extensive']
QUAL = ['High', 'Medium', 'Low']


def vehicle_default_rate(credit):
    tot = sum(credit.values())
    return sum(REL_DEFAULT[GOVT_GRADE if g == 'GOVT' else g] * w for g, w in credit.items()) / tot


def grade_of(rate):
    return next(g for ub, g in GRADE_BANDS if rate < ub)


def main():
    V = json.load(open(os.path.join(SUITE, 'bond_vehicle_data.json')))
    nav = json.load(open(os.path.join(NAVD, 'fund_nav.json')))
    ts = nav['ticker_sleeve']
    ref = V['reference_duration']['effective_duration']
    lo, hi = 0.75 * ref, 1.25 * ref

    out = {}
    for key in FR.ORDER:
        nm = FR.FUNDS[key]['name']
        hold = nav['holdings'][nm]
        bonds = {t: w for t, w in hold.items() if ts.get(t) in BOND_SLEEVES and w > 0}
        cash = {t: w for t, w in hold.items() if ts.get(t) in CASH_SLEEVES and w > 0}
        missing = [t for t in list(bonds) + list(cash) if t not in V['vehicles']]
        if missing:
            raise SystemExit(f'fi_style_box: no sourced duration/credit for {missing} held by {nm} — '
                             'add them to bond_vehicle_data.json from the issuer document first')
        if not bonds:
            out[key] = dict(name=nm, bond_weight=0.0, meaningful=False,
                            cash_weight=round(100 * sum(cash.values()), 2))
            continue
        tot = sum(bonds.values())
        dur = sum(V['vehicles'][t]['effective_duration'] * w for t, w in bonds.items()) / tot
        rate = sum(vehicle_default_rate(V['vehicles'][t]['credit']) * w for t, w in bonds.items()) / tot
        grade = grade_of(rate)
        sens = 'Limited' if dur < lo else ('Extensive' if dur >= hi else 'Moderate')
        qual = QUALITY[grade]
        out[key] = dict(
            name=nm, bond_weight=round(100 * tot, 2), cash_weight=round(100 * sum(cash.values()), 2),
            effective_duration=round(dur, 2), avg_default_rate=round(rate, 3), avg_grade=grade,
            sensitivity=sens, quality=qual, cell=[QUAL.index(qual), SENS.index(sens)],
            vehicles=[dict(ticker=t, weight_in_bonds=round(100 * w / tot, 1),
                           effective_duration=V['vehicles'][t]['effective_duration'],
                           grade=grade_of(vehicle_default_rate(V['vehicles'][t]['credit'])),
                           as_of=V['vehicles'][t]['as_of'], proxy=bool(V['vehicles'][t].get('proxy')))
                      for t, w in sorted(bonds.items(), key=lambda kv: -kv[1])])
        # A box built on a residual position describes the residual, not the portfolio: Alpha holds
        # 0.4% in long Treasuries. Below this share of the book the box is published as not meaningful.
        out[key]['meaningful'] = bool(100 * tot >= MIN_BOND_WEIGHT)
        o = out[key]
        print(f'  {nm:10s} bonds {o["bond_weight"]:5.1f}%  duration {dur:5.2f}y  avg {grade:3s}'
              f'  -> {qual}/{sens}')

    payload = dict(
        generated=V['collected'], sensitivities=SENS, qualities=QUAL,
        reference=dict(name=V['reference_duration']['index'], vehicle=V['reference_duration']['vehicle'],
                       effective_duration=ref, as_of=V['reference_duration']['as_of'],
                       limited_below=round(lo, 2), extensive_from=round(hi, 2)),
        method=('Morningstar Fixed-Income Style Box methodology (effective 2019-07-31): duration bands at '
                '75% and 125% of a core bond index duration; credit quality averaged on default rates, '
                'not letter grades. Bond sleeves only; T-bills are cash.'),
        limitation=('Morningstar\'s own reference (its Core Bond Index) is not published openly, so the '
                    'Bloomberg US Aggregate stands in for it: this is Morningstar\'s method applied to '
                    'issuer data, not Morningstar\'s rating of these portfolios. Vehicle figures are as of '
                    'each issuer\'s latest fact sheet.'),
        sources={t: dict(source=v['source'], url=v['url'], as_of=v['as_of'])
                 for t, v in V['vehicles'].items()},
        funds=out)
    f = os.path.join(SUITE, 'fi_style_box.json')
    json.dump(payload, open(f, 'w'), indent=1, allow_nan=False)
    print(f'wrote {f}')


if __name__ == '__main__':
    main()
