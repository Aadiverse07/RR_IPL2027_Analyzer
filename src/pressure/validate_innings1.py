"""Targeted, match-clustered validation of the four Phase 2 innings-1 flags.

Reads the already-built innings-1 state table; never fits or reads a chase model.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'data/interim/balls_pressure_innings1.csv'
OUT=ROOT/'reports/phase_2/first_innings_component_validation.csv'
SUMMARY=ROOT/'reports/phase_2/first_innings_component_validation_summary.json'
FLAGS=[
 ('press_bat_par','batter',{'runs':'lower','dot':'higher','dismissal':'higher'}),
 ('press_bat_collapse','batter',{'runs':'lower','dot':'higher','dismissal':'higher'}),
 ('press_bat_union','batter',{'runs':'lower','dot':'higher','dismissal':'higher'}),
 ('press_bowl_ahead','bowler',{'runs':'higher'}),
]
def read(path):
 with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(path,rows):
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def truth(v):return str(v).strip().lower()=='true'
def classify(direction,lo,hi):
 if direction=='lower':
  if hi<0:return 'PASS'
  if lo>0:return 'FAIL'
  return 'INCONCLUSIVE'
 if direction=='higher':
  if lo>0:return 'PASS'
  if hi<0:return 'FAIL'
  return 'INCONCLUSIVE'
 return 'NOT_GATED'
def main():
 cfg=yaml.safe_load((ROOT/'config/methodology.yaml').read_text())
 minimum=int(cfg['pressure']['innings1_par']['minimum_legal_balls'])
 reps=int(cfg['pressure']['chase']['bootstrap_replicates'])
 alpha_lo=float(cfg['pressure']['chase']['bootstrap_ci_low']);alpha_hi=float(cfg['pressure']['chase']['bootstrap_ci_high'])
 rng_seed=int(cfg['random_seed'])+8200
 src=read(SOURCE); rows=[]
 # Eligibility applies to every flag, including collapse. Batter opportunities exclude wides.
 for r in src:
  if int(r['legal_balls_before'])<minimum:continue
  rows.append(r)
 out=[]; gate={}; bootstrap_meta={'method':'match-clustered percentile bootstrap, 1000 replicates; within phase × wickets-lost × format contrasts weighted by eligible flagged deliveries','seed':rng_seed,'eligibility':'legal_balls_before >= configured 12 for all flags; batter excludes wides; bowler includes all deliveries'}
 for idx,(flag,role,directions) in enumerate(FLAGS):
  sample=[r for r in rows if role=='bowler' or truth(r['faced'])]
  flagged=[r for r in sample if truth(r[flag])]
  mids=sorted({r['match_id'] for r in sample},key=int);mi={m:i for i,m in enumerate(mids)}
  cells=sorted({(r['phase'],int(r['wickets_lost_before']),r['format']) for r in sample})
  ci={c:i for i,c in enumerate(cells)}
  # axes: match, phase/wickets/format cell, metric, [flag sum,count,ordinary sum,count]
  a=np.zeros((len(mids),len(cells),3,4),dtype=float)
  for r in sample:
   m=mi[r['match_id']];c=ci[(r['phase'],int(r['wickets_lost_before']),r['format'])]
   vals=(int(r['team_total_runs']),int(int(r['team_total_runs'])==0),int(truth(r['is_wicket'])))
   off=0 if truth(r[flag]) else 2
   for j,v in enumerate(vals):a[m,c,j,off]+=v;a[m,c,j,off+1]+=1
  # Bootstrap all-match samples once per flag; resampling is by match cluster.
  rng=np.random.default_rng(rng_seed+idx)
  draws=rng.integers(0,len(mids),size=(reps,len(mids)))
  mult=np.stack([np.bincount(d,minlength=len(mids)) for d in draws])
  def contrasts(tot):
   sf,cf,so,co=np.moveaxis(tot,-1,0)
   with np.errstate(divide='ignore',invalid='ignore'):
    return sf/cf-so/co
  all_total=a.sum(axis=0)
  point=contrasts(all_total)
  boot=np.empty((reps,len(cells),3),dtype=float)
  for b in range(reps):boot[b]=contrasts(np.tensordot(mult[b],a,axes=(0,0)))
  scopes=[('POOLED','ALL','ALL','ALL',list(range(len(cells))))]
  for phase in sorted({c[0] for c in cells}):
   for fmt in sorted({c[2] for c in cells}):
    ix=[j for j,c in enumerate(cells) if c[0]==phase and c[2]==fmt]
    if ix:scopes.append(('PHASE_FORMAT',phase,'ALL',fmt,ix))
  for cell_idx,cell in enumerate(cells):
   scopes.append(('PHASE_WICKETS_FORMAT',cell[0],cell[1],cell[2],[cell_idx]))
  metrics=['runs','dot','dismissal']
  per_flag=[]
  for scope,phase,wickets_scope,fmt,ix in scopes:
   # Weighted stratified contrasts use flagged sample count per wickets-state cell,
   # matching the project's pre-specified stratification and weighting.
   weights=all_total[ix,:,1]
   valid=(all_total[ix,:,1]>0)&(all_total[ix,:,3]>0)
   for j,metric in enumerate(metrics):
    if scope=='PHASE_WICKETS_FORMAT':
     cidx=ix[0]
     estimate=float(point[cidx,j])
     bvals=boot[:,cidx,j].tolist()
     nf=int(all_total[cidx,j,1]);no=int(all_total[cidx,j,3])
    elif scope=='PHASE_FORMAT':
     w=np.where(valid[:,j],weights[:,j],0)
     denom=w.sum()
     estimate=float(np.nansum(point[ix,j]*w)/denom) if denom else float('nan')
     bvals=[]
     for b in range(reps):
      bt=np.tensordot(mult[b],a,axes=(0,0))
      bp=contrasts(bt)
      bw=np.where((bt[ix,j,1]>0)&(bt[ix,j,3]>0)&(weights[:,j]>0),weights[:,j],0)
      bvals.append(float(np.nansum(bp[ix,j]*bw)/bw.sum()) if bw.sum() else np.nan)
     nf=int(all_total[ix,j,1].sum());no=int(all_total[ix,j,3].sum())
    else:
     # Overall stratified pooled contrast.
     w=np.where(valid[:,j],weights[:,j],0);denom=w.sum()
     estimate=float(np.nansum(point[ix,j]*w)/denom) if denom else float('nan')
     bvals=[]
     for b in range(reps):
      bt=np.tensordot(mult[b],a,axes=(0,0));bp=contrasts(bt)
      bw=np.where((bt[ix,j,1]>0)&(bt[ix,j,3]>0)&(weights[:,j]>0),weights[:,j],0)
      bvals.append(float(np.nansum(bp[ix,j]*bw)/bw.sum()) if bw.sum() else np.nan)
     nf=int(all_total[ix,j,1].sum());no=int(all_total[ix,j,3].sum())
    vals=np.asarray(bvals);vals=vals[np.isfinite(vals)]
    lo,hi=(float(np.quantile(vals,alpha_lo)),float(np.quantile(vals,alpha_hi))) if len(vals) else (float('nan'),float('nan'))
    direction=directions.get(metric,'NOT_GATED')
    status=classify(direction,lo,hi)
    if scope=='POOLED': scoped=sample
    elif scope=='PHASE_FORMAT': scoped=[r for r in sample if r['phase']==phase and r['format']==fmt]
    else: scoped=[r for r in sample if r['phase']==phase and r['format']==fmt and int(r['wickets_lost_before'])==int(wickets_scope)]
    scoped_flagged=[r for r in scoped if truth(r[flag])]
    row={'definition':flag,'role':role,'scope':scope,'phase':phase,'wickets_state':wickets_scope,'format':fmt,'metric':metric,
      'eligible_deliveries':len(scoped),'eligible_innings':len({(r['match_id'],r['innings']) for r in scoped}),
      'eligible_matches':len({r['match_id'] for r in scoped}),'flagged_deliveries':len(scoped_flagged),
      'flagged_innings':len({(r['match_id'],r['innings']) for r in scoped_flagged}),'flagged_matches':len({r['match_id'] for r in scoped_flagged}),
      'flag_share':len(scoped_flagged)/len(scoped) if scoped else 0,'n_flagged_in_scope':nf,'n_ordinary_in_scope':no,
      'contrast_flagged_minus_ordinary':estimate,'ci95_low':lo,'ci95_high':hi,'expected_direction':direction,'status':status,
      'bootstrap_valid_replicates':len(vals)}
    out.append(row)
    if scope=='POOLED' and direction!='NOT_GATED':per_flag.append(status)
  reversed_cells=[r for r in out if r['definition']==flag and r['scope']=='PHASE_WICKETS_FORMAT' and int(r['n_flagged_in_scope'])>=500 and r['status']=='FAIL']
  pooled_criterion='PASS' if per_flag and all(s=='PASS' for s in per_flag) else ('FAIL' if 'FAIL' in per_flag or reversed_cells else 'INCONCLUSIVE')
  gate[flag]={'pooled_directional_statuses':per_flag,'significantly_reversed_phase_wickets_format_cells_ge_500':len(reversed_cells),'reversed_cells':[{'phase':r['phase'],'wickets_state':r['wickets_state'],'format':r['format'],'metric':r['metric'],'n_flagged':r['n_flagged_in_scope'],'contrast':r['contrast_flagged_minus_ordinary'],'ci95_low':r['ci95_low'],'ci95_high':r['ci95_high']} for r in reversed_cells],'pooled_criterion':'FAIL' if reversed_cells else pooled_criterion}
 write(OUT,out)
 summary={'eligibility':bootstrap_meta['eligibility'],'eligible_population':{'all_roles_deliveries':len(rows),'matches':len({r['match_id'] for r in rows}),'innings':len({(r['match_id'],r['innings']) for r in rows})},
  'bootstrap':bootstrap_meta,'definitions':gate,'acceptance_note':'PASS requires all gated pooled metrics to have 95% CIs strictly in expected direction AND no phase-format scope with >=500 flagged deliveries and a significant reversed direction. A CI containing zero is INCONCLUSIVE, not FAIL. See detailed CSV.'}
 (SUMMARY).write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
