#!/usr/bin/env python3
"""
fund_registry.py — the single source of truth for what the five funds ARE.

Everything downstream (dashboard payloads, NAV, launch book, docs) reads identity from here, so a
fund's name, role, benchmark or provenance is defined once. It holds no returns and no weights: those
come from the engines (`fs6_core` / `pc_fs6_build`) and the priced book (`fund_nav`). Importing this
module has no side effects.

TAXONOMY NOTE — two class systems coexist deliberately, and neither is being replaced:

  * The **fund methodology** classes (fs6_core.CLASSES6): Equity · Defensive · Real assets ·
    Diversifiers · Cash. These express the investment philosophy and drive the optimiser's bands.
  * The **platform** classes used by the existing dashboard (portfolios.js SLEEVES): Equities ·
    FixedIncome · Commodities · RealEstate · Cash · AltsInsurance. These predate the funds and are
    wired into existing components.

PLATFORM_CLASS below is the crosswalk from sleeve to platform class, so the funds can render through
existing components without either taxonomy being redefined. Two mappings are judgement calls and are
flagged for the owner rather than assumed silently:
  * GOLD -> Commodities. The platform has no precious-metals class; our methodology files gold under
    real assets. 'Commodities' is the nearest existing home. (Alternative: AltsInsurance, if gold is
    to read as insurance rather than a commodity.)
  * CHF -> Cash. The franc is held as a foreign-currency deposit (FXF), so it is cash-like, not an
    alternative strategy. (Alternative: AltsInsurance, if it should read as a diversifier.)
"""

# sleeve -> platform class (the existing dashboard taxonomy)
PLATFORM_CLASS = {
    'US_EQ': 'Equities', 'DM_EQ': 'Equities', 'EM_EQ': 'Equities',
    'UST': 'FixedIncome', 'USTL': 'FixedIncome', 'TIPS': 'FixedIncome',
    'IG': 'FixedIncome', 'HY': 'FixedIncome',
    'CMDTY': 'Commodities', 'GOLD': 'Commodities',
    'REIT': 'RealEstate', 'INFRA': 'RealEstate',
    'MF': 'AltsInsurance',
    'CHF': 'Cash', 'Cash': 'Cash',
}
PLATFORM_CLASSES = ['Equities', 'FixedIncome', 'Commodities', 'RealEstate', 'Cash', 'AltsInsurance']

# Display colours: the single source for every page. Chosen 2026-09-27 and validated as a set
# (dataviz validate_palette, ALL pairs, since the range chart draws all five together): colour-blind
# separation worst dE 12.6, normal-vision worst dE 19.2, every colour >= 3:1 on white. None is a
# gain green, a loss red or the interaction blue. Meaning where it helps: Certain cyan (cash-like),
# Endowment brown (real assets), SAA violet (the anchor), DAA plum (SAA's deeper sibling — the same
# book run actively), Alpha amber (the hot one). Benchmarks are slate greys: references, not products.
# The previous set failed the checks (SAA/Endowment dE 13.2; DAA was the page navy; Alpha the loss red).
FUNDS = {
    'certain': dict(
        key='certain', managed='static', name='Certain', engine_label='fs6 certain', order=1,
        color='#0891b2', horizon='3+ years',
        role='Capital preservation tier — purchasing power first',
        status='Live since 2026-07-15',
        reference='ACWI 40 / Agg 60',
        thesis='Short duration by design, with T-bills held as a real position rather than a residual. '
               'Gold and the Swiss franc carry the store-of-value job. No trend sleeve, no listed '
               'property, no long Treasuries.',
        dials={'loss limit': '−8%', 'volatility budget': '5%'}),
    'endowment': dict(
        key='endowment', managed='static', name='Endowment', engine_label='fs6 endowment', order=2,
        color='#92400e', horizon='10+ years',
        role='Long-horizon real-asset tier',
        status='Live since 2026-07-15',
        reference='ACWI 60 / Agg 40',
        thesis='The endowment model made liquid: property, infrastructure, commodities and gold at a '
               'quarter of the fund, thin nominal bonds, TIPS-led. No trend sleeve.',
        dials={'loss limit': '−20%', 'volatility budget': '9.5%'}),
    'saa': dict(
        key='saa', managed='static', name='SAA', engine_label='fs6 saa', order=3,
        color='#8b5cf6', horizon='20+ years',
        role='House policy portfolio — the strategic anchor',
        status='Live since 2026-07-15',
        reference='ACWI 80 / Agg 20',
        thesis='Nine holdings and deliberately lean: equity, two Treasury durations, gold, commodities '
               'and a trend sleeve sized like a sleeve rather than a hedge fund.',
        dials={'loss limit': '−22%', 'volatility budget': '12%'}),
    'daa': dict(
        key='daa', managed='active', name='DAA', engine_label='fs6 daa', order=4,
        color='#86198f', horizon='20+ years',
        role='The policy portfolio run actively',
        status='Live since 2026-07-15',
        reference='ACWI 80 / Agg 20',
        base='saa', base_series='SAA book, untilted',
        thesis='The SAA book expressed through five engines — valuation from a live CMA, trend, '
               'relative strength, regime, and the size of the diversifier sleeve, which is a macro '
               'decision rather than a policy weight.',
        dials={'tilt budget': '12pp one-sided', 'rebalance band': '0.6pp'}),
    'alpha': dict(
        key='alpha', managed='active', base_series='Alpha book, untilted', name='Alpha', engine_label='fs6 alpha', order=5,
        color='#d97706', horizon='10+ years',
        role='Equity-level risk, run actively',
        status='Live since 2026-07-15',
        reference='S&P 500',
        thesis='Carries its own ~14% volatility budget rather than the policy portfolio\'s — the '
               'index\'s risk, spent better. Equity-led, with gold, long Treasuries and a macro-sized '
               'trend sleeve doing the defending.',
        dials={'volatility budget': '14%', 'tilt budget': '20pp one-sided'}),
}
ORDER = [k for k, _ in sorted(FUNDS.items(), key=lambda kv: kv[1]['order'])]
NAME_TO_KEY = {v['name']: k for k, v in FUNDS.items()}

# Benchmarks the funds are measured against. Built from real indices (see pc_fs6_build).
BENCHMARKS = {
    'spy': dict(key='spy', name='S&P 500', color='#334155'),
    'acwi': dict(key='acwi', name='MSCI ACWI', color='#64748b'),
    'agg': dict(key='agg', name='Bloomberg US Aggregate', color='#94a3b8'),
    'acwi8020': dict(key='acwi8020', name='ACWI 80 / Agg 20', color='#475569'),
    'acwi6040': dict(key='acwi6040', name='ACWI 60 / Agg 40', color='#7c8aa0'),
    'acwi4060': dict(key='acwi4060', name='ACWI 40 / Agg 60', color='#a3adbb'),
}


def platform_weights(sleeve_weights):
    """Roll a fund's sleeve weights up into the platform's six classes."""
    out = {c: 0.0 for c in PLATFORM_CLASSES}
    for s, w in sleeve_weights.items():
        c = PLATFORM_CLASS.get(s)
        if c is None:
            raise KeyError(f'sleeve {s!r} has no platform class mapping — add it to PLATFORM_CLASS')
        out[c] += float(w)
    return out
