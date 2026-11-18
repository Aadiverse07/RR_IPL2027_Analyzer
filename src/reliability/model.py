"""Phase 4 reliability core: variance estimators, empirical Bayes, format
combination, eligibility, tiers and consistency.

Read-only over Phase 3 outputs. Analytical scope is unchanged
(SDR-2026-11-18-01): batter evidence is chase-only; bowler evidence keeps
`chase` and `innings1_ahead_par` separate and never combines them. `ALL` is a
pooled-delivery comparison, never a formal format combination.

Only the validated component flags reach Phase 3 and therefore this module.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/processed'

COMPONENTS = DATA / 'player_components.csv'
RESIDUALS = DATA / 'player_match_residuals.csv'
DESCRIPTIVES = DATA / 'player_descriptives.csv'
PLAYERS = DATA / 'players_dim.csv'

# Owner-approved constants (config/methodology.yaml `reliability` and `score`).
Z90 = 1.6448536269514722
ELIGIBILITY_MIN = 0.20
TIER_HIGH = 0.50
TIER_MODERATE = 0.30
TIER_LIMITED = 0.20

# Phase 4 estimation settings (documented in the Phase 4 methodology decision).
KMIN = 20                 # minimum deliveries for tau^2 estimation
CONSISTENCY_K = 5         # pressure matches used for the consistency measure
FORMATS = ('IPL', 'T20I')
SIDES = {'A': 'pressure', 'B': 'baseline'}
SCORE_D_COEF = 0.30       # S = A - 0.30 * B


# --------------------------------------------------------------------- helpers

def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def fnum(v):
    return float(v) if v not in ('', None) else None


def group_residuals(rows, side):
    """(player, role, context, format) -> list of match-level residual sums."""
    out = defaultdict(list)
    for r in rows:
        if int(r[f'n_{side}']) > 0:
            out[(r['player_id'], r['role'], r['context'], r['format'])].append(r)
    return out


def pool_residual_groups(groups):
    """Concatenate format-specific match rows into a pooled-delivery `ALL`."""
    out = defaultdict(list)
    for (pid, role, ctx, _fmt), rows in groups.items():
        out[(pid, role, ctx, 'ALL')].extend(rows)
    return out


def _cell(rows, side):
    n = sum(int(r[f'n_{side}']) for r in rows)
    if n == 0:
        return None
    sy = math.fsum(float(r[f'sum_{side}_y']) for r in rows)
    mean = sy / n
    ssb = 0.0
    ssw = 0.0
    for r in rows:
        nm = int(r[f'n_{side}'])
        sm = float(r[f'sum_{side}_y'])
        s2 = float(r[f'sum_{side}_y2'])
        ssb += nm * (sm / nm - mean) ** 2
        ssw += s2 - sm * sm / nm
    return {'n': n, 'matches': len(rows), 'mean': mean,
            'ssb': max(ssb, 0.0), 'ssw': max(ssw, 0.0)}


def pooled_parameters(cells, side):
    """Pooled within-match variance and pooled match ICC for one stratum.

    sigma2 is the pooled within-match residual variance (between-match
    variation is excluded by construction). rho is the degrees-of-freedom
    weighted mean of the one-way random-effects ICC of each player's matches,
    clamped to [0, 1]; players with one match carry no ICC information.
    """
    ssw = 0.0
    dfw = 0
    num = 0.0
    den = 0.0
    n_obs = 0
    for rows in cells:
        c = _cell(rows, side)
        if c is None:
            continue
        n, M = c['n'], c['matches']
        n_obs += n
        ssw += c['ssw']
        dfw += n - 1
        if M < 2 or n - M < 1:
            continue
        nbar = (n - sum(int(r[f'n_{side}']) ** 2 for r in rows) / n) / (M - 1)
        msb = c['ssb'] / (M - 1)
        msw = c['ssw'] / (n - M)
        scale = msb + (nbar - 1) * msw
        rho = (msb - msw) / scale if scale > 0 else 0.0
        rho = min(1.0, max(0.0, rho))
        num += rho * (M - 1)
        den += M - 1
    return {'sigma2': ssw / dfw if dfw else 0.0,
            'rho': num / den if den else 0.0,
            'dfw': dfw, 'n_obs': n_obs, 'n_cells': len(cells)}


def cell_variance(rows, side, params):
    """E1 (match-clustered robust) and E2 (pooled variance x design effect)."""
    c = _cell(rows, side)
    if c is None:
        return None
    n, M = c['n'], c['matches']
    if n < 2:
        return None
    if M >= 2:
        nbar = (n - sum(int(r[f'n_{side}']) ** 2 for r in rows) / n) / (M - 1)
    else:
        nbar = float(n)
    deff = 1.0 + (nbar - 1.0) * params['rho']
    v2 = params['sigma2'] * deff / n
    v1 = None
    if M >= 2:
        ss = math.fsum((float(r[f'sum_{side}_y']) - int(r[f'n_{side}']) * c['mean']) ** 2
                       for r in rows)
        v1 = (M / (M - 1)) * ss / n ** 2
    return {'n': n, 'matches': M, 'n_mean': nbar, 'mean': c['mean'],
            'v_e1': v1, 'v_e2': v2, 'deff': deff}


def build_variances(components, groups, formats=FORMATS):
    """Variance table keyed by (player, role, context, format, side)."""
    params = {}
    for side_key, group in groups.items():
        field = SIDES[side_key]
        strata = defaultdict(list)
        for (pid, role, ctx, fmt), rows in group.items():
            if fmt in formats:
                strata[(role, ctx, fmt)].append(rows)
        for key, cells in strata.items():
            params[(key, side_key)] = pooled_parameters(cells, field)

    table = {}
    for c in components:
        if c['format'] not in formats:
            continue
        for side_key, group in groups.items():
            field = SIDES[side_key]
            key = (c['player_id'], c['role'], c['context'], c['format'])
            rows = group.get(key)
            if not rows:
                continue
            p = params.get(((c['role'], c['context'], c['format']), side_key))
            if p is None:
                continue
            cell = cell_variance(rows, field, p)
            if cell is None:
                continue
            table[(c['player_id'], c['role'], c['context'], c['format'], side_key)] = {
                **cell, 'sigma2_pool': p['sigma2'], 'rho_pool': p['rho'],
                'n_obs_stratum': p['n_obs'],
            }
    return table, params


def variance_value(var, basis='E2'):
    v1, v2 = var['v_e1'], var['v_e2']
    if basis == 'E2':
        return v2, False
    if basis == 'E1':
        return (v1, False) if v1 is not None and v1 > 0 else (v2, True)
    if basis == 'MAX':
        return (max(v1, v2), False) if v1 is not None else (v2, False)
    raise ValueError(basis)


def variance_table_rows(table):
    out = []
    for (pid, role, ctx, fmt, side), v in sorted(table.items()):
        v1 = v['v_e1']
        out.append({
            'player_id': pid, 'role': role, 'context': ctx, 'format': fmt,
            'side': side, 'n_deliveries': v['n'], 'matches': v['matches'],
            'n_mean': v['n_mean'], 'sigma2_pool': v['sigma2_pool'],
            'rho_pool': v['rho_pool'], 'design_effect': v['deff'],
            'v_e1': '' if v1 is None else v1,
            'se_e1': '' if v1 is None else math.sqrt(max(v1, 0.0)),
            'v_e2': v['v_e2'], 'se_e2': math.sqrt(max(v['v_e2'], 0.0)),
            'v_primary': v['v_e2'], 'se_primary': math.sqrt(max(v['v_e2'], 0.0)),
            'e1_defined': v1 is not None,
            'ratio_e1_e2': '' if v1 is None or v['v_e2'] == 0 else v1 / v['v_e2'],
        })
    return out


# ------------------------------------------------------------------ estimation

def dl_tau2(xs, vs):
    """DerSimonian-Laird moment estimator of the between-player variance."""
    k = len(xs)
    if k < 2:
        return 0.0, 0.0, xs[0] if xs else float('nan')
    w = [1.0 / v for v in vs]
    sw = math.fsum(w)
    m = math.fsum(x * wi for x, wi in zip(xs, w)) / sw
    q = math.fsum(wi * (x - m) ** 2 for x, wi in zip(xs, w))
    den = sw - math.fsum(wi * wi for wi in w) / sw
    tau2 = max(0.0, (q - (k - 1)) / den) if den > 0 else 0.0
    return tau2, q, m


def reml_tau2(xs, vs):
    """REML estimate by Fisher scoring, starting from the DL estimate."""
    k = len(xs)
    if k < 2:
        return 0.0
    tau2 = dl_tau2(xs, vs)[0]
    for _ in range(300):
        w = [1.0 / (v + tau2) for v in vs]
        sw = math.fsum(w)
        m = math.fsum(x * wi for x, wi in zip(xs, w)) / sw
        a = math.fsum(wi * wi * (x - m) ** 2 for x, wi in zip(xs, w))
        b = math.fsum(wi * wi for wi in w)
        if b == 0:
            break
        step = (a + b / sw - sw) / b
        new = max(0.0, tau2 + step)
        if abs(new - tau2) < 1e-10:
            tau2 = new
            break
        tau2 = new
    return tau2


def _gammaincc(a, x):
    """Regularized upper incomplete gamma Q(a, x), Numerical Recipes style."""
    if x <= 0:
        return 1.0
    if x < a + 1.0:
        ap = a
        term = 1.0 / a
        total = term
        for _ in range(1000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-14:
                break
        return 1.0 - total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b = x + 1.0 - a
    c = 1e300
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf_1(q):
    """Survival function of chi-square with one degree of freedom."""
    return math.erfc(math.sqrt(max(q, 0.0) / 2.0))


def chi2_sf(q, df):
    """Survival function of chi-square with df degrees of freedom."""
    return _gammaincc(df / 2.0, max(q, 0.0) / 2.0)


def eb_fit(xs, vs, ids, n_obs, estimator='DL', kmin=KMIN):
    """Empirical-Bayes fit for one role x context x format x side stratum."""
    est = [i for i, pid in enumerate(ids) if n_obs[pid] >= kmin]
    if len(est) < 3:
        est = list(range(len(ids)))
    ex = [xs[i] for i in est]
    ev = [vs[i] for i in est]
    tau2_dl, q, m = dl_tau2(ex, ev)
    tau2_reml = reml_tau2(ex, ev)
    tau2 = tau2_dl if estimator == 'DL' else tau2_reml
    rows = []
    for i, pid in enumerate(ids):
        v = vs[i]
        b = tau2 / (tau2 + v) if tau2 > 0 else 0.0
        star = m + b * (xs[i] - m)
        post_var = b * v if tau2 > 0 else v
        sd = math.sqrt(max(post_var, 0.0))
        rows.append({
            'player_id': pid, 'x_raw': xs[i], 'v': v, 'shrinkage': b,
            'x_star': star, 'post_sd': sd,
            'ci90_low': star - Z90 * sd, 'ci90_high': star + Z90 * sd,
            'unshrunk_low': xs[i] - Z90 * math.sqrt(v),
            'unshrunk_high': xs[i] + Z90 * math.sqrt(v),
            'posterior_var': post_var, 'm': m, 'tau2': tau2,
            'tau2_zero': tau2 == 0.0,
        })
    return {'tau2_dl': tau2_dl, 'tau2_reml': tau2_reml, 'tau2_used': tau2,
            'q_stat': q, 'q_df': len(est) - 1, 'm': m,
            'n_players': len(ids), 'n_estimation': len(est),
            'median_v': sorted(ev)[len(ev) // 2] if ev else float('nan'),
            'median_shrinkage': sorted(r['shrinkage'] for r in rows)[len(rows) // 2]
            if rows else float('nan'),
            'status': 'TAU2_ZERO_BOUNDARY' if tau2 == 0 else 'OK'}, rows


def fit_all_eb(components, table, estimator='DL', kmin=KMIN, basis='E2'):
    """EB separately for every role x context x format x side."""
    eb = {}
    params = []
    by = defaultdict(list)
    for c in components:
        by[(c['role'], c['context'], c['format'])].append(c)
    for (role, ctx, fmt), rows in sorted(by.items()):
        for side, field in SIDES.items():
            ids, xs, vs, nobs = [], [], [], {}
            for c in rows:
                key = (c['player_id'], role, ctx, fmt, side)
                if key not in table:
                    continue
                ids.append(c['player_id'])
                xs.append(float(c[side]))
                vs.append(variance_value(table[key], basis)[0])
                nobs[c['player_id']] = int(c[f'n_{field}'])
            if len(ids) < 2:
                continue
            p, out = eb_fit(xs, vs, ids, nobs, estimator=estimator, kmin=kmin)
            params.append({'role': role, 'context': ctx, 'format': fmt,
                           'side': side, **p})
            for rec in out:
                eb[(rec['player_id'], role, ctx, fmt, side)] = rec
    return eb, params


# --------------------------------------------------------------- combination

def _iv(estimates):
    """Inverse-variance combination of (value, variance) pairs."""
    w = [1.0 / v for _x, v in estimates]
    sw = math.fsum(w)
    value = math.fsum(wi * x for wi, (x, _v) in zip(w, estimates)) / sw
    return value, 1.0 / sw, w


def combine_formats(components, eb):
    """Two-stage, format-aware combination.

    Format-specific EB estimates are combined by inverse-variance weights, so a
    format's own tau^2 is respected instead of being overwritten by a common
    cross-format tau^2. `ALL` is never read here.
    """
    cells = defaultdict(dict)
    for c in components:
        if c['format'] not in FORMATS:
            continue
        cells[(c['player_id'], c['role'], c['context'])][c['format']] = c

    out = []
    for (pid, role, ctx), fmts in sorted(cells.items()):
        a_est, b_est = [], []
        per_format = {}
        for fmt in FORMATS:
            if fmt not in fmts:
                continue
            ea = eb.get((pid, role, ctx, fmt, 'A'))
            ebb = eb.get((pid, role, ctx, fmt, 'B'))
            if ea is None or ebb is None:
                continue
            a_est.append((ea['x_star'], ea['posterior_var']))
            b_est.append((ebb['x_star'], ebb['posterior_var']))
            per_format[fmt] = (ea, ebb, fmts[fmt])
        if not a_est or not b_est or len(a_est) != len(b_est):
            continue

        a_star, va_star, _ = _iv(a_est)
        b_star, vb_star, _ = _iv(b_est)
        a_raw, va_raw, wa = _iv([(eb[(pid, role, ctx, f, 'A')]['x_raw'],
                                 eb[(pid, role, ctx, f, 'A')]['v']) for f in per_format])
        b_raw, vb_raw, wb = _iv([(eb[(pid, role, ctx, f, 'B')]['x_raw'],
                                 eb[(pid, role, ctx, f, 'B')]['v']) for f in per_format])

        shrink_a = math.fsum(w * eb[(pid, role, ctx, f, 'A')]['shrinkage']
                             for w, f in zip(wa, per_format)) / math.fsum(wa)
        shrink_b = math.fsum(w * eb[(pid, role, ctx, f, 'B')]['shrinkage']
                             for w, f in zip(wb, per_format)) / math.fsum(wb)

        d_raw = a_raw - b_raw
        d_star = a_star - b_star
        s_raw = a_raw - SCORE_D_COEF * b_raw
        s_star = a_star - SCORE_D_COEF * b_star
        vs_star = va_star + SCORE_D_COEF ** 2 * vb_star
        sd_s = math.sqrt(max(vs_star, 0.0))

        q = ''
        pval = ''
        disagree = ''
        if len(per_format) == 2:
            wA = [1.0 / eb[(pid, role, ctx, f, 'A')]['v'] for f in per_format]
            xA = [eb[(pid, role, ctx, f, 'A')]['x_raw'] for f in per_format]
            q = math.fsum(wi * (x - a_raw) ** 2 for wi, x in zip(wA, xA))
            pval = chi2_sf_1(q)
            disagree = q > 3.841458820694124

        n_pressure = sum(int(per_format[f][2]['n_pressure']) for f in per_format)
        n_baseline = sum(int(per_format[f][2]['n_baseline']) for f in per_format)
        p_matches = sum(int(per_format[f][2]['n_pressure_matches']) for f in per_format)
        b_matches = sum(int(per_format[f][2]['n_baseline_matches']) for f in per_format)
        n_matches = sum(int(per_format[f][2]['n_matches']) for f in per_format)

        rec = {
            'player_id': pid, 'role': role, 'context': ctx,
            'formats_present': '+'.join(f for f in FORMATS if f in per_format),
            'n_formats': len(per_format),
            'A_raw': a_raw, 'v_A_raw': va_raw,
            'A_star': a_star, 'v_A_star': va_star,
            'B_raw': b_raw, 'v_B_raw': vb_raw,
            'B_star': b_star, 'v_B_star': vb_star,
            'D_raw': d_raw, 'D_star': d_star,
            'S_raw': s_raw, 'S_star': s_star,
            'S_post_sd': sd_s,
            'S_ci90_low': s_star - Z90 * sd_s,
            'S_ci90_high': s_star + Z90 * sd_s,
            'shrinkage_A': shrink_a, 'shrinkage_B': shrink_b,
            'n_pressure': n_pressure, 'n_baseline': n_baseline,
            'pressure_matches': p_matches, 'baseline_matches': b_matches,
            'total_matches': n_matches,
            'format_Q': q, 'format_p': pval, 'format_disagree': disagree,
        }
        for fmt in FORMATS:
            if fmt in per_format:
                ea, ebb, comp = per_format[fmt]
                rec[f'A_{fmt}'] = ea['x_raw']
                rec[f'A_star_{fmt}'] = ea['x_star']
                rec[f'B_{fmt}'] = ebb['x_raw']
                rec[f'B_star_{fmt}'] = ebb['x_star']
                rec[f'shrink_A_{fmt}'] = ea['shrinkage']
                rec[f'n_pressure_{fmt}'] = int(comp['n_pressure'])
                rec[f'pressure_matches_{fmt}'] = int(comp['n_pressure_matches'])
            else:
                rec[f'A_{fmt}'] = ''
                rec[f'A_star_{fmt}'] = ''
                rec[f'B_{fmt}'] = ''
                rec[f'B_star_{fmt}'] = ''
                rec[f'shrink_A_{fmt}'] = ''
                rec[f'n_pressure_{fmt}'] = 0
                rec[f'pressure_matches_{fmt}'] = 0
        rec['scored'] = True
        rec['evidence_tier'] = tier(shrink_a)
        rec['eligible'] = shrink_a >= ELIGIBILITY_MIN
        rec['reliability_status'] = (
            'BLOCKED_TAU2_ZERO' if any(
                eb[(pid, role, ctx, f, 'A')]['tau2_zero'] for f in per_format) else 'OK')
        out.append(rec)
    return out


def single_stage_combine(components, table, estimator='DL', kmin=KMIN, basis='E2',
                         formats=FORMATS):
    """Literal `combine raw formats, then shrink` comparison (spec task 3).

    Reported as a sensitivity only: one common tau^2 across formats overwrites
    format-specific heterogeneity and can erase the only detectable signal.
    """
    cells = defaultdict(dict)
    for c in components:
        if c['format'] in formats:
            cells[(c['player_id'], c['role'], c['context'])][c['format']] = c
    raw = []
    for (pid, role, ctx), fmts in sorted(cells.items()):
        est = {}
        ok = True
        for side in ('A', 'B'):
            pairs = []
            for fmt, c in fmts.items():
                key = (pid, role, ctx, fmt, side)
                if key not in table:
                    ok = False
                    break
                pairs.append((float(c[side]), variance_value(table[key], basis)[0]))
            if not ok or not pairs:
                ok = False
                break
            est[side] = _iv(pairs)
        if not ok:
            continue
        raw.append({'player_id': pid, 'role': role, 'context': ctx,
                    'formats_present': '+'.join(sorted(fmts)),
                    'A_raw': est['A'][0], 'v_A_raw': est['A'][1],
                    'B_raw': est['B'][0], 'v_B_raw': est['B'][1],
                    'n_pressure': sum(int(c['n_pressure']) for c in fmts.values()),
                    'n_baseline': sum(int(c['n_baseline']) for c in fmts.values()),
                    'pressure_matches': sum(int(c['n_pressure_matches']) for c in fmts.values()),
                    'baseline_matches': sum(int(c['n_baseline_matches']) for c in fmts.values()),
                    'total_matches': sum(int(c['n_matches']) for c in fmts.values())})

    out = []
    strata = defaultdict(list)
    for r in raw:
        strata[(r['role'], r['context'])].append(r)
    for (role, ctx), rows in strata.items():
        ids = [r['player_id'] for r in rows]
        nobs = {r['player_id']: r['n_pressure'] for r in rows}
        for side in ('A', 'B'):
            _p, fitted = eb_fit([r[f'{side}_raw'] for r in rows],
                                [r[f'v_{side}_raw'] for r in rows],
                                ids, nobs, estimator=estimator, kmin=kmin)
            for r, fit in zip(rows, fitted):
                r[f'{side}_star'] = fit['x_star']
                r[f'v_{side}_star'] = fit['posterior_var']
                r[f'shrink_{side}'] = fit['shrinkage']
                r[f'tau2_zero_{side}'] = fit['tau2_zero']
        for r in rows:
            r['D_raw'] = r['A_raw'] - r['B_raw']
            r['D_star'] = r['A_star'] - r['B_star']
            r['S_raw'] = r['A_raw'] - SCORE_D_COEF * r['B_raw']
            r['S_star'] = r['A_star'] - SCORE_D_COEF * r['B_star']
            r['S_post_sd'] = math.sqrt(max(r['v_A_star'] + SCORE_D_COEF ** 2 * r['v_B_star'], 0))
            r['scored'] = True
            r['shrinkage_A'] = r['shrink_A']
            r['shrinkage_B'] = r['shrink_B']
            r['evidence_tier'] = tier(r['shrink_A'])
            r['eligible'] = r['shrink_A'] >= ELIGIBILITY_MIN
            r['reliability_status'] = ('BLOCKED_TAU2_ZERO'
                                       if r['tau2_zero_A'] else 'OK')
            out.append(r)
    return out


def format_heterogeneity(components, table, basis='E2'):
    """Per-player and per-stratum IPL vs T20I heterogeneity."""
    cells = defaultdict(dict)
    for c in components:
        if c['format'] in FORMATS:
            cells[(c['player_id'], c['role'], c['context'])][c['format']] = c
    player_rows = []
    for (pid, role, ctx), fmts in sorted(cells.items()):
        if len(fmts) != 2:
            continue
        if any((pid, role, ctx, f, 'A') not in table for f in fmts):
            continue
        pairs = [(f, float(fmts[f]['A']),
                  variance_value(table[(pid, role, ctx, f, 'A')], basis)[0]) for f in FORMATS]
        w = [1.0 / v for _f, _x, v in pairs]
        sw = math.fsum(w)
        comb = math.fsum(wi * x for wi, (_f, x, _v) in zip(w, pairs)) / sw
        q = math.fsum(wi * (x - comb) ** 2 for wi, (_f, x, _v) in zip(w, pairs))
        player_rows.append({'player_id': pid, 'role': role, 'context': ctx,
                            'A_IPL': pairs[0][1], 'A_T20I': pairs[1][1],
                            'A_combined': comb, 'v_combined': 1.0 / sw,
                            'Q': q, 'p': chi2_sf_1(q), 'disagree': q > 3.841458820694124})

    strata = defaultdict(list)
    for r in player_rows:
        strata[(r['role'], r['context'])].append(r)
    out = []
    for (role, ctx), rows in strata.items():
        q_total = math.fsum(r['Q'] for r in rows)
        df = len(rows)
        weights = []
        for r in rows:
            w1 = 1.0 / _v_for(components, table, r['player_id'], role, ctx, 'IPL', basis)
            w2 = 1.0 / _v_for(components, table, r['player_id'], role, ctx, 'T20I', basis)
            weights.append((w1, w2))
        denom = math.fsum(w1 + w2 - (w1 * w1 + w2 * w2) / (w1 + w2)
                          for w1, w2 in weights)
        tau2_f = max(0.0, (q_total - df) / denom) if denom > 0 else 0.0
        med_v = sorted(r['v_combined'] for r in rows)[len(rows) // 2]
        out.append({'role': role, 'context': ctx, 'n_both_formats': len(rows),
                    'q_total': q_total, 'df': df,
                    'p': chi2_sf(q_total, df) if df else '',
                    'n_disagree': sum(1 for r in rows if r['disagree']),
                    'share_disagree': sum(1 for r in rows if r['disagree']) / len(rows),
                    'tau2_between_format': tau2_f, 'median_v_combined': med_v,
                    'tau2_lt_median_v': tau2_f < med_v,
                    'significant_share_ok': (sum(1 for r in rows if r['disagree']) / len(rows)) <= 0.15})
    return player_rows, out


def _v_for(components, table, pid, role, ctx, fmt, basis='E2'):
    return variance_value(table[(pid, role, ctx, fmt, 'A')], basis)[0]


def format_validation(components, table):
    """Per format: enough pressure volume and an estimable EB fit."""
    out = []
    for role in ('batter', 'bowler'):
        for ctx in ('chase', 'innings1_ahead_par'):
            for fmt in FORMATS:
                rows = [c for c in components if c['role'] == role
                        and c['context'] == ctx and c['format'] == fmt]
                if not rows:
                    continue
                enough = sum(1 for c in rows if int(c['n_pressure']) >= KMIN)
                out.append({'role': role, 'context': ctx, 'format': fmt,
                            'n_players': len(rows), 'n_players_pressure_ge_kmin': enough,
                            'validated': enough >= 30})
    return out


# ---------------------------------------------------------------- eligibility

def tier(shrinkage):
    if shrinkage >= TIER_HIGH:
        return 'High'
    if shrinkage >= TIER_MODERATE:
        return 'Moderate'
    if shrinkage >= TIER_LIMITED:
        return 'Limited'
    return 'Insufficient'


def eligibility_thresholds(combined, format_eb=None):
    """Counts at the approved thresholds plus decision-support thresholds."""
    out = []
    thresholds = (0.10, 0.15, 0.20, 0.30, 0.50)
    for role in ('batter', 'bowler'):
        contexts = ['chase'] if role == 'batter' else ['chase', 'innings1_ahead_par']
        for ctx in contexts:
            rows = [r for r in combined if r['role'] == role and r['context'] == ctx]
            if not rows:
                continue
            for t in thresholds:
                elig = [r for r in rows if r['shrinkage_A'] >= t]
                out.append({'role': role, 'context': ctx, 'scope': 'combined',
                            'threshold': t, 'n_players': len(rows),
                            'n_eligible': len(elig),
                            'share_eligible': len(elig) / len(rows),
                            'n_pressure_median': _median([r['n_pressure'] for r in elig])
                            if elig else ''})
            for fmt in FORMATS:
                frows = [r for r in rows if r[f'shrink_A_{fmt}'] != '']
                if not frows:
                    continue
                for t in thresholds:
                    elig = [r for r in frows if float(r[f'shrink_A_{fmt}']) >= t]
                    out.append({'role': role, 'context': ctx, 'scope': fmt,
                                'threshold': t, 'n_players': len(frows),
                                'n_eligible': len(elig),
                                'share_eligible': len(elig) / len(frows),
                                'n_pressure_median': _median([r[f'n_pressure_{fmt}'] for r in elig])
                                if elig else ''})
    return out


def _median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else ''


# ---------------------------------------------------------------- consistency

def consistency_rows(groups):
    """Share of positive pressure matches and match-level residual SD."""
    by = defaultdict(list)
    for (pid, role, ctx, _fmt), rows in groups.items():
        by[(pid, role, ctx)].extend(rows)
    out = {}
    for key, rows in by.items():
        use = [r for r in rows if int(r['n_pressure']) >= CONSISTENCY_K]
        means = [float(r['sum_pressure_y']) / int(r['n_pressure']) for r in use]
        pos = sum(1 for m in means if m > 0) / len(means) if means else None
        sd = (math.sqrt(math.fsum((m - math.fsum(means) / len(means)) ** 2
                                  for m in means) / (len(means) - 1))
              if len(means) >= 2 else None)
        out[key] = {'consistency_k': CONSISTENCY_K, 'consistency_matches': len(use),
                    'consistency_positive_share': pos, 'consistency_match_sd': sd}
    return out


# ------------------------------------------------------------------ bootstrap

def bootstrap_diagnostics(components, groups, table, reps=300, max_players=150, seed=20261117):
    """Match-block bootstrap check of the analytic 90% intervals for A.

    Coverage is the share of bootstrap A replicates inside the analytic CI.
    A well-calibrated interval covers about 90%.
    """
    rng = np.random.default_rng(seed)
    have = {(c['player_id'], c['role'], c['context'], c['format']) for c in components}
    keys = [k for k in groups['A'] if k in have and len(groups['A'][k]) >= 6]
    keys.sort()
    keys = [keys[i] for i in rng.choice(len(keys), size=min(max_players, len(keys)),
                                        replace=False)]
    out = []
    for k in keys:
        rows = groups['A'][k]
        n_m = np.array([int(r['n_pressure']) for r in rows], dtype=float)
        sy_m = np.array([float(r['sum_pressure_y']) for r in rows], dtype=float)
        M = len(rows)
        picks = rng.integers(0, M, size=(reps, M))
        boots = sy_m[picks].sum(axis=1) / n_m[picks].sum(axis=1)
        var = table.get((k[0], k[1], k[2], k[3], 'A'))
        if var is None:
            continue
        mean = sy_m.sum() / n_m.sum()
        for estimator, v in (('E1', var['v_e1']), ('E2', var['v_e2'])):
            if v is None:
                continue
            se = math.sqrt(max(v, 0.0))
            lo, hi = mean - Z90 * se, mean + Z90 * se
            cov = float(np.mean((boots >= lo) & (boots <= hi)))
            out.append({'player_id': k[0], 'role': k[1], 'context': k[2],
                        'format': k[3], 'matches': M, 'n_pressure': int(n_m.sum()),
                        'estimator': estimator, 'coverage': cov,
                        'analytic_sd': se, 'bootstrap_sd': float(boots.std(ddof=1)),
                        'sd_ratio': se / float(boots.std(ddof=1))
                        if boots.std(ddof=1) > 0 else ''})
    return out


# ------------------------------------------------------------------ ranking

def top_ten(rows, score='S_star', eligible_only=True):
    pool = [r for r in rows if (not eligible_only or r.get('eligible'))]
    pool = sorted(pool, key=lambda r: (-r[score], -r['shrinkage_A'],
                                       -r['n_pressure'], r['player_id']))
    return pool[:10]


def spearman(a, b):
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
    if n < 2:
        return None
    ma, mb = sum(ra) / n, sum(rb) / n
    num = math.fsum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(math.fsum((x - ma) ** 2 for x in ra)
                    * math.fsum((y - mb) ** 2 for y in rb))
    return num / den if den else None
