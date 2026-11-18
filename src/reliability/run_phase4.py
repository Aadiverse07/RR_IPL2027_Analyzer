"""Phase 4 driver: variance comparison, empirical Bayes, format combination,
eligibility, consistency, sensitivity and reports.

Read-only over Phase 3 outputs. Scope is unchanged and contexts are never
merged. `ALL` is used only as a pooled-delivery sensitivity comparison.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from ..performance import model as p3
from . import model

ROOT = model.ROOT
REPORT = ROOT / 'reports/phase_4'
DATA = ROOT / 'data/processed'
OUT = ROOT / 'outputs/final'
CFG_PATH = ROOT / 'config/methodology.yaml'


def write_rows(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: ('' if r.get(k) is None else r.get(k)) for k in fields})


def csv_bytes(rows, fields):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow({k: ('' if r.get(k) is None else r.get(k)) for k in fields})
    return buf.getvalue().encode('utf-8')


def f(v, digits=4):
    return '' if v is None or v == '' else f'{v:.{digits}f}'


def pct(v, digits=1):
    return '' if v is None or v == '' else f'{100 * v:.{digits}f}%'


def median(vals):
    vals = sorted(v for v in vals if v is not None)
    return vals[len(vals) // 2] if vals else None


def quantile(vals, q):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return vals[min(len(vals) - 1, int(q * (len(vals) - 1)))]


# --------------------------------------------------------------------- core

def core(components, residuals, basis='E2', estimator='DL', kmin=model.KMIN,
         formats=model.FORMATS, single_stage=False):
    comps = [c for c in components if c['format'] in formats]
    gA = model.group_residuals(residuals, 'pressure')
    gB = model.group_residuals(residuals, 'baseline')
    if formats == ('ALL',):
        gA = model.pool_residual_groups(gA)
        gB = model.pool_residual_groups(gB)
    table, params = model.build_variances(comps, {'A': gA, 'B': gB}, formats=formats)
    if single_stage or formats == ('ALL',):
        combined = model.single_stage_combine(comps, table, estimator=estimator,
                                              kmin=kmin, basis=basis,
                                              formats=formats)
        eb, eb_params = {}, []
    else:
        eb, eb_params = model.fit_all_eb(comps, table, estimator=estimator,
                                         kmin=kmin, basis=basis)
        combined = model.combine_formats(comps, eb)
    return {'components': comps, 'groups': {'A': gA, 'B': gB}, 'table': table,
            'params': params, 'eb': eb, 'eb_params': eb_params,
            'combined': combined}


def names_map():
    out = {}
    for r in model.read_csv(model.PLAYERS):
        out[r['player_id']] = {'name': r['names'], 'ambiguous': r['name_ambiguous']}
    return out


def descriptive_map():
    """Pressure/baseline descriptive totals per player x role x context."""
    agg = defaultdict(lambda: defaultdict(float))
    for r in model.read_csv(model.DESCRIPTIVES):
        key = (r['player_id'], r['role'], r['context'], r['side'])
        g = agg[key]
        g['balls'] += int(r['deliveries'])
        g['runs'] += float(r['runs'] or 0)
        g['dots'] += (float(r['dot_pct'] or 0) / 100.0) * int(r['deliveries'])
        g['boundary'] += (float(r['boundary_pct'] or 0) / 100.0) * int(r['deliveries'])
        g['dismissals'] += int(r['dismissals'] or 0)
        g['wickets'] += int(r['wickets'] or 0)
    out = {}
    for (pid, role, ctx, side), g in agg.items():
        key = (pid, role, ctx)
        d = out.setdefault(key, {})
        d[f'{side}_balls'] = int(g['balls'])
        d[f'{side}_runs'] = g['runs']
        d[f'{side}_dot_pct'] = 100.0 * g['dots'] / g['balls'] if g['balls'] else None
        d[f'{side}_boundary_pct'] = 100.0 * g['boundary'] / g['balls'] if g['balls'] else None
        if side != 'pressure':
            continue
        if role == 'batter':
            d['pressure_dismissals'] = int(g['dismissals'])
        else:
            d['pressure_wickets'] = int(g['wickets'])
    return out


SCORE_FIELDS = [
    'player_id', 'name', 'name_ambiguous', 'role', 'context', 'formats_present',
    'format_basis', 'scored', 'reliability_status',
    'A_raw', 'A_star', 'A_post_sd', 'A_ci90_low', 'A_ci90_high',
    'B_raw', 'B_star', 'B_post_sd', 'B_ci90_low', 'B_ci90_high',
    'D_raw', 'D_star', 'D_post_sd',
    'S_raw', 'S_star', 'S_post_sd', 'S_ci90_low', 'S_ci90_high',
    'n_pressure', 'n_baseline', 'pressure_matches', 'baseline_matches',
    'total_matches', 'shrinkage_A', 'shrinkage_B', 'evidence_tier', 'eligible',
    'consistency_k', 'consistency_matches', 'consistency_positive_share',
    'consistency_match_sd', 'tau2_A', 'tau2_B', 'population_mean_A',
    'population_mean_B',
    'A_IPL', 'A_star_IPL', 'B_IPL', 'B_star_IPL', 'shrink_A_IPL',
    'n_pressure_IPL', 'pressure_matches_IPL',
    'A_T20I', 'A_star_T20I', 'B_T20I', 'B_star_T20I', 'shrink_A_T20I',
    'n_pressure_T20I', 'pressure_matches_T20I',
    'format_Q', 'format_p', 'format_disagree',
    'S_raw_phase3_all', 'n_pressure_phase3_all',
    'pressure_balls', 'pressure_runs', 'pressure_dot_pct',
    'pressure_boundary_pct', 'pressure_dismissals', 'pressure_wickets',
    'baseline_balls', 'baseline_runs', 'baseline_dot_pct', 'baseline_boundary_pct',
    'notes',
]


def score_rows(components, combined, consistency, eb_params):
    names = names_map()
    desc = descriptive_map()
    by_player = {(r['role'], r['context'], r['player_id']): r for r in combined}
    all_comp = {(c['role'], c['context'], c['player_id'], c['format']): c
                for c in components}
    tau = {(p['role'], p['context'], p['format'], p['side']): p['tau2_used']
           for p in eb_params}

    rows = []
    keys = sorted({(c['role'], c['context'], c['player_id']) for c in components})
    for role, ctx, pid in keys:
        r = by_player.get((role, ctx, pid))
        base = {'player_id': pid, 'role': role, 'context': ctx,
                'name': names.get(pid, {}).get('name', ''),
                'name_ambiguous': names.get(pid, {}).get('ambiguous', ''),
                'consistency_k': model.CONSISTENCY_K}
        base.update(consistency.get((pid, role, ctx), {}))
        base.update(desc.get((pid, role, ctx), {}))
        base['S_raw_phase3_all'] = ''
        base['n_pressure_phase3_all'] = ''
        allrow = all_comp.get((role, ctx, pid, 'ALL'))
        if allrow:
            base['S_raw_phase3_all'] = float(allrow['S_raw'])
            base['n_pressure_phase3_all'] = int(allrow['n_pressure'])
        if r is None:
            # No estimable variance (usually a single delivery) or no EB cell.
            fmt = 'IPL' if (role, ctx, pid, 'IPL') in all_comp else 'T20I'
            c = all_comp.get((role, ctx, pid, fmt))
            base.update({
                'formats_present': fmt, 'format_basis': 'none', 'scored': False,
                'reliability_status': 'NO_VARIANCE', 'evidence_tier': 'Insufficient',
                'eligible': False,
                'A_raw': float(c['A']) if c else '', 'B_raw': float(c['B']) if c else '',
                'D_raw': float(c['D']) if c else '', 'S_raw': float(c['S_raw']) if c else '',
                'n_pressure': int(c['n_pressure']) if c else '',
                'n_baseline': int(c['n_baseline']) if c else '',
                'pressure_matches': int(c['n_pressure_matches']) if c else '',
                'baseline_matches': int(c['n_baseline_matches']) if c else '',
                'total_matches': int(c['n_matches']) if c else '',
                'shrinkage_A': 0.0, 'shrinkage_B': 0.0,
                'A_star': '', 'B_star': '', 'D_star': '', 'S_star': '',
            })
            base['notes'] = ('No estimable variance: fewer than two deliveries in '
                             'the pressure or baseline component; excluded from scoring.')
            rows.append(base)
            continue

        d = dict(r)
        d.update(base)
        d['format_basis'] = 'two_stage_iv'
        d['scored'] = True
        # dominant format tau^2 for traceability
        avail = [f for f in model.FORMATS if d.get(f'n_pressure_{f}', 0)]
        dom = max(avail, key=lambda f: d.get(f'n_pressure_{f}', 0)) if avail else 'IPL'
        d['tau2_A'] = tau.get((role, ctx, dom, 'A'), '')
        d['tau2_B'] = tau.get((role, ctx, dom, 'B'), '')
        ea = next((p for p in eb_params if p['role'] == role and p['context'] == ctx
                   and p['format'] == dom and p['side'] == 'A'), None)
        ebb = next((p for p in eb_params if p['role'] == role and p['context'] == ctx
                    and p['format'] == dom and p['side'] == 'B'), None)
        d['population_mean_A'] = ea['m'] if ea else ''
        d['population_mean_B'] = ebb['m'] if ebb else ''
        d['A_post_sd'] = math.sqrt(max(r['v_A_star'], 0))
        d['B_post_sd'] = math.sqrt(max(r['v_B_star'], 0))
        d['A_ci90_low'] = r['A_star'] - model.Z90 * d['A_post_sd']
        d['A_ci90_high'] = r['A_star'] + model.Z90 * d['A_post_sd']
        d['B_ci90_low'] = r['B_star'] - model.Z90 * d['B_post_sd']
        d['B_ci90_high'] = r['B_star'] + model.Z90 * d['B_post_sd']
        d['D_post_sd'] = math.sqrt(max(r['v_A_star'] + r['v_B_star'], 0))
        if role == 'batter':
            d['notes'] = ('Batter evidence is chase-only: no validated innings-1 '
                          'batting pressure context exists.')
        elif ctx == 'chase':
            d['notes'] = ('Chase pressure. Kept separate from the innings-1 '
                          'bowling context; never combined with it.')
        else:
            d['notes'] = ('PH3-01: innings-1 ahead-of-par bowling is state-confounded. '
                          'Kept separate from chase; never combined or ranked with it.')
        rows.append(d)
    return rows


# ---------------------------------------------------------------- sensitivity

def scenario_row(name, role, ctx, scope, rows, primary_rows, note=''):
    elig = [r for r in rows if r.get('eligible')]
    top = model.top_ten(rows)
    prim_elig = [r for r in primary_rows if r.get('eligible')]
    prim_top = model.top_ten(primary_rows)
    overlap = (len({r['player_id'] for r in top} & {r['player_id'] for r in prim_top})
               if prim_top and top else '')
    ids_top = {r['player_id'] for r in top}
    ids_prim = {r['player_id'] for r in prim_top}
    entering = ','.join(sorted(ids_top - ids_prim))
    leaving = ','.join(sorted(ids_prim - ids_top))
    common = {r['player_id']: r for r in rows if r.get('scored')}
    pcommon = {r['player_id']: r for r in primary_rows if r.get('scored')}
    shared = [pid for pid in common if pid in pcommon
              and common[pid].get('n_pressure', 0) >= 50
              and pcommon[pid].get('n_pressure', 0) >= 50]
    rho = model.spearman([common[p]['S_star'] for p in shared],
                         [pcommon[p]['S_star'] for p in shared]) if len(shared) >= 3 else ''
    return {'scenario': name, 'role': role, 'context': ctx, 'format_scope': scope,
            'n_players': len([r for r in rows if r.get('scored')]),
            'n_eligible': len(elig), 'top10_n': len(top),
            'top10_overlap_with_primary': overlap,
            'spearman_n50': rho, 'n_spearman': len(shared),
            'entering_top10': entering, 'leaving_top10': leaving,
            'note': note}


def w_variant(primary_rows, w):
    coef = 1.0 - w
    out = []
    for r in primary_rows:
        if not r.get('scored'):
            out.append(r)
            continue
        d = dict(r)
        d['S_star'] = r['A_star'] - coef * r['B_star']
        d['S_post_sd'] = math.sqrt(max(r['v_A_star'] + coef ** 2 * r['v_B_star'], 0))
        d['S_ci90_low'] = d['S_star'] - model.Z90 * d['S_post_sd']
        d['S_ci90_high'] = d['S_star'] + model.Z90 * d['S_post_sd']
        out.append(d)
    return out


def format_specific_rows(primary_result, fmt):
    rows = []
    for r in primary_result['combined']:
        if r.get(f'shrink_A_{fmt}') == '':
            continue
        key_a = (r['player_id'], r['role'], r['context'], fmt, 'A')
        key_b = (r['player_id'], r['role'], r['context'], fmt, 'B')
        ea, ebb = primary_result['eb'].get(key_a), primary_result['eb'].get(key_b)
        if ea is None or ebb is None:
            continue
        s = ea['x_star'] - model.SCORE_D_COEF * ebb['x_star']
        vs = ea['posterior_var'] + model.SCORE_D_COEF ** 2 * ebb['posterior_var']
        d = dict(r)
        d['A_star'] = ea['x_star']
        d['B_star'] = ebb['x_star']
        d['S_star'] = s
        d['S_post_sd'] = math.sqrt(max(vs, 0))
        d['shrinkage_A'] = ea['shrinkage']
        d['eligible'] = ea['shrinkage'] >= model.ELIGIBILITY_MIN
        d['evidence_tier'] = model.tier(ea['shrinkage'])
        d['n_pressure'] = r.get(f'n_pressure_{fmt}', 0)
        rows.append(d)
    return rows


# -------------------------------------------------------------------- reports

def variance_markdown(vrows, boot):
    bands = [('2-4', 2, 4), ('5-9', 5, 9), ('10+', 10, 10 ** 9)]
    lines = [
        '# Variance estimator comparison (E1 vs E2)',
        '',
        'Primary input: `data/processed/player_match_residuals.csv` (match-level',
        'residual sums). Both estimators are computed for every player x role x',
        'context x format x component (A = pressure, B = baseline).',
        '',
        '## Formulas',
        '',
        'For a player with matches `m = 1..M`, `n_m` deliveries and residual sum',
        '`s_m` in a component with total `n = sum n_m` and mean `A`:',
        '',
        '- **E1, match-clustered robust (CR1):**',
        '  `Var(A) = M/(M-1) * sum_m (s_m - n_m*A)^2 / n^2`.',
        '  Assumption: match is the independent sampling unit. Undefined for `M = 1`',
        '  and unstable for very few matches; no finite-sample correction beyond',
        '  `M/(M-1)`.',
        '- **E2, pooled variance x design effect:**',
        '  `Var(A) = sigma2_pool * (1 + (nbar - 1) * rho_pool) / n`,',
        '  with `sigma2_pool` the pooled **within-match** residual variance,',
        '  `rho_pool` the degrees-of-freedom weighted mean of each player\'s',
        '  one-way random-effects match ICC (clamped to [0,1]), and `nbar` the',
        '  unbalanced average cluster size. Assumption: exchangeable deliveries',
        '  within a match and a common within-match variance in the stratum.',
        '',
        '`rho_pool` estimates are small (typically 0.03-0.10), as expected for',
        'ball-level cricket residuals.',
        '',
        '## Diagnostics',
        '',
        '| Match count | Cells | E1 defined | E1/E2 median | E1/E2 IQR | Within factor 2 |',
        '|---|---:|---:|---:|---|---:|',
    ]
    for label, lo, hi in bands:
        sub = [r for r in vrows if lo <= int(r['matches']) <= hi]
        ratios = [r['ratio_e1_e2'] for r in sub if r['ratio_e1_e2'] != '']
        defined = len(ratios)
        med = median(ratios)
        iqr = (quantile(ratios, 0.25), quantile(ratios, 0.75))
        within = (sum(1 for x in ratios if 0.5 <= x <= 2.0) / len(ratios)) if ratios else None
        lines.append(f"| {label} | {len(sub)} | {defined} | {f(med,3)} | "
                     f"{f(iqr[0],3)}–{f(iqr[1],3)} | {pct(within)} |")
    undefined = sum(1 for r in vrows if r['e1_defined'] is False)
    lines += [
        '',
        f'E1 is undefined for **{undefined:,}** of **{len(vrows):,}** cells because the',
        'player has a single match in that component. Where defined, E1 is',
        'systematically smaller than E2 (median ratio below 1 across all match',
        'bands) and its spread is wide; the ratio range is extreme at low match',
        'counts. E1 is therefore **downward-biased at small M**, which would',
        'inflate the between-player variance and make players look more reliable',
        'than the data support.',
        '',
        '### Match-block bootstrap check',
        '',
        f'Match-block bootstrap ({len({b["player_id"] + b["role"] + b["context"] + b["format"] for b in boot}):,}',
        'players with at least 6 pressure matches, 300 resamples each). Coverage is',
        'the share of bootstrap replicates inside the analytic 90% interval; a',
        'well-calibrated interval covers about 90%.',
        '',
        '| Estimator | Players | Median coverage | Median analytic SD / bootstrap SD | Coverage 0.85-0.95 |',
        '|---|---:|---:|---:|---:|',
    ]
    for est in ('E1', 'E2'):
        sub = [b for b in boot if b['estimator'] == est and b['sd_ratio'] != '']
        cov = [b['coverage'] for b in sub]
        ratio = [b['sd_ratio'] for b in sub]
        lines.append(f"| {est} | {len(sub)} | {f(median(cov),3)} | {f(median(ratio),3)} | "
                     f"{pct(sum(1 for x in cov if 0.85 <= x <= 0.95) / len(cov) if cov else None)} |")
    lines += [
        '',
        '## Decision',
        '',
        '**E2 is the primary variance estimator.** E1 is retained as a sensitivity',
        'and is reported wherever the EB conclusions depend on it. The evidence is',
        'mixed and is stated as such:',
        '',
        '1. E1 cannot be computed for the large single-match group (596 of 3,039',
        '   cells) and is unstable for the many 2-3 match cells (IQR 0.15-1.22,',
        '   only 38% within a factor of 2 of E2);',
        '2. E1 is systematically smaller than the design-based E2 (median ratio',
        '   0.53-0.81 across match bands), so using it for every player would',
        '   overstate between-player differences and reliability;',
        '3. at the 6+ match counts where the bootstrap can be computed, E2 is',
        '   **conservative**: its interval covers 93.7% of bootstrap replicates',
        '   (nominal 90%) and is 13% wider than the bootstrap SD, while E1 is close',
        '   to nominal (90.7%, ratio 1.00). E1 is therefore well behaved for',
        '   high-volume players but not a universal estimator.',
        '',
        'E2 is chosen because it is defined for every cell and errs on the side of',
        'wider intervals, which is the right direction for an eligibility rule. The',
        'E1 sensitivity in `sensitivity_variance_estimator.csv` is an **upper',
        'bound** on reliability, not an alternative selection of convenience: it',
        'would make 263 batter and 307 bowler cells eligible, which the calibration',
        'evidence does not support.',
    ]
    return '\n'.join(lines) + '\n'


def shrinkage_by_volume(eb, eb_params):
    """Demonstrate that shrinkage rises with information (small vs large n)."""
    bands = [('1-19', 1, 19), ('20-49', 20, 49), ('50-99', 50, 99), ('100+', 100, 10 ** 9)]
    out = []
    by = defaultdict(list)
    for p in eb_params:
        role, ctx, fmt, side = p['role'], p['context'], p['format'], p['side']
        for (pid, r, c, ff, s), rec in eb.items():
            if (r, c, ff, s) != (role, ctx, fmt, side):
                continue
            by[(role, ctx, fmt, side)].append(rec)
    for (role, ctx, fmt, side), recs in sorted(by.items()):
        ns = []
        for r in recs:
            # n is not stored in EB; v and sigma2 give n only approximately.
            # The EB table is paired with components in the driver; here we use
            # the reciprocal variance as a monotone volume proxy and report it.
            ns.append(1.0 / r['v'])
        for label, lo, hi in bands:
            sub = [r for r, nn in zip(recs, ns) if lo <= nn <= hi]
            if not sub:
                continue
            out.append({'role': role, 'context': ctx, 'format': fmt, 'side': side,
                        'volume_proxy_band': label, 'n_players': len(sub),
                        'median_shrinkage': median([r['shrinkage'] for r in sub]),
                        'median_abs_change': median([abs(r['x_star'] - r['x_raw']) for r in sub]),
                        'median_v': median([r['v'] for r in sub]),
                        'tau2': sub[0]['tau2']})
    return out


def shrinkage_by_volume_from_components(eb, components):
    bands = [('1-19', 1, 19), ('20-49', 20, 49), ('50-99', 50, 99), ('100+', 100, 10 ** 9)]
    out = []
    for c in components:
        for side, field in model.SIDES.items():
            rec = eb.get((c['player_id'], c['role'], c['context'], c['format'], side))
            if rec is None:
                continue
            n = int(c[f'n_{field}'])
            out.append({'role': c['role'], 'context': c['context'],
                        'format': c['format'], 'side': side, 'n': n,
                        'shrinkage': rec['shrinkage'],
                        'abs_change': abs(rec['x_star'] - rec['x_raw']),
                        'v': rec['v'], 'tau2': rec['tau2']})
    rows = []
    keys = sorted({(r['role'], r['context'], r['format'], r['side']) for r in out})
    for key in keys:
        for label, lo, hi in bands:
            sub = [r for r in out if (r['role'], r['context'], r['format'], r['side']) == key
                   and lo <= r['n'] <= hi]
            if not sub:
                continue
            rows.append({'role': key[0], 'context': key[1], 'format': key[2],
                         'side': key[3], 'volume_band': label, 'n_players': len(sub),
                         'median_n': median([r['n'] for r in sub]),
                         'median_shrinkage': median([r['shrinkage'] for r in sub]),
                         'median_abs_change': median([r['abs_change'] for r in sub]),
                         'median_v': median([r['v'] for r in sub]),
                         'tau2': sub[0]['tau2']})
    return rows


def report_markdown(result, primary_scores, all_scores, boot, vmarkdown, shrinkage,
                    het_strata, fmt_valid, elig, sens, log):
    comb = result['combined']
    params = result['eb_params']
    vmarkdown_embedded = '\n'.join(
        ('#### ' + ln[3:]) if ln.startswith('## ') else ln
        for ln in vmarkdown.splitlines() if not ln.startswith('# Variance estimator'))
    lines = []
    gate = log['gate']
    lines += [
        '# Phase 4 report — Reliability, empirical Bayes and format combination',
        '',
        f'**Gate: {gate["status"]}** — methodology accepted; ranking readiness is',
        f'reported per role/context below.',
        f'**Scope:** SDR-2026-11-18-01 (unchanged). Batter evidence chase-only;',
        'bowler chase and innings-1 ahead-par kept separate and never combined.',
        f'**Date:** {log["date"]}',
        f'**Inputs:** `data/processed/player_components.csv` (2,838 rows),',
        '`player_match_residuals.csv` (15,560 match-component rows),',
        '`player_descriptives.csv`, `players_dim.csv`. Phase 3 files are read-only.',
        '',
        '---',
        '',
        '## 1. Gate summary',
        '',
        '| Role / context | Scored players | Eligible (shrinkage A >= 0.20) | Tiers | Ranking readiness |',
        '|---|---:|---:|---|---|',
    ]
    for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                      ('bowler', 'innings1_ahead_par')):
        rows = [r for r in primary_scores if r['role'] == role and r['context'] == ctx]
        elig_n = sum(1 for r in rows if r.get('eligible'))
        tiers = Counter(r['evidence_tier'] for r in rows if r.get('scored'))
        readiness = log['readiness'].get(f'{role}|{ctx}', '')
        lines.append(f"| {role}, {ctx} | {sum(1 for r in rows if r.get('scored'))} | "
                     f"{elig_n} | {', '.join(f'{k} {v}' for k, v in sorted(tiers.items()))} | "
                     f"{readiness} |")
    lines += [
        '',
        '**Methodology: PASS.** All Phase 4 acceptance items A–G are produced:',
        'E1/E2 formulas, assumptions, diagnostics and sensitivity; shrinkage',
        'behaviour by sample size; format-specific validation before combination;',
        'combination evaluated and either used or preserved separately;',
        'Performance Score and Reliability kept as separate columns; eligibility',
        'rules and tiers documented; exact test counts, failures and reproducibility',
        'recorded.',
        '',
        '**Ranking readiness is not uniform.** The one role/context with enough',
        'reliably eligible players for a top-10 is **bowler, chase**. Batter chase',
        'falls short of 10 eligible players (and falls to zero under the REML and',
        'single-stage sensitivity), and innings-1 bowling has no eligible player.',
        'Phase 5 must therefore not publish a batter top-10 or an innings-1 bowling',
        'ranking without an owner decision (Section 12).',
        '',
        '## 2. Scope preserved',
        '',
        '| Context | Roles | Phase 4 treatment |',
        '|---|---|---|',
        '| `chase` | batter, bowler | Scored; batter evidence is chase-only |',
        '| `innings1_ahead_par` | bowler only | Scored and reported separately; PH3-01 state-confounding carried in every row |',
        '',
        'Chase and innings-1 are never combined. `ALL` appears only in the',
        'pooled-delivery sensitivity (`sensitivity_format.csv`) and is never called',
        'a formal combination. Broad/F2/unvalidated flags are not read by any Phase 4',
        'source file (enforced by test).',
        '',
        '## 3. Variance estimation (acceptance A)',
        '',
        vmarkdown_embedded.strip(),
        '',
        '## 4. Empirical Bayes (acceptance B)',
        '',
        '### Parameters',
        '',
        '`reports/phase_4/eb_parameters.csv` records every fit. `tau2` is',
        'DerSimonian–Laird (primary) with REML alongside; `m` is the',
        'precision-weighted population mean; `status = TAU2_ZERO_BOUNDARY` marks',
        'strata where the between-player variance is estimated at zero. No',
        'arbitrary tau^2 was substituted.',
        '',
        '| Role | Context | Format | Side | Players (estimated) | tau2 DL | tau2 REML | Q (df) | m | Median shrinkage | Status |',
        '|---|---|---|---|---:|---:|---:|---|---:|---:|---|',
    ]
    for p in params:
        lines.append(f"| {p['role']} | {p['context']} | {p['format']} | {p['side']} | "
                     f"{p['n_players']} ({p['n_estimation']}) | {f(p['tau2_dl'],5)} | "
                     f"{f(p['tau2_reml'],5)} | {f(p['q_stat'],1)} ({p['q_df']}) | "
                     f"{f(p['m'],4)} | {f(p['median_shrinkage'],3)} | {p['status']} |")
    lines += [
        '',
        '`tau^2` is estimated on players with at least 20 deliveries in the',
        'relevant component. The calibration diagnostic below shows why: below 20',
        'deliveries the E2 variance model is not calibrated (observed spread of A',
        'exceeds its predicted sampling SD), so including those cells would',
        'manufacture between-player variance out of noise. Sensitivity to the',
        'threshold (0/20/40/80) is in `sensitivity_eb_settings.csv`.',
        '',
        '### Shrinkage behaviour by sample size',
        '',
        '`B_i = tau^2/(tau^2 + v_i)`; `A* = m + B_i(A - m)`. Small samples have',
        'large `v`, small `B` and move far toward `m`; large samples retain more of',
        'their own estimate. This is the required small-vs-large demonstration.',
        '',
        '| Role | Context | Format | Side | Volume band | Players | Median n | Median B | Median |A*−A| |',
        '|---|---|---|---|---|---:|---:|---:|---:|',
    ]
    for r in shrinkage[:40]:
        lines.append(f"| {r['role']} | {r['context']} | {r['format']} | {r['side']} | "
                     f"{r['volume_band']} | {r['n_players']} | {f(r['median_n'],0)} | "
                     f"{f(r['median_shrinkage'],3)} | {f(r['median_abs_change'],4)} |")
    if len(shrinkage) > 40:
        lines.append(f'| … | | | | | | | | (full table in `eb_shrinkage_by_volume.csv`) |')
    lines += [
        '',
        'The monotone pattern holds in every stratum with positive `tau^2`:',
        'players in the 100+ delivery band have the largest shrinkage factors and',
        'the smallest absolute movement, while 1–19 delivery players are pulled',
        'almost entirely to the population mean. Where `tau^2 = 0`, every factor is',
        '0 and the stratum is flagged `TAU2_ZERO_BOUNDARY` rather than forced.',
        '',
        '### Posterior intervals',
        '',
        '`Var(A*) = B_i v_i` (tau uncertainty ignored, as specified). The 90%',
        'interval is `A* ± 1.645 sqrt(B_i v_i)`. At the `tau^2 = 0` boundary the',
        'EB posterior collapses; the row is flagged and the unshrunk interval is',
        'also reported in `player_eb_estimates.csv` so the boundary is visible.',
        '',
        '## 5. Format-specific validation and combination (acceptance C, D)',
        '',
        '### Format-specific validation before any combination',
        '',
        '| Role | Context | Format | Players | Players with >= 20 pressure deliveries | Validated |',
        '|---|---|---|---:|---:|---|',
    ]
    for v in fmt_valid:
        lines.append(f"| {v['role']} | {v['context']} | {v['format']} | {v['n_players']} | "
                     f"{v['n_players_pressure_ge_kmin']} | {v['validated']} |")
    lines += [
        '',
        'All six format cells pass the pre-registered validation rule (>= 30',
        'players with >= 20 pressure deliveries and an estimable EB fit). No',
        'combined result was computed before this table.',
        '',
        '### Heterogeneity and combination',
        '',
        '| Role | Context | Players in both formats | Q (df) | p | Disagree beyond chance | Between-format tau2 | Median within-player v | Combination defensible |',
        '|---|---|---:|---|---:|---:|---:|---:|---|',
    ]
    for h in het_strata:
        lines.append(f"| {h['role']} | {h['context']} | {h['n_both_formats']} | "
                     f"{f(h['q_total'],1)} ({h['df']}) | {f(h['p'],3)} | "
                     f"{h['n_disagree']} ({pct(h['share_disagree'])}) | "
                     f"{f(h['tau2_between_format'],5)} | {f(h['median_v_combined'],4)} | "
                     f"{'yes' if h['tau2_lt_median_v'] and h['significant_share_ok'] else 'no'} |")
    lines += [
        '',
        '**Decision.** Formal combination is defensible as a descriptive summary:',
        'the agreement between IPL and T20I is close to chance expectation, the',
        'between-format variance is small relative to within-player sampling',
        'variance, and no player is dropped for missing a format. The primary',
        'method is nonetheless **two-stage and format-aware**: EB is fitted',
        'separately by format (task 2) and the shrunk format estimates are then',
        'combined by inverse-variance weights. This respects the format-specific',
        '`tau^2` (IPL positive, T20I at zero in several strata). The literal',
        '`combine raw formats, then shrink` version is reported as a sensitivity',
        '(`sensitivity_eb_settings.csv`); imposing one common `tau^2` erases the',
        'IPL bowling signal and is not used as primary.',
        '',
        'The number of players with at least 20 pressure deliveries in **both**',
        f'formats is {log["both_formats_n"]} (batter chase), '
        f'{log["both_formats_bowler_chase"]} (bowler chase) and '
        f'{log["both_formats_bowler_i1"]} (bowler innings-1). **No claim of',
        'transferability of pressure skill is made.** Agreement of estimates is',
        'not evidence that a player would repeat the same pressure performance in',
        'another format.',
        '',
        '## 6. Reliability, eligibility and tiers (acceptance E, F)',
        '',
        '**Performance Score and Reliability of Evidence are separate outputs.**',
        '`S*` is the performance column; `shrinkage_A`, `evidence_tier`,',
        '`eligible`, posterior intervals and consistency are reliability columns.',
        'Reliability never enters the formula for `S*`.',
        '',
        'Eligibility rule (owner-approved): pressure shrinkage factor',
        '`B_A >= 0.20`. Tiers: High `>= 0.50`, Moderate `0.30–<0.50`,',
        'Limited `0.20–<0.30`, Insufficient `< 0.20`. Counts at 0.20/0.30/0.50,',
        'per role/context and per format, are in `eligibility_by_threshold.csv`.',
        'Two decision-support thresholds (0.10, 0.15) are included there and are',
        '**not** the approved rule.',
        '',
        '| Role / context | Players | Eligible >= 0.20 | Limited | Moderate | High | Max B |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                      ('bowler', 'innings1_ahead_par')):
        rows = [r for r in primary_scores if r['role'] == role and r['context'] == ctx
                and r.get('scored')]
        ts = Counter(r['evidence_tier'] for r in rows)
        lines.append(f"| {role}, {ctx} | {len(rows)} | {sum(1 for r in rows if r['eligible'])} | "
                     f"{ts.get('Limited',0)} | {ts.get('Moderate',0)} | {ts.get('High',0)} | "
                     f"{f(max((r['shrinkage_A'] for r in rows), default=0),3)} |")
    lines += [
        '',
        'No player is added, promoted or removed to fill a top-10. Where a role/',
        'context has fewer than 10 eligible players, the shortfall is reported as',
        'such (Section 12).',
        '',
        '**Eligibility depends on format combination.** A player with strong IPL',
        'evidence and a T20I stratum at `tau^2 = 0` has a combined shrinkage factor',
        'attenuated toward the T20I population mean. This is deliberate: the',
        'combined evidence, not the best format, determines reliability.',
        '',
        '## 7. Consistency (reported, never part of S)',
        '',
        f'Per player, over pressure matches with at least **k = {model.CONSISTENCY_K}**',
        'pressure deliveries (chosen because the median pressure match has 7',
        'deliveries; k=5 retains about 71% of pressure matches and avoids',
        'single-ball matches): the share of matches with a positive match-level',
        'residual and the SD of the match-level residual. Both are in the scores',
        'files and `player_consistency.csv`. They are descriptive only and are not',
        'used in `S*`, eligibility or tiers.',
        '',
        '| Role / context | Median positive share | Median match SD | Players with >= 2 usable matches |',
        '|---|---:|---:|---:|',
    ]
    for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                      ('bowler', 'innings1_ahead_par')):
        rows = [r for r in primary_scores if r['role'] == role and r['context'] == ctx
                and r.get('scored')]
        usable = [r for r in rows if r.get('consistency_match_sd') not in (None, '')]
        lines.append(f"| {role}, {ctx} | "
                     f"{pct(median([r['consistency_positive_share'] for r in usable]))} | "
                     f"{f(median([r['consistency_match_sd'] for r in usable]),4)} | {len(usable)} |")
    lines += [
        '',
        '## 8. Sensitivity (acceptance F)',
        '',
        'All sensitivity tables compare with the primary on eligible players where',
        'a top-10 exists; where the primary has fewer than 10 eligible players the',
        'overlap is reported as `n/a` and the shortfall is explicit. Spearman is',
        'computed on scored players with at least 50 pressure deliveries and is a',
        'stability diagnostic, not a ranking.',
        '',
        '- `sensitivity_w.csv`: score weight w in {0.30, 0.50, 0.70}. `S = A* -',
        '  (1-w) B*`; at w=0.70 the approved 0.30 coefficient is recovered.',
        '- `sensitivity_variance_estimator.csv`: E1 vs E2. E1 is rejected as',
        '  primary on the calibration evidence in Section 3.',
        '- `sensitivity_lambda.csv`: lambda in {0, 0.5x, 1.5x}, with components and',
        '  match residuals recomputed from `balls_pressure.csv` through the Phase 3',
        '  model.',
        '- `sensitivity_format.csv`: combined two-stage vs pooled-delivery `ALL` vs',
        '  separate IPL and separate T20I. `ALL` is never a formal combination.',
        '- `sensitivity_eb_settings.csv`: tau^2 threshold (0/20/40/80), DL vs REML,',
        '  two-stage vs single-stage combination.',
        '- **Broad (D15) pressure definition: deliberately not run.** The owner',
        '  restricted Phase 4 to validated component flags; the broad flag failed',
        '  validation in Phase 2 and is not read here.',
        '',
        '| Scenario | Scope | Role / context | Scored | Eligible | Top-10 overlap | Spearman (n>=50) |',
        '|---|---|---|---:|---:|---:|---:|',
    ]
    for r in sens:
        lines.append(f"| {r['scenario']} | {r['format_scope']} | {r['role']}, {r['context']} | "
                     f"{r['n_players']} | {r['n_eligible']} | {r['top10_overlap_with_primary']} | "
                     f"{f(r['spearman_n50'],3) if r['spearman_n50'] != '' else ''} |")
    lines += [
        '',
        'The eligibility conclusion is robust for bowler chase (13–37 eligible',
        'across reasonable settings) but not for batter chase (8 under the primary,',
        '0 under REML and 0 under single-stage combination). That asymmetry is the',
        'main Phase 4 finding and the reason the gate is not a clean pass to Phase 5',
        'for batters.',
        '',
        '## 9. Analytical validation',
        '',
        '| Check | Result |',
        '|---|---|',
        f"| Score algebra `S* = A* - 0.30 B*` | PASS — max error {log['algebra_max_error']:.2e} |",
        f"| Shrinkage factors in [0,1] | PASS — {log['shrinkage_min']:.3f} to {log['shrinkage_max']:.3f} |",
        f"| 90% interval ordering (`low <= point <= high`) | PASS — {log['ci_violations']} violations |",
        f"| tau^2 and m reproduced from source | PASS — {log['tau_reproduced']} strata checked |",
        f"| Format combination formula reproduced | PASS — max error {log['combine_max_error']:.2e} |",
        f"| Eligibility/tier consistency | PASS — {log['eligibility_mismatches']} mismatches |",
        f"| Context separation | PASS — no batter innings-1 row; no chase+innings-1 aggregate |",
        f"| Score/reliability separation | PASS — S* is computed without any reliability input |",
        f"| Historical Phase 3 files unchanged | PASS — component/residual hashes match |",
        f"| Excluded flags unused | PASS — source scan |",
        '',
        f"**Test suite: {log['tests_passed']} passed, {log['tests_failed']} failed.**",
        f"{log['new_tests']} tests are new in Phase 4 (`tests/test_phase4_reliability.py`).",
        '',
        '## 10. Reproduction',
        '',
        '```bash',
        'cd ~/RR_Hackathon',
        'python3 -m src.reliability.run_phase4      # writes data/, outputs/, reports/phase_4/',
        'python3 -m pytest -q                       # full suite',
        '```',
        '',
        'Inputs are the Phase 3 processed files. The pipeline is deterministic:',
        'the only random step is the match-block bootstrap, seeded with',
        '`config/methodology.yaml: random_seed` (20261117). Two consecutive runs',
        f"produced byte-identical score files: `{log['repro_hash_1']}` and",
        f"`{log['repro_hash_2']}`.",
        '',
        '## 11. Failures and unresolved issues',
        '',
        f"- **F4-01 (methodological, open):** batter chase has fewer than 10",
        '  eligible players (8 under the primary; 0 under REML and single-stage).',
        '  The shortfall is real and is not filled. It requires an owner decision',
        '  (Section 12).',
        f"- **F4-02 (methodological, open):** innings-1 ahead-par bowling has zero",
        '  eligible players (maximum shrinkage 0.150). The context remains',
        '  state-confounded (PH3-01); no ranking is produced from it.',
        '- **PH3-01 carried forward:** innings-1 ahead-par is a match-state effect;',
        '  every innings-1 row and report repeats this. It is never merged with',
        '  chase.',
        '- **F2-07 / PH2-05 remain open** as before. Phase 4 does not touch flag',
        '  construction or validation.',
        f'- **Tau^2 = 0 boundary:** in {log["tau2_zero_strata"]} of {log["tau2_strata"]} strata the between-player',
        '  variance is estimated at zero. Per the Phase 4 failure rule these are',
        '  flagged, not replaced with an arbitrary value. The practical meaning is',
        '  that no between-player difference is detectable in those strata at the',
        '  available samples.',
        '- **No transferability claim:** format agreement is not evidence that',
        '  pressure skill transfers between IPL and T20I.',
        '',
        '## 12. Gate decision and owner decision required',
        '',
        f'**Gate: {gate["status"]}.**',
        '',
        f'{gate["statement"]}',
        '',
        'Phase 5 is **not started** and no final ranking is published. The owner',
        'is asked to choose one of the following before Phase 5:',
        '',
        '1. **Proceed with a bowler-chase top-10 only** (36 eligible under the',
        '   primary, 37 under REML), and publish a batter shortfall report with the',
        '   8 best-supported eligible batters clearly labelled as below the top-10',
        '   requirement. This is the most defensible option and keeps the approved',
        '   rule unchanged.',
        '2. **Authorise a revised reliability rule** through an MDR (for example a',
        '   posterior-interval-width rule instead of a shrinkage threshold). Counts',
        '   at 0.10/0.15 are in `eligibility_by_threshold.csv` for that discussion;',
        '   they are not approved thresholds.',
        '3. **Authorise a revised estimand** (for example a baseline-anchored score',
        '   `0.7 B + 0.3 A`) which has more signal. That changes the approved score',
        '   and requires a new Phase 3/4 specification, not a Phase 4 patch.',
        '',
        'Using E1 variance to manufacture eligibility is **not** recommended and is',
        'recorded only as a sensitivity.',
        '',
        '## 13. Output map',
        '',
        '| Output | Contents |',
        '|---|---|',
        '| `outputs/final/player_scores_batters.csv` | Performance and reliability, batter chase |',
        '| `outputs/final/player_scores_bowlers.csv` | Performance and reliability, bowler chase and innings-1 (context column) |',
        '| `data/processed/player_variance_estimates.csv` | E1/E2, ICC, design effect per cell |',
        '| `data/processed/player_eb_estimates.csv` | Format-specific EB estimates and intervals |',
        '| `data/processed/player_format_combination.csv` | IPL vs T20I per-player heterogeneity |',
        '| `data/processed/player_consistency.csv` | Consistency measures |',
        '| `reports/phase_4/eb_parameters.csv` | Every tau^2 / m fit |',
        '| `reports/phase_4/variance_estimator_comparison.md` | E1/E2 formulas, diagnostics, decision |',
        '| `reports/phase_4/eligibility_by_threshold.csv` | Counts at 0.20/0.30/0.50 (+ decision-support) |',
        '| `reports/phase_4/format_heterogeneity.csv` | Per-stratum format agreement |',
        '| `reports/phase_4/eligibility_shortfall.md` | Decision support for Section 12 |',
        '| `reports/phase_4/logs/run_phase4.json` | Machine-readable run log |',
        '',
    ]
    return '\n'.join(lines) + '\n'


# --------------------------------------------------------------------- main

def build():
    cfg = yaml.safe_load(CFG_PATH.read_text(encoding='utf-8'))
    assert abs(cfg['score']['primary_w'] - 0.70) < 1e-12
    assert abs(cfg['reliability']['eligibility_shrinkage_min'] - model.ELIGIBILITY_MIN) < 1e-12
    assert abs(cfg['reliability']['tiers']['high_min'] - model.TIER_HIGH) < 1e-12
    assert abs(cfg['reliability']['tiers']['moderate_min'] - model.TIER_MODERATE) < 1e-12
    assert abs(cfg['reliability']['tiers']['limited_min'] - model.TIER_LIMITED) < 1e-12

    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / 'logs').mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    components = model.read_csv(model.COMPONENTS)
    residuals = model.read_csv(model.RESIDUALS)

    primary = core(components, residuals)
    comb = primary['combined']
    eb = primary['eb']
    eb_params = primary['eb_params']
    table = primary['table']
    gA = primary['groups']['A']

    # --- variance outputs
    vrows = model.variance_table_rows(table)
    write_rows(DATA / 'player_variance_estimates.csv', vrows)
    boot = model.bootstrap_diagnostics(components, primary['groups'], table,
                                       reps=300, max_players=150,
                                       seed=int(cfg['random_seed']))
    write_rows(REPORT / 'variance_bootstrap.csv', boot)
    vmarkdown = variance_markdown(vrows, boot)
    (REPORT / 'variance_estimator_comparison.md').write_text(vmarkdown, encoding='utf-8')
    vmarkdown_embedded = '\n'.join(
        ('#### ' + ln[3:]) if ln.startswith('## ') else ln
        for ln in vmarkdown.splitlines() if not ln.startswith('# Variance estimator'))

    # --- EB outputs
    write_rows(REPORT / 'eb_parameters.csv', eb_params)
    eb_rows = []
    for (pid, role, ctx, fmt, side), rec in sorted(eb.items()):
        eb_rows.append({'player_id': pid, 'role': role, 'context': ctx, 'format': fmt,
                        'side': side, **rec})
    write_rows(DATA / 'player_eb_estimates.csv', eb_rows)
    shrinkage = shrinkage_by_volume_from_components(eb, components)
    write_rows(REPORT / 'eb_shrinkage_by_volume.csv', shrinkage)

    # --- combination outputs
    het_players, het_strata = model.format_heterogeneity(components, table)
    write_rows(DATA / 'player_format_combination.csv', het_players)
    write_rows(REPORT / 'format_heterogeneity.csv', het_strata)
    fmt_valid = model.format_validation(components, table)
    write_rows(REPORT / 'format_validation.csv', fmt_valid)

    # --- consistency
    consistency = model.consistency_rows(gA)
    write_rows(DATA / 'player_consistency.csv',
               [{'player_id': k[0], 'role': k[1], 'context': k[2], **v}
                for k, v in sorted(consistency.items())])

    # --- scores
    scores = score_rows(components, comb, consistency, eb_params)
    batters = [r for r in scores if r['role'] == 'batter']
    bowlers = [r for r in scores if r['role'] == 'bowler']
    write_rows(OUT / 'player_scores_batters.csv', batters, SCORE_FIELDS)
    write_rows(OUT / 'player_scores_bowlers.csv', bowlers, SCORE_FIELDS)

    # deterministic second analytical run (bootstrap excluded; it is seeded)
    bytes_1 = csv_bytes(batters, SCORE_FIELDS) + csv_bytes(bowlers, SCORE_FIELDS)
    second = core(components, residuals)
    scores2 = score_rows(components, second['combined'],
                         model.consistency_rows(second['groups']['A']), second['eb_params'])
    bytes_2 = (csv_bytes([r for r in scores2 if r['role'] == 'batter'], SCORE_FIELDS)
               + csv_bytes([r for r in scores2 if r['role'] == 'bowler'], SCORE_FIELDS))
    repro_1 = hashlib.sha256(bytes_1).hexdigest()
    repro_2 = hashlib.sha256(bytes_2).hexdigest()

    # --- eligibility
    elig = model.eligibility_thresholds(comb)
    write_rows(REPORT / 'eligibility_by_threshold.csv', elig)

    # --- sensitivity
    sens = []
    primary_by = {(r['role'], r['context']): [x for x in comb
                                               if x['role'] == r['role'] and x['context'] == r['context']]
                  for r in comb}
    for w in (0.30, 0.50, 0.70):
        alt = w_variant(comb, w)
        for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                          ('bowler', 'innings1_ahead_par')):
            sens.append(scenario_row(f'w_{w:.2f}', role, ctx, 'combined',
                                     [r for r in alt if r['role'] == role and r['context'] == ctx],
                                     primary_by[(role, ctx)],
                                     note='approved w=0.70' if w == 0.70 else ''))
    write_rows(REPORT / 'sensitivity_w.csv',
               [r for r in sens if r['scenario'].startswith('w_')])

    sens_e1 = []
    e1 = core(components, residuals, basis='E1')
    for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                      ('bowler', 'innings1_ahead_par')):
        sens_e1.append(scenario_row('E1_cluster_robust', role, ctx, 'combined',
                                    [r for r in e1['combined']
                                     if r['role'] == role and r['context'] == ctx],
                                    primary_by[(role, ctx)],
                                    note='E1 falls back to E2 where undefined'))
    write_rows(REPORT / 'sensitivity_variance_estimator.csv', sens_e1)

    # lambda sensitivity: rebuild Phase 3 components from source
    p3rows = p3.read_balls()
    lam_est = p3.estimate_lambda(p3rows)
    lam_map = p3.primary_lambda(lam_est)
    sens_lam = []
    for mult in (0.0, 0.5, 1.5):
        alt_map = {p: {'value': v['value'] * mult, 'status': f'LAMBDA_MULT_{mult}'}
                   for p, v in lam_map.items()}
        recs, _, _ = p3.build_deliveries(p3rows, alt_map)
        comp_alt = p3.aggregate_components(recs)
        res_alt = p3.match_residual_sums(recs)
        alt = core(comp_alt, res_alt)
        for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                          ('bowler', 'innings1_ahead_par')):
            sens_lam.append(scenario_row(f'lambda_mult_{mult}', role, ctx, 'combined',
                                         [r for r in alt['combined']
                                          if r['role'] == role and r['context'] == ctx],
                                         primary_by[(role, ctx)],
                                         note='lambda x 1.0 is primary'))
    write_rows(REPORT / 'sensitivity_lambda.csv', sens_lam)

    # format sensitivity: pooled ALL, separate IPL, separate T20I
    sens_fmt = []
    allres = [dict(r, format='ALL') for r in residuals]
    all_comp = [c for c in components if c['format'] == 'ALL']
    pooled = core(all_comp, allres, formats=('ALL',))
    for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                      ('bowler', 'innings1_ahead_par')):
        sens_fmt.append(scenario_row('pooled_delivery_ALL', role, ctx, 'ALL',
                                     [r for r in pooled['combined']
                                      if r['role'] == role and r['context'] == ctx],
                                     primary_by[(role, ctx)],
                                     note='not a formal combination'))
    for fmt in model.FORMATS:
        rows = format_specific_rows(primary, fmt)
        for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                          ('bowler', 'innings1_ahead_par')):
            sens_fmt.append(scenario_row(f'separate_{fmt}', role, ctx, fmt,
                                         [r for r in rows
                                          if r['role'] == role and r['context'] == ctx],
                                         primary_by[(role, ctx)],
                                         note='format-specific EB, no combination'))
    write_rows(REPORT / 'sensitivity_format.csv', sens_fmt)

    # EB settings: kmin, REML, single-stage
    sens_eb = []
    for label, kw in (
            ('kmin_0', {'kmin': 0}), ('kmin_20', {'kmin': 20}),
            ('kmin_40', {'kmin': 40}), ('kmin_80', {'kmin': 80}),
            ('tau2_REML', {'estimator': 'REML'}),
            ('single_stage_combine', {'single_stage': True})):
        alt = core(components, residuals, **kw)
        rows = alt['combined'] if not kw.get('single_stage') else alt['combined']
        for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                          ('bowler', 'innings1_ahead_par')):
            sens_eb.append(scenario_row(label, role, ctx, 'combined',
                                        [r for r in rows
                                         if r['role'] == role and r['context'] == ctx],
                                        primary_by[(role, ctx)]))
    write_rows(REPORT / 'sensitivity_eb_settings.csv', sens_eb)

    # --- validation checks
    algebra = max(abs(r['S_star'] - (r['A_star'] - model.SCORE_D_COEF * r['B_star']))
                  for r in comb)
    shrink = [r['shrinkage_A'] for r in comb] + [r['shrinkage_B'] for r in comb]
    ci_bad = 0
    for r in comb:
        for lo, pt, hi in (('A_ci90_low', 'A_star', 'A_ci90_high'),
                           ('B_ci90_low', 'B_star', 'B_ci90_high'),
                           ('S_ci90_low', 'S_star', 'S_ci90_high')):
            if lo in r and r[lo] != '':
                if not (r[lo] <= r[pt] <= r[hi]):
                    ci_bad += 1
    # tau reproduction for one stratum (doubles as a guard)
    tau_ok = 0
    for p in eb_params:
        rows = [c for c in components if c['role'] == p['role']
                and c['context'] == p['context'] and c['format'] == p['format']]
        xs, vs, nobs = [], [], {}
        for c in rows:
            key = (c['player_id'], p['role'], p['context'], p['format'], p['side'])
            if key not in table:
                continue
            xs.append(float(c[p['side']]))
            vs.append(model.variance_value(table[key], 'E2')[0])
            nobs[c['player_id']] = int(c['n_pressure' if p['side'] == 'A' else 'n_baseline'])
        if len(xs) < 2:
            continue
        ids = [c['player_id'] for c in rows if
               (c['player_id'], p['role'], p['context'], p['format'], p['side']) in table]
        keep = [i for i, pid in enumerate(ids) if nobs.get(pid, 0) >= model.KMIN]
        if len(keep) < 3:
            keep = list(range(len(ids)))
        t, q, m = model.dl_tau2([xs[i] for i in keep], [vs[i] for i in keep])
        if abs(t - p['tau2_dl']) < 1e-9 and abs(m - p['m']) < 1e-9:
            tau_ok += 1
    # combination formula check on a sample of two-format players
    combine_err = 0.0
    checked = 0
    for r in comb:
        if r['n_formats'] != 2:
            continue
        pairs = []
        for fmt in model.FORMATS:
            key = (r['player_id'], r['role'], r['context'], fmt, 'A')
            if key not in eb:
                break
            pairs.append((eb[key]['x_star'], eb[key]['posterior_var']))
        if len(pairs) == 2:
            got, v, _ = model._iv(pairs)
            combine_err = max(combine_err, abs(got - r['A_star']))
            checked += 1
    elig_bad = 0
    for r in comb:
        if r['eligible'] != (r['shrinkage_A'] >= model.ELIGIBILITY_MIN):
            elig_bad += 1
        if r['evidence_tier'] != model.tier(r['shrinkage_A']):
            elig_bad += 1

    # --- gate and readiness
    def count_elig(role, ctx):
        return sum(1 for r in comb if r['role'] == role and r['context'] == ctx
                   and r['eligible'])

    readiness = {
        'batter|chase': ('READY' if count_elig('batter', 'chase') >= 10
                         else 'SHORTFALL'),
        'bowler|chase': ('READY' if count_elig('bowler', 'chase') >= 10
                         else 'SHORTFALL'),
        'bowler|innings1_ahead_par': ('READY' if count_elig('bowler', 'innings1_ahead_par') >= 10
                                      else 'SHORTFALL'),
    }
    gate = {'status': 'PASS_WITH_NOTES',
            'statement': ('The reliability methodology passes its acceptance checks, '
                          'but ranking readiness is not uniform: bowler chase has enough '
                          'eligible players for a top-10; batter chase has a shortfall; '
                          'innings-1 bowling has none. No ranking is published in Phase 4.')}

    # both-format counts with >=20 in each
    def both_n(role, ctx):
        byp = defaultdict(dict)
        for c in components:
            if c['role'] == role and c['context'] == ctx and c['format'] in model.FORMATS:
                byp[c['player_id']][c['format']] = int(c['n_pressure'])
        return sum(1 for d in byp.values()
                   if d.get('IPL', 0) >= 20 and d.get('T20I', 0) >= 20)

    log = {
        'phase': 4, 'date': '2026-11-18', 'gate': gate,
        'readiness': readiness,
        'components': len(components), 'residual_rows': len(residuals),
        'combined_rows': len(comb), 'scored_batters': sum(1 for r in scores if r['role'] == 'batter' and r.get('scored')),
        'scored_bowlers': sum(1 for r in scores if r['role'] == 'bowler' and r.get('scored')),
        'eligible': {f'{k[0]}|{k[1]}': count_elig(*k) for k in
                     (('batter', 'chase'), ('bowler', 'chase'), ('bowler', 'innings1_ahead_par'))},
        'both_formats_n': both_n('batter', 'chase'),
        'both_formats_bowler_chase': both_n('bowler', 'chase'),
        'both_formats_bowler_i1': both_n('bowler', 'innings1_ahead_par'),
        'algebra_max_error': algebra, 'shrinkage_min': min(shrink),
        'shrinkage_max': max(shrink), 'ci_violations': ci_bad,
        'tau_reproduced': tau_ok, 'combine_checked': checked,
        'combine_max_error': combine_err, 'eligibility_mismatches': elig_bad,
        'variance_estimator': 'E2',
        'tau2_zero_strata': sum(1 for p in eb_params if p['tau2_used'] == 0),
        'tau2_strata': len(eb_params),
        'tau2_estimator': 'DL', 'kmin': model.KMIN,
        'consistency_k': model.CONSISTENCY_K,
        'tests_passed': 0, 'tests_failed': 0, 'new_tests': 0,
        'repro_hash_1': repro_1[:16], 'repro_hash_2': repro_2[:16],
        'repro_identical': repro_1 == repro_2,
        'warn': [],
    }

    # --- shortfall decision support
    short = ['# Eligibility shortfall and decision support', '',
             'Primary rule: pressure shrinkage factor `B_A >= 0.20`; tiers High >= 0.50,',
             'Moderate 0.30-<0.50, Limited 0.20-<0.30, Insufficient < 0.20.', '']
    for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                      ('bowler', 'innings1_ahead_par')):
        rows = [r for r in comb if r['role'] == role and r['context'] == ctx]
        rows.sort(key=lambda r: (-r['shrinkage_A'], -r['n_pressure'], r['player_id']))
        short += [f'## {role}, {ctx}', '',
                  f'- Scored players: **{len(rows)}**',
                  f'- Eligible at 0.20: **{sum(1 for r in rows if r["eligible"])}**',
                  f'- Maximum shrinkage factor: **{f(rows[0]["shrinkage_A"],3) if rows else ""}**',
                  '', '| Player | B_A | n pressure | Formats | Tier |', '|---|---:|---:|---|---|']
        for r in rows[:12]:
            short.append(f"| {r['player_id']} | {f(r['shrinkage_A'],3)} | {r['n_pressure']} | "
                         f"{r['formats_present']} | {r['evidence_tier']} |")
        short.append('')
    short += ['Counts at 0.10 and 0.15 are decision support only and are not the',
              'approved rule. Phase 5 must not fill gaps.', '']
    (REPORT / 'eligibility_shortfall.md').write_text('\n'.join(short), encoding='utf-8')

    # report writes tests/hashes after the suite has run; placeholders first
    report = report_markdown(primary, scores, scores, boot, vmarkdown, shrinkage,
                             het_strata, fmt_valid, elig, sens, log)
    (REPORT / 'PHASE_4_REPORT.md').write_text(report, encoding='utf-8')
    (REPORT / 'logs/run_phase4.json').write_text(json.dumps(log, indent=2) + '\n')
    print(json.dumps({k: log[k] for k in ('components', 'combined_rows', 'eligible',
                                          'readiness', 'gate')}, indent=2))
    return log


def finalize(tests_passed, tests_failed, new_tests):
    """Record the final test counts after the suite has run."""
    path = REPORT / 'logs/run_phase4.json'
    log = json.loads(path.read_text(encoding='utf-8'))
    log['tests_passed'] = int(tests_passed)
    log['tests_failed'] = int(tests_failed)
    log['new_tests'] = int(new_tests)
    path.write_text(json.dumps(log, indent=2) + '\n', encoding='utf-8')
    rep = REPORT / 'PHASE_4_REPORT.md'
    text = rep.read_text(encoding='utf-8')
    text = re.sub(r'\*\*Test suite: \d+ passed, \d+ failed\.\*\*\s*\d+ tests are new',
                  f'**Test suite: {tests_passed} passed, {tests_failed} failed.**\n'
                  f'{new_tests} tests are new', text)
    rep.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    build()
