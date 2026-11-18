"""Proposed Phase 2 F2 chase fallback; outputs are explicitly provisional."""
from __future__ import annotations
import csv,json
from collections import defaultdict
from pathlib import Path
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[2]
BALLS=ROOT/'data/processed/balls_primary.csv'
REPORT=ROOT/'reports/phase_2'
OUT=ROOT/'data/interim/chase_f2_fallback.csv'

def read_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_rows(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else []
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def build():
    cfg=yaml.safe_load((ROOT/'config/methodology.yaml').read_text(encoding='utf-8'))
    rate_scale=int(cfg['innings']['rate_scale_balls'])
    rows=[r for r in read_rows(BALLS) if r['innings']=='2']
    excluded=set(str(x) for x in cfg['data_quality_exceptions']['phase2_exclude_chase_match_ids'])
    sample=[]
    for r in rows:
        if r['match_id'] in excluded or r.get('dls_exception_flag')=='DLS_UNRESOLVED_TARGET':continue
        if not r.get('required_run_rate_before'):continue
        if r.get('legal')=='true':sample.append(r)
    # Context expectation is the format × phase mean scoring rate, leave-one-match-out.
    by_context=defaultdict(lambda:[0,0]);by_context_match=defaultdict(lambda:[0,0])
    for r in sample:
        k=(r['format'],r['phase']);mid=r['match_id'];runs=int(r['team_total_runs'])
        by_context[k][0]+=runs;by_context[k][1]+=1
        by_context_match[(k,mid)][0]+=runs;by_context_match[(k,mid)][1]+=1
    scored=[]
    for r in rows:
        mid=r['match_id'];key=(mid,'2',r['innings_ball_num'])
        if mid in excluded or r.get('dls_exception_flag')=='DLS_UNRESOLVED_TARGET' or not r.get('required_run_rate_before'):
            continue
        k=(r['format'],r['phase']);total_runs,total_legal=by_context[k];own_runs,own_legal=by_context_match[(k,mid)]
        denom=total_legal-own_legal
        if denom<=0:continue
        expected=rate_scale*(total_runs-own_runs)/denom
        score=float(r['required_run_rate_before'])-expected
        scored.append({'match_id':mid,'innings_ball_num':r['innings_ball_num'],'format':r['format'],'phase':r['phase'],'f2_pressure_score':score,'phase_expected_scoring_rate_loo':expected,
            'required_run_rate_before':r['required_run_rate_before'],'dls_exception_flag':r.get('dls_exception_flag','')})
    top=float(cfg['pressure']['chase']['quantile_top']);method=cfg['pressure']['chase']['quantile_method']
    groups=defaultdict(list)
    for r in scored:groups[(r['format'],r['phase'])].append(r)
    thresholds={}
    for key,items in groups.items():thresholds[key]=float(np.quantile([x['f2_pressure_score'] for x in items],1-top,method=method))
    for r in scored:r['press_chase_fallback_f2']=str(r['f2_pressure_score']>=thresholds[(r['format'],r['phase'])]).lower()
    write_rows(OUT,scored)
    summary={'fallback':'F2','label':'PROVISIONAL-FALLBACK','rows':len(scored),'eligible_matches':len({r['match_id'] for r in scored}),
        'formula':'required_run_rate_before - leave-one-match-out format × phase expected scoring rate',
        'threshold':'top quartile within format × phase', 'thresholds_by_format_phase':{f'{a}|{b}':v for (a,b),v in thresholds.items()},
        'source_exclusions':['24822','28334'],
        'methodology_status':'Proposed fallback from Phase 2 prompt; not owner-approved; original leverage flags remain preserved.'}
    (REPORT/'f2_fallback_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':build()
