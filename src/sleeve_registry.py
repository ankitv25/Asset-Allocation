#!/usr/bin/env python3
"""
sleeve_registry.py — what each sleeve is FOR, and why each vehicle fills it.

WHY THIS EXISTS
The dashboard's sleeve cards and the construction drill-down have always carried three things per
sleeve: a thesis, a per-instrument role, and a per-instrument rationale. When the five funds were
built, all three were populated from `fund_suite_v6.impl` — which is an implementation string. The
page therefore rendered:

    US equity          thesis: "VOO / IVV"
      VOO   role: core   rationale: "VOO / IVV"

That is the sleeve's ticker printed three times, not its investment case. Everything the reader needed
in order to know why the sleeve exists had gone.

WHAT THIS IS, AND WHAT IT IS NOT
This is the house description of each sleeve and vehicle. Factual claims (index tracked, inception,
duration bucket, hedging, structure) are from DATA_UNIVERSE.md and fs6_core. The investment reasoning
restates the mandate each fund already declares in `fs6_core.FUNDS6[*].identity` — it does NOT set
policy, introduce a constraint, or state a target. Where a number matters it is computed and passed
in by the caller, not written here.

Anything this module cannot source is left empty rather than filled with something plausible.
"""

# ---------------------------------------------------------------------------
# Sleeve theses — why the sleeve exists and what job it does in a book
# ---------------------------------------------------------------------------
SLEEVE = {
    'US_EQ': dict(
        thesis='The compounding engine. US large-cap is the deepest, most liquid equity market and '
               'the longest clean return history the platform has, so it carries the growth weight '
               'rather than being spread thinly across regions for its own sake.',
        role='Growth — the primary source of long-run return',
        risk='The dominant risk contributor in every book that holds it: expect it to consume a '
             'larger share of risk than of capital.'),
    'DM_EQ': dict(
        thesis='Developed markets outside the US, held CURRENCY-HEDGED. Unhedged developed equity '
               'pays the investor to take a currency bet that carries no expected return; hedging '
               'keeps the equity exposure and removes the FX leg, so the sleeve does the job it was '
               'bought for.',
        role='Growth — diversification of the equity leg across economies, not currencies',
        risk='Equity-like, correlated to US equity in crises; the hedge removes the dollar factor '
             'rather than the drawdown.'),
    'EM_EQ': dict(
        thesis='Emerging-market equity for the growth that is not in developed indices — different '
               'demographics, different policy cycles, different index composition. Held smaller '
               'than market weight because the governance and concentration risks are real.',
        role='Growth — the highest-dispersion equity leg',
        risk='The widest tail of the equity sleeves; adds return dispersion more than it adds '
             'diversification during a global drawdown.'),
    'UST': dict(
        thesis='Intermediate Treasuries: the defensive core. Government credit with enough duration '
               'to rally when growth disappoints, but not so much that it becomes an interest-rate '
               'bet in its own right.',
        role='Defensive — the first line, and the liquidity the book rebalances from',
        risk='The reliable negative-correlation leg in a growth shock; it is NOT a hedge against '
             'inflation, which is what 2022 demonstrated.'),
    'USTL': dict(
        thesis='Long Treasuries, held deliberately as a separate sleeve rather than blended into the '
               'Treasury weight. Long duration is the sharpest available convexity against a '
               'deflationary growth shock — and the sleeve most exposed to an inflation shock. '
               'Separating it makes that trade explicit rather than hiding it in an average duration.',
        role='Defensive — convexity, sized as its own decision',
        risk='The most volatile defensive sleeve. It is the one that hurt in 2022 and the one that '
             'paid in 2008.'),
    'TIPS': dict(
        thesis='Inflation-linked Treasuries: the only holding in the range whose contractual payoff '
               'is a REAL return. Where nominal bonds promise a number of dollars, these promise '
               'purchasing power, which is why the preservation mandate is built around them.',
        role='Defensive — real, not nominal',
        risk='Carries duration like any Treasury, so it can fall in a rate shock even while doing '
             'its inflation job.'),
    'IG': dict(
        thesis='Investment-grade corporate credit: a spread over Treasuries for taking corporate '
               'balance-sheet risk. Held thin, and only where the mandate wants it, because in a '
               'genuine crisis it behaves like equity with a coupon.',
        role='Defensive — a yield pickup, honestly priced as partial equity risk',
        risk='Correlation to equity rises exactly when the defensive sleeve is needed.'),
    'HY': dict(
        thesis='High-yield credit. Equity risk in a bond wrapper, with the upside capped at par and '
               'the downside uncapped — held only where a mandate explicitly wants that trade.',
        role='Growth — credit beta',
        risk='Sells off with equity and loses liquidity when it matters most.'),
    'REIT': dict(
        thesis='Listed real estate: property cashflows, priced daily. Liquid access to an asset class '
               'that otherwise demands lock-ups, which is what makes an endowment model possible for '
               'a portfolio that must be priced every day.',
        role='Real assets — income-linked property exposure',
        risk='Trades as equity in the short run and as property over the long run; leverage in the '
             'underlying vehicles makes it rate-sensitive.'),
    'INFRA': dict(
        thesis='Listed global infrastructure: regulated and concession assets whose revenues are '
               'often contractually linked to inflation. The part of the real-asset sleeve with a '
               'cashflow rather than only a price.',
        role='Real assets — inflation-linked cashflow',
        risk='Equity-listed, so it carries equity beta in a drawdown; history begins 2007, which '
             'limits what can be claimed about it.'),
    'CMDTY': dict(
        thesis='Broad commodities: the asset class that rises when an inflation shock is a supply '
               'shock. It has no yield and no expected real return to speak of, and it is held for '
               'what it does to the SHAPE of the portfolio, not for its own return.',
        role='Real assets — the inflation-shock leg',
        risk='Long stretches of negative return between the episodes that justify it. Judged on '
             'behaviour in 2022 and 2008, not on standalone CAGR.'),
    'GOLD': dict(
        thesis='Gold: a monetary asset, not a commodity in how it behaves. It responds to real '
               'rates and to confidence in currency rather than to industrial demand, which makes it '
               'the store of value in a book that cannot hold illiquid alternatives.',
        role='Real assets — store of value',
        risk='No cashflow, so it cannot be valued on fundamentals; its diversification is real but '
             'episodic.'),
    'MF': dict(
        thesis='Managed futures, sized like a sleeve rather than like a hedge-fund allocation. Trend '
               'following is the one diversifier in the range with a documented record of paying in '
               'exactly the slow-moving drawdowns where everything else is falling together.',
        role='Diversifiers — the crisis-convexity leg',
        risk='Loses money in choppy, trendless markets, which is the premium paid for the convexity. '
             'Tracked against real funds only, never a synthetic index.'),
    'CHF': dict(
        thesis='The Swiss franc, held as a foreign-currency deposit. A second store of value '
               'denominated outside the dollar, for a mandate whose job is purchasing power rather '
               'than dollar accounting.',
        role='Real assets in the fund taxonomy, cash-like in the platform taxonomy — a store of '
             'value, not a diversifier strategy',
        risk='A currency has no expected real return; this is held for what it protects against, and '
             'it is the one position whose taxonomy mapping is an explicit judgement call.'),
    'Cash': dict(
        thesis='T-bills, held as a real position rather than as whatever is left over. When the '
               'short rate is positive, cash is a funded, liquid, zero-duration asset — and the only '
               'one that is certain to be worth its face value when the book wants to buy something.',
        role='Cash — optionality with a yield',
        risk='Loses purchasing power to inflation; that is the cost of the optionality.'),
}

# ---------------------------------------------------------------------------
# Instruments — the vehicle actually held, and why this one
# Facts (index, inception, structure) are from DATA_UNIVERSE.md.
# ---------------------------------------------------------------------------
INSTRUMENT = {
    'VOO': ('US large-cap core', 'Vanguard S&P 500. The core US equity holding: the deepest and '
            'cheapest access to the large-cap market, tracking an index with clean history back to 1993.'),
    'IVV': ('US large-cap core', 'iShares S&P 500 — the same index as VOO, held as the alternate '
            'vehicle so the sleeve is never dependent on a single issuer.'),
    'ITOT': ('US total market', 'iShares Core S&P Total US Stock Market. Extends the core beyond '
             'large-cap to the full listed market, adding mid- and small-cap breadth in one line.'),
    'SCHX': ('US large-cap core', 'Schwab US Large-Cap — a third issuer for the same exposure, used '
             'where a sleeve is large enough that concentration in one fund would itself be a risk.'),
    'DBEF': ('Developed ex-US, currency-hedged', 'Xtrackers MSCI EAFE Hedged Equity. The hedged '
             'vehicle is the point: it delivers developed ex-US equity without the dollar bet that '
             'an unhedged fund forces the holder to take alongside it.'),
    'VWO': ('Emerging markets, broad', 'Vanguard FTSE Emerging Markets. FTSE classifies Korea as '
            'developed, so VWO includes it while MSCI-based funds do not — a deliberate composition '
            'choice, documented rather than incidental.'),
    'VGIT': ('Intermediate Treasuries', 'Vanguard Intermediate-Term Treasury, tracking the 7–10 year '
             'part of the curve: enough duration to respond to a growth shock without becoming a '
             'long-rate position.'),
    'SCHR': ('Intermediate Treasuries', 'Schwab Intermediate-Term Treasury — the same duration bucket '
             'from a second issuer.'),
    'VGLT': ('Long Treasuries', 'Vanguard Long-Term Treasury, 20 years and out. Held where a mandate '
             'wants explicit convexity against a deflationary shock and accepts the inflation risk '
             'that comes with it.'),
    'SCHP': ('Broad TIPS', 'Schwab US TIPS, tracking the broad Bloomberg TIPS index. The real-return '
             'holding: principal is indexed to CPI, so the payoff is in purchasing power.'),
    'VCIT': ('Intermediate IG credit', 'Vanguard Intermediate-Term Corporate Bond. Investment-grade '
             'spread at a duration close to the Treasury sleeve, so the credit decision is not '
             'confounded with a duration decision.'),
    'VNQ': ('US listed real estate', 'Vanguard Real Estate, tracking the MSCI US REIT index — the '
            'deepest listed-property vehicle, with history from 2004.'),
    'GII': ('Global listed infrastructure', 'SPDR S&P Global Infrastructure. Utilities, transport and '
            'energy infrastructure worldwide; no history before 2007, which bounds what the backtest '
            'can say about this sleeve.'),
    'PDBC': ('Broad commodities, optimised roll', 'Invesco Optimum Yield Diversified Commodity. The '
             'optimised roll matters: a naive front-month commodity fund bleeds return to contango, '
             'and that cost is a large part of why commodity sleeves have historically disappointed.'),
    'GLDM': ('Gold bullion', 'SPDR Gold MiniShares — allocated physical gold at a lower expense '
             'ratio than the larger legacy vehicle, which matters for a position held for decades.'),
    'DBMF': ('Managed futures, CTA replication', 'iMGP DBi Managed Futures. Replicates the aggregate '
             'positioning of the CTA industry at a fraction of hedge-fund fees. Live from 2019, so '
             'the long-run sleeve history is built from real funds that existed at the time, never '
             'from a synthetic index.'),
    'FXF': ('Swiss franc deposit', 'Invesco CurrencyShares Swiss Franc — a franc deposit in listed '
            'form. This is how the store-of-value mandate is expressed outside the dollar.'),
    'SGOV': ('0–3 month T-bills', 'iShares 0–3 Month Treasury Bond. Effectively zero duration and '
             'zero credit risk: cash as a funded position that earns the short rate.'),
}


def sleeve_thesis(code):
    return SLEEVE.get(code, {}).get('thesis', '')


def sleeve_role(code):
    return SLEEVE.get(code, {}).get('role', '')


def sleeve_risk(code):
    return SLEEVE.get(code, {}).get('risk', '')


def instrument(ticker):
    """(role, rationale) for a held vehicle; empty strings when unknown, never a guess."""
    return INSTRUMENT.get(ticker, ('', ''))
