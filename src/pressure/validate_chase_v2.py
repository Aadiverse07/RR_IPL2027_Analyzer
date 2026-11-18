"""Corrected directional validation for the shared chase flag.

Implements MDR-2026-11-18-01: a shared chase flag marks pressure on the chasing
batting side, so both batter runs and runs conceded by bowlers are expected to
be lower; batter dot rate higher; dismissal is reported as a disclosed
limitation. Reuses the existing estimator unchanged and reproduces the
superseded run's replicates exactly (same seed offsets), so the before/after
difference is attributable to the rule alone.

Validation only. Reads config, never writes flags or thresholds.
"""
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
import yaml

from .validate import clustered_bootstrap, read_rows, write_rows, ROOT, PRESS

OUT = ROOT / 'reports/phase_2/validation_v2'
CFG = ROOT / 'config/methodology.yaml'
OLD_VALIDATION = ROOT / 'reports/phase_2/difficulty_validation.csv'
SNAPSHOT = ROOT / 'reports/phase_2/revisions/2026-11-18_pre_chase_direction_v2/reports/difficulty_validation.csv'

# The superseded run passed seed_offset 2 (batter) and 3 (bowler) for press_chase.
# Reusing them keeps the bootstrap draws identical; only the rule differs.
ROLE_SPEC = [('batter', 2), ('bowler', 3)]
FLAG = 'press_chase'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def rule_from_config(cfg):
    rule = cfg['validation']['chase_direction_rule']
    return {
        'version': str(rule['version']),
        'decision_record': rule['decision_record'],
        'expected': dict(rule['expected_direction']),
        'mandatory': set(rule['mandatory_metrics']),
        'consistent': set(rule['directionally_consistent_metrics']),
        'reported': set(rule.get('disclosed_limitation_metrics', [])),
        'min_flagged': int(rule['reversed_cell_min_flagged']),
    }


def metric_key(role, metric):
    return f'{role}_{metric}'


def classify(direction, diff, lo, hi):
    if direction == 'lower':
        if hi < 0:
            return 'PASS'
        return 'FAIL' if lo > 0 else 'INCONCLUSIVE'
    if direction == 'higher':
        if lo > 0:
            return 'PASS'
        return 'FAIL' if hi < 0 else 'INCONCLUSIVE'
    return 'REPORTED'


def classify_directionally_consistent(direction, diff, lo, hi):
    """Apply the point-estimate direction rule separately from its CI check.

    MDR-2026-11-18-01 requires the batter-dot point estimate to be >= 0 and
    separately forbids a significantly reversed confidence interval. Equality
    is allowed. Preserve the ordinary confidence-interval classification when
    the point estimate meets the directional condition.
    """
    if direction == 'higher' and diff < 0:
        return 'FAIL'
    return classify(direction, diff, lo, hi)


def is_reversed(direction, lo, hi):
    return (direction == 'lower' and lo > 0) or (direction == 'higher' and hi < 0)


def evaluate(rule, rows):
    out = []
    for r in rows:
        expected = rule['expected'].get(metric_key(r['role'], r['outcome_metric']))
        direction = expected or 'reported'
        diff, lo, hi = float(r['difference']), float(r['ci_low']), float(r['ci_high'])
        key = metric_key(r['role'], r['outcome_metric'])
        if key in rule['consistent']:
            # The approved rule requires both a nonnegative point estimate
            # and no significant reverse CI; do not collapse these conditions.
            status = classify_directionally_consistent(direction, diff, lo, hi)
        else:
            status = classify(direction, diff, lo, hi)
        gated = key in rule['mandatory'] or key in rule['consistent']
        row = dict(r)
        row.update({
            'rule_version': rule['version'],
            'metric_key': key,
            'expected_direction': direction,
            'gated': str(gated).lower(),
            'metric_status': status,
            'significant_reversed_direction': str(is_reversed(direction, lo, hi)).lower(),
        })
        out.append(row)
    return out


def summarise(rule, rows):
    pooled = [r for r in rows if r['group_level'] == 'pooled_wickets_stratified']
    cells = [r for r in rows if r['group_level'] == 'phase_wickets_format']
    gating_cells = [c for c in cells if c['gated'] == 'true' and int(c['n_flagged']) >= rule['min_flagged']]
    blockers = [c for c in gating_cells if c['significant_reversed_direction'] == 'true']

    pooled_by_metric = {r['metric_key']: r for r in pooled}
    mandatory_failures, mandatory_inconclusive = [], []
    for key in sorted(rule['mandatory']):
        r = pooled_by_metric.get(key)
        if r is None:
            mandatory_inconclusive.append({'metric': key, 'reason': 'missing'})
        elif r['metric_status'] == 'FAIL':
            mandatory_failures.append(key)
        elif r['metric_status'] != 'PASS':
            mandatory_inconclusive.append({'metric': key, 'reason': r['metric_status']})

    consistent_failures = [k for k in sorted(rule['consistent'])
                           if k in pooled_by_metric and pooled_by_metric[k]['metric_status'] == 'FAIL']

    if mandatory_failures or consistent_failures or blockers:
        verdict = 'FAIL'
    elif mandatory_inconclusive:
        verdict = 'INCONCLUSIVE'
    else:
        verdict = 'PASS_WITH_DISCLOSED_LIMITATION'

    return {
        'rule_version': rule['version'],
        'decision_record': rule['decision_record'],
        'definition': FLAG,
        'verdict': verdict,
        'mandatory_metrics': {
            k: {f: pooled_by_metric[k][f] for f in
                ('difference', 'ci_low', 'ci_high', 'n_flagged', 'n_ordinary')}
            | {'status': pooled_by_metric[k]['metric_status']}
            for k in sorted(rule['mandatory']) if k in pooled_by_metric
        },
        'directionally_consistent_metrics': {
            k: {f: pooled_by_metric[k][f] for f in
                ('difference', 'ci_low', 'ci_high', 'n_flagged', 'n_ordinary')}
            | {'status': pooled_by_metric[k]['metric_status']}
            for k in sorted(rule['consistent']) if k in pooled_by_metric
        },
        'reported_metrics': {
            k: {f: pooled_by_metric[k][f] for f in
                ('difference', 'ci_low', 'ci_high', 'n_flagged', 'n_ordinary')}
            | {'status': pooled_by_metric[k]['metric_status']}
            for k in sorted(pooled_by_metric) if k not in rule['mandatory'] | rule['consistent']
        },
        'mandatory_failures': mandatory_failures,
        'mandatory_inconclusive': mandatory_inconclusive,
        'directionally_consistent_failures': consistent_failures,
        'cells_ge_min_flagged_gated': len(gating_cells),
        'reversed_gating_cells': [{k: c[k] for k in
            ('role', 'phase', 'wickets_state', 'format', 'outcome_metric',
             'n_flagged', 'difference', 'ci_low', 'ci_high')} for c in blockers],
        'disclosed_limitation': {
            'metric': 'batter dismissal',
            'status': pooled_by_metric['batter_dismissal']['metric_status'],
            'note': 'Dismissal is reported, not gated (owner-approved limitation, MDR-2026-11-18-01 §2.3).',
        },
        'inconclusive_is_pass': False,
    }


def estimates_match(rows, old_rows):
    key = lambda r: (r['definition'], r['role'], r['group_level'], r['phase'],
                     str(r['wickets_state']), r['format'], r['outcome_metric'])
    old = {key(r): r for r in old_rows if r['definition'] == FLAG}
    if len(old) != len(rows):
        return {'match': False, 'reason': f'row count {len(old)} vs {len(rows)}'}
    worst = 0.0
    for r in rows:
        o = old.get(key(r))
        if o is None:
            return {'match': False, 'reason': f'missing old row {key(r)}'}
        for f in ('difference', 'ci_low', 'ci_high'):
            worst = max(worst, abs(float(r[f]) - float(o[f])))
    return {'match': worst < 1e-12, 'max_abs_estimate_delta': worst,
            'rows_compared': len(rows)}


def before_after(rule, new_rows, old_rows):
    key = lambda r: (r['role'], r['outcome_metric'], r['group_level'])
    old = {key(r): r for r in old_rows if r['definition'] == FLAG}
    out = []
    for r in new_rows:
        o = old.get(key(r))
        if o is None:
            continue
        out.append({
            'role': r['role'], 'outcome_metric': r['outcome_metric'],
            'group_level': r['group_level'], 'n_flagged': r['n_flagged'],
            'difference': r['difference'], 'ci_low': r['ci_low'], 'ci_high': r['ci_high'],
            'superseded_expected_direction': o['expected_direction'],
            'superseded_status': o['direction_check'],
            'corrected_expected_direction': r['expected_direction'],
            'corrected_status': r['metric_status'],
            'status_changed': str(o['direction_check'] != r['metric_status']).lower(),
        })
    return out


def write_before_after_md(summary, cmp_rows, old_reversed, new_reversed, rule):
    pooled = [r for r in cmp_rows if r['group_level'] == 'pooled_wickets_stratified']
    lines = [
        '# Chase validation — before / after rule correction',
        '',
        f'Rule version **{rule["version"]}** (`{rule["decision_record"]}`).',
        f'Definition: `{FLAG}` (original calibrated model, unchanged). Bootstrap draws identical: '
        'seed offsets 2 (batter) and 3 (bowler) reused from the superseded run.',
        '',
        '## Pooled contrasts',
        '',
        '| Role | Metric | n flagged | Estimate | 95% CI | Superseded rule | Corrected rule |',
        '|---|---|---:|---:|---|---|---|',
    ]
    for r in pooled:
        lines.append(
            f"| {r['role']} | {r['outcome_metric']} | {int(float(r['n_flagged'])):,} | "
            f"{float(r['difference']):+.5f} | [{float(r['ci_low']):+.5f}, {float(r['ci_high']):+.5f}] | "
            f"{r['superseded_expected_direction']} → {r['superseded_status']} | "
            f"{r['corrected_expected_direction']} → **{r['corrected_status']}** |")
    lines += [
        '',
        '## Subgroup reversals (≥500 flagged deliveries, gating metrics)',
        '',
        f'- Superseded rule: **{len(old_reversed)}** reversed cells.',
        f'- Corrected rule: **{len(new_reversed)}** reversed cells.',
        '',
        'The corrected verdict follows MDR-2026-11-18-01 §2.3: mandatory runs must be conclusive, '
        'batter dot must be directionally consistent without a significant reversal, and an '
        'inconclusive dismissal result is a disclosed limitation.',
        '',
        f'**Verdict: {summary["verdict"]}**',
    ]
    (OUT / 'BEFORE_AFTER.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def true_counts():
    """Actual flagged/ordinary delivery counts per role (legacy pooled rows summed
    the same counts once per metric, inflating n by 3; cell rows were correct)."""
    out = {}
    data = read_rows(PRESS)
    for role in ('batter', 'bowler'):
        nf = no = 0
        for r in data:
            if r['innings'] != '2' or r['chase_pressure_status'] != 'ELIGIBLE':
                continue
            if role == 'batter' and r['faced'].strip().lower() != 'true':
                continue
            if r.get(FLAG, '') == '':
                continue
            if r[FLAG].strip().lower() == 'true':
                nf += 1
            else:
                no += 1
        out[role] = (nf, no)
    return out


def build():
    cfg = yaml.safe_load(CFG.read_text(encoding='utf-8'))
    rule = rule_from_config(cfg)
    data = read_rows(PRESS)
    rows = []
    for role, offset in ROLE_SPEC:
        book_rows, book_summary = clustered_bootstrap(data, FLAG, role, False,
                                                      ['runs', 'dot', 'dismissal'], cfg, offset)
        rows.extend(evaluate(rule, book_rows))
    rows.sort(key=lambda r: (r['role'], r['outcome_metric'], r['group_level'], r['phase'],
                             str(r['wickets_state']), r['format']))
    # Legacy pooled rows summed flagged/ordinary counts once per metric (3x). Replace
    # with true delivery counts for this rule run; cell rows already use per-metric counts.
    counts = true_counts()
    legacy_counts = {}
    for r in rows:
        if r['group_level'] != 'pooled_wickets_stratified':
            continue
        nf, no = counts[r['role']]
        reported = int(float(r['n_flagged']))
        legacy_counts[r['role']] = {'legacy_reported_n_flagged': reported,
                                    'actual_flagged_deliveries': nf,
                                    'legacy_inflation_factor': round(reported / nf, 3) if nf else None}
        r['n_flagged'] = str(nf)
        r['n_ordinary'] = str(no)
    OUT.mkdir(parents=True, exist_ok=True)
    write_rows(OUT / 'chase_validation_v2.csv', rows)

    summary = summarise(rule, rows)
    summary['sample_size_counts'] = {
        'note': 'Pooled n_flagged/n_ordinary are true per-role delivery counts. The superseded '
                'validation table summed the same counts once per metric (3x); cell-level '
                'counts were always per-metric and are unchanged. See FAILURE_REGISTER F2-13.',
        'per_role': legacy_counts,
    }
    old_rows = read_rows(OLD_VALIDATION)
    summary['estimator_unchanged'] = estimates_match(rows, old_rows)
    summary['sources'] = {
        'data': {'path': str(PRESS.relative_to(ROOT)), 'sha256': sha256(PRESS)},
        'config': {'path': str(CFG.relative_to(ROOT)), 'sha256': sha256(CFG)},
        'superseded_validation': {'path': str(OLD_VALIDATION.relative_to(ROOT)),
                                  'sha256': sha256(OLD_VALIDATION)},
    }
    (OUT / 'chase_validation_v2_summary.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')

    matrix = []
    for r in rows:
        if r['group_level'] != 'pooled_wickets_stratified':
            continue
        matrix.append({'metric_key': r['metric_key'], 'role': r['role'],
                       'metric': r['outcome_metric'], 'expected': r['expected_direction'],
                       'estimate': r['difference'], 'ci_low': r['ci_low'], 'ci_high': r['ci_high'],
                       'n_flagged': r['n_flagged'], 'status': r['metric_status'],
                       'gated': r['gated']})
    write_rows(OUT / 'pass_fail_matrix.csv', matrix)

    cmp_rows = before_after(rule, rows, old_rows)
    write_rows(OUT / 'before_after_comparison.csv', cmp_rows)
    old_rev = [r for r in old_rows
               if r['definition'] == FLAG and r['group_level'] == 'phase_wickets_format'
               and int(r['n_flagged']) >= rule['min_flagged']
               and r['significant_reversed_direction'].lower() in ('true', '1')]
    new_rev = summary['reversed_gating_cells']
    write_before_after_md(summary, cmp_rows, old_rev, new_rev, rule)

    log = {'flag': FLAG, 'rule_version': rule['version'], 'rows_written': len(rows),
           'cells_written': sum(1 for r in rows if r['group_level'] == 'phase_wickets_format'),
           'verdict': summary['verdict'],
           'superseded_reversed_cells': len(old_rev), 'corrected_reversed_cells': len(new_rev),
           'estimator_unchanged': summary['estimator_unchanged'],
           'sources': summary['sources']}
    (OUT / 'logs').mkdir(parents=True, exist_ok=True)
    (OUT / 'logs/run_validate_chase_v2.json').write_text(json.dumps(log, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == '__main__':
    build()
