"""Phase 3 performance and baseline modelling.

Core logic only, no report writing: context expectations mu, wicket value lambda,
per-delivery residuals, and the A / B / D / S_raw components.

Scope is fixed by SDR-2026-11-18-01: validated component flags only
(`press_chase` on innings 2, `press_bowl_ahead` on eligible innings 1 for
bowlers). Broad combined pressure flags are never read here.
"""
from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PRESS = ROOT / 'data/processed/balls_pressure.csv'

MIN_CELL = 200
WICKET_CAP = 3
SCORE_W = {'A': 0.70, 'D': 0.30}

METRICS = {'batter': ('runs', 'dis'), 'bowler': ('charged', 'wk')}

BATTER_CHAIN = [
    ('format', 'innings', 'phase', 'wbin', 'order', 'bowl_kind'),
    ('format', 'innings', 'phase', 'wbin', 'bowl_kind'),
    ('format', 'innings', 'phase', 'wbin'),
    ('format', 'innings', 'phase'),
    ('innings', 'phase'),
    ('phase',),
    (),
]
BOWLER_CHAIN = [
    ('format', 'innings', 'phase', 'wbin', 'hand'),
    ('format', 'innings', 'phase', 'wbin'),
    ('format', 'innings', 'phase'),
    ('innings', 'phase'),
    ('phase',),
    (),
]

FIELDS = ('match_id', 'innings', 'striker_id', 'non_striker_id', 'bowler_id',
          'batting_type', 'pace_or_spin', 'batting_order_group', 'format', 'phase',
          'wickets_lost_before', 'legal_balls_remaining', 'team_runs_before', 'runs', 'extras1_runs',
          'extras_2_runs', 'bowler_charged_runs', 'faced', 'dismissed_batter_id',
          'bowler_credit_wicket', 'par_eligible', 'press_chase', 'press_bowl_ahead',
          'chase_pressure_status', 'is_wicket', 'dismissal_type', 'is_four', 'is_six')


def yes(v):
    return str(v).strip().lower() == 'true'


def wbin(wickets):
    return min(int(wickets), WICKET_CAP)


def read_balls(path=PRESS):
    out = []
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            out.append({k: r[k] for k in FIELDS})
    return out


def row_context(row, role):
    """Validated pressure context for a delivery, or None if outside scope."""
    if row['innings'] == '2' and row['chase_pressure_status'] == 'ELIGIBLE':
        return 'chase'
    if (role == 'bowler' and row['innings'] == '1'
            and yes(row['par_eligible']) and row['press_bowl_ahead'] != ''):
        return 'innings1_ahead_par'
    return None


def row_flag(row, context):
    if context == 'chase':
        return yes(row['press_chase'])
    if context == 'innings1_ahead_par':
        return yes(row['press_bowl_ahead'])
    return None


def _levels(chain, row):
    base = {
        'format': row['format'],
        'innings': row['innings'],
        'phase': row['phase'],
        'wbin': wbin(row['wickets_lost_before']),
        'order': row['batting_order_group'],
        'bowl_kind': row['pace_or_spin'],
        'hand': row['batting_type'],
    }
    return [tuple(base[f] for f in level) for level in chain]


def mu_observations(rows, role, include_runouts=True):
    """Context-expectation observations for one role.

    Batters: one observation per ball faced, keyed to the striker. A non-striker
    run-out adds a dismissal-only observation for the dismissed batter (no ball
    faced) unless `include_runouts` is False.
    Bowlers: one observation per delivery, including wides and no-balls.
    """
    chain = BATTER_CHAIN if role == 'batter' else BOWLER_CHAIN
    out = []
    for r in rows:
        if role == 'batter':
            if yes(r['faced']):
                out.append({'levels': _levels(chain, r), 'player_id': r['striker_id'],
                            'match_id': r['match_id'], 'format': r['format'],
                            'phase': r['phase'], 'row': r,
                            'runs': float(r['runs']),
                            'dis': float(r['dismissed_batter_id'] == r['striker_id']),
                            'faced_obs': True})
            if include_runouts and yes(r['is_wicket']) and r['dismissed_batter_id'] \
                    and r['dismissed_batter_id'] != r['striker_id']:
                out.append({'levels': _levels(chain, r),
                            'player_id': r['dismissed_batter_id'],
                            'match_id': r['match_id'], 'format': r['format'],
                            'phase': r['phase'], 'row': r,
                            'runs': 0.0, 'dis': 1.0, 'faced_obs': False})
        else:
            out.append({'levels': _levels(chain, r), 'player_id': r['bowler_id'],
                        'match_id': r['match_id'], 'format': r['format'],
                        'phase': r['phase'], 'row': r,
                        'charged': float(r['bowler_charged_runs']),
                        'wk': float(r['bowler_credit_wicket']),
                        'faced_obs': True})
    return out


class MuModel:
    """Smoothed cell expectations with a documented back-off hierarchy."""

    def __init__(self, role, min_cell=MIN_CELL):
        self.role = role
        self.min_cell = min_cell
        self.metrics = METRICS[role]
        self.chain = BATTER_CHAIN if role == 'batter' else BOWLER_CHAIN
        self.tables = []

    def fit(self, observations):
        self.tables = [defaultdict(lambda: [0, {m: 0.0 for m in self.metrics}])
                       for _ in self.chain]
        for o in observations:
            for li, key in enumerate(o['levels']):
                rec = self.tables[li][key]
                rec[0] += 1
                for m in self.metrics:
                    rec[1][m] += o[m]
        return self

    def predict(self, levels):
        for li, key in enumerate(levels):
            rec = self.tables[li].get(key)
            if rec is not None and rec[0] >= self.min_cell:
                return {m: rec[1][m] / rec[0] for m in self.metrics}, li
        raise RuntimeError('no usable context level; global level must exist')

    def level_usage(self, observations):
        used = defaultdict(int)
        total = 0
        for o in observations:
            _, li = self.predict(o['levels'])
            used[li] += 1
            total += 1
        return {'total': total,
                'by_level': {self.chain[li]: used.get(li, 0) for li in range(len(self.chain))}}


# --------------------------------------------------------------------------- lambda

def _cluster_ols(X, y, groups):
    XtX = X.T @ X
    bread = np.linalg.pinv(XtX)
    beta = bread @ (X.T @ y)
    resid = y - X @ beta
    uniq = {g: i for i, g in enumerate(sorted(set(groups)))}
    gi = np.array([uniq[g] for g in groups])
    scores = np.zeros((len(uniq), X.shape[1]))
    np.add.at(scores, gi, X * resid[:, None])
    meat = scores.T @ scores
    n, k = X.shape
    g = len(uniq)
    cov = bread @ meat @ bread * (g / (g - 1)) * ((n - 1) / (n - k))
    return beta, np.sqrt(np.diag(cov)), g


def lambda_records(rows):
    totals = defaultdict(float)
    key = lambda r: (r['match_id'], r['innings'])
    for r in rows:
        totals[key(r)] += float(r['runs']) + float(r['extras1_runs']) + float(r['extras_2_runs'])
    out = []
    for r in rows:
        out.append({'match_id': r['match_id'], 'format': r['format'],
                    'phase': r['phase'],
                    'innings2': 1.0 if r['innings'] == '2' else 0.0,
                    'wickets': float(r['wickets_lost_before']),
                    'balls_remaining': float(r['legal_balls_remaining']),
                    'remaining': totals[key(r)] - float(r['team_runs_before'])})
    return out


def _fit_lambda(recs):
    w = np.array([x['wickets'] for x in recs])
    b = np.array([x['balls_remaining'] for x in recs])
    X = np.column_stack([np.ones(len(recs)), w, b, b ** 2,
                         np.array([x['innings2'] for x in recs])])
    y = np.array([x['remaining'] for x in recs])
    beta, se, g = _cluster_ols(X, y, [x['match_id'] for x in recs])
    lam, lam_se = -beta[1], se[1]
    return {'lambda': float(lam), 'se': float(lam_se),
            'ci_low': float(lam - 1.96 * lam_se),
            'ci_high': float(lam + 1.96 * lam_se),
            'n_deliveries': len(recs), 'n_matches': g}


def estimate_lambda(rows):
    """Wicket value per phase, in runs.

    Per phase and format, and pooled across formats within phase, regress
    remaining-innings runs on wickets lost, controlling for legal balls
    remaining (linear and quadratic) and innings, with match-clustered SEs.
    """
    recs = lambda_records(rows)
    out = []
    for phase in ('powerplay_overs', 'middle_overs', 'death_overs'):
        for scope in ('IPL', 'T20I', 'ALL'):
            sub = [x for x in recs if x['phase'] == phase
                   and (scope == 'ALL' or x['format'] == scope)]
            row = {'phase': phase, 'scope': scope, **_fit_lambda(sub)}
            out.append(row)
    by = {(r['phase'], r['scope']): r for r in out}
    for phase in ('powerplay_overs', 'middle_overs', 'death_overs'):
        pooled = by[(phase, 'ALL')]
        per_format = [by[(phase, f)] for f in ('IPL', 'T20I')]
        stable = pooled['ci_low'] > 0 and all(f['ci_low'] > 0 for f in per_format)
        sign_flip = any(f['ci_low'] <= 0 for f in per_format)
        for r in [pooled] + per_format:
            r['phase_stable'] = stable
            r['format_ci_spans_zero'] = sign_flip
    return out


def primary_lambda(estimates):
    """Primary lambda map with PROVISIONAL-FALLBACK when estimation is unstable."""
    out = {}
    for phase in ('powerplay_overs', 'middle_overs', 'death_overs'):
        rows = [r for r in estimates if r['phase'] == phase]
        pooled = next(r for r in rows if r['scope'] == 'ALL')
        if pooled['phase_stable']:
            out[phase] = {'value': pooled['lambda'], 'status': 'ESTIMATED'}
        else:
            out[phase] = {'value': 0.0,
                          'status': 'PROVISIONAL-FALLBACK:lambda=0',
                          'estimated_value': pooled['lambda']}
    return out


# --------------------------------------------------------------------- components

def build_deliveries(rows, lam_map, mu_fit_rows=None, include_runouts=True):
    """Per-delivery residual records for both roles, restricted to validated contexts."""
    fit_rows = rows if mu_fit_rows is None else mu_fit_rows
    fit_obs = {role: mu_observations(fit_rows, role, include_runouts)
               for role in ('batter', 'bowler')}
    models = {role: MuModel(role).fit(fit_obs[role]) for role in ('batter', 'bowler')}
    records = []
    usage = {}
    for role in ('batter', 'bowler'):
        obs = fit_obs[role] if mu_fit_rows is None else mu_observations(rows, role, include_runouts)
        used = defaultdict(int)
        for o in obs:
            context = row_context(o['row'], role)
            if context is None:
                continue
            flag = row_flag(o['row'], context)
            if flag is None:
                continue
            mu, level = models[role].predict(o['levels'])
            used[level] += 1
            lam = lam_map[o['phase']]['value']
            if role == 'batter':
                y = (o['runs'] - mu['runs']) - lam * (o['dis'] - mu['dis'])
            else:
                y = -(o['charged'] - mu['charged']) + lam * (o['wk'] - mu['wk'])
            records.append({'player_id': o['player_id'], 'role': role,
                            'context': context, 'format': o['format'],
                            'match_id': o['match_id'], 'pressure': flag,
                            'phase': o['phase'], 'y': y,
                            'faced_obs': o['faced_obs'], 'row': o['row']})
        usage[role] = {'total': sum(used.values()),
                       'by_level': {str(models[role].chain[k]): used.get(k, 0)
                                    for k in range(len(models[role].chain))}}
    return records, models, usage


def _stats(vals):
    n = len(vals)
    s = math.fsum(vals)
    return n, s, math.fsum(v * v for v in vals)


def aggregate_components(records, formats=('IPL', 'T20I')):
    """A, B, D, S_raw per player x role x context x format, plus pooled format=ALL."""
    groups = defaultdict(lambda: {'p': [], 'b': [], 'pm': set(), 'bm': set()})
    for r in records:
        key = (r['player_id'], r['role'], r['context'], r['format'])
        g = groups[key]
        side = 'p' if r['pressure'] else 'b'
        g[side].append(r['y'])
        g['pm' if r['pressure'] else 'bm'].add(r['match_id'])
    rows = []
    base_keys = {(p, r, c) for (p, r, c, _f) in groups}
    for player, role, context in sorted(base_keys):
        for scope in list(formats) + ['ALL']:
            if scope == 'ALL':
                members = [groups[k] for k in
                           [(player, role, context, f) for f in formats] if k in groups]
            else:
                key = (player, role, context, scope)
                members = [groups[key]] if key in groups else []
            if not members:
                continue
            p = [v for m in members for v in m['p']]
            b = [v for m in members for v in m['b']]
            if not p or not b:
                continue
            np_, sp, _ = _stats(p)
            nb, sb, _ = _stats(b)
            A, B = sp / np_, sb / nb
            D = A - B
            S = SCORE_W['A'] * A + SCORE_W['D'] * D
            rows.append({
                'player_id': player, 'role': role, 'context': context, 'format': scope,
                'n_pressure': np_, 'n_baseline': nb,
                'n_matches': len(set().union(*[m['pm'] | m['bm'] for m in members])),
                'n_pressure_matches': len(set().union(*[m['pm'] for m in members])),
                'n_baseline_matches': len(set().union(*[m['bm'] for m in members])),
                'A': A, 'B': B, 'D': D, 'S_raw': S,
            })
    return rows


def match_residual_sums(records):
    """Per player x role x context x format x match residual sums (Phase 4 input)."""
    groups = defaultdict(lambda: {'p': [], 'b': []})
    for r in records:
        key = (r['player_id'], r['role'], r['context'], r['format'], r['match_id'])
        groups[key]['p' if r['pressure'] else 'b'].append(r['y'])
    out = []
    for (player, role, context, fmt, match), g in sorted(groups.items()):
        np_, sp, sp2 = _stats(g['p'])
        nb, sb, sb2 = _stats(g['b'])
        out.append({'player_id': player, 'role': role, 'context': context,
                    'format': fmt, 'match_id': match,
                    'n_pressure': np_, 'sum_pressure_y': sp, 'sum_pressure_y2': sp2,
                    'n_baseline': nb, 'sum_baseline_y': sb, 'sum_baseline_y2': sb2})
    return out


def descriptive_rows(records):
    """Descriptive indicators per player x role x context x format x pressure side.

    These never enter S_raw; they are reported separately.
    """
    groups = defaultdict(lambda: defaultdict(float))
    matches = defaultdict(set)
    for r in records:
        key = (r['player_id'], r['role'], r['context'], r['format'],
               'pressure' if r['pressure'] else 'baseline')
        row = r['row']
        g = groups[key]
        if r['role'] == 'batter':
            if r['faced_obs']:
                g['balls'] += 1
                g['runs'] += float(row['runs'])
                g['dots'] += 1.0 if float(row['runs']) == 0 else 0.0
                g['fours'] += 1.0 if yes(row['is_four']) else 0.0
                g['sixes'] += 1.0 if yes(row['is_six']) else 0.0
            g['dismissals'] += float(row['dismissed_batter_id'] == r['player_id'])
        else:
            g['balls'] += 1
            g['runs'] += float(row['bowler_charged_runs'])
            g['dots'] += 1.0 if float(row['bowler_charged_runs']) == 0 else 0.0
            g['fours'] += 1.0 if yes(row['is_four']) else 0.0
            g['sixes'] += 1.0 if yes(row['is_six']) else 0.0
            g['wickets'] += float(row['bowler_credit_wicket'])
        matches[key].add(r['match_id'])
    out = []
    for key, g in groups.items():
        player, role, context, fmt, side = key
        balls = g.get('balls', 0.0)
        out.append({
            'player_id': player, 'role': role, 'context': context, 'format': fmt,
            'side': side, 'deliveries': int(balls), 'matches': len(matches[key]),
            'runs': g.get('runs', 0.0),
            'strike_rate': 100.0 * g.get('runs', 0.0) / balls if balls else None,
            'dot_pct': 100.0 * g.get('dots', 0.0) / balls if balls else None,
            'boundary_pct': 100.0 * (g.get('fours', 0.0) + g.get('sixes', 0.0)) / balls if balls else None,
            'dismissals': int(g.get('dismissals', 0.0)),
            'dismissal_pct': 100.0 * g.get('dismissals', 0.0) / balls if balls else None,
            'wickets': int(g.get('wickets', 0.0)),
            'economy': 6.0 * g.get('runs', 0.0) / balls if balls else None,
        })
    return out


# ------------------------------------------------------------------- sensitivity

def spearman(a, b):
    """Spearman rank correlation with average ranks for ties."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else float('nan')


def fold_of(match_id, folds=5):
    h = hashlib.md5(str(match_id).encode()).hexdigest()
    return int(h, 16) % folds
