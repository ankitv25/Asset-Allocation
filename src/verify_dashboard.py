#!/usr/bin/env python3
"""
verify_dashboard.py — the check that can actually see the platform getting smaller.

The previous standard (no "Uncaught" in console, SVG count > 0) reported 40/40 clean on pages with
nine blank tiles. It could not see them because app.js guards optional modules with `if (d.matrix)`,
`if (d.risk_detail)`, `if (d.stress_forward)` — a missing payload key renders nothing and raises
nothing, and other tiles on the same page still draw an SVG.

This enforces three contracts instead:
  C1  MODULE PRESENCE — if a page carries an element id, every portfolio payload carries the path
      that fills it. This is the check that catches silent module loss.
  C2  STALE VOCABULARY — no page the selector drives may carry copy describing a different product
      or a superseded book.
  C3  PARAMETER PROVENANCE — no risk limit renders unless it is declared approved, with a source.
  C4  SERIES PROVENANCE — every performance series declares what it is (live / backtest /
      walk-forward), over what window, on what weights, with what costs. Two pages say
      "performance" and mean different things; an unlabelled series is how that gets blurred.
  C5  SLEEVE NARRATIVE — no sleeve renders as a bare label. Every held sleeve carries a thesis, a
      role, and a per-instrument rationale that is not just its own ticker string.

Exit 0 = clean. Exit 1 = at least one contract broken; every breach is listed with its page,
portfolio and path.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The dashboard tree defaults to its location in this repo. `--dash <dir>` (or DASH_DIR) aims the
# same five contracts at another copy of it: the public mirror ships this file and runs it with
# `--dash .`, where the pages sit at the repo root rather than under Research/. Passing neither
# leaves the private-repo behaviour exactly as it was.
DASH = os.environ.get('DASH_DIR') or os.path.join(ROOT, 'Research/Portfolio_Construction/dashboard')
if '--dash' in sys.argv:
    DASH = sys.argv[sys.argv.index('--dash') + 1]
DASH = os.path.abspath(DASH)
CONTRACT = os.path.join(DASH, 'module_contract.json')
BOOKS = os.path.join(DASH, 'data/portfolio_books.json')

# Pages the portfolio selector drives (they load portfolio-select.js + app.js).
SELECTOR_PAGES = ['index.html', 'construction.html', 'holdings.html', 'performance.html',
                  'attribution.html', 'risk.html', 'stress.html', 'montecarlo.html']


def dig(obj, path):
    """Walk a dotted path; return (found, value)."""
    cur = obj
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def empty(v):
    return v is None or (isinstance(v, (list, dict, str)) and len(v) == 0)


def ids_in(html):
    return set(re.findall(r'id="([A-Za-z0-9_-]+)"', html))


def main():
    contract = json.load(open(CONTRACT))
    books = json.load(open(BOOKS))
    order, B = books['order'], books['books']
    fails, warns = [], []

    # ---------- C1: module presence ----------
    for page in SELECTOR_PAGES:
        p = os.path.join(DASH, page)
        if not os.path.exists(p):
            fails.append(f'C1 {page}: page missing')
            continue
        present = ids_in(open(p).read())
        for eid, paths in contract['elements'].items():
            if eid not in present:
                continue
            for path in paths:
                for k in order:
                    ok, val = dig(B[k], path)
                    if not ok:
                        fails.append(f'C1 {page} [{k}] #{eid} -> payload path "{path}" MISSING '
                                     f'(tile renders blank, no error)')
                    elif empty(val):
                        fails.append(f'C1 {page} [{k}] #{eid} -> payload path "{path}" EMPTY')

    # ---------- C2: stale vocabulary ----------
    pats = [(s, re.compile(s, re.I)) for s in contract['stale_vocabulary']['patterns']]
    for page in SELECTOR_PAGES + ['portfolios.html', 'live.html']:
        p = os.path.join(DASH, page)
        if not os.path.exists(p):
            continue
        raw = open(p).read()
        raw = re.sub(r'<!--.*?-->', '', raw, flags=re.S)      # comments are not page copy
        for ln, line in enumerate(raw.split('\n'), 1):
            for src, rx in pats:
                if rx.search(line):
                    fails.append(f'C2 {page}:{ln} stale copy /{src}/ -> {line.strip()[:96]}')

    # ---------- C3: parameter provenance ----------
    for k in order:
        rk = B[k].get('risk', {})
        for field in ('vol_budget', 'dd_budget', 'vol_util'):
            if field in rk and rk[field] is not None:
                prov = (B[k].get('provenance', {}) or {}).get('risk_limits')
                if not prov or not prov.get('approved'):
                    fails.append(f'C3 [{k}] risk.{field} = {rk[field]} renders with no approved '
                                 f'source (provenance.risk_limits.approved missing)')
        for kp in B[k].get('kpis', []):
            if 'budget' in str(kp.get('sub', '')).lower():
                prov = (B[k].get('provenance', {}) or {}).get('risk_limits')
                if not prov or not prov.get('approved'):
                    fails.append(f'C3 [{k}] KPI "{kp["label"]}" sub "{kp["sub"]}" states a budget '
                                 f'with no approved source')

    # ---------- C4: series provenance ----------
    REQUIRED = ('basis', 'window', 'weights', 'rebalance', 'costs')
    for k in order:
        prov = (B[k].get('provenance') or {}).get('series')
        if not prov:
            fails.append(f'C4 [{k}] no provenance.series — performance charts would render unlabelled')
            continue
        named = {m['name'] for m in (B[k].get('comparison', {}).get('metrics') or [])}
        for nm2 in sorted(named):
            if nm2.endswith('— untilted'):
                continue                      # the base book is documented by its parent series
            if nm2 in ('60/40', 'All-Equity', 'S&P 500'):
                continue                      # index benchmarks, not constructed series
            if nm2 not in prov:
                fails.append(f'C4 [{k}] series "{nm2}" is plotted but has no provenance entry')
        for nm2, v in prov.items():
            miss = [f for f in REQUIRED if not v.get(f)]
            if miss:
                fails.append(f'C4 [{k}] provenance "{nm2}" missing {", ".join(miss)}')
            if v.get('basis') not in ('live', 'backtest', 'walk-forward backtest', 'simulated'):
                fails.append(f'C4 [{k}] provenance "{nm2}" basis {v.get("basis")!r} is not one of '
                             f'live / backtest / walk-forward backtest / simulated')

    # ---------- C5: sleeve narrative ----------
    for k in order:
        for sl in (B[k].get('construction', {}).get('sleeves') or []):
            if sl.get('weight', 0) < 0.05:
                continue
            nm2, th = sl.get('label', sl.get('sleeve')), (sl.get('thesis') or '').strip()
            impl = (sl.get('implementation') or '').strip()
            if len(th) < 40:
                fails.append(f'C5 [{k}] sleeve "{nm2}" thesis is {len(th)} chars — renders as a label')
            elif impl and th == impl:
                fails.append(f'C5 [{k}] sleeve "{nm2}" thesis IS its implementation string {impl!r}')
            if not (sl.get('role') or '').strip():
                fails.append(f'C5 [{k}] sleeve "{nm2}" has no role')
            for ins in (sl.get('instruments') or []):
                rat = (ins.get('rationale') or '').strip()
                if len(rat) < 30 or (impl and rat == impl):
                    fails.append(f'C5 [{k}] {nm2}/{ins.get("ticker")} rationale is the implementation '
                                 f'string or too short to be a rationale')
                if (ins.get('role') or '') == 'core' and len(sl.get('instruments') or []) > 0:
                    fails.append(f'C5 [{k}] {nm2}/{ins.get("ticker")} role is the placeholder "core"')

    # ---------- report ----------
    n_checks = sum(1 for p in SELECTOR_PAGES for e in contract['elements']) * len(order)
    print(f'verify_dashboard — {len(order)} portfolios x {len(SELECTOR_PAGES)} selector pages')
    print(f'  C1 module presence · C2 stale vocabulary · C3 parameter provenance · C4 series provenance')
    print('  C5 sleeve narrative')
    print()
    if not fails:
        print(f'PASS — no contract breaches.')
        for w in warns:
            print('  warn:', w)
        return 0
    # group for readability
    for c in ('C1', 'C2', 'C3', 'C4', 'C5'):
        grp = [f for f in fails if f.startswith(c)]
        if not grp:
            continue
        print(f'{c} — {len(grp)} breach(es)')
        seen = set()
        for f in grp:
            # collapse the five-portfolio repetition into one line per page/element/path
            key = re.sub(r'\[[a-z]+\]', '[*]', f)
            if key in seen:
                continue
            seen.add(key)
            n = sum(1 for x in grp if re.sub(r'\[[a-z]+\]', '[*]', x) == key)
            print(f'   {f}' + (f'   (x{n} portfolios)' if n > 1 else ''))
        print()
    print(f'FAIL — {len(fails)} breach(es)')
    return 1


if __name__ == '__main__':
    sys.exit(main())
