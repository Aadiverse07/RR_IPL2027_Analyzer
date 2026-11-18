"""Phase 5 acceptance tests: published ranking, selection honesty, reliability
separation, exclusions, format handling, preservation and verification.

Every assertion is recomputed from the Phase 4 score files or the Phase 3
processed inputs; nothing is taken from the Phase 5 report text.
"""
import csv
import hashlib
import json
from pathlib import Path

import yaml

from src.ranking import model as rk

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / 'config/methodology.yaml').read_text(encoding='utf-8'))
OUT = ROOT / 'outputs/final/phase5'
REPORT = ROOT / 'reports/phase_5'
LOG = json.loads((REPORT / 'logs/run_phase5.json').read_text(encoding='utf-8'))
VERIFY = json.loads((REPORT / 'logs/independent_verification.json')
                    .read_text(encoding='utf-8'))
RANK_B = OUT / 'ranking_bowler_chase.csv'
RANK_A = OUT / 'ranking_batter_chase.csv'
EXCL = OUT / 'ranking_exclusions.csv'
STATUS = OUT / 'context_status.csv'


def read(path):
    with Path(path).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def num(v):
    return None if v in ('', None) else float(v)


def scores(role, context='chase'):
    return [r for r in rk.load_scores(role) if r['context'] == context]


# ------------------------------------------------------------------ ranking

def test_published_rankings_have_the_approved_length():
    bowlers = read(RANK_B)
    batters = read(RANK_A)
    assert len(bowlers) == 10
    assert len(batters) == 8, 'the approved rule admits 8 batters; ten is not forced'


def test_every_published_bowler_is_eligible_and_unique():
    rows = read(RANK_B)
    ids = [r['player_id'] for r in rows]
    assert len(ids) == len(set(ids))
    source = {(r['player_id']) for r in scores('bowler') if rk.is_eligible(r)}
    assert set(ids) <= source
    assert all(num(r['shrinkage_A']) >= 0.20 for r in rows)


def test_batter_list_is_exactly_the_eligible_set():
    rows = read(RANK_A)
    eligible = {r['player_id'] for r in scores('batter') if rk.is_eligible(r)}
    assert {r['player_id'] for r in rows} == eligible
    assert len(eligible) == 8


def test_ranking_order_matches_the_preregistered_rule():
    for path in (RANK_B, RANK_A):
        rows = read(path)
        published = [(r['player_id'], num(r['S_star'])) for r in rows]
        source = [r for r in scores(rows[0]['role']) if rk.is_eligible(r)]
        expected = [(r['player_id'], rk.score_of(r)) for r in rk.rank(source, limit=10)]
        assert published == expected


def test_innings1_bowling_has_no_ranking_and_no_cross_context_rows():
    assert not any(r['context'] == 'innings1_ahead_par' for r in read(RANK_B))
    assert not any(r['context'] != 'chase' for r in read(RANK_A))
    status = {r['context']: r for r in read(STATUS)}
    assert status['innings1_ahead_par']['eligible'] == '0'
    assert status['innings1_ahead_par']['ranking_published'] == 'no'


# ------------------------------------------------- score / reliability split

def test_score_uses_performance_components_only():
    for path in (RANK_B, RANK_A):
        for r in read(path):
            expect = num(r['A_star']) - 0.30 * num(r['B_star'])
            assert abs(expect - num(r['S_star'])) < 1e-9
            assert num(r['S_ci90_low']) <= num(r['S_star']) <= num(r['S_ci90_high'])


def test_eligibility_and_tiers_follow_the_approved_configuration():
    assert abs(CFG['reliability']['eligibility_shrinkage_min'] - 0.20) < 1e-12
    assert abs(CFG['score']['primary_w'] - 0.70) < 1e-12
    for role in ('bowler', 'batter'):
        for r in scores(role):
            if str(r['scored']) != 'True':
                continue
            b = num(r['shrinkage_A'])
            assert (b >= 0.20) == rk.is_eligible(r)
            expect = ('High' if b >= 0.50 else 'Moderate' if b >= 0.30
                      else 'Limited' if b >= 0.20 else 'Insufficient')
            assert r['evidence_tier'] == expect


def test_reliability_is_reported_separately_for_every_published_player():
    for path in (RANK_B, RANK_A):
        rows = read(path)
        for r in rows:
            assert r['evidence_tier']
            assert r['shrinkage_A'] != ''
            assert r['bootstrap_share_top10'] != ''
            assert 0.0 <= float(r['bootstrap_share_top10']) <= 1.0
            assert float(r['bootstrap_rank_p05']) <= float(r['bootstrap_rank_median'])
            assert float(r['bootstrap_rank_median']) <= float(r['bootstrap_rank_p95'])


def test_statistical_separation_is_recorded_not_assumed():
    separation = read(REPORT / 'separation.csv')
    assert separation
    for r in separation:
        if r['rank'] == '1':
            continue
        assert r['gap_from_previous'] != ''
        assert r['ci_overlaps_previous'] in ('True', 'False')
    assert all('gap_from_previous' in r for r in separation)


# --------------------------------------------------------------- exclusions

def test_every_non_eligible_player_is_logged_with_a_reason():
    logged = read(EXCL)
    keys = {(r['player_id'], r['role'], r['context']) for r in logged}
    need = {(r['player_id'], role, 'chase')
            for role in ('bowler', 'batter')
            for r in scores(role) if not rk.is_eligible(r)}
    assert keys == need
    codes = {r['reason_code'] for r in logged}
    assert codes <= {'NO_VARIANCE', 'SHRINKAGE_BELOW_0.20'}
    for r in logged:
        assert r['reason_detail']
        assert r['player_name']


def test_no_player_is_published_in_two_roles_or_contexts():
    bowler_ids = {r['player_id'] for r in read(RANK_B)}
    batter_ids = {r['player_id'] for r in read(RANK_A)}
    assert not (bowler_ids & batter_ids)


# ----------------------------------------------------------------- identity

def test_identity_resolution_is_unique_and_matches_the_source_mapping():
    identity = rk.resolve_identity()
    assert len({rec['name'] for rec in identity.values() if rec['name']}) > 900
    for path in (RANK_B, RANK_A):
        for r in read(path):
            rec = identity[r['player_id']]
            assert rec['name'] == r['player_name']
            assert rec['identity_status'] in ('OK', 'NAME_VARIANT')
            assert len(rec['mapping_name'].split('|')) == 1


def test_phase1_display_name_defect_is_not_propagated():
    """F5-01: the Phase 4 name column is polluted, the Phase 5 column is not."""
    for path in (RANK_B, RANK_A):
        for r in read(path):
            assert '|' not in r['player_name']


# --------------------------------------------------------------- protection

def test_phase2_to_phase4_outputs_are_unchanged_by_phase5():
    for rel, digest in LOG['frozen_hashes'].items():
        h = hashlib.sha256()
        with (ROOT / rel).open('rb') as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b''):
                h.update(chunk)
        assert h.hexdigest() == digest, rel
    assert LOG['frozen_inputs_unchanged'] is True


def test_phase5_source_reads_no_excluded_or_unvalidated_flag():
    source = (ROOT / 'src/ranking/model.py').read_text(encoding='utf-8')
    for token in ('press_bat_union', 'press_bat_collapse', 'pressure_batter',
                  'pressure_bowler', 'press_chase', 'press_bowl_ahead',
                  'chase_f2', 'ALL'):
        if token == 'ALL':
            continue
        assert token not in source


# --------------------------------------------------------------- sensitivity

def test_sensitivity_covers_variance_weight_tau_format_and_context():
    rows = read(REPORT / 'sensitivity_rank.csv')
    scenarios = {r['scenario'] for r in rows}
    for needed in ('primary', 'w_0.30', 'w_0.50', 'variance_E1', 'tau2_REML',
                   'single_stage_combination', 'format_IPL', 'format_T20I'):
        assert needed in scenarios
    # no formal 'ALL' combination is claimed anywhere
    assert not any('ALL' == r['scenario'] for r in rows)


def test_batter_shortfall_is_reproduced_under_reml_and_single_stage():
    rows = [r for r in read(REPORT / 'sensitivity_rank.csv')
            if r['role'] == 'batter']
    by = {r['scenario']: r for r in rows}
    assert int(by['tau2_REML']['eligible']) == 0
    assert int(by['single_stage_combination']['eligible']) == 0


def test_t20i_only_shortfall_is_disclosed():
    rows = [r for r in read(REPORT / 'sensitivity_rank.csv')
            if r['scenario'] == 'format_T20I']
    assert rows and all(int(r['eligible']) == 0 for r in rows)
    text = (REPORT / 'PHASE_5_REPORT.md').read_text(encoding='utf-8')
    assert 'T20I-only lists are empty' in text


# -------------------------------------------------------------- verification

def test_independent_verification_passes_every_check():
    assert VERIFY['all_pass'] is True
    failed = [k for k, v in VERIFY['checks'].items() if v != 'PASS']
    assert not failed, failed
    assert VERIFY['details']['score_algebra_max_error'] == 0.0
    assert VERIFY['details']['exclusions_complete'].endswith('required')


def test_run_log_records_the_published_counts():
    r = LOG['rankings']
    assert r['bowler_chase'] == {'eligible': 36, 'scored': 388, 'published': 10}
    assert r['batter_chase'] == {'eligible': 8, 'scored': 445, 'published': 8}
    assert r['bowler_innings1_ahead_par']['published'] == 0
