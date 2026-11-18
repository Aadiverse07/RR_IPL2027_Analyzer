import csv
import math
from collections import defaultdict
from pathlib import Path
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def test_innings1_flags_respect_scope_thresholds_and_dls_traceability():
    rows=read(ROOT/'data/interim/balls_pressure_innings1.csv')
    cfg=yaml.safe_load((ROOT/'config/methodology.yaml').read_text())
    assert len(rows)==97915
    assert {r['match_id'] for r in rows}.__len__()==788
    assert all(r['innings']=='1' for r in rows)
    minimum=cfg['pressure']['innings1_par']['minimum_legal_balls']
    zmin=cfg['pressure']['innings1_batting']['behind_par_z_min']
    ahead=cfg['pressure']['innings1_bowling']['ahead_par_z_min']
    collapse=cfg['pressure']['innings1_batting']['collapse_wickets_min']
    seen_exception=set()
    for r in rows:
        if r['match_id'] in {'24822','28334'}:
            assert r['unresolved_dls_outcome_exception']=='true'
            assert r['dls_exception_flag']=='DLS_UNRESOLVED_TARGET'
            seen_exception.add(r['match_id'])
        eligible=r['par_eligible']=='true'
        if int(r['legal_balls_before'])<minimum:
            assert not eligible and r['press_bat_par']=='false' and r['press_bowl_ahead']=='false'
        if r['z_behind_par']:
            assert math.isclose(float(r['z_behind_par']),-float(r['z_ahead_par']),abs_tol=1e-12)
            assert (r['press_bat_par']=='true')==(eligible and float(r['z_behind_par'])>=zmin)
            assert (r['press_bowl_ahead']=='true')==(eligible and float(r['z_ahead_par'])>=ahead)
        assert (r['press_bat_collapse']=='true')==(int(r['legal_balls_before'])>=minimum and int(r['wickets_in_previous_12_legal_balls'])>=collapse)
        assert (r['press_bat_union']=='true')==(r['press_bat_par']=='true' or r['press_bat_collapse']=='true')
    assert seen_exception=={'24822','28334'}

def test_par_is_leave_one_match_out_and_uses_configured_local_neighbours():
    rows=read(ROOT/'data/interim/balls_pressure_innings1.csv')
    cfg=yaml.safe_load((ROOT/'config/methodology.yaml').read_text())
    half=cfg['pressure']['innings1_par']['smoothing_neighbour_half_window']
    grouped=defaultdict(dict);formats={}
    for r in rows:
        mid=r['match_id'];formats[mid]=r['format'];n=int(r['legal_balls_before'])
        if n>0:grouped[mid].setdefault(n,int(r['team_runs_before']))
    target=next(r for r in rows if r['par_eligible']=='true' and int(r['legal_balls_before'])>=13)
    mid=target['match_id'];n=int(target['legal_balls_before']);fmt=target['format']
    sample=[]
    for other,points in grouped.items():
        if other==mid or formats[other]!=fmt:continue
        for neighbor in range(max(1,n-half),n+half+1):
            if neighbor in points:sample.append(points[neighbor])
    mean=sum(sample)/len(sample)
    sd=(sum((x-mean)**2 for x in sample)/len(sample))**0.5
    assert math.isclose(float(target['par_runs_loo']),mean,rel_tol=0,abs_tol=1e-12)
    assert math.isclose(float(target['par_sd_loo']),sd,rel_tol=0,abs_tol=1e-12)
    assert sd>0
