"""Grouped out-of-fold chase model and leverage for eligible matches.

Uses a small, regularized logistic model implemented with NumPy so the
feature set, folds, and calibration are inspectable. DLS-unresolved chase
innings and Super Over final-winner labels are excluded from model fitting.
"""
from __future__ import annotations
import csv, json, math, random
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[2]
BALLS=ROOT/'data/processed/balls_primary.csv'
CONFIG=ROOT/'config/methodology.yaml'
OUT=ROOT/'data/interim/chase_oof_predictions.csv'
REPORT=ROOT/'reports/phase_2'

def read_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write_rows(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else []
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def numeric_features(need,target,remaining,wickets,legal_limit):
    need=np.maximum(np.asarray(need,dtype=float),0.0)
    target=np.maximum(np.asarray(target,dtype=float),1.0)
    remaining=np.asarray(remaining,dtype=float)
    wickets=np.asarray(wickets,dtype=float)
    rr=6.0*need/np.maximum(remaining,1.0)
    return np.column_stack((np.log1p(need),need/target,rr,remaining/legal_limit,wickets/10.0))

def feature_matrix_from_rows(rows,legal_limit):
    """Read only approved pre-delivery chase fields; never inspect outcomes."""
    return numeric_features([int(r['runs_needed_before']) for r in rows],[int(r['target']) for r in rows],
        [int(r['legal_balls_remaining']) for r in rows],[10-int(r['wickets_lost_before']) for r in rows],legal_limit)

def apply_terminal_probabilities(probabilities,need,remaining,wickets_available):
    p=np.asarray(probabilities,dtype=float).copy()
    need=np.asarray(need,dtype=float);remaining=np.asarray(remaining,dtype=float);wickets_available=np.asarray(wickets_available,dtype=float)
    p[need<=0]=1.0
    p[(need>0)&((remaining<=0)|(wickets_available<=0))]=0.0
    return p

def sigmoid(z):
    z=np.clip(z,-35,35)
    return 1.0/(1.0+np.exp(-z))

def fit_logistic(x,y,l2,max_iter,tol):
    mean=x.mean(axis=0);scale=x.std(axis=0);scale=np.where(scale>1e-10,scale,1.0)
    z=(x-mean)/scale
    design=np.column_stack((np.ones(len(z)),z))
    beta=np.zeros(design.shape[1],dtype=float)
    # The objective uses mean negative log-likelihood, so scale the configured
    # L2 penalty by n. Without this, a unit penalty overwhelms the data gradient.
    penalty=np.eye(design.shape[1])*(l2/len(y));penalty[0,0]=0
    for _ in range(max_iter):
        p=sigmoid(design@beta)
        grad=design.T@(p-y)/len(y)+penalty@beta
        weights=np.maximum(p*(1-p),1e-8)
        hess=(design.T*weights)@design/len(y)+penalty
        try:step=np.linalg.solve(hess,grad)
        except np.linalg.LinAlgError:step=np.linalg.lstsq(hess,grad,rcond=None)[0]
        beta-=step
        if np.max(np.abs(step))<tol:break
    return {'mean':mean,'scale':scale,'beta':beta}

def predict(model,x):
    z=(x-model['mean'])/model['scale']
    return sigmoid(np.column_stack((np.ones(len(z)),z))@model['beta'])

def metrics(y,p,bins,clip):
    y=np.asarray(y,dtype=int);p=np.clip(np.asarray(p,dtype=float),clip,1-clip)
    n=len(y);pos=int(y.sum());neg=n-pos
    if n==0:return {'n':0,'auc':'','brier':'','log_loss':'','ece':'','calibration_slope':''}
    order=np.argsort(p,kind='mergesort');ranks=np.empty(n,dtype=float);ranks[order]=np.arange(1,n+1)
    # Average ranks preserve the standard AUC definition when predictions tie.
    unique,inv,cnt=np.unique(p,return_inverse=True,return_counts=True)
    starts=np.cumsum(np.r_[0,cnt[:-1]])+1
    avg=starts+(cnt-1)/2
    ranks=avg[inv]
    auc=(float(ranks[y==1].sum())-pos*(pos+1)/2)/(pos*neg) if pos and neg else ''
    brier=float(np.mean((p-y)**2));ll=float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p)))
    edges=np.linspace(0,1,bins+1);ece=0.0
    for i in range(bins):
        mask=(p>=edges[i])&((p<edges[i+1]) if i<bins-1 else (p<=edges[i+1]))
        if mask.any():ece+=float(mask.mean())*abs(float(p[mask].mean())-float(y[mask].mean()))
    logits=np.log(p/(1-p)).reshape(-1,1)
    slope_model=fit_logistic(logits,y.astype(float),0.0,80,1e-7)
    slope=float(slope_model['beta'][1]/slope_model['scale'][0])
    return {'n':n,'auc':auc,'brier':brier,'log_loss':ll,'ece':ece,'calibration_slope':slope}

def calibration_tables(records,cfg):
    bins=int(cfg['pressure']['chase']['calibration_bins']);clip=float(cfg['pressure']['chase']['probability_clip'])
    keys=[('ALL','ALL')]+sorted({(r['format'],r['phase']) for r in records})
    metrics_rows=[];decile_rows=[]
    for fmt,phase in keys:
        subset=[r for r in records if (fmt=='ALL' or r['format']==fmt) and (phase=='ALL' or r['phase']==phase)]
        y=np.array([int(r['label']) for r in subset]);p=np.array([float(r['p_win']) for r in subset])
        m=metrics(y,p,bins,clip)
        metrics_rows.append({'format':fmt,'phase':phase,**m})
        if len(p):
            order=np.argsort(p,kind='mergesort')
            for d,ix in enumerate(np.array_split(order,bins),1):
                if len(ix):decile_rows.append({'format':fmt,'phase':phase,'decile':d,'n':len(ix),'mean_predicted':float(p[ix].mean()),'observed_win_rate':float(y[ix].mean()),'absolute_deviation':abs(float(p[ix].mean())-float(y[ix].mean()))})
    return metrics_rows,decile_rows

def grouped_folds(match_ids,k,seed):
    mids=sorted(set(match_ids),key=lambda x:int(x))
    random.Random(seed).shuffle(mids)
    return {mid:i%k for i,mid in enumerate(mids)}

def prepare():
    cfg=yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    rows=read_rows(BALLS)
    k=int(cfg['pressure']['chase']['calibration_folds']);seed=int(cfg['random_seed'])
    excluded_ids=set(str(x) for x in cfg['data_quality_exceptions']['phase2_exclude_chase_match_ids'])
    chase=[];exclusion=Counter()
    for r in rows:
        if int(r['innings'])!=2:continue
        mid=r['match_id']
        if r.get('dls_exception_flag')=='DLS_UNRESOLVED_TARGET':exclusion['DLS_UNRESOLVED_TARGET']+=1;continue
        if mid in excluded_ids:exclusion['OWNER_APPROVED_CHASE_EXCLUSION']+=1;continue
        if 'super over' in r.get('source_result_preserved','').lower():exclusion['SUPER_OVER_FINAL_RESULT_LABEL']+=1;continue
        if not r.get('target') or not r.get('label_only_batting_side_won'):
            exclusion['MISSING_APPROVED_TARGET_OR_LABEL']+=1;continue
        chase.append(r)
    if not chase:raise RuntimeError('No eligible chase deliveries for model fitting.')
    match_label={}
    for r in chase:
        mid=r['match_id'];y=int(r['label_only_batting_side_won']=='true')
        if mid in match_label and match_label[mid]!=y:raise ValueError(f'inconsistent chase labels for {mid}')
        match_label[mid]=y
    # Assign every primary match a fold so matches whose final winner came from
    # a Super Over can receive pressure-state predictions without entering fit.
    all_chase_ids={r['match_id'] for r in rows if int(r['innings'])==2}
    fold_by=grouped_folds(all_chase_ids,k,seed)
    legal_limit=int(cfg['innings']['legal_balls'])
    x=feature_matrix_from_rows(chase,legal_limit)
    y=np.array([int(r['label_only_batting_side_won']=='true') for r in chase],dtype=float)
    mids=np.array([r['match_id'] for r in chase]);folds=np.array([fold_by[m] for m in mids])
    raw_p=np.empty(len(chase),dtype=float);models={};fold_rows=[]
    for fold in range(k):
        test=folds==fold;train=~test
        if not test.any() or len(set(y[train]))<2:raise RuntimeError(f'fold {fold} is empty or has one outcome class')
        model=fit_logistic(x[train],y[train],float(cfg['pressure']['chase']['logistic_l2']),int(cfg['pressure']['chase']['logistic_max_iterations']),float(cfg['pressure']['chase']['logistic_tolerance']))
        models[fold]=model;raw_p[test]=predict(model,x[test])
        fold_rows.append({'fold':fold,'train_matches':len(set(mids[train])),'test_matches':len(set(mids[test])),'train_deliveries':int(train.sum()),'test_deliveries':int(test.sum()),'train_wins':int(y[train].sum()),'test_wins':int(y[test].sum())})
    records=[]
    for i,r in enumerate(chase):
        need=int(r['runs_needed_before']);remaining=int(r['legal_balls_remaining']);available=10-int(r['wickets_lost_before'])
        p=float(apply_terminal_probabilities([raw_p[i]],[need],[remaining],[available])[0])
        records.append({'match_id':r['match_id'],'innings_ball_num':r['innings_ball_num'],'format':r['format'],'phase':r['phase'],'label':int(y[i]),'p_win':p,'fold':int(folds[i]),'runs_needed_before':need,'target':r['target'],'legal_balls_remaining':remaining,'wickets_available':available})
    metrics_rows,decile_rows=calibration_tables(records,cfg)
    REPORT.mkdir(parents=True,exist_ok=True)
    write_rows(REPORT/'calibration_metrics.csv',metrics_rows)
    write_rows(REPORT/'calibration_deciles.csv',decile_rows)
    write_rows(REPORT/'chase_fold_summary.csv',fold_rows)
    write_rows(OUT,records)
    overall=metrics_rows[0]
    decile_max=max((float(r['absolute_deviation']) for r in decile_rows if r['format']=='ALL' and r['phase']=='ALL' and int(r['n'])>=int(cfg['pressure']['chase']['minimum_decile_count'])),default=0.0)
    summary={'eligible_matches':len(match_label),'eligible_deliveries':len(chase),'eligible_wins_by_match':sum(match_label.values()),'eligible_losses_by_match':len(match_label)-sum(match_label.values()),'excluded_chase_rows_by_reason':dict(exclusion),'folds':k,'random_seed':seed,'global_oof_metrics':overall,'max_global_decile_absolute_deviation_at_min_n':decile_max,
        'criteria':{'slope_min':cfg['pressure']['chase']['calibration_slope_min'],'slope_max':cfg['pressure']['chase']['calibration_slope_max'],'ece_max':cfg['pressure']['chase']['expected_calibration_error_max'],'max_decile_deviation':cfg['pressure']['chase']['decile_deviation_max'],'min_decile_count':cfg['pressure']['chase']['minimum_decile_count']},
        'calibration_pass':bool(cfg['pressure']['chase']['calibration_slope_min']<=overall['calibration_slope']<=cfg['pressure']['chase']['calibration_slope_max'] and overall['ece']<=cfg['pressure']['chase']['expected_calibration_error_max'] and decile_max<=cfg['pressure']['chase']['decile_deviation_max']),
        'model':'L2-regularized logistic regression; features are log1p(runs needed), runs-needed/target, required rate, legal balls remaining fraction, wickets available fraction; all sourced pre-delivery.'}
    (REPORT/'chase_model_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)))
    return summary,records,models,fold_by

def build_leverage(oof_records,models,fold_by,cfg):
    """Score eligible and Super Over-final chase states from pre-delivery fields."""
    rows=read_rows(BALLS);legal_limit=int(cfg['innings']['legal_balls'])
    excluded=set(str(x) for x in cfg['data_quality_exceptions']['phase2_exclude_chase_match_ids'])
    score_rows=[];reason_counts=Counter()
    for r in rows:
        if int(r['innings'])!=2:continue
        if r.get('dls_exception_flag')=='DLS_UNRESOLVED_TARGET' or r['match_id'] in excluded:
            reason_counts['DLS_UNRESOLVED_TARGET']+=1;continue
        if not r.get('target'):
            reason_counts['MISSING_TARGET']+=1;continue
        if 'super over' in r.get('source_result_preserved','').lower():
            reason_counts['SUPER_OVER_FINAL_RESULT_LABEL_SCORED_WITHOUT_LABEL_USE']+=1
        score_rows.append(r)
    oof={(r['match_id'],r['innings_ball_num']):r for r in oof_records}
    fold_total=defaultdict(Counter);fold_parts=defaultdict(Counter);broad_total=defaultdict(Counter);broad_parts=defaultdict(Counter)
    for r in rows:
        if int(r['innings'])!=2 or not r.get('target') or r.get('dls_exception_flag')=='DLS_UNRESOLVED_TARGET':continue
        if 'super over' in r.get('source_result_preserved','').lower():continue
        mid=r['match_id'];f=fold_by[mid]
        outcome=(int(r['team_total_runs']),int(str(r['is_wicket']).lower()=='true'),int(str(r['legal']).lower()=='true'))
        exact=(r['format'],r['phase'],int(r['wickets_lost_before']))
        broad=(r['format'],r['phase'])
        fold_total[exact][outcome]+=1;fold_parts[(f,exact)][outcome]+=1
        broad_total[broad][outcome]+=1;broad_parts[(f,broad)][outcome]+=1
    groups=defaultdict(list)
    for i,r in enumerate(score_rows):
        fold=fold_by[r['match_id']]
        groups[(fold,r['format'],r['phase'],int(r['wickets_lost_before']))].append(i)
    leverage=np.full(len(score_rows),np.nan);current_p=np.full(len(score_rows),np.nan);transition_n=np.zeros(len(score_rows),dtype=int);support=[]
    min_sample=int(cfg['pressure']['chase']['outcome_transition_min_sample'])
    for (fold,fmt,phase,wickets),ix in groups.items():
        key=(fmt,phase,wickets);dist=fold_total[key]-fold_parts[(fold,key)]
        source='PHASE_WICKETS'
        if sum(dist.values())<min_sample:
            bkey=(fmt,phase);dist=broad_total[bkey]-broad_parts[(fold,bkey)];source='PHASE_POOLED_WICKETS'
        ntrans=sum(dist.values())
        if ntrans<min_sample:
            support.append({'fold':fold,'format':fmt,'phase':phase,'wickets_lost':wickets,'states':len(ix),'transition_rows':ntrans,'support_status':'INSUFFICIENT_TRANSITIONS'})
            continue
        outcomes=list(dist.items());counts=np.array([n for _,n in outcomes],dtype=float);weights=counts/counts.sum()
        subset=[score_rows[i] for i in ix]
        need=np.array([int(r['runs_needed_before']) for r in subset],dtype=float)
        target=np.array([int(r['target']) for r in subset],dtype=float)
        remain=np.array([int(r['legal_balls_remaining']) for r in subset],dtype=float)
        available=np.array([10-int(r['wickets_lost_before']) for r in subset],dtype=float)
        model=models[fold]
        x=feature_matrix_from_rows(subset,legal_limit)
        pcur=predict(model,x)
        pcur=apply_terminal_probabilities(pcur,need,remain,available)
        for krow,i in enumerate(ix):
            rec=oof.get((score_rows[i]['match_id'],score_rows[i]['innings_ball_num']))
            if rec is not None:
                pcur[krow]=float(rec['p_win'])
        expected=np.zeros(len(ix),dtype=float)
        for (runs,wicket,islegal),prob in zip((x[0] for x in outcomes),weights):
            nneed=need-runs;nremain=remain-islegal;navail=available-wicket
            nx=numeric_features(nneed,target,nremain,navail,legal_limit)
            pn=predict(model,nx)
            pn=apply_terminal_probabilities(pn,nneed,nremain,navail)
            expected+=prob*np.abs(pn-pcur)
        leverage[ix]=expected;current_p[ix]=pcur;transition_n[ix]=ntrans
        support.append({'fold':fold,'format':fmt,'phase':phase,'wickets_lost':wickets,'states':len(ix),'transition_rows':ntrans,'support_status':source})
    qcore=float(cfg['pressure']['chase']['quantile_top']);qbroad=float(cfg['pressure']['chase']['broad_quantile_top'])
    qmethod=cfg['pressure']['chase'].get('quantile_method','linear')
    thresholds={};broad_thresholds={}
    for fmt,phase in sorted({(r['format'],r['phase']) for r in score_rows}):
        ix=[i for i,r in enumerate(score_rows) if r['format']==fmt and r['phase']==phase and not np.isnan(leverage[i])]
        if not ix:continue
        vals=leverage[ix]
        thresholds[(fmt,phase)]=float(np.quantile(vals,1-qcore,method=qmethod))
        broad_thresholds[(fmt,phase)]=float(np.quantile(vals,1-qbroad,method=qmethod))
    out=[]
    for i,r in enumerate(score_rows):
        key=(r['format'],r['phase']);lev=leverage[i]
        core=bool(not np.isnan(lev) and lev>=thresholds[key]) if key in thresholds else False
        broad=bool(not np.isnan(lev) and lev>=broad_thresholds[key]) if key in broad_thresholds else False
        out.append({'match_id':r['match_id'],'innings_ball_num':r['innings_ball_num'],'format':r['format'],'season':r['season'],'phase':r['phase'],'fold':fold_by[r['match_id']],
            'p_win':current_p[i] if not np.isnan(current_p[i]) else '', 'leverage':lev if not np.isnan(lev) else '',
            'transition_rows':int(transition_n[i]),'press_chase':str(core).lower() if not np.isnan(lev) else '',
            'press_chase_broad':str(broad).lower() if not np.isnan(lev) else '',
            'chase_pressure_status':'ELIGIBLE' if not np.isnan(lev) else 'INSUFFICIENT_TRANSITION_SUPPORT',
            'dls_exception_flag':r.get('dls_exception_flag','')})
    write_rows(REPORT/'leverage_transition_support.csv',support)
    write_rows(ROOT/'data/interim/chase_leverage.csv',out)
    summary={'scored_chase_rows':len(out),'dls_exception_rows_excluded':reason_counts['DLS_UNRESOLVED_TARGET'],'super_over_final_result_rows_scored_without_label_use':reason_counts['SUPER_OVER_FINAL_RESULT_LABEL_SCORED_WITHOUT_LABEL_USE'],
        'rows_without_transition_support':sum(x['leverage']=='' for x in out),'core_thresholds_by_format_phase':{f'{a}|{b}':v for (a,b),v in thresholds.items()},
        'broad_thresholds_by_format_phase':{f'{a}|{b}':v for (a,b),v in broad_thresholds.items()},'outcome_transition_min_sample':min_sample,
        'transition_definition':'Empirical distribution of team_total_runs, source is_wicket, and legal status from training-fold deliveries grouped by format, phase, and wickets lost; fallback pools wickets within format × phase when an exact cell has fewer than configured minimum rows.'}
    (REPORT/'leverage_summary.json').write_text(json.dumps(summary,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+'\n')
    print(json.dumps(summary,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)))
    return summary

if __name__=='__main__':
    summary,records,models,fold_by=prepare()
    if summary['calibration_pass']:
        build_leverage(records,models,fold_by,yaml.safe_load(CONFIG.read_text(encoding='utf-8')))
