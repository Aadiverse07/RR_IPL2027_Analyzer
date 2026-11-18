import csv
import math
from pathlib import Path
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.pressure.chase import apply_terminal_probabilities,feature_matrix_from_rows,grouped_folds

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def test_chase_oof_excludes_owner_approved_dls_and_super_over_labels():
    rows=read(ROOT/'data/interim/chase_oof_predictions.csv')
    ids={r['match_id'] for r in rows}
    assert len(ids)==780
    assert not ids.intersection({'24822','28334','48610'})
    assert len(rows)==89167
    assert all(0.0<=float(r['p_win'])<=1.0 for r in rows)
    assert {int(r['fold']) for r in rows}==set(range(5))

def test_chase_calibration_meets_prespecified_global_criteria():
    import json
    summary=json.loads((ROOT/'reports/phase_2/chase_model_summary.json').read_text())
    cfg=yaml.safe_load((ROOT/'config/methodology.yaml').read_text())['pressure']['chase']
    metrics=summary['global_oof_metrics']
    assert summary['calibration_pass'] is True
    assert cfg['calibration_slope_min']<=metrics['calibration_slope']<=cfg['calibration_slope_max']
    assert metrics['ece']<=cfg['expected_calibration_error_max']
    assert summary['max_global_decile_absolute_deviation_at_min_n']<=cfg['decile_deviation_max']

def test_features_ignore_current_and_future_outcome_fields():
    a={'runs_needed_before':'24','target':'160','legal_balls_remaining':'18','wickets_lost_before':'6','label_only_batting_side_won':'true','is_wicket':'false','team_total_runs':'2'}
    b=dict(a,label_only_batting_side_won='false',is_wicket='true',team_total_runs='99')
    import numpy as np
    assert np.array_equal(feature_matrix_from_rows([a],120),feature_matrix_from_rows([b],120))

def test_chase_terminal_probabilities_are_deterministic():
    values=apply_terminal_probabilities([0.2,0.6,0.5,0.8],[0,4,7,1],[60,0,14,0],[10,5,0,0])
    assert list(values)==[1.0,0.0,0.0,0.0]

def test_grouped_folds_keep_each_match_in_one_fold():
    mapping=grouped_folds(['10','10','11','12','12','13'],5,123)
    assert mapping==grouped_folds(['10','11','12','13'],5,123)
    oof=read(ROOT/'data/interim/chase_oof_predictions.csv')
    assignment={}
    for r in oof:
        if r['match_id'] in assignment:assert assignment[r['match_id']]==r['fold']
        assignment[r['match_id']]=r['fold']
    fold_summary=read(ROOT/'reports/phase_2/chase_fold_summary.csv')
    assert len(assignment)==780
    assert all(int(r['train_matches'])+int(r['test_matches'])==780 for r in fold_summary)

def test_pressure_output_propagates_and_excludes_dls_chases():
    rows=read(ROOT/'data/processed/balls_pressure.csv')
    assert len(rows)==187968
    assert {r['match_id'] for r in rows}=={r['match_id'] for r in read(ROOT/'data/processed/matches_primary.csv')}
    by={m:set() for m in ['24822','28334']}
    first_innings_rows=0
    for r in rows:
        if r['innings']=='1':
            first_innings_rows+=1
            assert r['pressure_batter_without_innings1_union']=='false'
        if r['match_id'] in by:
            by[r['match_id']].add(r['innings'])
            assert r['dls_exception_flag']=='DLS_UNRESOLVED_TARGET'
            if r['innings']=='1':
                assert r['pressure_batter']!='' and r['pressure_bowler']!=''
            else:
                assert r['chase_pressure_status']=='DLS_UNRESOLVED_TARGET_EXCLUDED_FROM_CHASE_ANALYSIS'
                assert r['p_win']=='' and r['leverage']=='' and r['press_chase']==''
    assert all(v=={'1','2'} for v in by.values())
    assert first_innings_rows==97915
    assert '48610' not in {r['match_id'] for r in rows}

def test_provisional_f2_fallback_is_traceable_and_dls_safe():
    rows=read(ROOT/'data/processed/balls_pressure.csv')
    fallback=read(ROOT/'data/interim/chase_f2_fallback.csv')
    assert fallback
    assert not {r['match_id'] for r in fallback}.intersection({'24822','28334','48610'})
    chase_rows=[r for r in rows if r['innings']=='2' and r['chase_pressure_status']=='ELIGIBLE']
    assert chase_rows
    assert all(r['pressure_flag_status']=='PROVISIONAL-FALLBACK:F2' for r in chase_rows)
    assert all(r['pressure_batter']==r['press_chase_fallback_f2'] for r in chase_rows)
    assert all(r['pressure_batter_original']==r['press_chase_original'] for r in chase_rows)
    import json
    summary=json.loads((ROOT/'reports/phase_2/difficulty_validation_summary.json').read_text())
    assert summary['provisional_f2_applied'] is True
    assert summary['critical_chase_fallback_validation_pass'] is False

def test_no_role_or_phase_share_is_below_one_percent():
    counts=read(ROOT/'reports/phase_2/pressure_counts.csv')
    assert counts
    assert all(float(r['core_share'])>=0.01 for r in counts)
