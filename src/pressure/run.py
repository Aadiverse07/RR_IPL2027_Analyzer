"""Run Phase 2 state construction after Phase 1 has passed."""
from __future__ import annotations
import csv,json
from collections import defaultdict,deque,Counter
from pathlib import Path
import yaml
from src.pressure import innings1,chase,fallback,validate

ROOT=Path(__file__).resolve().parents[2]
BALLS=ROOT/'data/processed/balls_primary.csv'
OUT=ROOT/'data/processed/balls_pressure.csv'
REPORT=ROOT/'reports/phase_2'

def read_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_rows(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else []
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def yes(v):return str(v).strip().lower()=='true'
def key(r):return (r['match_id'],r['innings'],r['innings_ball_num'])

def build():
    cfg=yaml.safe_load((ROOT/'config/methodology.yaml').read_text(encoding='utf-8'))
    innings1.build()
    chase_summary,oof_records,models,fold_by=chase.prepare()
    if not chase_summary['calibration_pass']:
        raise RuntimeError('Chase OOF calibration failed preset criteria; no chase pressure flags were built.')
    leverage_summary=chase.build_leverage(oof_records,models,fold_by,cfg)
    phase1=read_rows(BALLS)
    first=read_rows(ROOT/'data/interim/balls_pressure_innings1.csv')
    leverage=read_rows(ROOT/'data/interim/chase_leverage.csv')
    first_by={key(r):r for r in first};lev_by={(r['match_id'],'2',r['innings_ball_num']):r for r in leverage}
    win=int(cfg['pressure']['broad']['collapse_legal_ball_window'])
    zmin=float(cfg['pressure']['broad']['behind_par_z_min'])
    collapse_min=int(cfg['pressure']['broad']['collapse_wickets_min'])
    histories=defaultdict(lambda:deque(maxlen=win));broad_collapse={}
    for r in phase1:
        if r['innings']!='1':continue
        mid=r['match_id'];broad_collapse[key(r)]=sum(histories[mid])>=collapse_min
        if yes(r['legal']):histories[mid].append(int(yes(r['is_wicket'])))
    output=[]
    for r in phase1:
        row=dict(r); k=key(r)
        if r['innings']=='1':
            f=first_by[k];bc=broad_collapse[k]
            broad_par=bool(f['par_eligible']=='true' and f.get('z_behind_par') not in ('','null') and float(f['z_behind_par'])>=zmin)
            broad_bowl=bool(f['par_eligible']=='true' and f.get('z_ahead_par') not in ('','null') and float(f['z_ahead_par'])>=float(cfg['pressure']['broad']['ahead_par_z_min']))
            row.update({'par_runs_loo':f['par_runs_loo'],'par_sd_loo':f['par_sd_loo'],'z_behind_par':f['z_behind_par'],'z_ahead_par':f['z_ahead_par'],'par_eligible':f['par_eligible'],
                'press_bat_par':f['press_bat_par'],'press_bat_collapse':f['press_bat_collapse'],'press_bat_union':f['press_bat_union'],'press_bowl_ahead':f['press_bowl_ahead'],
                'press_bat_broad_par':str(broad_par).lower(),'press_bat_broad_collapse':str(bc).lower(),'press_bat_broad_union':str(broad_par or bc).lower(),'press_bowl_broad_ahead':str(broad_bowl).lower(),
                'p_win':'','leverage':'','press_chase':'','press_chase_broad':'','chase_pressure_status':'NOT_APPLICABLE_INNINGS_1',
                'pressure_batter':f['press_bat_union'],'pressure_bowler':f['press_bowl_ahead'],
                'pressure_batter_original':f['press_bat_union'],'pressure_bowler_original':f['press_bowl_ahead'],
                'press_chase_original':'','press_chase_fallback_f2':'','pressure_batter_fallback_f2':'','pressure_bowler_fallback_f2':'','pressure_flag_status':'APPROVED_CORE',
                'pressure_batter_without_innings1_union':'false','pressure_bowler_without_innings1_ahead':'false',
                'pressure_batter_broad':str(broad_par or bc).lower(),'pressure_bowler_broad':str(broad_bowl).lower(),
                'pressure_batter_without_innings1_broad':'false','pressure_bowler_without_innings1_broad':'false'})
        else:
            lv=lev_by.get(k)
            if r.get('dls_exception_flag')=='DLS_UNRESOLVED_TARGET':
                status='DLS_UNRESOLVED_TARGET_EXCLUDED_FROM_CHASE_ANALYSIS';p=lev=core=broad=''
            elif lv is None:
                status='NO_VALIDATED_CHASE_STATE';p=lev=core=broad=''
            else:
                status=lv['chase_pressure_status'];p=lv['p_win'];lev=lv['leverage'];core=lv['press_chase'];broad=lv['press_chase_broad']
            row.update({'par_runs_loo':'','par_sd_loo':'','z_behind_par':'','z_ahead_par':'','par_eligible':'',
                'press_bat_par':'','press_bat_collapse':'','press_bat_union':'','press_bowl_ahead':'',
                'press_bat_broad_par':'','press_bat_broad_collapse':'','press_bat_broad_union':'','press_bowl_broad_ahead':'',
                'p_win':p,'leverage':lev,'press_chase':core,'press_chase_broad':broad,'chase_pressure_status':status,
                'pressure_batter':core,'pressure_bowler':core,'pressure_batter_original':core,'pressure_bowler_original':core,
                'press_chase_original':core,'press_chase_fallback_f2':'','pressure_batter_fallback_f2':'','pressure_bowler_fallback_f2':'','pressure_flag_status':status,
                'pressure_batter_without_innings1_union':core,'pressure_bowler_without_innings1_ahead':core,
                'pressure_batter_broad':broad,'pressure_bowler_broad':broad,
                'pressure_batter_without_innings1_broad':broad,'pressure_bowler_without_innings1_broad':broad})
        output.append(row)
    write_rows(OUT,output)
    original_validation=validate.build()
    use_f2=not original_validation.get('validation_pass_by_definition',{}).get('press_chase',False)
    f2_summary=None;final_validation=original_validation
    if use_f2:
        (REPORT/'difficulty_validation_original_leverage.csv').write_text((REPORT/'difficulty_validation.csv').read_text())
        (REPORT/'difficulty_validation_summary_original_leverage.json').write_text((REPORT/'difficulty_validation_summary.json').read_text())
        f2_summary=fallback.build();f2_by={(r['match_id'],'2',r['innings_ball_num']):r for r in read_rows(ROOT/'data/interim/chase_f2_fallback.csv')}
        for r in output:
            if r['innings']!='2':continue
            fr=f2_by.get(key(r));flag=fr['press_chase_fallback_f2'] if fr else ''
            r['press_chase_fallback_f2']=flag
            r['pressure_batter_fallback_f2']=flag;r['pressure_bowler_fallback_f2']=flag
            if flag!='':
                r['pressure_batter']=flag;r['pressure_bowler']=flag
                r['pressure_batter_without_innings1_union']=flag;r['pressure_bowler_without_innings1_ahead']=flag
                r['pressure_flag_status']='PROVISIONAL-FALLBACK:F2'
        write_rows(OUT,output)
        final_validation=validate.build()
    else:
        for r in output:
            if r['innings']=='2':r['pressure_batter_fallback_f2']='';r['pressure_bowler_fallback_f2']=''
        write_rows(OUT,output)
    final_validation['provisional_f2_applied']=bool(use_f2)
    final_validation['provisional_f2_summary']=f2_summary
    (REPORT/'difficulty_validation_summary.json').write_text(json.dumps(final_validation,indent=2)+'\n')
    # Counts and per-player distributions. Batters use faced rows; bowlers use all rows.
    counts=defaultdict(lambda:{'eligible':0,'core':0,'broad':0})
    player=defaultdict(lambda:{'core':0,'broad':0,'matches':set(),'format':None})
    for r in output:
        inn=int(r['innings']);fmt=r['format'];phase=r['phase']
        for role,flag,field in [('batter','pressure_batter','striker_id'),('bowler','pressure_bowler','bowler_id')]:
            eligible=(role=='bowler' or yes(r['faced']))
            if not eligible:continue
            if inn==2 and r['chase_pressure_status']=='DLS_UNRESOLVED_TARGET_EXCLUDED_FROM_CHASE_ANALYSIS':continue
            core=yes(r.get(flag,''));broad=yes(r.get(flag+'_broad',''))
            rec=counts[(role,inn,phase,fmt)];rec['eligible']+=1;rec['core']+=int(core);rec['broad']+=int(broad)
            p=player[(role,r[field],fmt)];p['core']+=int(core);p['broad']+=int(broad)
            if core:p['matches'].add(r['match_id'])
            p['format']=fmt
    count_rows=[]
    for (role,inn,phase,fmt),v in sorted(counts.items()):
        count_rows.append({'role':role,'innings':inn,'phase':phase,'format':fmt,'eligible_deliveries':v['eligible'],'core_pressure_deliveries':v['core'],'core_share':v['core']/v['eligible'] if v['eligible'] else '',
            'broad_pressure_deliveries':v['broad'],'broad_share':v['broad']/v['eligible'] if v['eligible'] else ''})
    write_rows(REPORT/'pressure_counts.csv',count_rows)
    no_flag=defaultdict(lambda:{'eligible':0,'original_pressure':0,'sensitivity_pressure':0})
    for r in output:
        if r['innings']!='1' or not yes(r['faced']):continue
        x=no_flag[(r['format'],r['phase'])];x['eligible']+=1;x['original_pressure']+=int(yes(r['pressure_batter_original']))
        x['sensitivity_pressure']+=int(yes(r['pressure_batter_without_innings1_union']))
    write_rows(REPORT/'first_innings_no_flag_sensitivity.csv',[{'role':'batter','innings':1,'format':fmt,'phase':phase,'eligible_deliveries':x['eligible'],
        'core_pressure_deliveries':x['original_pressure'],'no_innings1_batting_flag_deliveries':x['sensitivity_pressure'],
        'sensitivity_status':'FIRST_INNINGS_BATTING_PRESSURE_FLAG_WITHHELD_FOR_SENSITIVITY'} for (fmt,phase),x in sorted(no_flag.items())])
    player_rows=[]
    for (role,pid,fmt),v in sorted(player.items()):
        player_rows.append({'role':role,'player_id':pid,'format':fmt,'core_pressure_deliveries':v['core'],'broad_pressure_deliveries':v['broad'],'matches_with_core_pressure':len(v['matches']),
            **{f'core_ge_{n}':v['core']>=n for n in [20,50,100,200]}})
    write_rows(REPORT/'per_player_pressure_counts.csv',player_rows)
    broad_rows=[]
    for (role,inn,phase,fmt),v in sorted(counts.items()):
        broad_rows.append({'scenario':'BROAD','role':role,'innings':inn,'phase':phase,'format':fmt,'core_pressure_deliveries':v['core'],'broad_pressure_deliveries':v['broad'],
            'core_share':v['core']/v['eligible'] if v['eligible'] else '', 'broad_share':v['broad']/v['eligible'] if v['eligible'] else '',
            'count_delta':v['broad']-v['core']})
    write_rows(REPORT/'broad_vs_core.csv',broad_rows)
    summary={'pressure_rows':len(output),'primary_matches':len({r['match_id'] for r in output}),'primary_deliveries':len(output),
        'dls_unresolved_target_chase_rows_excluded':sum(r['dls_exception_flag']=='DLS_UNRESOLVED_TARGET' and r['innings']=='2' for r in output),
        'dls_flagged_first_innings_rows_retained':sum(r['dls_exception_flag']=='DLS_UNRESOLVED_TARGET' and r['innings']=='1' for r in output),
        'core_pressure_flags':{'batter':sum(yes(r['pressure_batter']) for r in output if r['pressure_batter']!=''),'bowler':sum(yes(r['pressure_bowler']) for r in output if r['pressure_bowler']!='')},
        'chase_status_counts':dict(Counter(r['chase_pressure_status'] for r in output if r['innings']=='2')),
        'chase_calibration_pass':chase_summary['calibration_pass'],'chase_calibration_metrics':chase_summary['global_oof_metrics'],
        'eligible_chase_matches':chase_summary['eligible_matches'],'eligible_chase_deliveries':chase_summary['eligible_deliveries'],
        'leverage_scored_chase_rows':leverage_summary['scored_chase_rows'],'provisional_f2_applied':bool(use_f2),
        'critical_chase_fallback_validation_pass':final_validation.get('critical_chase_fallback_validation_pass',False),
        'original_leverage_chase_validation_pass':original_validation.get('validation_pass_by_definition',{}).get('press_chase',False),
        'first_innings_batter_validation_pass':final_validation.get('validation_pass_by_definition',{}).get('pressure_batter',False)}
    (REPORT/'pressure_output_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':build()
