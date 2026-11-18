"""Phase 3 acceptance tests: directions, algebra, scope separation, recalculation."""
import csv
import json
from pathlib import Path

import yaml

from src.performance import model

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / 'data/processed/player_components.csv'
DESCRIPTIVES = ROOT / 'data/processed/player_descriptives.csv'
REPORT = ROOT / 'reports/phase_3'
CFG = yaml.safe_load((ROOT / 'config/methodology.yaml').read_text())


def read(path):
    with Path(path).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def ball(**kw):
    base = dict(match_id='1', innings='2', striker_id='', non_striker_id='',
                bowler_id='', batting_type='RHB', pace_or_spin='Pace',
                batting_order_group='source_2', format='IPL', phase='middle_overs',
                wickets_lost_before='1', legal_balls_remaining='30',
                team_runs_before='50', runs='0', extras1_runs='0', extras_2_runs='0',
                bowler_charged_runs='0', faced='true', dismissed_batter_id='',
                bowler_credit_wicket='0', par_eligible='', press_chase='false',
                press_bowl_ahead='', chase_pressure_status='ELIGIBLE',
                is_wicket='false', dismissal_type='', is_four='false', is_six='false')
    base.update(kw)
    return {k: base[k] for k in model.FIELDS}


def synthetic():
    rows = []
    for i in range(400):
        rows.append(ball(striker_id='9001', bowler_id='9003', runs='6',
                         bowler_charged_runs='6', is_six='true', press_chase='true'))
        rows.append(ball(striker_id='9002', bowler_id='9004', runs='0',
                         bowler_charged_runs='0', press_chase='true'))
        rows.append(ball(striker_id='9001', bowler_id='9003', runs='6',
                         bowler_charged_runs='6', is_six='true', press_chase='false'))
        rows.append(ball(striker_id='9002', bowler_id='9004', runs='0',
                         bowler_charged_runs='0', press_chase='false'))
    return rows


LAM0 = {p: {'value': 0.0, 'status': 'TEST'} for p in
        ('powerplay_overs', 'middle_overs', 'death_overs')}


def test_direction_batter_scores_six_ranks_above_dot_batter():
    recs, _, _ = model.build_deliveries(synthetic(), LAM0)
    comp = {(c['player_id'], c['role']): c for c in model.aggregate_components(recs)}
    six, dot = comp[('9001', 'batter')], comp[('9002', 'batter')]
    assert six['A'] > dot['A']
    assert six['S_raw'] > dot['S_raw']
    assert six['A'] == 3.0 and dot['A'] == -3.0


def test_direction_bowler_conceding_sixes_ranks_below_dot_bowler():
    recs, _, _ = model.build_deliveries(synthetic(), LAM0)
    comp = {(c['player_id'], c['role']): c for c in model.aggregate_components(recs)}
    sixer, dot = comp[('9003', 'bowler')], comp[('9004', 'bowler')]
    assert sixer['S_raw'] < dot['S_raw']
    assert sixer['A'] == -3.0 and dot['A'] == 3.0


def test_bowler_gets_no_credit_for_run_out_and_batter_is_not_charged_a_ball():
    rows = [ball(striker_id='1', non_striker_id='2', bowler_id='3',
                 dismissed_batter_id='2', dismissal_type='RunOut', is_wicket='true',
                 bowler_credit_wicket='0')]
    batter_obs = model.mu_observations(rows, 'batter')
    dismissal_only = [o for o in batter_obs if o['player_id'] == '2']
    assert len(dismissal_only) == 1
    assert dismissal_only[0]['dis'] == 1.0
    assert dismissal_only[0]['faced_obs'] is False
    bowler_obs = model.mu_observations(rows, 'bowler')
    assert bowler_obs[0]['wk'] == 0.0


def test_required_component_fields_have_no_nan_or_blanks():
    rows = read(COMPONENTS)
    assert rows
    required = ('player_id', 'role', 'context', 'format', 'n_pressure', 'n_baseline',
                'n_matches', 'A', 'B', 'D', 'S_raw')
    for r in rows:
        for field in required:
            assert r[field] != '', (r['player_id'], field)
            if field not in ('player_id', 'role', 'context', 'format'):
                assert not (isinstance(r[field], str) and r[field].lower() == 'nan')


def test_score_algebra_and_weights():
    cfg = CFG['performance']['score_weights']
    rows = read(COMPONENTS)
    for r in rows:
        A, B, D, S = (float(r[k]) for k in ('A', 'B', 'D', 'S_raw'))
        assert abs(D - (A - B)) < 1e-12
        assert abs(S - (cfg['A'] * A + cfg['D'] * D)) < 1e-12
    assert cfg['A'] == 0.70 and cfg['D'] == 0.30


def test_contexts_are_separate_and_batters_have_no_innings1_context():
    rows = read(COMPONENTS)
    assert {r['context'] for r in rows} == {'chase', 'innings1_ahead_par'}
    for r in rows:
        if r['role'] == 'batter':
            assert r['context'] == 'chase'
        if r['context'] == 'innings1_ahead_par':
            assert r['role'] == 'bowler'
    assert not any(r['role'] == 'batter' and r['context'] == 'innings1_ahead_par'
                   for r in rows)


def test_no_combined_or_excluded_flags_are_consumed():
    sources = '\n'.join(p.read_text() for p in (ROOT / 'src/performance').glob('*.py'))
    forbidden = ('pressure_batter', 'pressure_bowler', 'press_bat_union',
                 'press_bat_par', 'press_bat_collapse', 'press_chase_fallback_f2',
                 'press_chase_broad', 'press_bowl_broad_ahead')
    for name in forbidden:
        assert name not in sources, f'excluded flag referenced: {name}'
    for r in read(COMPONENTS):
        assert 'fallback' not in r['context'] and 'broad' not in r['context']


def test_lambda_estimates_have_intervals_and_stability_is_recorded():
    rows = read(REPORT / 'lambda_estimates.csv')
    assert len(rows) == 9
    for r in rows:
        assert float(r['ci_low']) < float(r['ci_high'])
        assert int(r['n_matches']) > 300
    primary = json.loads((REPORT / 'logs/run_phase3.json').read_text())['lambda_primary']
    by = {(r['phase'], r['scope']): r for r in rows}
    for phase, rec in primary.items():
        pooled = by[(phase, 'ALL')]
        formats = [by[(phase, f)] for f in ('IPL', 'T20I')]
        stable = float(pooled['ci_low']) > 0 and all(float(f['ci_low']) > 0 for f in formats)
        if stable:
            assert rec['status'] == 'ESTIMATED'
            assert abs(rec['value'] - float(pooled['lambda'])) < 1e-12
        else:
            assert rec['status'].startswith('PROVISIONAL')
            assert rec['value'] == 0.0


def test_league_means_reported_for_every_context():
    rows = read(REPORT / 'league_means.csv')
    keys = {(r['role'], r['context'], r['format']) for r in rows}
    assert {('batter', 'chase'), ('bowler', 'chase'),
            ('bowler', 'innings1_ahead_par')} <= {(k[0], k[1]) for k in keys}
    for r in rows:
        for f in ('player_mean_A', 'player_mean_B', 'player_mean_D',
                  'delivery_weighted_A', 'delivery_weighted_B'):
            assert r[f] not in ('', 'nan')
        assert int(r['n_pressure_deliveries']) > 0


def test_descriptives_are_separate_and_never_feed_the_score():
    comp_fields = set(read(COMPONENTS)[0])
    desc_fields = set(read(DESCRIPTIVES)[0])
    assert {'A', 'B', 'D', 'S_raw'}.isdisjoint(desc_fields)
    assert {'strike_rate', 'dot_pct', 'boundary_pct'}.isdisjoint(comp_fields)
    assert {'A', 'B', 'D', 'S_raw'} <= comp_fields


def test_sensitivity_covers_lambda_and_mu_variants():
    rows = read(REPORT / 'sensitivity_lambda_mu.csv')
    variants = {r['variant'] for r in rows}
    assert {'lambda_multiplier_0.0', 'lambda_multiplier_0.5',
            'lambda_multiplier_1.5', 'mu_out_of_fold',
            'drop_nonstriker_runouts'} == variants
    tested = [r for r in rows if r['role'] == 'batter' and r['context'] == 'chase'
              and r['variant'] == 'lambda_multiplier_0.0'][0]
    assert int(tested['n_players']) >= 50
    assert float(tested['spearman_vs_primary']) > 0.5


def test_manual_recalculation_matches_pipeline():
    rows = read(REPORT / 'manual_recalc.csv')
    assert len(rows) >= 6
    assert sum(1 for r in rows if r['role'] == 'batter') >= 3
    assert sum(1 for r in rows if r['role'] == 'bowler') >= 3
    assert {r['context'] for r in rows if r['role'] == 'bowler'} == \
        {'chase', 'innings1_ahead_par'}
    worst = max(float(r['max_abs_delta']) for r in rows)
    assert worst < 1e-9
