"""Phase 4 acceptance tests: variance, empirical Bayes, combination,
eligibility/tiers, context separation, preservation and determinism.

Every assertion is recomputed from the Phase 3 processed files rather than
trusting the report, except where the number is a deliberate regression guard.
"""
import csv
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import yaml

from src.reliability import model, run_phase4

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / 'data/processed/player_components.csv'
RESIDUALS = ROOT / 'data/processed/player_match_residuals.csv'
SCORES_B = ROOT / 'outputs/final/player_scores_batters.csv'
SCORES_W = ROOT / 'outputs/final/player_scores_bowlers.csv'
REPORT = ROOT / 'reports/phase_4'
LOG = REPORT / 'logs/run_phase4.json'
CFG = yaml.safe_load((ROOT / 'config/methodology.yaml').read_text(encoding='utf-8'))
Z90 = 1.6448536269514722


def read(path):
    with Path(path).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def phase3():
    return model.read_csv(COMPONENTS), model.read_csv(RESIDUALS)


@lru_cache(maxsize=1)
def primary():
    components, residuals = phase3()
    result = run_phase4.core(components, residuals)
    consistency = model.consistency_rows(result['groups']['A'])
    scores = run_phase4.score_rows(components, result['combined'], consistency,
                                   result['eb_params'])
    return result, scores


@lru_cache(maxsize=1)
def log():
    return json.loads(LOG.read_text(encoding='utf-8'))


def scored(rows, role, ctx):
    return [r for r in rows if r['role'] == role and r['context'] == ctx
            and r.get('scored')]


# ------------------------------------------------------------------ variance

def test_every_variance_cell_has_a_positive_e2_and_e1_rule_is_exact():
    components, residuals = phase3()
    gA = model.group_residuals(residuals, 'pressure')
    gB = model.group_residuals(residuals, 'baseline')
    table, params = model.build_variances(components, {'A': gA, 'B': gB})
    assert table
    for key, v in table.items():
        assert v['v_e2'] > 0, key
        assert v['deff'] >= 1.0, key
        assert 0.0 <= v['rho_pool'] <= 1.0, key
        # E1 exists exactly when there is more than one match in the component.
        assert (v['v_e1'] is not None) == (v['matches'] >= 2), key
        if v['v_e1'] is not None:
            assert v['v_e1'] >= 0.0
    for p in params.values():
        assert p['sigma2'] >= 0.0
        assert p['dfw'] > 0


def test_e1_undefined_count_matches_report_and_bootstrap():
    vrows = read('data/processed/player_variance_estimates.csv')
    undefined = sum(1 for r in vrows if r['e1_defined'] == 'False')
    assert (undefined, len(vrows)) == (596, 3039)
    boot = read(REPORT / 'variance_bootstrap.csv')
    for est in ('E1', 'E2'):
        sub = [r for r in boot if r['estimator'] == est]
        assert len(sub) == 150
        assert all(0.0 <= float(r['coverage']) <= 1.0 for r in sub)
    # E2 is the primary and the bootstrap says it is the conservative one.
    e2 = sorted(float(r['coverage']) for r in boot if r['estimator'] == 'E2')
    e1 = sorted(float(r['coverage']) for r in boot if r['estimator'] == 'E1')
    assert e2[len(e2) // 2] > e1[len(e1) // 2]
    assert e2[len(e2) // 2] >= 0.90


def test_primary_variance_is_e2_in_outputs():
    vrows = read('data/processed/player_variance_estimates.csv')
    for r in vrows:
        assert float(r['v_primary']) == float(r['v_e2'])
    assert log()['variance_estimator'] == 'E2'


# ------------------------------------------------------------- empirical Bayes

def test_shrinkage_formula_bounds_and_zero_tau_flag():
    result, _ = primary()
    for (pid, role, ctx, fmt, side), rec in result['eb'].items():
        b, v = rec['shrinkage'], rec['v']
        assert 0.0 <= b <= 1.0
        if rec['tau2'] > 0:
            assert math.isclose(b, rec['tau2'] / (rec['tau2'] + v), rel_tol=1e-12)
            assert math.isclose(rec['x_star'],
                                rec['m'] + b * (rec['x_raw'] - rec['m']),
                                rel_tol=1e-12, abs_tol=1e-12)
            assert rec['posterior_var'] > 0
        else:
            assert b == 0.0
            assert rec['x_star'] == rec['m']
            assert rec['tau2_zero'] is True
            assert rec['posterior_var'] == v
        lo = rec['x_star'] - Z90 * rec['post_sd']
        hi = rec['x_star'] + Z90 * rec['post_sd']
        assert lo <= rec['x_star'] <= hi


def test_shrinkage_increases_with_information():
    """Large samples get a larger weight on their own estimate, so less movement."""
    result, _ = primary()
    eb, params = result['eb'], result['eb_params']
    comp = {(c['player_id'], c['role'], c['context'], c['format']): c
            for c in result['components']}
    for p in params:
        if p['tau2_used'] <= 0:
            continue
        side = p['side']
        field = model.SIDES[side]
        small, large = [], []
        for (pid, role, ctx, fmt, s), rec in eb.items():
            if (role, ctx, fmt, s) != (p['role'], p['context'],
                                       p['format'], side):
                continue
            n = int(comp[(pid, role, ctx, fmt)][f'n_{field}'])
            item = (rec['shrinkage'], abs(rec['x_star'] - rec['x_raw']))
            if n <= 19:
                small.append(item)
            elif n >= 100:
                large.append(item)
        if len(small) >= 5 and len(large) >= 5:
            def med(xs):
                return sorted(xs)[len(xs) // 2]
            assert med([x[0] for x in small]) < med([x[0] for x in large]), p
            assert med([x[1] for x in small]) > med([x[1] for x in large]), p


def test_tau2_m_and_reml_are_reproducible_for_every_stratum():
    result, _ = primary()
    table = result['table']
    seen = 0
    for p in result['eb_params']:
        rows = [c for c in result['components']
                if (c['role'], c['context'], c['format'])
                == (p['role'], p['context'], p['format'])]
        field = 'pressure' if p['side'] == 'A' else 'baseline'
        ids, xs, vs = [], [], []
        for c in rows:
            key = (c['player_id'], p['role'], p['context'], p['format'], p['side'])
            if key not in table:
                continue
            ids.append(c['player_id'])
            xs.append(float(c[p['side']]))
            vs.append(model.variance_value(table[key], 'E2')[0])
        comp_by_id = {c['player_id']: c for c in rows}
        keep = [i for i, pid in enumerate(ids)
                if int(comp_by_id[pid][f'n_{field}']) >= model.KMIN]
        if len(keep) < 3:
            keep = list(range(len(ids)))
        assert len(keep) == p['n_estimation']
        tau, q, m = model.dl_tau2([xs[i] for i in keep], [vs[i] for i in keep])
        assert math.isclose(tau, p['tau2_dl'], rel_tol=1e-12, abs_tol=1e-15)
        assert math.isclose(m, p['m'], rel_tol=1e-12, abs_tol=1e-15)
        reml = model.reml_tau2([xs[i] for i in keep], [vs[i] for i in keep])
        assert math.isclose(reml, p['tau2_reml'], rel_tol=1e-9, abs_tol=1e-12)
        assert p['status'] == ('TAU2_ZERO_BOUNDARY' if tau == 0 else 'OK')
        seen += 1
    assert seen == 12
    assert sum(1 for p in result['eb_params'] if p['tau2_used'] == 0) == 3


def test_posterior_intervals_are_ordered_in_scores():
    _, scores = primary()
    for r in scores:
        if not r.get('scored'):
            continue
        for lo, pt, hi in (('A_ci90_low', 'A_star', 'A_ci90_high'),
                           ('B_ci90_low', 'B_star', 'B_ci90_high'),
                           ('S_ci90_low', 'S_star', 'S_ci90_high')):
            assert r[lo] <= r[pt] <= r[hi], (r['player_id'], pt)
        assert r['A_post_sd'] >= 0 and r['S_post_sd'] >= 0


# ------------------------------------------------------------- combination

def test_score_algebra_uses_approved_weights_only():
    _, scores = primary()
    for r in scores:
        if not r.get('scored'):
            continue
        assert math.isclose(r['S_raw'], r['A_raw'] - 0.30 * r['B_raw'],
                            rel_tol=1e-12, abs_tol=1e-12)
        assert math.isclose(r['S_star'], r['A_star'] - 0.30 * r['B_star'],
                            rel_tol=1e-12, abs_tol=1e-12)
        assert math.isclose(r['D_raw'], r['A_raw'] - r['B_raw'],
                            rel_tol=1e-12, abs_tol=1e-12)
    assert CFG['score']['primary_w'] == 0.70


def test_combination_is_two_stage_format_aware_inverse_variance():
    result, _ = primary()
    comb = {(r['player_id'], r['role'], r['context']): r
            for r in result['combined']}
    eb = result['eb']
    checked = 0
    for r in result['combined']:
        if r['n_formats'] != 2:
            continue
        pairs, shrunk_equal = [], []
        for fmt in model.FORMATS:
            ea = eb[(r['player_id'], r['role'], r['context'], fmt, 'A')]
            pairs.append((ea['x_star'], ea['posterior_var']))
            shrunk_equal.append(ea['x_star'])
        want, var, _ = model._iv(pairs)
        assert math.isclose(r['A_star'], want, rel_tol=1e-12, abs_tol=1e-15)
        assert math.isclose(r['v_A_star'], var, rel_tol=1e-12, abs_tol=1e-15)
        # Not a reprojection of a single combined EB fit: the two-stage value
        # differs from the plain mean of the format-specific shrunk estimates.
        if abs(shrunk_equal[0] - shrunk_equal[1]) > 1e-3:
            assert not math.isclose(r['A_star'], sum(shrunk_equal) / 2,
                                    rel_tol=1e-9, abs_tol=1e-9)
        checked += 1
    assert checked == log()['combine_checked'] == 275


def test_all_is_never_a_formal_combination():
    _, scores = primary()
    for r in scores:
        assert 'ALL' not in str(r.get('formats_present', ''))
        assert r.get('format_basis') in ('two_stage_iv', 'none')
    sens = read(REPORT / 'sensitivity_format.csv')
    all_rows = [r for r in sens if r['scenario'] == 'pooled_delivery_ALL']
    assert {r['format_scope'] for r in all_rows} == {'ALL'}
    assert all('not a formal combination' in r['note'] for r in all_rows)
    # The pooled-delivery sensitivity must actually score players.
    assert max(int(r['n_players']) for r in all_rows) > 300


def test_single_stage_sensitivity_is_reported_and_weaker():
    components, residuals = phase3()
    alt = run_phase4.core(components, residuals, single_stage=True)
    counts = {(role, ctx): sum(1 for r in alt['combined']
                              if r['role'] == role and r['context'] == ctx
                              and r['eligible'])
              for role, ctx in (('batter', 'chase'), ('bowler', 'chase'),
                                ('bowler', 'innings1_ahead_par'))}
    assert counts == {('batter', 'chase'): 0, ('bowler', 'chase'): 13,
                      ('bowler', 'innings1_ahead_par'): 0}
    for r in alt['combined']:
        assert r['reliability_status'] in ('OK', 'BLOCKED_TAU2_ZERO')


def test_format_specific_validation_passes_before_combination():
    rows = read(REPORT / 'format_validation.csv')
    assert len(rows) == 6
    for r in rows:
        assert int(r['n_players_pressure_ge_kmin']) >= 30
        assert r['validated'] == 'True'
    het = read(REPORT / 'format_heterogeneity.csv')
    assert len(het) == 3
    for r in het:
        assert int(r['n_both_formats']) >= 40
        assert 0.0 <= float(r['share_disagree']) <= 0.10
        assert float(r['tau2_between_format']) < float(r['median_v_combined'])


def test_separate_formats_are_preserved_as_a_sensitivity():
    rows = read(REPORT / 'sensitivity_format.csv')
    assert {r['scenario'] for r in rows} == {
        'pooled_delivery_ALL', 'separate_IPL', 'separate_T20I'}
    ipl = [r for r in rows if r['scenario'] == 'separate_IPL']
    by = {(r['role'], r['context']): int(r['n_eligible']) for r in ipl}
    assert by[('batter', 'chase')] == 16
    assert by[('bowler', 'chase')] == 47
    assert by[('bowler', 'innings1_ahead_par')] == 0
    t20 = [r for r in rows if r['scenario'] == 'separate_T20I']
    assert all(int(r['n_eligible']) == 0 for r in t20)


def test_eb_settings_sensitivity_covers_kmin_reml_and_single_stage():
    rows = read(REPORT / 'sensitivity_eb_settings.csv')
    scenarios = {r['scenario'] for r in rows}
    assert {'kmin_0', 'kmin_20', 'kmin_40', 'kmin_80', 'tau2_REML',
            'single_stage_combine'} <= scenarios
    count = {(r['scenario'], r['role'], r['context']): int(r['n_eligible'])
             for r in rows}
    assert count[('kmin_0', 'batter', 'chase')] == 47
    assert count[('kmin_40', 'batter', 'chase')] == 0
    assert count[('kmin_80', 'batter', 'chase')] == 0
    assert count[('tau2_REML', 'batter', 'chase')] == 0
    assert count[('tau2_REML', 'bowler', 'chase')] == 37
    assert count[('tau2_REML', 'bowler', 'innings1_ahead_par')] == 0


# ----------------------------------------------- eligibility, tiers, consistency

def test_eligibility_and_tiers_follow_the_approved_rule():
    _, scores = primary()
    for r in scores:
        if not r.get('scored'):
            continue
        assert r['eligible'] == (r['shrinkage_A'] >= 0.20)
        assert r['evidence_tier'] == model.tier(r['shrinkage_A'])
        assert model.tier(0.50) == 'High'
        assert model.tier(0.30) == 'Moderate'
        assert model.tier(0.20) == 'Limited'
        assert model.tier(0.199) == 'Insufficient'
    assert sum(1 for r in scored(scores, 'batter', 'chase') if r['eligible']) == 8
    assert sum(1 for r in scored(scores, 'bowler', 'chase') if r['eligible']) == 36
    assert sum(1 for r in scored(scores, 'bowler', 'innings1_ahead_par')
               if r['eligible']) == 0


def test_no_player_is_added_to_fill_a_top_ten():
    _, scores = primary()
    bat = scored(scores, 'batter', 'chase')
    wch = scored(scores, 'bowler', 'chase')
    assert len(model.top_ten(bat)) == 8
    assert len(model.top_ten(wch)) == 10
    assert len(model.top_ten(scored(scores, 'bowler', 'innings1_ahead_par'))) == 0
    # Nothing resembling a published final ranking exists yet.
    assert not (ROOT / 'outputs/final/top10.csv').exists()
    thresholds = read(REPORT / 'eligibility_by_threshold.csv')
    primary_b = [r for r in thresholds if r['role'] == 'batter'
                 and r['context'] == 'chase' and r['scope'] == 'combined'
                 and float(r['threshold']) == 0.20][0]
    assert int(primary_b['n_eligible']) == 8


def test_score_and_reliability_are_separate_outputs():
    _, scores = primary()
    fields = set(scores[0])
    perf = {'A_star', 'B_star', 'D_star', 'S_star', 'S_raw', 'A_raw', 'B_raw'}
    rel = {'shrinkage_A', 'shrinkage_B', 'evidence_tier', 'eligible',
           'reliability_status', 'A_post_sd', 'B_post_sd', 'S_post_sd',
           'consistency_positive_share', 'consistency_match_sd'}
    assert perf <= fields and rel <= fields
    # The score columns are reproducible without any reliability column.
    for r in scores:
        if not r.get('scored'):
            continue
        assert math.isclose(r['S_star'], r['A_star'] - 0.30 * r['B_star'],
                            rel_tol=1e-12, abs_tol=1e-12)
    import inspect
    score_src = inspect.getsource(model.combine_formats)
    assert 'consistency' not in score_src
    assert 'SCORE_D_COEF' in score_src
    formula = [ln.strip() for ln in score_src.splitlines()
               if ln.strip().startswith('s_star =')][0]
    for reliability_token in ('tier', 'shrink', 'eligible', 'consistency', 'ci90'):
        assert reliability_token not in formula


def test_consistency_is_descriptive_only():
    _, scores = primary()
    for r in scores:
        if not r.get('scored'):
            continue
        assert r['consistency_k'] == model.CONSISTENCY_K == 5
        if r['consistency_positive_share'] not in ('', None):
            assert 0.0 <= float(r['consistency_positive_share']) <= 1.0
    import inspect
    for fn in (model.combine_formats, model.single_stage_combine):
        assert 'consistency' not in inspect.getsource(fn)
    assert 'consistency' not in inspect.getsource(model.tier)


# ------------------------------------------------------- scope and preservation

def test_contexts_stay_separate_and_ph3_01_is_carried():
    _, scores = primary()
    assert not [r for r in scores if r['role'] == 'batter'
                and r['context'] != 'chase']
    assert {r['context'] for r in scores if r['role'] == 'bowler'} == {
        'chase', 'innings1_ahead_par'}
    for r in scores:
        assert '+' not in r['context']
        if r['role'] == 'bowler' and r['context'] == 'innings1_ahead_par' \
                and r.get('scored'):
            assert 'PH3-01' in r['notes']
            assert 'separate' in r['notes']


def test_phase4_sources_never_reference_excluded_flags():
    sources = '\n'.join((ROOT / 'src/reliability' / name).read_text(encoding='utf-8')
                        for name in ('model.py', 'run_phase4.py', '__init__.py'))
    forbidden = ('press_bat_par', 'press_bat_collapse', 'press_bat_union',
                 'press_chase_broad', 'press_chase_fallback_f2',
                 'press_bowl_broad_ahead', 'pressure_batter', 'pressure_bowler')
    for name in forbidden:
        assert name not in sources, f'excluded flag referenced: {name}'


def test_phase3_inputs_are_unchanged():
    manifest = {}
    for line in (ROOT / 'reports/audit_bundle/sha256_outputs.txt').read_text(
            encoding='utf-8').splitlines():
        if not line.strip():
            continue
        digest, path = line.split(None, 1)
        manifest[path.strip()] = digest
    for rel in ('./data/processed/player_components.csv',
                './data/processed/player_match_residuals.csv',
                './tests/test_phase3_performance.py'):
        assert hashlib.sha256((ROOT / rel[2:]).read_bytes()).hexdigest() \
            == manifest[rel], rel


def test_outputs_are_deterministic_and_match_the_run_log():
    result, scores = primary()
    components, residuals = phase3()
    second = run_phase4.core(components, residuals)
    scores2 = run_phase4.score_rows(
        components, second['combined'],
        model.consistency_rows(second['groups']['A']), second['eb_params'])
    fields = run_phase4.SCORE_FIELDS
    h1 = hashlib.sha256(
        run_phase4.csv_bytes([r for r in scores if r['role'] == 'batter'], fields)
        + run_phase4.csv_bytes([r for r in scores if r['role'] == 'bowler'], fields)
    ).hexdigest()
    h2 = hashlib.sha256(
        run_phase4.csv_bytes([r for r in scores2 if r['role'] == 'batter'], fields)
        + run_phase4.csv_bytes([r for r in scores2 if r['role'] == 'bowler'], fields)
    ).hexdigest()
    assert h1 == h2
    assert h1[:16] == log()['repro_hash_1'] == log()['repro_hash_2']
    assert log()['repro_identical'] is True


def test_score_files_carry_the_same_players_as_the_pipeline():
    result, scores = primary()
    by_key = {(r['role'], r['context'], r['player_id']): r for r in scores}
    for r in result['combined']:
        assert (r['role'], r['context'], r['player_id']) in by_key
    bat = read(SCORES_B)
    bowl = read(SCORES_W)
    assert {r['role'] for r in bat} == {'batter'}
    assert {r['context'] for r in bowl} == {'chase', 'innings1_ahead_par'}
    assert len(bat) + len(bowl) == len(scores)
    for r in bat + bowl:
        if r['scored'] == 'True':
            assert r['S_star'] not in ('', 'nan')
            assert r['shrinkage_A'] not in ('', 'nan')
