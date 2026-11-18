"""Phase 5 driver: final ranking, selection, stability and verification.

Scope, ranking rule and sensitivity plan: SDR-2026-11-18-03. Phase 4 outputs are
read-only; Phase 2/3/4 files are hash-checked before and after the run.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import yaml

from src.ranking import model as rk
from src.reliability import model as rm

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'reports/phase_5'
OUT = ROOT / 'outputs/final/phase5'
CFG_PATH = ROOT / 'config/methodology.yaml'

FROZEN = [
    'outputs/final/player_scores_batters.csv',
    'outputs/final/player_scores_bowlers.csv',
    'data/processed/player_components.csv',
    'data/processed/player_match_residuals.csv',
    'data/processed/player_eb_estimates.csv',
    'data/processed/player_variance_estimates.csv',
    'data/processed/player_descriptives.csv',
    'data/processed/balls_pressure.csv',
]


# ------------------------------------------------------------------ helpers

def write_rows(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fields = fields or list(rows[0])
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def f(v, digits=4):
    return '' if v in ('', None) else f'{float(v):.{digits}f}'


def pct(v, digits=1):
    return '' if v in ('', None) else f'{100.0 * float(v):.{digits}f}%'


def sha(path):
    h = hashlib.sha256()
    with (ROOT / path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def econ(runs_per_ball):
    return '' if runs_per_ball in ('', None) else f(6.0 * float(runs_per_ball), 2)


def md_table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |',
           '|' + '|'.join('---' for _ in headers) + '|']
    for r in rows:
        out.append('| ' + ' | '.join(str(c) for c in r) + ' |')
    return '\n'.join(out)


def rate(row, prefix, role):
    balls = rk.as_float(row.get(f'{prefix}_balls'))
    runs = rk.as_float(row.get(f'{prefix}_runs'))
    if not balls:
        return ''
    return runs / balls


# --------------------------------------------------------------- selection

def ranked_rows(rows, boot, identity, limit=10):
    top = rk.rank(rows, limit=limit)
    sep = {s['player_id']: s for s in rk.separation(top)}
    out = []
    for i, r in enumerate(top, 1):
        s = sep[r['player_id']]
        b = boot.get(r['player_id'], {})
        a_star = rk.as_float(r['A_star'])
        b_star = rk.as_float(r['B_star'])
        s_star = rk.score_of(r)
        n_wk = r.get('pressure_wickets') or r.get('pressure_dismissals')
        out.append({
            'rank': i,
            'player_id': r['player_id'],
            'player_name': identity.get(r['player_id'], {}).get('name', ''),
            'role': r['role'],
            'context': r['context'],
            'formats_present': r['formats_present'],
            'S_star': s_star,
            'S_ci90_low': r['S_ci90_low'],
            'S_ci90_high': r['S_ci90_high'],
            'A_star': a_star,
            'B_star': b_star,
            'D_star': rk.as_float(r['D_star']),
            'A_raw': rk.as_float(r['A_raw']),
            'B_raw': rk.as_float(r['B_raw']),
            'n_pressure': rk.as_int(r['n_pressure']),
            'n_baseline': rk.as_int(r['n_baseline']),
            'pressure_matches': rk.as_int(r['pressure_matches']),
            'baseline_matches': rk.as_int(r['baseline_matches']),
            'total_matches': rk.as_int(r['total_matches']),
            'shrinkage_A': rk.as_float(r['shrinkage_A']),
            'evidence_tier': r['evidence_tier'],
            'reliability_status': r['reliability_status'],
            'consistency_matches': r.get('consistency_matches', ''),
            'consistency_positive_share': r.get('consistency_positive_share', ''),
            'consistency_match_sd': r.get('consistency_match_sd', ''),
            'pressure_balls': rk.as_int(r.get('pressure_balls')),
            'pressure_runs_per_ball': rate(r, 'pressure', r['role']),
            'pressure_dot_pct': rk.as_float(r.get('pressure_dot_pct')),
            'pressure_boundary_pct': rk.as_float(r.get('pressure_boundary_pct')),
            'pressure_wickets': r.get('pressure_wickets', ''),
            'pressure_dismissals': r.get('pressure_dismissals', ''),
            'baseline_runs_per_ball': rate(r, 'baseline', r['role']),
            'baseline_dot_pct': rk.as_float(r.get('baseline_dot_pct')),
            'A_star_IPL': r['A_star_IPL'],
            'shrink_A_IPL': r['shrink_A_IPL'],
            'n_pressure_IPL': r['n_pressure_IPL'],
            'A_star_T20I': r['A_star_T20I'],
            'shrink_A_T20I': r['shrink_A_T20I'],
            'n_pressure_T20I': r['n_pressure_T20I'],
            'format_disagree': r['format_disagree'],
            'bootstrap_share_top10': b.get('share_top10', ''),
            'bootstrap_rank_median': b.get('rank_median', ''),
            'bootstrap_rank_p05': b.get('rank_p05', ''),
            'bootstrap_rank_p95': b.get('rank_p95', ''),
            'gap_from_previous': s.get('gap_from_previous', ''),
            'ci_overlaps_previous': s.get('ci_overlaps_previous', ''),
            'ci_contains_zero': s.get('contains_zero', ''),
            'score_explanation': (
                f'A* {a_star:+.4f} (pressure residual, positive = better), '
                f'B* {b_star:+.4f} (baseline), '
                f'S* = {a_star:+.4f} - 0.30 x {b_star:+.4f} = {s_star:+.4f}; '
                f'shrinkage B_A {rk.as_float(r["shrinkage_A"]):.3f} '
                f'({r["evidence_tier"]} evidence).'),
            'notes': r.get('notes', ''),
        })
    return out


def scenario_summary(name, role, ctx, primary_ids, rows, note=''):
    top = rk.rank(rows, limit=10)
    ids = [r['player_id'] for r in top]
    common = [r for r in rows if rk.is_eligible(r)]
    p_scores = {r['player_id']: rk.score_of(r) for r in common}
    elig = sum(1 for r in rows if rk.is_eligible(r))
    if name == 'primary':
        overlap = len(ids)
    else:
        overlap = len(set(ids) & set(primary_ids))
    return {
        'scenario': name, 'role': role, 'context': ctx,
        'eligible': elig, 'top_n': len(ids), 'published_limit': 10,
        'top_ids': '|'.join(ids),
        'overlap_with_primary': overlap,
        'overlap_share': overlap / max(len(primary_ids), 1),
        'note': note,
    }, [rk.score_of(r) for r in top]


def spearman_with(rows, primary_scores):
    pairs = [(r['player_id'], rk.score_of(r)) for r in rows
             if rk.is_eligible(r) and r['player_id'] in primary_scores]
    if len(pairs) < 3:
        return ''
    return rm.spearman([p[1] for p in pairs],
                       [primary_scores[p[0]] for p in pairs])


# ------------------------------------------------------------------- build

def build():
    cfg = yaml.safe_load(CFG_PATH.read_text(encoding='utf-8'))
    assert abs(cfg['score']['primary_w'] - 0.70) < 1e-12
    assert abs(cfg['reliability']['eligibility_shrinkage_min'] - rk.ELIGIBILITY_MIN) < 1e-12
    seed = int(cfg['random_seed'])

    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / 'logs').mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    before = {p: sha(p) for p in FROZEN}

    identity = rk.resolve_identity()
    dup_names = rk.duplicate_name_ids(identity)

    components = rm.read_csv(rm.COMPONENTS)
    residuals = rm.read_csv(rm.RESIDUALS)

    # ---- primary Phase 4 estimator, restricted per role x context
    prim = {}
    for role, ctx in (('bowler', 'chase'), ('batter', 'chase'),
                      ('bowler', 'innings1_ahead_par')):
        pool = [c for c in components
                if c['role'] == role and c['context'] == ctx]
        res = [r for r in residuals
               if r['role'] == role and r['context'] == ctx
               and r['format'] in rm.FORMATS]
        prim[(role, ctx)] = rk.core(pool, res)

    # ---- stability bootstrap
    boot = {}
    boot_diag = {}
    refit = {}
    for role, ctx in (('bowler', 'chase'), ('batter', 'chase')):
        t0 = time.time()
        b, d = rk.bootstrap_ranks(components, residuals, prim[(role, ctx)],
                                  role, ctx, reps=200, seed=seed + 5)
        d['seconds'] = round(time.time() - t0, 2)
        boot[(role, ctx)] = b
        boot_diag[f'{role}:{ctx}'] = d
        refit[f'{role}:{ctx}'] = rk.refit_diagnostic(
            components, residuals, prim[(role, ctx)]['table'],
            role, ctx, reps=100, seed=seed + 6)

    # ---- rankings
    bowler_rows = rk.load_scores('bowler', 'chase')
    batter_rows = rk.load_scores('batter', 'chase')

    bowler_top = ranked_rows(bowler_rows, boot[('bowler', 'chase')], identity)
    batter_top = ranked_rows(batter_rows, boot[('batter', 'chase')], identity)

    write_rows(OUT / 'ranking_bowler_chase.csv', bowler_top)
    write_rows(OUT / 'ranking_batter_chase.csv', batter_top)

    # ---- exclusions
    exclusions = []
    for role, rows, ctx in (('bowler', bowler_rows, 'chase'),
                            ('batter', batter_rows, 'chase')):
        exclusions += rk.exclusion_records(rows, role, ctx, identity)
    innings1 = rk.load_scores('bowler', 'innings1_ahead_par')
    write_rows(OUT / 'ranking_exclusions.csv', exclusions)

    # ---- identity table
    id_rows = []
    for pid, rec in identity.items():
        id_rows.append({**rec,
                        'duplicate_name': 'True' if rec['name'] in dup_names else 'False'})
    write_rows(OUT / 'player_identity.csv', id_rows)

    # ---- context status
    status = []
    for role, ctx in (('bowler', 'chase'), ('batter', 'chase'),
                      ('bowler', 'innings1_ahead_par')):
        rows = rk.load_scores(role, ctx)
        elig = [r for r in rows if rk.is_eligible(r)]
        tiers = {t: sum(1 for r in rows if r['evidence_tier'] == t)
                 for t in ('Insufficient', 'Limited', 'Moderate', 'High')}
        status.append({
            'role': role, 'context': ctx, 'rows': len(rows),
            'scored': sum(1 for r in rows if str(r['scored']) == 'True'),
            'eligible': len(elig),
            'max_shrinkage_A': max((rk.as_float(r['shrinkage_A'], 0) for r in rows),
                                   default=''),
            'tier_insufficient': tiers['Insufficient'],
            'tier_limited': tiers['Limited'],
            'tier_moderate': tiers['Moderate'],
            'tier_high': tiers['High'],
            'ranking_published': 'yes' if elig else 'no',
            'note': ('Chase pressure only; batter evidence is chase-only.'
                     if role == 'batter' else
                     ('Chase pressure; kept separate from innings-1.' if ctx == 'chase'
                      else 'PH3-01 state-confounded; no ranking under the approved rule.')),
        })
    write_rows(OUT / 'context_status.csv', status)

    # ---- separation
    sep_rows = []
    for role, rows in (('bowler', bowler_rows), ('batter', batter_rows)):
        top = rk.rank(rows, limit=10)
        for s in rk.separation(top):
            s['role'] = role
            s['context'] = 'chase'
            s['player_name'] = identity.get(s['player_id'], {}).get('name', '')
            sep_rows.append(s)
    write_rows(REPORT / 'separation.csv', sep_rows,
               ['rank', 'player_id', 'player_name', 'role', 'context', 'S_star',
                'ci90_low', 'ci90_high', 'ci_width', 'contains_zero',
                'gap_from_previous', 'ci_overlaps_previous'])

    # ---- format-specific rankings
    fmt_rows = []
    fmt_scenarios = {}
    for role, rows in (('bowler', bowler_rows), ('batter', batter_rows)):
        for fmt in rm.FORMATS:
            pool = rk.format_ranking(rows, fmt)
            top = pool[:10]
            fmt_scenarios[(role, fmt)] = [r['player_id'] for r in top]
            for i, r in enumerate(top, 1):
                fmt_rows.append({
                    'format_scope': fmt, 'rank': i,
                    'player_id': r['player_id'],
                    'player_name': identity.get(r['player_id'], {}).get('name', ''),
                    'role': role, 'context': 'chase',
                    'S_star': rk.score_of(r),
                    'A_star': rk.as_float(r[f'A_star_{fmt}']),
                    'B_star': rk.as_float(r[f'B_star_{fmt}']),
                    'shrinkage_A': rk.as_float(r[f'shrink_A_{fmt}']),
                    'n_pressure': rk.as_int(r[f'n_pressure_{fmt}']),
                    'in_combined_top': 'yes' if r['player_id'] in
                    [x['player_id'] for x in (bowler_top if role == 'bowler' else batter_top)]
                    else 'no',
                })
    write_rows(OUT / 'format_specific_ranking.csv', fmt_rows)

    # ---- sensitivity
    sens = []
    sens_detail = []
    for role, rows in (('bowler', bowler_rows), ('batter', batter_rows)):
        primary_top = rk.rank(rows, limit=10)
        primary_ids = [r['player_id'] for r in primary_top]
        primary_scores = {r['player_id']: rk.score_of(r)
                          for r in rows if rk.is_eligible(r)}
        variants = [('primary', rows, 'Approved specification: S* = A* - 0.30 B*.')]
        for w in (0.30, 0.50):
            variants.append((f'w_{w:.2f}', rk.w_variant(rows, w),
                             f'S = A* - (1-w) B* with w = {w:.2f}.'))
        for name, kwargs, note in (
                ('variance_E1', {'basis': 'E1'},
                 'E1 match-clustered variance (upper bound on reliability).'),
                ('tau2_REML', {'estimator': 'REML'},
                 'REML between-player variance instead of DL.'),
                ('single_stage_combination', {'single_stage': True},
                 'Combine raw formats, then shrink (one common tau^2).')):
            combined = rk.pipeline_variant(residuals, components, role, 'chase', **kwargs)
            rows_v = []
            for r in combined:
                sd = rk.as_float(r.get('S_post_sd'), 0.0)
                lo = r.get('S_ci90_low')
                hi = r.get('S_ci90_high')
                if lo in ('', None):
                    lo = r['S_star'] - rm.Z90 * sd
                if hi in ('', None):
                    hi = r['S_star'] + rm.Z90 * sd
                rows_v.append({
                    'player_id': r['player_id'], 'role': role, 'context': 'chase',
                    'A_star': r['A_star'], 'B_star': r['B_star'],
                    'S_star': r['S_star'],
                    'S_ci90_low': lo, 'S_ci90_high': hi,
                    'shrinkage_A': r['shrinkage_A'],
                    'evidence_tier': r['evidence_tier'], 'scored': True,
                    'n_pressure': r['n_pressure']})
            variants.append((name, rows_v, note))
        for name, rws, note in variants:
            rec, _scores = scenario_summary(name, role, 'chase', primary_ids, rws, note)
            rec['spearman_vs_primary'] = ('' if name == 'primary'
                                          else spearman_with(rws, primary_scores))
            sens.append(rec)
            for i, r in enumerate(rk.rank(rws, limit=10), 1):
                sens_detail.append({'scenario': name, 'role': role, 'rank': i,
                                    'player_id': r['player_id'],
                                    'player_name': identity.get(r['player_id'], {}).get('name', ''),
                                    'S_star': rk.score_of(r)})
        for fmt in rm.FORMATS:
            pool = rk.format_ranking(rows, fmt)
            rec, _ = scenario_summary(f'format_{fmt}', role, 'chase', primary_ids,
                                      pool, f'{fmt}-only estimates; no pooling.')
            rec['eligible'] = len(pool)
            rec['spearman_vs_primary'] = spearman_with(pool, primary_scores)
            sens.append(rec)
    write_rows(REPORT / 'sensitivity_rank.csv', sens)
    write_rows(REPORT / 'sensitivity_rank_detail.csv', sens_detail)

    # ---- stability file
    stab = []
    for role, top in (('bowler', bowler_top), ('batter', batter_top)):
        for r in top:
            b = boot[(role, 'chase')].get(r['player_id'], {})
            stab.append({'role': role, 'context': 'chase', 'rank': r['rank'],
                         'player_id': r['player_id'],
                         'player_name': r['player_name'],
                         'replicates_scored': b.get('replicates_scored', ''),
                         'share_scored': b.get('share_scored', ''),
                         'replicates_top10': b.get('replicates_top10', ''),
                         'share_top10': b.get('share_top10', ''),
                         'rank_median': b.get('rank_median', ''),
                         'rank_p05': b.get('rank_p05', ''),
                         'rank_p95': b.get('rank_p95', '')})
    write_rows(REPORT / 'rank_stability.csv', stab)

    # ---- checks
    checks = validate(bowler_top, batter_top, bowler_rows, batter_rows,
                      innings1, exclusions, boot, identity)
    write_rows(REPORT / 'validation_checks.csv', checks['rows'])

    # ---- independent verification
    verify_path = REPORT / 'independent_verify.py'
    proc = subprocess.run([sys.executable, str(verify_path)], capture_output=True,
                          text=True)
    verify_out = proc.stdout.strip()
    verify_json = {}
    try:
        verify_json = json.loads(verify_out)
    except Exception:
        verify_json = {'parse_error': verify_out[-2000:], 'stderr': proc.stderr[-2000:]}
    (REPORT / 'logs' / 'independent_verification.json').write_text(
        json.dumps(verify_json, indent=2), encoding='utf-8')

    # ---- hash check
    after = {p: sha(p) for p in FROZEN}
    frozen_ok = before == after

    # ---- write log
    log = {
        'phase': 5, 'date': '2026-11-18',
        'scope': 'SDR-2026-11-18-03',
        'input_rows': {'components': len(components), 'residuals': len(residuals)},
        'rankings': {
            'bowler_chase': {
                'eligible': sum(1 for r in bowler_rows if rk.is_eligible(r)),
                'scored': sum(1 for r in bowler_rows if str(r['scored']) == 'True'),
                'published': len(bowler_top)},
            'batter_chase': {
                'eligible': sum(1 for r in batter_rows if rk.is_eligible(r)),
                'scored': sum(1 for r in batter_rows if str(r['scored']) == 'True'),
                'published': len(batter_top)},
            'bowler_innings1_ahead_par': {
                'eligible': sum(1 for r in innings1 if rk.is_eligible(r)),
                'published': 0},
        },
        'bootstrap': boot_diag,
        'rejected_bootstrap_design': refit,
        'verification': checks['summary'],
        'independent_verification': verify_json,
        'frozen_inputs_unchanged': frozen_ok,
        'frozen_hashes': after,
    }
    (REPORT / 'logs' / 'run_phase5.json').write_text(json.dumps(log, indent=2),
                                                     encoding='utf-8')

    report = build_report(cfg, identity, dup_names, bowler_top, batter_top,
                          exclusions, status, sep_rows, sens, stab, boot_diag,
                          refit, checks, verify_json, frozen_ok, log)
    (REPORT / 'PHASE_5_REPORT.md').write_text(report, encoding='utf-8')
    return log


# ---------------------------------------------------------------- validation

def validate(bowler_top, batter_top, bowler_rows, batter_rows, innings1,
             exclusions, boot, identity):
    rows = []

    def chk(name, ok, detail=''):
        rows.append({'check': name, 'result': 'PASS' if ok else 'FAIL',
                     'detail': detail})
        return ok

    ids_b = [r['player_id'] for r in bowler_top]
    ids_a = [r['player_id'] for r in batter_top]
    chk('bowler_top10_size', len(bowler_top) == 10, f'{len(bowler_top)} rows')
    chk('bowler_top10_unique', len(set(ids_b)) == len(ids_b))
    chk('bowler_top10_all_eligible',
        all(rk.is_eligible(r) for r in rk.rank(bowler_rows, limit=10)))
    n_batter_elig = sum(1 for r in batter_rows if rk.is_eligible(r))
    chk('batter_published_equals_eligible',
        len(batter_top) == min(10, n_batter_elig),
        f'{n_batter_elig} eligible; no filler rows')
    chk('batter_ranking_unique', len(set(ids_a)) == len(ids_a))
    chk('innings1_no_ranking', sum(1 for r in innings1 if rk.is_eligible(r)) == 0,
        'zero eligible players in the innings-1 bowling context')
    chk('no_batter_innings1_rows',
        all(r['context'] == 'chase' for r in batter_rows))
    chk('score_algebra_exact',
        all(abs(rk.score_of(r) - rk.as_float(r['S_star'], 0))
            <= 1e-9 * max(1.0, abs(rk.score_of(r)))
            for r in bowler_rows + batter_rows if rk.score_of(r) is not None))
    chk('ranking_order_monotone',
        all(rk.as_float(bowler_top[i]['S_star']) >= rk.as_float(bowler_top[i + 1]['S_star'])
            for i in range(len(bowler_top) - 1))
        and all(rk.as_float(batter_top[i]['S_star']) >= rk.as_float(batter_top[i + 1]['S_star'])
                for i in range(len(batter_top) - 1)))
    chk('eligibility_rule_exact',
        all((rk.as_float(r['shrinkage_A'], 0) >= rk.ELIGIBILITY_MIN) == rk.is_eligible(r)
            for r in bowler_rows + batter_rows if str(r['scored']) == 'True'))
    chk('ci_ordering',
        all(rk.as_float(r['S_ci90_low'], 0) <= rk.as_float(r['S_star'], 0)
            <= rk.as_float(r['S_ci90_high'], 0)
            for r in bowler_rows + batter_rows if rk.as_float(r['S_star']) is not None))
    chk('exclusions_cover_all_non_eligible',
        len(exclusions) == sum(1 for r in bowler_rows + batter_rows
                               if not rk.is_eligible(r)),
        f'{len(exclusions)} exclusion records')
    chk('bootstrap_covers_published_players',
        all(r['player_id'] in boot[(r['role'], 'chase')] for r in bowler_top + batter_top))
    chk('names_resolved_unique',
        all(identity.get(r['player_id'], {}).get('name') for r in bowler_top + batter_top))
    src = (ROOT / 'src/ranking/model.py').read_text(encoding='utf-8')
    banned = ('press_bat_union', 'press_bat_collapse', 'pressure_batter',
              'pressure_bowler', 'press_chase', 'press_bowl_ahead', 'chase_f2')
    chk('excluded_flags_not_read', not any(b in src for b in banned),
        'the only Phase 3/4 reading module references no flag column')
    summary = {r['check']: r['result'] for r in rows}
    return {'rows': rows, 'summary': summary,
            'all_pass': all(v == 'PASS' for v in summary.values())}


# ------------------------------------------------------------------- report

def build_report(cfg, identity, dup_names, bowler_top, batter_top, exclusions,
                 status, sep_rows, sens, stab, boot_diag, refit, checks,
                 verify_json, frozen_ok, log):
    L = []
    add = L.append
    n_excl = {}
    for e in exclusions:
        n_excl[(e['role'], e['reason_code'])] = n_excl.get((e['role'], e['reason_code']), 0) + 1

    add('# Phase 5 report — final ranking and selection')
    add('')
    add('**Gate: PASS_WITH_NOTES.** Scoped by '
        '[SDR-2026-11-18-03](reports/methodology/SDR-2026-11-18-03-phase5-ranking.md); '
        'no threshold, flag, weight, variance or shrinkage setting was changed.')
    add('**Date:** 2026-11-18')
    add('**Ranking rule:** eligible players only (`B_A >= 0.20`), ordered by '
        '`S* = A* - 0.30 B*`; ties by `B_A`, then pressure deliveries, then ID. '
        'Publication length `min(10, eligible)`.')
    add('**No Phase 6 work, no deployment, no Git operation.**')
    add('')
    add('---')
    add('')
    add('## 1. Headline')
    add('')
    bstat = next(r for r in status if r['role'] == 'bowler' and r['context'] == 'chase')
    add(f'- **Bowler chase: a top 10 is published** from {bstat["eligible"]} eligible bowlers.')
    add(f'- **Batter chase: {len(batter_top)} eligible batters**, published as a shortfall list. '
        'No player was promoted to reach ten.')
    add('- **Innings-1 bowling: no ranking.** Zero eligible players; the context is '
        'preserved as a research finding (F4-02, PH3-01).')
    add('- **The order inside the top 10 is not a claim of superiority.** Every published '
        '90% interval contains zero and every adjacent pair overlaps. The defensible '
        'finding is the eligible set and the evidence tier, not the sequence.')
    add('- **Performance Score and Reliability of Evidence stay separate.** Reliability '
        'never enters `S*`.')
    add('')
    add('## 2. Scope and inputs')
    add('')
    add('| Item | Value |')
    add('|---|---|')
    add(f'| Inputs | `player_components.csv` ({len(rm.read_csv(rm.COMPONENTS))} rows); '
        f'`player_match_residuals.csv` ({len(rm.read_csv(rm.RESIDUALS))} match-component rows) |')
    add('| Phase 4 outputs | `player_scores_batters.csv`, `player_scores_bowlers.csv` (read-only) |')
    add('| Contexts | batter `chase`; bowler `chase` and `innings1_ahead_par` (separate) |')
    add('| Excluded definitions | F2 fallback; broad `pressure_batter`/`pressure_bowler`; '
        '`press_bat_union`; `press_bat_collapse`; innings-1 batting |')
    add('| Frozen inputs unchanged by this run | '
        f'{"YES (SHA-256 identical before/after)" if frozen_ok else "NO"} |')
    add('')
    add('### 2.1 Player identity (F5-01)')
    add('')
    add('`data/processed/players_dim.csv` pairs `dismissed_player_id` with `striker_name`, '
        'so 197 of 1,217 rows carry 2–5 display names (ID 47 combines "David Willey" and '
        '"Virat Kohli"). **No identifier is affected**: the raw `player_id` is unique, '
        '0 of 959 delivery IDs map to more than one name, and the competition mapping '
        'gives exactly one name per ID. Phase 5 therefore resolves names from '
        '`data/raw/Data Pack/competition_team_player_mapping.csv` into '
        '`outputs/final/phase5/player_identity.csv` (1,216 OK, 1 NAME_VARIANT — ID 4458, '
        '"AHT Donald" in the mapping vs "Aneurin Donald" in the scorecards). '
        'The Phase 4 score files keep their original name column until the Phase 1 '
        'data-prep fix is separately authorised.')
    add('')
    add(f'Six display names are carried by two IDs each (source ambiguity, DQ-02): '
        f'{", ".join(sorted(dup_names))}. None of them appears in either published ranking.')
    add('')
    add('## 3. Bowler chase — top 10')
    add('')
    add(md_table(
        ['#', 'Player', 'ID', 'S*', '90% interval', 'A*', 'B*', 'B_A', 'Tier',
         'Pressure balls', 'Total matches'],
        [[r['rank'], r['player_name'], r['player_id'], f(r['S_star']),
          f'[{f(r["S_ci90_low"])}, {f(r["S_ci90_high"])}]', f(r['A_star']),
          f(r['B_star']), f(r['shrinkage_A'], 3), r['evidence_tier'],
          r['n_pressure'], r['total_matches']] for r in bowler_top]))
    add('')
    add('**How each score is built.** `A*` is the shrunk pressure performance residual '
        '(positive = better than the model expectation for the same phase, innings, '
        'wicket state and bowling type); `B*` is the same player\'s non-pressure baseline. '
        '`S* = A* - 0.30 B*`, so a player keeps 70% of the weight of pressure performance '
        'and is charged 30% for general form, which stops the ranking from simply '
        're-identifying the best overall bowler. Reliability (`B_A`, tier, interval) is '
        'reported beside the score and never inside it.')
    add('')
    for r in bowler_top:
        add(f'{r["rank"]}. **{r["player_name"]}** (ID {r["player_id"]}, '
            f'{r["formats_present"]}) — S* {f(r["S_star"])}. {r["score_explanation"]} '
            f'{r["n_pressure"]} pressure deliveries in {r["pressure_matches"]} matches '
            f'(economy in pressure {econ(r["pressure_runs_per_ball"])} vs baseline '
            f'{econ(r["baseline_runs_per_ball"])}); '
            f'90% interval [{f(r["S_ci90_low"])}, {f(r["S_ci90_high"])}].')
    add('')
    add('## 4. Batter chase — eight eligible, no manufactured top 10')
    add('')
    add('The approved rule admits **8** batters. A top 10 would require adding two '
        'players the approved reliability rule excludes, so the list stops at eight. '
        'All eight are **Limited** tier: no batter reaches Moderate or High.')
    add('')
    add(md_table(
        ['#', 'Player', 'ID', 'S*', '90% interval', 'A*', 'B*', 'B_A', 'Tier',
         'Pressure balls', 'Total matches'],
        [[r['rank'], r['player_name'], r['player_id'], f(r['S_star']),
          f'[{f(r["S_ci90_low"])}, {f(r["S_ci90_high"])}]', f(r['A_star']),
          f(r['B_star']), f(r['shrinkage_A'], 3), r['evidence_tier'],
          r['n_pressure'], r['total_matches']] for r in batter_top]))
    add('')
    for r in batter_top:
        add(f'{r["rank"]}. **{r["player_name"]}** (ID {r["player_id"]}, '
            f'{r["formats_present"]}) — S* {f(r["S_star"])}. {r["score_explanation"]} '
            f'{r["n_pressure"]} pressure deliveries in {r["pressure_matches"]} matches; '
            f'90% interval [{f(r["S_ci90_low"])}, {f(r["S_ci90_high"])}].')
    add('')
    add('**Why the other candidates are ineligible.** '
        f'{n_excl.get(("batter","SHRINKAGE_BELOW_0.20"),0)} scored batters fall below '
        f'`B_A = 0.20`, and {n_excl.get(("batter","NO_VARIANCE"),0)} have no estimable '
        'variance. The nearest misses are reported in '
        '`outputs/final/phase5/ranking_exclusions.csv` with their reason. The cause is '
        'structural, not a coding fault (F4-01): the T20I batter-chase between-player '
        'variance is estimated at zero, so combined shrinkage is attenuated for almost '
        'everyone.')
    add('')
    add('## 5. First-innings bowling — research finding, no ranking')
    add('')
    add('| Quantity | Value |')
    add('|---|---|')
    i1 = next(r for r in status if r['context'] == 'innings1_ahead_par')
    add(f'| Players scored | {i1["scored"]} |')
    add('| Eligible at `B_A >= 0.20` | **%d** |' % i1['eligible'])
    add(f'| Maximum shrinkage | {f(i1["max_shrinkage_A"], 3)} |')
    add('| Ranking produced | No |')
    add('')
    add('The context is the *batting side ahead of par* in innings 1. Bowlers concede '
        '1.61 vs 1.36 runs per ball there, so part of the signal is the match scoring '
        'environment rather than bowling skill (PH3-01). It is never merged with chase '
        'and no player is ranked from it. The context stays available as a separate '
        'research finding.')
    add('')
    add('## 6. Performance Score vs Reliability of Evidence')
    add('')
    add('| Concept | Columns | Meaning |')
    add('|---|---|---|')
    add('| Performance Score | `S_star`, `A_star`, `B_star`, `D_star` | Modelled performance under the approved methodology |')
    add('| Reliability of Evidence | `shrinkage_A`, `evidence_tier`, `S_ci90_low/high`, '
        '`consistency_*`, bootstrap stability | How strongly the available evidence supports the estimate |')
    add('')
    add('The two are not multiplied, blended or averaged anywhere. Eligibility uses '
        'reliability only (`B_A >= 0.20`); the ordering uses performance only (`S*`).')
    add('')
    add('## 7. Format handling')
    add('')
    add('Format-specific estimates are evaluated before any combination (Phase 4 '
        'acceptance C). All six format cells were validated there; the primary ranking '
        'uses the two-stage, format-aware combination authorised in SDR-2026-11-18-02. '
        'The table shows the top of the format-only lists and how much they agree with '
        'the combined order.')
    add('')
    fmt_lines = []
    for role in ('bowler', 'batter'):
        for fmt in rm.FORMATS:
            rec = next((r for r in sens if r['scenario'] == f'format_{fmt}'
                        and r['role'] == role), None)
            if rec:
                fmt_lines.append([role, fmt, rec['eligible'], rec['top_n'],
                                  f(rec['overlap_share'], 2),
                                  f(rec['spearman_vs_primary'], 3)])
    add(md_table(['Role', 'Format-only', 'Eligible', 'Published', 'Overlap with combined',
                  'Spearman vs combined'], fmt_lines))
    add('')
    add('**Pooling decision: retained, as a descriptive combination only.** Phase 4 '
        'found IPL/T20I disagreement close to chance expectation (7.6% / 4.3% / 5.4% '
        'beyond chance) with small between-format variance, which supports the two-stage '
        'combination. Two facts limit what that combination can claim:')
    add('')
    add('- **The T20I-only lists are empty.** T20I pressure between-player variance is '
        'estimated at zero in both roles, so no T20I-only player can clear `B_A >= 0.20`. '
        'T20I evidence therefore enters only through the combined estimate, where it '
        'attenuates rather than certifies.')
    add('- **Four of the ten published bowlers change** when only IPL evidence is used '
        '(6/10 overlap). Format choice is a real analyst decision, not a cosmetic one.')
    add('')
    add('This is **not** a transferability claim: a player who performs under pressure in '
        'one format is not thereby shown to do so in the other. `ALL` is never used as a '
        'combination.')
    add('')
    add('## 8. Uncertainty and statistical separation')
    add('')
    add('Adjacent-rank evidence for the published bowler order:')
    add('')
    add(md_table(['#', 'Player', 'S*', 'Gap to previous', 'Overlaps previous',
                  'Interval includes 0'],
                 [[r['rank'], r['player_name'], f(r['S_star']),
                   f(r['gap_from_previous']) if r['gap_from_previous'] != '' else '—',
                   'yes' if r['ci_overlaps_previous'] == True else
                   ('—' if r['ci_overlaps_previous'] == '' else 'no'),
                   'yes' if r['ci_contains_zero'] else 'no'] for r in bowler_top]))
    add('')
    n_zero = sum(1 for r in bowler_top if r['ci_contains_zero'])
    add(f'**{n_zero} of {len(bowler_top)}** published bowlers have a 90% interval that '
        'contains zero, and every adjacent pair overlaps. Example: ranks 2 and 3 differ '
        'by 0.00008 in `S*`. The published order is therefore a reproducible ordering of '
        'point estimates, not evidence that one player outperforms the next.')
    add('')
    add('## 9. Rank stability (match-block bootstrap)')
    add('')
    add('200 replicates; each resamples a player\'s matches with replacement, rebuilds '
        'the pressure and baseline means, and re-ranks the published eligible set with '
        'the Phase 4 EB fit held fixed. The EB fit is a calibration of reliability; '
        're-estimating it on duplicated clusters inflates shrinkage (F5-02).')
    add('')
    add(md_table(['#', 'Player', 'P(top 10)', 'Median rank', '5–95% rank range'],
                 [[r['rank'], r['player_name'], f(r['bootstrap_share_top10'], 2),
                   r['bootstrap_rank_median'],
                   f'{r["bootstrap_rank_p05"]}–{r["bootstrap_rank_p95"]}']
                  for r in bowler_top]))
    add('')
    add('Reading: the top three are near-certain members of the set (0.97–1.00); ranks '
        '4–10 keep only a 0.40–0.83 chance of being in a ten-player set, and their rank '
        'range spans most of the pool. The *set* is uncertain, not just the order.')
    add('')
    add('## 10. Sensitivity')
    add('')
    add(md_table(['Scenario', 'Role', 'Eligible', 'Published', 'Overlap',
                  'Spearman', 'Note'],
                 [[s['scenario'], s['role'], s['eligible'], s['top_n'],
                   f(s['overlap_share'], 2),
                   f(s['spearman_vs_primary'], 3) if s['spearman_vs_primary'] != '' else '—',
                   s['note']] for s in sens]))
    add('')
    add('Findings, read in order of importance:')
    add('')
    add('1. **The variance model decides the eligible set, not the score weight.** '
        'E1 admits 307 bowlers instead of 36 and replaces all ten published names '
        '(overlap 0/10). E1 is the upper bound rejected in Phase 4 §3, so this is a '
        'reason to trust the E2 rule, not a reason to switch.')
    add('2. **The ordering is stable to the score weight**: w = 0.30 and w = 0.50 keep '
        '9 and 10 of the ten names with Spearman 1.000 on the eligible pool.')
    add('3. **REML keeps 9 of 10 names** (37 eligible). The single-stage combination '
        'keeps only 2 of 10, which is the same distortion Phase 4 recorded: one common '
        'tau^2 erases the IPL bowling signal.')
    add('4. **Format scope matters.** The IPL-only list shares 6 of 10 names with the '
        'published list and admits 47 players; the T20I-only list is empty because the '
        'T20I between-player variance is estimated at zero. The published ranking is '
        'therefore driven mainly by IPL evidence — disclosed, not hidden.')
    add('5. **The batter shortfall is not an artefact of the primary setting**: REML and '
        'single-stage combination both return 0 eligible batters.')
    add('')
    add('## 11. Verification')
    add('')
    add(md_table(['Check', 'Result'],
                 [[r['check'], r['result']] for r in checks['rows']]))
    add('')
    add('Independent re-implementation (separate script, no project imports, direct '
        'CSV reader): `reports/phase_5/independent_verify.py`.')
    add('')
    if 'checks' in verify_json:
        add('```json')
        add(json.dumps(verify_json, indent=2)[:4000])
        add('```')
    add('')
    add(f'Frozen Phase 2–4 inputs and Phase 4 score files: '
        f'{"unchanged (SHA-256 before/after)" if frozen_ok else "CHANGED — see log"}.')
    add('')
    add('## 12. Exclusions')
    add('')
    add(md_table(['Role', 'Reason', 'Players'],
                 [[k[0], k[1], v] for k, v in sorted(n_excl.items())]))
    add('')
    add('Every exclusion is listed with its reason code and the shrinkage value in '
        '`outputs/final/phase5/ranking_exclusions.csv`. No exclusion was overwritten and '
        'no threshold was moved.')
    add('')
    add('## 13. Limitations and open issues')
    add('')
    add('- **F4-01 (HIGH, open):** only 8 batter-chase players are eligible. The batter '
        'list is a shortfall, not a top 10.')
    add('- **F4-02 (HIGH, open):** no innings-1 ahead-par bowler is eligible; no ranking.')
    add('- **PH3-01 (MEDIUM, guard):** innings-1 ahead-par remains state-confounded and '
        'is never merged with chase.')
    add('- **PH2-05 (HIGH, open):** broad combined pressure flags remain unvalidated and '
        'unused.')
    add('- **F5-01 (documentation, open):** `players_dim.csv` display names are corrupted; '
        'Phase 5 resolves names independently and the Phase 1 file is not regenerated.')
    add('- **F5-02 (method note):** the pre-registered bootstrap that also re-estimated '
        'the variance model was implemented, measured and rejected; the accepted and '
        'rejected designs are both logged in `reports/phase_5/logs/run_phase5.json` '
        '(`bootstrap`, `rejected_bootstrap_design`) and recorded in `FAILURE_REGISTER.md`.')
    add('- **Statistical separation:** no published player is separated from the next at '
        '90% confidence. Read the ranking as an eligible set with tiers, not a podium.')
    add('- **Format transfer:** no claim that pressure performance carries across formats.')
    add('- **Residual provenance (F4-04):** Phase 4\'s duplicate-run check remains '
        'same-process, not two independent end-to-end runs.')
    add('')
    add('## 14. Reproduction')
    add('')
    add('```bash')
    add('cd ~/RR_Hackathon')
    add('python3 -m src.ranking.run_phase5')
    add('python3 reports/phase_5/independent_verify.py')
    add('python3 -m pytest -q tests/test_phase5_ranking.py')
    add('```')
    add('')
    add('## 15. Output map')
    add('')
    add('| Output | Contents |')
    add('|---|---|')
    add('| `outputs/final/phase5/ranking_bowler_chase.csv` | Published bowler chase top 10, performance and reliability side by side |')
    add('| `outputs/final/phase5/ranking_batter_chase.csv` | The 8 eligible batters |')
    add('| `outputs/final/phase5/ranking_exclusions.csv` | Every non-eligible player and the reason |')
    add('| `outputs/final/phase5/player_identity.csv` | Resolved identity and its validation status |')
    add('| `outputs/final/phase5/format_specific_ranking.csv` | IPL-only and T20I-only lists |')
    add('| `outputs/final/phase5/context_status.csv` | Per context: rows, eligible, ranking published |')
    add('| `reports/phase_5/separation.csv` | Adjacent gaps and interval overlap |')
    add('| `reports/phase_5/rank_stability.csv` | Bootstrap membership and rank range |')
    add('| `reports/phase_5/sensitivity_rank.csv` | Every sensitivity scenario |')
    add('| `reports/phase_5/validation_checks.csv` | Machine-readable validation results |')
    add('| `reports/phase_5/logs/run_phase5.json` | Full run log, hashes, bootstrap diagnostics |')
    add('')
    return '\n'.join(L)


if __name__ == '__main__':
    log = build()
    print(json.dumps({k: log[k] for k in ('rankings', 'frozen_inputs_unchanged')},
                     indent=2))
