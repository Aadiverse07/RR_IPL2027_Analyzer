"""Phase 5 ranking and selection core.

Read-only over Phase 4 outputs (SDR-2026-11-18-03). Scope, ranking rule and
sensitivity plan are pre-registered in `reports/methodology/
SDR-2026-11-18-03-phase5-ranking.md`.

Nothing here changes a flag, threshold, weight, variance estimator or
shrinkage setting: the Phase 4 estimator is imported and used as-is.
"""
from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from pathlib import Path

from src.reliability import model as rm
from src.reliability.run_phase4 import core

ROOT = Path(__file__).resolve().parents[2]
SCORES = {
    'batter': ROOT / 'outputs/final/player_scores_batters.csv',
    'bowler': ROOT / 'outputs/final/player_scores_bowlers.csv',
}
PLAYER_MATCH = ROOT / 'data/processed/player_match.csv'
MAPPING = ROOT / 'data/raw/Data Pack/competition_team_player_mapping.csv'

LIMIT = 10
SCORE_COEF = rm.SCORE_D_COEF           # S = A - 0.30 B (owner-approved w = 0.70)
ELIGIBILITY_MIN = rm.ELIGIBILITY_MIN   # B_A >= 0.20 (unchanged)
EPS = 1e-9

CONTEXTS = {'batter': ('chase',), 'bowler': ('chase', 'innings1_ahead_par')}


# ------------------------------------------------------------------ helpers

def as_float(v, default=None):
    if v in ('', None):
        return default
    return float(v)


def as_int(v, default=0):
    if v in ('', None):
        return default
    return int(float(v))


def load_scores(role, context=None):
    rows = rm.read_csv(SCORES[role])
    if context is not None:
        rows = [r for r in rows if r['context'] == context]
    return rows


def score_of(row):
    """S* recomputed from the stored shrunk components (never from reliability)."""
    a = as_float(row['A_star'])
    b = as_float(row['B_star'])
    if a is None or b is None:
        return None
    return a - SCORE_COEF * b


def is_eligible(row):
    """Owner-approved rule, re-derived: scored and merged shrinkage >= 0.20."""
    if str(row.get('scored')) != 'True':
        return False
    b = as_float(row.get('shrinkage_A'))
    return b is not None and b >= ELIGIBILITY_MIN


# ----------------------------------------------------------------- identity

def resolve_identity():
    """Authoritative display identity per player_id.

    Raw `player_id` is unique per person in the source pack. The Phase 1
    `players_dim.csv` name column is corrupted by a `dismissed_player_id` /
    `striker_name` pairing (F5-01), so names are resolved here from the
    competition mapping and cross-checked against player-match names.
    """
    mapping = defaultdict(set)
    for r in rm.read_csv(MAPPING):
        mapping[r['player_id']].add(r['player_name'])
    seen = defaultdict(set)
    for r in rm.read_csv(PLAYER_MATCH):
        if r['name']:
            seen[r['player_id']].add(r['name'])
    out = {}
    for pid in sorted(set(mapping) | set(seen), key=lambda x: int(x)):
        mnames = sorted(mapping.get(pid, set()))
        snames = sorted(seen.get(pid, set()))
        if not mnames:
            status = 'MISSING_FROM_MAPPING'
        elif len(mnames) > 1:
            status = 'MULTIPLE_MAPPING_NAMES'
        elif snames and snames != mnames:
            status = 'NAME_VARIANT'
        else:
            status = 'OK'
        name = mnames[0] if len(mnames) == 1 else (snames[0] if snames else '')
        out[pid] = {'player_id': pid, 'name': name,
                    'mapping_name': '|'.join(mnames),
                    'names_observed': '|'.join(snames),
                    'n_names_observed': len(snames),
                    'identity_status': status}
    return out


def duplicate_name_ids(identity):
    """Display names carried by more than one player_id (source ambiguity)."""
    by_name = defaultdict(list)
    for pid, rec in identity.items():
        if rec['name']:
            by_name[rec['name']].append(pid)
    return {n: pids for n, pids in by_name.items() if len(pids) > 1}


# ------------------------------------------------------------------ ranking

def rank(rows, limit=LIMIT, score_key='S_star'):
    """Eligible-only ranking with the pre-registered deterministic order."""
    pool = [r for r in rows if is_eligible(r)]
    pool.sort(key=lambda r: (-as_float(r[score_key], -1e9),
                             -as_float(r['shrinkage_A'], 0.0),
                             -as_int(r['n_pressure']),
                             str(r['player_id'])))
    return pool[:limit]


def exact_ties(ranked, score_key='S_star'):
    """Adjacent pairs with an identical score to the last stored digit."""
    ties = []
    for i in range(len(ranked) - 1):
        a, b = ranked[i], ranked[i + 1]
        if abs(as_float(a[score_key]) - as_float(b[score_key])) <= 1e-12:
            ties.append((i + 1, i + 2))
    return ties


def separation(ranked, score_key='S_star'):
    """Adjacent gap and 90% interval overlap for the published order."""
    out = []
    for i, r in enumerate(ranked):
        lo = as_float(r['S_ci90_low'])
        hi = as_float(r['S_ci90_high'])
        rec = {'rank': i + 1, 'player_id': r['player_id'],
               'S_star': as_float(r[score_key]),
               'ci90_low': lo, 'ci90_high': hi,
               'ci_width': None if lo is None or hi is None else hi - lo,
               'contains_zero': None if lo is None or hi is None else (lo <= 0 <= hi)}
        if i:
            prev = ranked[i - 1]
            gap = as_float(prev[score_key]) - as_float(r[score_key])
            plo, phi = as_float(prev['S_ci90_low']), as_float(prev['S_ci90_high'])
            rec['gap_from_previous'] = gap
            rec['ci_overlaps_previous'] = not (hi < plo or phi < lo)
        out.append(rec)
    return out


def exclusion_records(rows, role, context, identity):
    """Every non-eligible player with the reason code and its evidence."""
    out = []
    for r in rows:
        if is_eligible(r):
            continue
        if str(r.get('scored')) != 'True':
            reason = 'NO_VARIANCE'
            detail = ('Fewer than two deliveries in the pressure or baseline '
                      'component; no E2 variance is estimable.')
        else:
            reason = 'SHRINKAGE_BELOW_0.20'
            detail = ('Pressure shrinkage B_A = %.4f is below the approved '
                      '0.20 eligibility minimum.' % as_float(r['shrinkage_A']))
            if r.get('reliability_status') == 'BLOCKED_TAU2_ZERO':
                detail += (' At least one format stratum has tau^2 at the zero '
                           'boundary (TAU2_ZERO_BOUNDARY), which attenuates the '
                           'combined shrinkage.')
        out.append({
            'player_id': r['player_id'],
            'player_name': identity.get(r['player_id'], {}).get('name', ''),
            'role': role, 'context': context,
            'reason_code': reason, 'reason_detail': detail,
            'formats_present': r['formats_present'],
            'shrinkage_A': r['shrinkage_A'],
            'evidence_tier': r['evidence_tier'],
            'S_star': r['S_star'],
            'n_pressure': r['n_pressure'],
            'total_matches': r['total_matches'],
        })
    out.sort(key=lambda x: (-as_float(x['shrinkage_A'], -1), str(x['player_id'])))
    return out


# ------------------------------------------------------- sensitivity variants

def w_variant(rows, w):
    """S = A* - (1-w) B*, keeping every reliability column untouched."""
    coef = 1.0 - w
    out = []
    for r in rows:
        d = dict(r)
        a, b = as_float(r['A_star']), as_float(r['B_star'])
        if a is None or b is None:
            d['S_star'] = ''
            out.append(d)
            continue
        d['S_star'] = a - coef * b
        va = as_float(r['A_post_sd'], 0.0) ** 2
        vb = as_float(r['B_post_sd'], 0.0) ** 2
        sd = math.sqrt(max(va + coef ** 2 * vb, 0.0))
        d['S_post_sd'] = sd
        d['S_ci90_low'] = d['S_star'] - rm.Z90 * sd
        d['S_ci90_high'] = d['S_star'] + rm.Z90 * sd
        out.append(d)
    return out


def format_ranking(rows, fmt):
    """Format-specific ranking from the stored per-format shrunk estimates."""
    pool = []
    for r in rows:
        sa = as_float(r.get(f'shrink_A_{fmt}'))
        a = as_float(r.get(f'A_star_{fmt}'))
        b = as_float(r.get(f'B_star_{fmt}'))
        if sa is None or a is None or b is None:
            continue
        if sa < ELIGIBILITY_MIN:
            continue
        d = dict(r)
        d['S_star'] = a - SCORE_COEF * b
        d['shrinkage_A'] = sa
        d[f'n_pressure_{fmt}'] = as_int(r.get(f'n_pressure_{fmt}'))
        pool.append(d)
    pool.sort(key=lambda r: (-as_float(r['S_star']), -as_float(r['shrinkage_A']),
                             -as_int(r[f'n_pressure_{fmt}']), str(r['player_id'])))
    return pool


def pipeline_variant(residuals, components, role, context, **kwargs):
    """Re-run the Phase 4 estimator over a restricted pool with settings."""
    comps = [c for c in components
             if c['role'] == role and c['context'] == context
             and c['format'] in rm.FORMATS]
    res = [r for r in residuals
           if r['role'] == role and r['context'] == context
           and r['format'] in rm.FORMATS]
    result = core(comps, res, **kwargs)
    return [r for r in result['combined']
            if r['role'] == role and r['context'] == context]


# ----------------------------------------------------------- bootstrap ranks

def _groups(residuals):
    out = defaultdict(list)
    for r in residuals:
        out[(r['player_id'], r['role'], r['context'], r['format'])].append(r)
    return out


def _resample(groups, rng):
    rows = []
    for key in sorted(groups):
        g = groups[key]
        m = len(g)
        for _ in range(m):
            rows.append(g[rng.randrange(m)])
    return rows


def _components_from_rows(rows):
    agg = {}
    for r in rows:
        key = (r['player_id'], r['role'], r['context'], r['format'])
        d = agg.setdefault(key, {'nA': 0, 'sA': 0.0, 'nB': 0, 'sB': 0.0,
                                 'mA': 0, 'mB': 0})
        nA, nB = int(r['n_pressure']), int(r['n_baseline'])
        d['nA'] += nA
        d['nB'] += nB
        d['sA'] += float(r['sum_pressure_y'])
        d['sB'] += float(r['sum_baseline_y'])
        if nA:
            d['mA'] += 1
        if nB:
            d['mB'] += 1
    out = []
    for key, d in agg.items():
        if d['nA'] == 0 or d['nB'] == 0:
            continue
        A = d['sA'] / d['nA']
        B = d['sB'] / d['nB']
        out.append({'player_id': key[0], 'role': key[1], 'context': key[2],
                    'format': key[3],
                    'n_pressure': d['nA'], 'n_baseline': d['nB'],
                    'n_matches': max(d['mA'], d['mB']),
                    'n_pressure_matches': d['mA'],
                    'n_baseline_matches': d['mB'],
                    'A': A, 'B': B, 'D': A - B,
                    'S_raw': A - SCORE_COEF * B})
    return out


def _eb_fixed_variance(comps, table):
    """Rebuild the Phase 4 EB fit with the sampling variance held fixed.

    Duplicating a cluster in a nonparametric bootstrap would drive the
    within-player ICC toward zero and inflate eligibility, so the variance
    model (`v` from the primary E2 fit) is held fixed and only the match-level
    component means, tau^2, the population mean, shrinkage and the format
    combination are re-estimated.
    """
    eb = {}
    by = defaultdict(list)
    for c in comps:
        by[(c['role'], c['context'], c['format'])].append(c)
    for (role, ctx, fmt), rows in by.items():
        for side, field in rm.SIDES.items():
            ids, xs, vs, nobs = [], [], [], {}
            for c in rows:
                key = (c['player_id'], role, ctx, fmt, side)
                if key not in table:
                    continue
                ids.append(c['player_id'])
                xs.append(float(c[side]))
                vs.append(rm.variance_value(table[key], 'E2')[0])
                nobs[c['player_id']] = int(c[f'n_{field}'])
            if len(ids) < 2:
                continue
            _p, out = rm.eb_fit(xs, vs, ids, nobs)
            for rec in out:
                eb[(rec['player_id'], role, ctx, fmt, side)] = rec
    return rm.combine_formats(comps, eb)


def _combined_score(pid, by_format, eb, role, ctx):
    """Published score for one player from resampled component means.

    The EB fit (tau^2, population mean, shrinkage factor, posterior variance)
    is held at its primary value, so only the match-level performance varies.
    """
    a_est, b_est = [], []
    for fmt in rm.FORMATS:
        c = by_format.get((pid, fmt))
        if c is None:
            continue
        ea = eb.get((pid, role, ctx, fmt, 'A'))
        ebb = eb.get((pid, role, ctx, fmt, 'B'))
        if ea is None or ebb is None:
            continue
        if ea['posterior_var'] <= 0 or ebb['posterior_var'] <= 0:
            continue
        a_est.append((ea['m'] + ea['shrinkage'] * (c['A'] - ea['m']),
                      ea['posterior_var']))
        b_est.append((ebb['m'] + ebb['shrinkage'] * (c['B'] - ebb['m']),
                      ebb['posterior_var']))
    if not a_est or len(a_est) != len(b_est):
        return None
    a = rm._iv(a_est)[0]
    b = rm._iv(b_est)[0]
    return a - SCORE_COEF * b


def refit_diagnostic(components, residuals, table, role, context, reps, seed):
    """Rejected bootstrap design, kept as recorded evidence for F5-02.

    Resamples matches *and* re-estimates E2 variances under duplication. The
    duplicated clusters drive the within-player ICC toward zero and the DL
    tau^2 up, so shrinkage — and therefore eligibility — inflates. Measured and
    reported, never used for the published ranking.
    """
    res = [r for r in residuals
           if r['role'] == role and r['context'] == context
           and r['format'] in rm.FORMATS]
    groups = _groups(res)
    rng = random.Random(seed)
    counts = []
    fails = 0
    for _ in range(reps):
        rows = _resample(groups, rng)
        try:
            comps = _components_from_rows(rows)
            combined = _eb_fixed_variance(comps, table)
        except Exception:            # pragma: no cover - defensive
            fails += 1
            continue
        counts.append(sum(1 for r in combined
                          if r['role'] == role and r['context'] == context
                          and r['shrinkage_A'] >= ELIGIBILITY_MIN))
    return {'design': 'refit_variance_under_duplication',
            'reps': reps, 'seed': seed, 'failed_replicates': fails,
            'median_eligible': _median(counts) if counts else '',
            'min_eligible': min(counts) if counts else '',
            'max_eligible': max(counts) if counts else ''}


def bootstrap_ranks(components, residuals, primary, role, context, reps, seed,
                    limit=LIMIT):
    """Match-block bootstrap of the published ranking.

    Each replicate resamples a player's match-level residual rows with
    replacement and rebuilds the raw pressure/baseline means. The EB fit itself
    is held at the primary values: it is a calibration of reliability, not a
    quantity whose resample-to-resample noise should redefine the eligible set
    (a refitted version was implemented, tested and rejected — see F5-02).

    Resampling is within player x format, so both formats keep their own volume
    and the inverse-variance combination keeps its own weights.
    """
    res = [r for r in residuals
           if r['role'] == role and r['context'] == context
           and r['format'] in rm.FORMATS]
    groups = _groups(res)
    eb = primary['eb']
    eligible = sorted(r['player_id'] for r in primary['combined']
                      if r['role'] == role and r['context'] == context
                      and r['shrinkage_A'] >= ELIGIBILITY_MIN)
    meta = {r['player_id']: r for r in primary['combined']
            if r['role'] == role and r['context'] == context}
    rng = random.Random(seed)
    stats = defaultdict(lambda: {'runs': 0, 'top': 0, 'ranks': []})
    sets = CounterLike()
    fails = 0
    for _ in range(reps):
        rows = _resample(groups, rng)
        try:
            comps = _components_from_rows(rows)
        except Exception as exc:      # pragma: no cover - defensive
            fails += 1
            sets.failures.append(f'{type(exc).__name__}: {exc}')
            continue
        by_format = {(c['player_id'], c['format']): c for c in comps}
        scores = {}
        for pid in eligible:
            s = _combined_score(pid, by_format, eb, role, context)
            if s is not None:
                scores[pid] = s
        ordered = sorted(scores, key=lambda p: (-scores[p],
                                                -meta[p]['shrinkage_A'],
                                                -meta[p]['n_pressure'],
                                                str(p)))
        top = ordered[:limit]
        sets.add(tuple(top))
        for rank_i, pid in enumerate(ordered, 1):
            rec = stats[pid]
            rec['runs'] += 1
            rec['ranks'].append(rank_i)
        for pid in top:
            stats[pid]['top'] += 1
    out = {}
    for pid in stats:
        s = stats[pid]
        ranks = sorted(s['ranks'])
        out[pid] = {
            'player_id': pid,
            'replicates_scored': s['runs'],
            'replicates_top10': s['top'],
            'share_scored': s['runs'] / reps,
            'share_top10': s['top'] / reps if s['runs'] else '',
            'rank_median': ranks[len(ranks) // 2] if ranks else '',
            'rank_p05': ranks[int(0.05 * (len(ranks) - 1))] if ranks else '',
            'rank_p95': ranks[int(0.95 * (len(ranks) - 1))] if ranks else '',
        }
    diag = {
        'reps': reps, 'seed': seed, 'failed_replicates': fails,
        'eligible_pool': len(eligible),
        'distinct_top_sets': sets.distinct(),
        'most_common_set_share': sets.mode_share(),
        'failures': sets.failures[:5],
    }
    return out, diag


class CounterLike:
    def __init__(self):
        self.counts = defaultdict(int)
        self.failures = []

    def add(self, key):
        self.counts[key] += 1

    def distinct(self):
        return len(self.counts)

    def mode_share(self):
        if not self.counts:
            return ''
        return max(self.counts.values()) / sum(self.counts.values())


def _median(vals):
    if not vals:
        return ''
    s = sorted(vals)
    return s[len(s) // 2]


def percentile(vals, q):
    if not vals:
        return ''
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * (len(s) - 1)))]
