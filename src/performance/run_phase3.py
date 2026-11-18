"""Phase 3 driver: build components, league means, descriptives and sensitivity.

Scope: SDR-2026-11-18-01. Uses only validated component flags.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from . import model

ROOT = model.ROOT
REPORT = ROOT / 'reports/phase_3'
DATA = ROOT / 'data/processed'
CFG_PATH = ROOT / 'config/methodology.yaml'


def write_rows(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def fmt(v, digits=5):
    return f'{v:+.{digits}f}'


def league_means(components):
    out = []
    for role in ('batter', 'bowler'):
        for context in ('chase', 'innings1_ahead_par'):
            for scope in ('IPL', 'T20I', 'ALL'):
                sub = [c for c in components if c['role'] == role
                       and c['context'] == context and c['format'] == scope]
                if not sub:
                    continue
                n_players = len(sub)
                total_p = sum(c['n_pressure'] for c in sub)
                out.append({
                    'role': role, 'context': context, 'format': scope,
                    'n_players': n_players,
                    'n_pressure_deliveries': int(total_p),
                    'n_baseline_deliveries': int(sum(c['n_baseline'] for c in sub)),
                    'player_mean_A': sum(c['A'] for c in sub) / n_players,
                    'player_mean_B': sum(c['B'] for c in sub) / n_players,
                    'player_mean_D': sum(c['D'] for c in sub) / n_players,
                    'player_mean_S_raw': sum(c['S_raw'] for c in sub) / n_players,
                    'delivery_weighted_A': sum(c['A'] * c['n_pressure'] for c in sub) / total_p,
                    'delivery_weighted_B': sum(c['B'] * c['n_baseline'] for c in sub)
                    / sum(c['n_baseline'] for c in sub),
                })
    return out


def mu_report(models, usage, obs_counts, full_cell_counts):
    lines = [
        '# Context expectations (mu) — fit and cell counts',
        '',
        'Context expectations are estimated from **all** primary deliveries in each',
        'context, without the pressure flag, then used for every delivery regardless of',
        'flag value. Sparse cells back off along a fixed hierarchy; a level is used only',
        f'if it holds at least **{model.MIN_CELL}** observations for that role.',
        '',
    ]
    for role in ('batter', 'bowler'):
        m = models[role]
        lines += [f'## {role}', '',
                  f'- Observations modelled: **{obs_counts[role]:,}**',
                  f'- Full-context cells: **{full_cell_counts[role]:,}**',
                  f'- Cells meeting the {model.MIN_CELL}-observation minimum at the full level: '
                  f'**{sum(1 for rec in m.tables[0].values() if rec[0] >= model.MIN_CELL):,}**',
                  '',
                  '| Back-off level | Deliveries | Share |', '|---|---:|---:|']
        total = usage[role]['total'] or 1
        for level, n in usage[role]['by_level'].items():
            lines.append(f"| `{level}` | {n:,} | {100 * n / total:.1f}% |")
        lines.append('')
    lines += ['## Hierarchy', '',
              'Batter: ' + ' → '.join(f'`{l}`' for l in model.BATTER_CHAIN), '',
              'Bowler: ' + ' → '.join(f'`{l}`' for l in model.BOWLER_CHAIN), '',
              '`wbin` caps wickets lost at 3 (0, 1, 2, 3+). `order` is the source',
              'batting-order group, `bowl_kind` is pace/spin, `hand` is the batter hand.', '']
    (REPORT / 'mu_fit.md').write_text('\n'.join(lines), encoding='utf-8')


def sensitivity(rows, lam_map, primary_components):
    variants = []
    base = {(c['player_id'], c['role'], c['context']): c['S_raw']
            for c in primary_components if c['format'] == 'ALL'}
    base_n = {(c['player_id'], c['role'], c['context']): c['n_pressure']
              for c in primary_components if c['format'] == 'ALL'}

    def compare(name, components):
        got = {(c['player_id'], c['role'], c['context']): c['S_raw']
               for c in components if c['format'] == 'ALL'}
        for role in ('batter', 'bowler'):
            for context in ('chase', 'innings1_ahead_par'):
                keys = [k for k in got if k[1] == role and k[2] == context
                        and base_n.get(k, 0) >= 50]
                if len(keys) < 3:
                    variants.append({'variant': name, 'role': role, 'context': context,
                                     'n_players': len(keys), 'spearman_vs_primary': None,
                                     'mean_abs_delta_S': None, 'max_abs_delta_S': None})
                    continue
                rho = model.spearman([base[k] for k in keys], [got[k] for k in keys])
                deltas = [abs(got[k] - base[k]) for k in keys]
                variants.append({'variant': name, 'role': role, 'context': context,
                                 'n_players': len(keys), 'spearman_vs_primary': rho,
                                 'mean_abs_delta_S': sum(deltas) / len(deltas),
                                 'max_abs_delta_S': max(deltas)})

    for mult in (0.0, 0.5, 1.5):
        alt = {p: {'value': v['value'] * mult, 'status': f'LAMBDA_MULT_{mult}'}
               for p, v in lam_map.items()}
        recs, _, _ = model.build_deliveries(rows, alt)
        compare(f'lambda_multiplier_{mult}', model.aggregate_components(recs))

    no_runout, _, _ = model.build_deliveries(rows, lam_map, include_runouts=False)
    compare('drop_nonstriker_runouts', model.aggregate_components(no_runout))

    oof_recs = []
    for fold in range(5):
        train = [r for r in rows if model.fold_of(r['match_id']) != fold]
        test = [r for r in rows if model.fold_of(r['match_id']) == fold]
        recs, _, _ = model.build_deliveries(test, lam_map, mu_fit_rows=train)
        oof_recs.extend(recs)
    compare('mu_out_of_fold', model.aggregate_components(oof_recs))
    return variants


def build():
    cfg = yaml.safe_load(CFG_PATH.read_text(encoding='utf-8'))
    perf = cfg['performance']
    assert perf['context_min_cell'] == model.MIN_CELL, 'config/code min_cell mismatch'
    assert perf['wicket_bin_cap'] == model.WICKET_CAP, 'config/code wicket cap mismatch'
    assert abs(perf['score_weights']['A'] - model.SCORE_W['A']) < 1e-12
    assert abs(perf['score_weights']['D'] - model.SCORE_W['D']) < 1e-12

    rows = model.read_balls()
    lam_estimates = model.estimate_lambda(rows)
    lam_map = model.primary_lambda(lam_estimates)
    write_rows(REPORT / 'lambda_estimates.csv', lam_estimates)

    records, models, usage = model.build_deliveries(rows, lam_map)

    components = model.aggregate_components(records)
    write_rows(DATA / 'player_components.csv', components)
    write_rows(DATA / 'player_match_residuals.csv', model.match_residual_sums(records))
    desc = model.descriptive_rows(records)
    write_rows(DATA / 'player_descriptives.csv', desc)
    write_rows(REPORT / 'descriptive_stats.csv', desc)

    means = league_means(components)
    write_rows(REPORT / 'league_means.csv', means)

    obs_counts = {role: len(model.mu_observations(rows, role)) for role in ('batter', 'bowler')}
    full_cells = {role: len(models[role].tables[0]) for role in ('batter', 'bowler')}
    mu_report(models, usage, obs_counts, full_cells)

    sens = sensitivity(rows, lam_map, components)
    write_rows(REPORT / 'sensitivity_lambda_mu.csv', sens)

    scope_counts = Counter((r['role'], r['context'], 'pressure' if r['pressure'] else 'baseline')
                           for r in records)
    runouts = [r for r in rows if str(r['is_wicket']).lower() == 'true'
               and r['dismissed_batter_id'] and r['dismissed_batter_id'] != r['striker_id']]
    runout_chase = sum(1 for r in runouts if r['innings'] == '2'
                       and r['chase_pressure_status'] == 'ELIGIBLE')
    odd_ids = sum(1 for r in rows if r['dismissed_batter_id']
                  and r['dismissed_batter_id'] != r['striker_id']
                  and str(r['is_wicket']).lower() != 'true')
    log = {
        'phase': 3,
        'scope_decision': perf['scope_decision'],
        'model_version': perf['version'],
        'deliveries_read': len(rows),
        'component_rows': len(components),
        'component_players': {role: len({c['player_id'] for c in components if c['role'] == role})
                              for role in ('batter', 'bowler')},
        'scope_counts': {f'{k[0]}|{k[1]}|{k[2]}': v for k, v in sorted(scope_counts.items())},
        'non_striker_runouts': {'total': len(runouts), 'chase_eligible': runout_chase,
                                'dismissed_id_without_wicket_ignored': odd_ids},
        'lambda_primary': lam_map,
        'lambda_estimates': lam_estimates,
        'mu_level_usage': usage,
        'mu_observations': obs_counts,
        'mu_full_cells': full_cells,
        'min_cell': model.MIN_CELL,
        'warn': [],
    }
    if any(v['status'].startswith('PROVISIONAL') for v in lam_map.values()):
        log['warn'].append('lambda unstable: PROVISIONAL-FALLBACK lambda=0 used as primary')
    (REPORT / 'logs').mkdir(parents=True, exist_ok=True)
    (REPORT / 'logs/run_phase3.json').write_text(json.dumps(log, indent=2) + '\n')
    print(json.dumps({k: log[k] for k in ('deliveries_read', 'component_rows',
                                          'component_players', 'lambda_primary')},
                     indent=2))
    return log


if __name__ == '__main__':
    build()
