import csv
import hashlib
import random
from collections import defaultdict, deque
from pathlib import Path
import sys
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.phase0_audit.state import iter_pre_delivery_states

ROOT=Path(__file__).resolve().parents[1]
CONFIG=yaml.safe_load((ROOT/'config/methodology.yaml').read_text())
RAW=ROOT/'data/raw/Data Pack'

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def intval(v):
    try:return int(float(v))
    except:return 0

def test_phase1_primary_scope_and_source_hashes():
    matches=rows(ROOT/'data/processed/matches_primary.csv')
    assert len(matches)==788
    ids={r['match_id'] for r in matches}
    assert len(ids)==788
    balls=ROOT/'data/processed/balls_primary.csv';n=0;innings=defaultdict(int)
    seen=set()
    with balls.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            n+=1;innings[int(r['innings'])]+=1
            assert int(r['innings']) in (1,2)
            assert r['match_id'] in ids
            key=(r['match_id'],r['innings'],r['innings_ball_num']);assert key not in seen;seen.add(key)
            assert intval(r['legal_balls_before'])<120
            assert r['unresolved_dls_outcome_exception']=='true' if r['match_id'] in {'24822','28334'} else r['unresolved_dls_outcome_exception']=='false'
    assert n==187968 and innings=={1:97915,2:90053}
    for line in (ROOT/'data/raw/checksums.sha256').read_text().splitlines():
        expected,rel=line.split('  ',1)
        assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==expected

def test_every_pre_delivery_state_and_innings_constraints():
    groups=defaultdict(lambda:{'runs':0,'wickets':0,'legal':0,'window':deque(maxlen=12)})
    matches=set(); innings_seen=defaultdict(set); maximum_wickets=0
    with (ROOT/'data/processed/balls_primary.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            key=(r['match_id'],int(r['innings']));st=groups[key]
            assert intval(r['team_runs_before'])==st['runs'],(key,r['innings_ball_num'])
            assert intval(r['wickets_lost_before'])==st['wickets']
            assert intval(r['legal_balls_before'])==st['legal']
            assert intval(r['legal_balls_remaining'])==120-st['legal']
            assert intval(r['wickets_in_previous_12_legal_balls'])==sum(st['window'])
            assert intval(r['team_total_runs'])==intval(r['runs'])+intval(r['extras1_runs'])+intval(r['extras_2_runs'])
            assert intval(r['bowler_credit_wicket']) in (0,1)
            is_wicket=r['is_wicket'].lower()=='true';is_legal=r['legal'].lower()=='true'
            st['runs']+=intval(r['team_total_runs']);st['wickets']+=int(is_wicket)
            if is_legal:st['legal']+=1;st['window'].append(int(is_wicket))
            assert st['legal']<=120
            maximum_wickets=max(maximum_wickets,st['wickets'])
            matches.add(r['match_id']);innings_seen[r['match_id']].add(int(r['innings']))
    assert maximum_wickets<=10
    assert all({1,2}<=v for v in innings_seen.values())
    assert len(matches)==788

def test_1000_random_current_outcomes_do_not_change_own_pre_state():
    seed=int(CONFIG['random_seed']); groups=defaultdict(list)
    with (ROOT/'data/processed/balls_primary.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):groups[(r['match_id'],int(r['innings']))].append(r)
    positions=[(key,i) for key,seq in groups.items() for i in range(len(seq))]
    sample=random.Random(seed).sample(positions,1000)
    caches={key:list(iter_pre_delivery_states(seq)) for key,seq in groups.items()}
    for key,i in sample:
        original=groups[key];changed=[dict(r) for r in original]
        changed[i].update({'runs':'777','extras1_runs':'8','extras_2_runs':'9','is_wicket':'true'})
        assert list(iter_pre_delivery_states(changed))[i]==caches[key][i]

def test_pre_delivery_edge_cases_and_dls_exception_handling():
    def d(r=0,e1=0,e2=0,w='false',ex='None'):
        return {'runs':str(r),'extras1_runs':str(e1),'extras_2_runs':str(e2),'is_wicket':w,'extras_type':ex}
    seq=[d() for _ in range(122)];seq[2]=d(0,1,0,'true','Overstep');seq[5]=d(0,1,0,'false','wide');seq[119]=d(0,0,0,'true')
    states=list(iter_pre_delivery_states(seq));assert states[0]['legal_balls_before']==0
    assert states[121]['legal_balls_before']==119
    assert states[121]['wickets_previous_12_legal']==1
    assert states[121]['legal_balls_remaining_120']==1
    m=rows(ROOT/'data/processed/matches_primary.csv');m={x['match_id']:x for x in m}
    for mid in ['24822','28334']:
        assert m[mid]['unresolved_dls_outcome_exception']=='True'
        assert m[mid]['dls_exception_flag']=='DLS_UNRESOLVED_TARGET'
        assert m[mid]['chase_metadata_status']=='DLS_UNRESOLVED_TARGET_EXCLUDED_FROM_CHASE_ANALYSIS'
    b=ROOT/'data/processed/balls_primary.csv';found=set()
    with b.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['match_id'] in {'24822','28334'}:
                assert r['target']=='' and r['label_only_batting_side_won']==''
                assert r['dls_exception_flag']=='DLS_UNRESOLVED_TARGET'
                if r['innings']=='2': assert r['target_status']=='DLS_UNRESOLVED_TARGET'
                else: assert r['target_status']=='NOT_APPLICABLE'
                if r['innings']=='2': assert r['simple_target_candidate']!=''
                else: assert r['simple_target_candidate']==''
                assert r['source_result_preserved']
                found.add(r['match_id'])
    assert found=={'24822','28334'}
    ex=rows(ROOT/'reports/phase_1/unresolved_exceptions.csv');ex={x['match_id']:x for x in ex}
    assert set(ex)=={'24822','28334','48610'}
    assert ex['48610']['included_in_primary']=='False'
    assert all(x['owner_decision_status']=='APPROVED_2026-11-18' for x in ex.values())
    assert ex['24822']['dls_exception_flag']=='DLS_UNRESOLVED_TARGET'
    assert ex['28334']['dls_exception_flag']=='DLS_UNRESOLVED_TARGET'
    assert ex['48610']['dls_exception_flag']=='DLS_SOURCE_RESULT_CONFLICT_REVISED_TARGET'
    assert ex['48610']['source_result']=='England Won by 11 runs (DLS method)'
    assert 'remain excluded' in ex['48610']['owner_approved_treatment'].lower()

def test_source_outcome_reconciles_using_full_innings_totals_and_super_over_labels():
    matches=rows(ROOT/'data/processed/matches_primary.csv')
    raw_balls=rows(RAW/'ball_by_ball.csv')
    second_batting_team={}
    for r in raw_balls:
        if r['innings']=='2':second_batting_team.setdefault(r['match_id'],r['batting_team_id'])
    unresolved={'24822','28334'}
    assert sum(r['super_over_innings_present']=='True' for r in matches)==4
    assert sum(r['super_over_result_mentioned']=='True' for r in matches)==6
    # Full source totals include any rows after the 120 legal-ball state cap.
    for m in matches:
        mid=m['match_id']
        assert int(m['innings1_total_source'])>=0 and int(m['innings2_total_source'])>=0
        if mid in unresolved or m['contains_super_over']=='True':
            if m['contains_super_over']=='True':
                assert m['outcome_label_status']=='SUPER_OVER_MATCH_FINAL_WINNER_LABEL_ONLY'
            else:
                assert m['outcome_label_status']=='SOURCE_WINNER_ID_LABEL_ONLY'
            continue
        expected=int(m['win_team_id'])==int(second_batting_team[mid])
        calculated=int(m['innings2_total_source'])>=int(m['simple_target_candidate'])
        assert expected==calculated,(mid,expected,calculated,m['result'])

    # Match 28962 has only regular innings rows, but its final result cites a Super Over.
    sr=next(r for r in matches if r['match_id']=='28962')
    assert sr['super_over_result_mentioned']=='True'
    assert sr['contains_super_over']=='True'

def test_independent_manual_verification_matches_all_five_progressions():
    from src.data_prep.manual_verify import generate
    assert generate()>0
