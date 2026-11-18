import csv
import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.phase0_audit.state import iter_pre_delivery_states

ROOT=Path(__file__).resolve().parents[1]

def row(runs=0, extras1=0, extras2=0, wicket='false', extras='None'):
    return {'runs':str(runs),'extras1_runs':str(extras1),'extras_2_runs':str(extras2),'is_wicket':wicket,'extras_type':extras}

def assert_current_outcome_does_not_change_own_state(rows):
    original=[dict(r) for r in rows]
    states=list(iter_pre_delivery_states(original))
    for i in range(len(original)):
        changed=[dict(r) for r in original]
        changed[i].update(runs='777',extras1_runs='8',extras_2_runs='9',is_wicket='true')
        assert list(iter_pre_delivery_states(changed))[i]==states[i]

def test_perturbing_current_delivery_cannot_change_its_own_pre_state():
    seq=[row(1),row(0,1,0,'false','wide'),row(0,1,0,'true','Overstep'),row(4),row(0,0,0,'true')]
    assert_current_outcome_does_not_change_own_state(seq)

def test_first_ball_wide_no_ball_and_legal_ball_12_to_13_window():
    seq=[row() for _ in range(13)]
    seq[2]=row(0,1,0,'true','Overstep') # wicket on no-ball is not a legal-ball-window wicket
    seq[5]=row(0,1,0,'false','wide')
    seq[11]=row(0,0,0,'true')
    states=list(iter_pre_delivery_states(seq))
    assert states[0]['legal_balls_before']==0
    assert states[12]['legal_balls_before']==10
    assert states[12]['wickets_previous_12_legal']==1
    assert states[12]['legal_balls_remaining_120']==110

def test_source_sample_1000_rows_prestate_is_outcome_independent():
    p=ROOT/'data/raw/Data Pack/ball_by_ball.csv'
    with p.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        groups={}
        for r in reader:
            key=(r['match_id'],r['innings'])
            groups.setdefault(key,[]).append(r)
            if sum(map(len,groups.values()))>=1200: break
    checked=0
    for rows in groups.values():
        baseline=list(iter_pre_delivery_states(rows))
        for i in range(len(rows)):
            altered=[dict(r) for r in rows]
            altered[i].update(runs='777',extras1_runs='8',extras_2_runs='9',is_wicket='true')
            assert list(iter_pre_delivery_states(altered))[i]==baseline[i]
            checked+=1
            if checked>=1000: return
    assert checked>=1000
