"""Phase 2 pressure-vs-ordinary validation with match-clustered bootstrap CIs."""
from __future__ import annotations
import csv, json
from collections import defaultdict
from pathlib import Path
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[2]
PRESS=ROOT/'data/processed/balls_pressure.csv'
REPORT=ROOT/'reports/phase_2'

def read_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_rows(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else []
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def yes(v):return str(v).strip().lower()=='true'

def _summarize_stats(stats):
    # Last axis: sum flagged, count flagged, sum ordinary, count ordinary.
    sf,cf,so,co=np.moveaxis(stats,-1,0)
    with np.errstate(divide='ignore',invalid='ignore'):
        return sf/cf-so/co

def clustered_bootstrap(data,flag_name,role,broad,metrics,cfg,seed_offset=0):
    innings=1 if flag_name.startswith('pressure_bat') or flag_name.startswith('pressure_bowl') else 2
    selected=[]
    for r in data:
        if int(r['innings'])!=innings:continue
        if innings==2 and r['chase_pressure_status']!='ELIGIBLE':continue
        if role=='batter' and not yes(r['faced']):continue
        flag=yes(r.get(flag_name,''))
        if flag_name not in r or r.get(flag_name,'')=='':continue
        selected.append((r,flag))
    if not selected:return [],{'status':'NO_ELIGIBLE_ROWS'}
    mids=sorted({r['match_id'] for r,_ in selected},key=lambda x:int(x));mi={m:i for i,m in enumerate(mids)}
    cellkeys=sorted({(r['phase'],int(r['wickets_lost_before']),r['format']) for r,_ in selected})
    ci={k:i for i,k in enumerate(cellkeys)};metricnames=['runs','dot','dismissal']
    stat=np.zeros((len(mids),len(cellkeys),len(metricnames),4),dtype=float)
    for r,flag in selected:
        m=mi[r['match_id']];c=ci[(r['phase'],int(r['wickets_lost_before']),r['format'])]
        values=[int(r['team_total_runs']),int(int(r['team_total_runs'])==0),int(yes(r['is_wicket']))]
        offset=0 if flag else 2
        for j,value in enumerate(values):stat[m,c,j,offset]+=value;stat[m,c,j,offset+1]+=1
    cell_totals=stat.sum(axis=0)
    point=_summarize_stats(cell_totals)
    nflag=cell_totals[:,:,1];nordinary=cell_totals[:,:,3]
    weights=nflag.copy()
    weights=np.where((nflag>0)&(nordinary>0),weights,0)
    pooled_point=np.nansum(point*weights,axis=0)/weights.sum(axis=0)
    reps=int(cfg['pressure']['chase']['bootstrap_replicates']);rng=np.random.default_rng(int(cfg['random_seed'])+seed_offset)
    boot_cell=np.full((reps,len(cellkeys),len(metricnames)),np.nan)
    boot_pool=np.full((reps,len(metricnames)),np.nan)
    for b in range(reps):
        draw=rng.integers(0,len(mids),size=len(mids))
        mult=np.bincount(draw,minlength=len(mids))
        totals=np.tensordot(mult,stat,axes=(0,0))
        diff=_summarize_stats(totals)
        boot_cell[b]=diff
        valid=(totals[:,:,1]>0)&(totals[:,:,3]>0)&(weights>0)
        for j in range(len(metricnames)):
            w=np.where(valid[:,j],weights[:,j],0)
            if w.sum():boot_pool[b,j]=np.nansum(diff[:,j]*w)/w.sum()
    low=float(cfg['pressure']['chase']['bootstrap_ci_low']);high=float(cfg['pressure']['chase']['bootstrap_ci_high'])
    rows=[]
    def ci(v):
        v=v[np.isfinite(v)]
        return (float(np.quantile(v,low)),float(np.quantile(v,high))) if len(v) else ('','')
    for j,metric in enumerate(metricnames):
        lo,hi=ci(boot_pool[:,j]);rows.append({'definition':flag_name,'role':role,'scenario':'BROAD' if broad else 'CORE','group_level':'pooled_wickets_stratified','phase':'ALL','wickets_state':'ALL','format':'ALL','outcome_metric':metric,
            'n_flagged':int(nflag.sum()),'n_ordinary':int(nordinary.sum()),'difference':float(pooled_point[j]),'ci_low':lo,'ci_high':hi})
    for c,k in enumerate(cellkeys):
        for j,metric in enumerate(metricnames):
            if nflag[c,j]==0 or nordinary[c,j]==0:continue
            lo,hi=ci(boot_cell[:,c,j]);rows.append({'definition':flag_name,'role':role,'scenario':'BROAD' if broad else 'CORE','group_level':'phase_wickets_format','phase':k[0],'wickets_state':k[1],'format':k[2],
                'outcome_metric':metric,'n_flagged':int(nflag[c,j]),'n_ordinary':int(nordinary[c,j]),'difference':float(point[c,j]),'ci_low':lo,'ci_high':hi})
    return rows,{'status':'OK','matches':len(mids),'cells':len(cellkeys),'flagged':int(nflag.sum()),'ordinary':int(nordinary.sum())}

def build():
    cfg=yaml.safe_load((ROOT/'config/methodology.yaml').read_text(encoding='utf-8'));data=read_rows(PRESS)
    specs=[('pressure_batter','batter'),('pressure_bowler','bowler'),('press_chase','batter'),('press_chase','bowler'),
        ('press_chase_fallback_f2','batter'),('press_chase_fallback_f2','bowler'),
        ('pressure_batter_broad','batter'),('pressure_bowler_broad','bowler'),('press_chase_broad','batter'),('press_chase_broad','bowler')]
    allrows=[];summaries=[];offset=0
    for flag,role in specs:
        broad=flag.endswith('_broad')
        rows,summary=clustered_bootstrap(data,flag,role,broad,['runs','dot','dismissal'],cfg,offset)
        offset+=1;summaries.append({'flag':flag,'role':role,**summary});allrows.extend(rows)
    write_rows(REPORT/'difficulty_validation.csv',allrows)
    # Validation status is explicitly role-aware: batters expect lower runs and
    # higher dot/dismissal rates; bowlers expect higher runs conceded.
    expected={('batter','runs'):'lower',('batter','dot'):'higher',('batter','dismissal'):'higher',('bowler','runs'):'higher'}
    for r in allrows:
        direction=expected.get((r['role'],r['outcome_metric']),'reported_no_directional_gate')
        r['expected_direction']=direction
        lo=r['ci_low'];hi=r['ci_high'];diff=float(r['difference'])
        if direction=='lower':r['direction_check']='PASS' if float(hi)<0 else 'FAIL'
        elif direction=='higher':r['direction_check']='PASS' if float(lo)>0 else 'FAIL'
        else:r['direction_check']='REPORTED'
        r['significant_reversed_direction']=bool(direction=='lower' and float(lo)>0 or direction=='higher' and float(hi)<0)
    write_rows(REPORT/'difficulty_validation.csv',allrows)
    pooled=[r for r in allrows if r['group_level']=='pooled_wickets_stratified' and (r['role'],r['outcome_metric']) in expected]
    pooled_pass=all(r['direction_check']=='PASS' for r in pooled)
    by_definition={}
    for definition in sorted({r['definition'] for r in pooled}):
        subset=[r for r in pooled if r['definition']==definition]
        by_definition[definition]=bool(subset and all(r['direction_check']=='PASS' for r in subset))
    # The spec calls out phase × format cells with >=500 flagged rows.
    reversed_cells=[]
    for r in allrows:
        if r['group_level']=='phase_wickets_format' and int(r['n_flagged'])>=500 and r['significant_reversed_direction']:
            reversed_cells.append({k:r[k] for k in ['definition','role','phase','wickets_state','format','outcome_metric','n_flagged','difference','ci_low','ci_high']})
    core_chase_fallback_pass=by_definition.get('press_chase_fallback_f2',False)
    fallback_reversals=[r for r in reversed_cells if r['definition']=='press_chase_fallback_f2']
    chase_fallback_pass=bool(core_chase_fallback_pass and not fallback_reversals)
    summary={'comparison_sets':summaries,'pooled_expected_direction_ci_pass':pooled_pass,'validation_pass_by_definition':by_definition,'significant_reversed_cells_ge_500_flagged':reversed_cells,
        'validation_pass':bool(pooled_pass and not reversed_cells),'bootstrap_replicates':cfg['pressure']['chase']['bootstrap_replicates'],'ci_method':'match-clustered percentile bootstrap; pooled contrast is stratified by phase × exact wickets-lost state × format and weighted by flagged-row counts',
        'critical_chase_fallback_validation_pass':chase_fallback_pass,'critical_chase_fallback_reversals_ge_500':fallback_reversals,
        'directional_rules':{'batter':'lower runs per delivery, higher dot rate, higher is_wicket rate','bowler':'higher team runs conceded per delivery; dot and dismissal contrasts are reported without a directional gate'}}
    (REPORT/'difficulty_validation_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':build()
