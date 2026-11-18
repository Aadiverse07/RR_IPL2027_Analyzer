"""Idempotent Phase 1 data preparation. Reads raw files; writes interim/processed CSVs."""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path
import yaml
from src.phase0_audit.state import iter_pre_delivery_states

ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/'data/raw'/'Data Pack'
INTERIM=ROOT/'data/interim'
PROCESSED=ROOT/'data/processed'
REPORT=ROOT/'reports/phase_1'


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if fields is None: fields=list(rows[0]) if rows else []
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def is_null(v):return v is None or str(v).strip().lower() in {'','null','none','na','nan'}
def as_int(v,default=0):
    try:return int(float(v))
    except (TypeError,ValueError):return default
def as_bool(v):return str(v).strip().lower() in {'true','1','yes'}
def source_format(comp, cfg):
    if comp.get('comp_name','').startswith(cfg['scope']['ipl_comp_name_prefix']):return 'IPL'
    if comp.get('match_format')==cfg['scope']['international_match_format']:return 'T20I'
    return ''
def read_config():
    return yaml.safe_load((ROOT/'config/methodology.yaml').read_text(encoding='utf-8'))
def write_json(path,obj):path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')



DERIVED_CONTRACT={
 'format':('string','Analysis format derived from competition name/format.','IPL or T20I'),
 'season':('source string','Season copied from competitions.csv.','As supplied'),
 'contains_super_over':('boolean-like','Source has innings >2 or result text says super over; match retained, extra innings excluded.','true/false'),
 'super_over_innings_present':('boolean-like','A source innings greater than 2 is present.','true/false'),
 'super_over_result_mentioned':('boolean-like','Source result text mentions a Super Over.','true/false'),
 'innings1_total_source':('integer nullable','Full innings-1 total from all raw delivery rows, including any delivery after the 120-ball cap.','Source formula runs + extras1_runs + extras_2_runs'),
 'innings2_total_source':('integer nullable','Full innings-2 total from all raw delivery rows, including any delivery after the 120-ball cap.','Source formula runs + extras1_runs + extras_2_runs'),
 'simple_target_candidate':('integer nullable','Innings-1 source total + 1; target is only used for non-exception chases.','Innings 1 source total + 1'),
 'unresolved_dls_outcome_exception':('boolean-like','Owner-identified unresolved DLS/outcome exception.','true/false'),
 'dls_exception_flag':('string nullable','Explicit owner-approved DLS exception flag, propagated to both innings of affected retained matches.','DLS_UNRESOLVED_TARGET or blank; excluded match 48610 flagged in exclusion table'),
 'chase_metadata_status':('string','Whether chase-target metadata is available or its chase rows are excluded under owner decision.','SOURCE_FIELDS_AVAILABLE or DLS_UNRESOLVED_TARGET_EXCLUDED_FROM_CHASE_ANALYSIS'),
 'outcome_label_status':('string','Reliability/eligibility note for source winner label.','Status labels documented in phase report'),
 'target_status':('string','Status of the per-delivery chase target; no DLS target is inferred.','NOT_APPLICABLE, DERIVED_INNINGS1_TOTAL_PLUS_1, or DLS_UNRESOLVED_TARGET'),
 'legal':('boolean-like','Legal delivery under approved definition.','false for wide/Overstep; true otherwise'),
 'faced':('boolean-like','Batter ball faced under approved definition.','false for wide; true otherwise'),
 'team_total_runs':('integer','Runs + extras1_runs + extras_2_runs on this source row.','Non-negative integer'),
 'bowler_charged_runs':('integer','Bat runs plus extras1_runs for wide/Overstep; byes/legbyes excluded.','Non-negative integer; extras2 semantics limitation documented'),
 'phase':('string','Phase from configured over boundaries.','powerplay_overs, middle_overs, death_overs, unknown'),
 'batting_order_group':('string','Exact source batting_order value, without newly invented bins.','source_<value> or unknown'),
 'team_runs_before':('integer','Cumulative team total strictly before this delivery.','Non-negative integer'),
 'wickets_lost_before':('integer','Cumulative source is_wicket count strictly before this delivery.','Non-negative integer'),
 'legal_balls_before':('integer','Legal deliveries strictly before this row in the innings.','0 through configured innings limit'),
 'legal_balls_remaining':('integer','Configured legal-ball limit minus legal_balls_before.','0 through 120'),
 'wickets_in_previous_12_legal_balls':('integer','Source is_wicket count on previous 12 legal deliveries.','0 through 10'),
 'current_run_rate_before':('numeric nullable','Team runs before × configured 6 balls/over / legal balls before.','Blank at zero prior legal balls'),
 'target':('integer nullable','For non-exception chases, innings-1 total + 1. Withheld for flagged DLS exceptions.','Blank for innings 1 and unresolved DLS exceptions'),
 'simple_target_candidate':('integer nullable','Transparent innings-1 total + 1 candidate; not asserted as DLS-adjusted target.','Blank for innings 1; present for innings 2'),
 'runs_needed_before':('integer nullable','target minus team_runs_before where target is approved/available.','Blank where target withheld'),
 'required_run_rate_before':('numeric nullable','runs_needed_before × rate scale / legal_balls_remaining.','Blank if target unavailable or no legal balls remain'),
 'label_only_batting_side_won':('boolean-like nullable','Source winner ID equals this delivery batting team; withheld for unresolved DLS exceptions.','true/false/blank'),
 'outcome_label_status':('string','Label-only status; source winner/result columns remain unchanged.','see report'),
 'dismissed_batter_id':('identifier nullable','Copy of source dismissed_player_id, independent of striker.','Player ID or blank'),
 'dismissal_credit_class':('string','Configured class mapping; unclassifiable classes conservatively not credited.','bowler_credited/not_bowler_credited/unclassified_not_credited/no_dismissal_class'),
 'bowler_credit_wicket':('integer','1 only for configured bowler-credited dismissal class with dismissed player ID.','0 or 1'),
 'source_result_preserved':('string','Exact source result text copied for traceability.','As supplied'),
 'source_win_team_id_preserved':('identifier nullable','Exact source win_team_id copied for traceability.','As supplied'),
 'unresolved_dls_outcome_exception':('boolean-like','Match ID is one of the three approved exception IDs.','true/false')}

def write_data_contract(cfg):
    dictrows=read_csv(ROOT/'reports/phase0_audit/data_dictionary.csv')
    src_desc={r['column']:r['description'] for r in dictrows}
    tables={'data/processed/matches_primary.csv':('match',matches_fields()),'data/processed/balls_primary.csv':('delivery',set(read_csv(RAW/'ball_by_ball.csv')[0].keys())|set(DERIVED_CONTRACT)), 'data/processed/players_dim.csv':('player dimension',set()),'data/processed/player_match.csv':('player-match',set())}
    lines=['# Phase 1 data contract','','CSV is used for all outputs. Source columns are carried unchanged unless a derived field is appended. Dtypes are stored as CSV text; source-column meaning is linked to the Phase 0 data dictionary.','']
    for path,(kind,_) in tables.items():
        rows=read_csv(ROOT/path); fields=list(rows[0]) if rows else []
        lines += [f'## `{path}`','', '| Column | Type | Meaning | Derivation | Allowed values / notes |','|---|---|---|---|---|']
        for col in fields:
            if col in DERIVED_CONTRACT:
                typ,meaning,allowed=DERIVED_CONTRACT[col]
                derivation={'format':'competition-name prefix / match_format','season':'competitions.csv by comp_id','team_total_runs':'runs + extras1_runs + extras_2_runs','bowler_charged_runs':'runs + extras1_runs only for extras_type wide/Overstep','legal':'extras_type not wide/Overstep','faced':'extras_type != wide','dismissed_batter_id':'dismissed_player_id','target':'innings 1 total + 1 except unresolved DLS exceptions','simple_target_candidate':'innings 1 total + 1 (candidate only)','source_result_preserved':'exact copy from matches.csv','innings1_total_source':'aggregate all raw inning 1 deliveries','innings2_total_source':'aggregate all raw inning 2 deliveries','source_win_team_id_preserved':'exact copy from matches.csv','label_only_batting_side_won':'win_team_id == batting_team_id; withheld for DLS exceptions'}.get(col,'scripted from configured methodology and strictly pre-delivery source rows' if col in {'team_runs_before','wickets_lost_before','legal_balls_before','legal_balls_remaining','wickets_in_previous_12_legal_balls','current_run_rate_before','runs_needed_before','required_run_rate_before'} else 'scripted from config or exception register')
            elif col in src_desc:
                typ='CSV text (Phase 0 inferred type)';meaning=src_desc[col];derivation='Copied unchanged from raw source.';allowed='As observed in Phase 0 categorical/range profiles; see data_dictionary.csv.'
            else:
                typ='CSV text';meaning={'names':'Pipe-delimited observed display names; player_id remains join key.','name_ambiguous':'Whether any name maps to multiple player IDs.','team_ids_observed':'Pipe-delimited team IDs observed in source deliveries.','balls_faced':'Count of source batter rows with faced=true.','legal_balls_bowled':'Count of legal deliveries bowled.','deliveries_bowled':'Count of all delivery rows bowled.','bat_runs':'Sum of source runs for batter rows.','dismissals_as_batter':'Dismissals attributed by dismissed_player_id.','bowler_charged_runs':'Sum of derived per-delivery bowler_charged_runs.','bowler_credit_wickets':'Sum of configured bowler_credit_wicket.'}.get(col,'Derived player-match measure from processed delivery/player-XI rows.')
                derivation='Scripted aggregation by player_id, match_id and team_id.';allowed='Non-negative integer or source boolean/text as named.'
            lines.append(f'| `{col}` | {typ} | {meaning} | {derivation} | {allowed} |')
        lines.append('')
    (REPORT/'data_contract.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def matches_fields():
    return set(read_csv(RAW/'matches.csv')[0])

def prepare():
    cfg=read_config()
    balls=read_csv(RAW/'ball_by_ball.csv'); matches=read_csv(RAW/'matches.csv'); comps=read_csv(RAW/'competitions.csv')
    teams=read_csv(RAW/'teams.csv'); playing=read_csv(RAW/'playing_eleven.csv'); mapping=read_csv(RAW/'competition_team_player_mapping.csv')
    comp_by={r['comp_id']:r for r in comps}; match_by={r['match_id']:r for r in matches}
    balls_by_match=defaultdict(list); balls_by_inn=defaultdict(list)
    for r in balls:
        mid=r['match_id']; inn=as_int(r['innings']);balls_by_match[mid].append(r);balls_by_inn[(mid,inn)].append(r)
    revised_fields=cfg['scope']['revised_target_fields']
    exception_ids=set(str(x) for x in cfg.get('data_quality_exceptions',{}).get('unresolved_dls_outcome_match_ids',[]))
    unresolved_target_ids=set(str(x) for x in cfg.get('data_quality_exceptions',{}).get('unresolved_target_match_ids',[]))
    result_conflict_ids=exception_ids-unresolved_target_ids
    state={}; cohort=[]; excluded=[]
    for m in matches:
        mid=m['match_id']; c=comp_by.get(m['comp_id'],{}); fmt=source_format(c,cfg)
        result=m.get('result','').lower()
        is_abandoned='abandon' in result;is_noresult='no result' in result or 'no-result' in result
        revised=any(not is_null(m.get(k,'')) for k in revised_fields)
        innings_present={i for (x,i),rs in balls_by_inn.items() if x==mid and rs}
        both={1,2}.issubset(innings_present)
        winner_ok=not is_null(m.get('win_team_id')) and as_int(m.get('win_team_id'))!=0
        reasons=[]
        if not fmt:reasons.append('out_of_scope_competition')
        if is_abandoned:reasons.append('abandoned')
        if is_noresult:reasons.append('no_result')
        if revised:reasons.append('revised_target_fields_nonnull')
        if not both:reasons.append('missing_innings_1_or_2')
        if not winner_ok:reasons.append('missing_decided_winner')
        keep=not reasons
        super_over_innings_present=any(i>2 for i in innings_present)
        super_over_result_mentioned='super over' in result
        state[mid]={'format':fmt,'season':c.get('season',''),'keep':keep,'reasons':reasons,
            'super_over':super_over_innings_present or super_over_result_mentioned,
            'super_over_innings_present':super_over_innings_present,
            'super_over_result_mentioned':super_over_result_mentioned,
            'exception':mid in exception_ids,'match':m}
        if keep:cohort.append(mid)
        else:excluded.append({**m,'format':fmt,'exclusion_reasons':';'.join(reasons),'unresolved_dls_outcome_exception':mid in exception_ids,
            'dls_exception_flag':'DLS_SOURCE_RESULT_CONFLICT_REVISED_TARGET' if mid in result_conflict_ids else ''})
    cohort_set=set(cohort)
    def balls_by_inn_innings(mid):return [i for (m,i),rs in balls_by_inn.items() if m==mid and rs]
    # Approved team total, all-row innings totals, and per-delivery legal cap filter.
    innings_total=defaultdict(int); innings_wickets=defaultdict(int)
    legal_by_inn=defaultdict(int); kept_balls=[]
    phase_cfg=cfg['innings_phases']; max_legal=int(cfg.get('innings',{}).get('legal_balls',120)); rate_scale=int(cfg.get('innings',{}).get('rate_scale_balls',6))
    illegal=set(str(x).lower() for x in cfg['delivery_accounting']['legal_extras_excluded'])
    faced_exclude=set(str(x).lower() for x in cfg['delivery_accounting']['batter_ball_faced_excluded'])
    for r in balls:
        mid=r['match_id']; inn=as_int(r['innings']);key=(mid,inn)
        innings_total[key]+=as_int(r.get('runs'))+as_int(r.get('extras1_runs'))+as_int(r.get('extras_2_runs'))
        innings_wickets[key]+=int(as_bool(r.get('is_wicket')))
        if mid not in cohort_set or inn>int(cfg['scope']['regular_innings_max']):continue
        nlegal=legal_by_inn[key]
        r['_legal_balls_before_phase1']=nlegal
        if nlegal<max_legal:kept_balls.append(r)
        if str(r.get('extras_type','')).lower() not in illegal:legal_by_inn[key]+=1
    # Match records retain source winner/result exactly and expose exception status.
    matches_primary=[]
    for mid in sorted(cohort_set,key=lambda x:int(x)):
        st=state[mid];m=dict(st['match']);m['format']=st['format'];m['season']=st['season']
        m['contains_super_over']=st['super_over'];m['super_over_innings_present']=st['super_over_innings_present'];m['super_over_result_mentioned']=st['super_over_result_mentioned'];m['unresolved_dls_outcome_exception']=st['exception']
        m['dls_exception_flag']='DLS_UNRESOLVED_TARGET' if mid in unresolved_target_ids else ''
        m['innings1_total_source']=innings_total.get((mid,1),'');m['innings2_total_source']=innings_total.get((mid,2),'')
        m['simple_target_candidate']=innings_total[(mid,1)]+1 if (mid,1) in innings_total else ''
        m['chase_metadata_status']='DLS_UNRESOLVED_TARGET_EXCLUDED_FROM_CHASE_ANALYSIS' if mid in unresolved_target_ids else 'SOURCE_FIELDS_AVAILABLE'
        m['outcome_label_status']='SUPER_OVER_MATCH_FINAL_WINNER_LABEL_ONLY' if st['super_over'] else 'SOURCE_WINNER_ID_LABEL_ONLY'
        matches_primary.append(m)
    # Per-delivery state is produced from the complete raw regular innings prefix.
    state_rows=[]
    for mid in cohort:
        for inn in (1,2):
            rs=balls_by_inn[(mid,inn)]
            target_candidate=innings_total[(mid,1)]+1 if inn==2 else ''
            for seq,(r,pre) in enumerate(zip(rs,iter_pre_delivery_states(rs)),1):
                # Only rows whose pre-delivery legal-ball count is below the configured innings limit are materialized.
                if r['_legal_balls_before_phase1']>=max_legal:continue
                state_rows.append((r,pre,seq,target_candidate))
    # Source identity keys are unique per Phase 0 audit; enrich rows without mutating raw dictionaries.
    extra=[]; labels=[]; primary=[]
    phase_bounds={name:tuple(bounds) for name,bounds in phase_cfg.items()}
    credited=set(cfg['dismissals']['bowler_credited_types']); noncredited=set(cfg['dismissals']['not_bowler_credited_types'])
    for r,pre,seq,target_candidate in state_rows:
        mid=r['match_id'];inn=as_int(r['innings']);st=state[mid];ex=st['exception'];extras=str(r.get('extras_type',''));exlo=extras.lower()
        legal=exlo not in illegal; faced=exlo not in faced_exclude
        over=as_int(r.get('overid'),-1)
        phase='unknown'
        for name,(lo,hi) in phase_bounds.items():
            if lo<=over<=hi:phase=name;break
        order=r.get('batting_order','')
        order_group=('source_'+str(order)) if not is_null(order) else 'unknown'
        target_value='' if inn!=2 or ex else target_candidate
        target_status='NOT_APPLICABLE' if inn==1 else ('DLS_UNRESOLVED_TARGET' if mid in unresolved_target_ids else 'DERIVED_INNINGS1_TOTAL_PLUS_1')
        runs_needed=(int(target_value)-pre['runs_before']) if target_value!='' else ''
        legal_remaining=pre['legal_balls_remaining_120']
        required_rate=(float(runs_needed)*rate_scale/legal_remaining) if runs_needed!='' and legal_remaining>0 else ''
        current_rr=(pre['runs_before']*rate_scale/pre['legal_balls_before']) if pre['legal_balls_before']>0 else ''
        etype=str(r.get('dismissal_type','')).strip()
        dismissed=r.get('dismissed_player_id','')
        credit='bowler_credited' if etype in credited and not is_null(dismissed) else ('not_bowler_credited' if etype in noncredited else ('unclassified_not_credited' if etype else 'no_dismissal_class'))
        bowler_credit=int(credit=='bowler_credited')
        # extras1 contains the base wide/no-ball penalty for these source classes; byes/leg-byes excluded.
        charged=as_int(r.get('runs'))+(as_int(r.get('extras1_runs')) if exlo in {'wide','overstep'} else 0)
        result=st['match'].get('result','');winner=st['match'].get('win_team_id','')
        side_label=''
        if not ex and not is_null(winner):side_label=str(as_int(r.get('batting_team_id'))==as_int(winner)).lower()
        row=dict(r);row.pop('_legal_balls_before_phase1',None)
        row.update({'format':st['format'],'season':st['season'],'legal':str(legal).lower(),'faced':str(faced).lower(),
            'team_total_runs':as_int(r.get('runs'))+as_int(r.get('extras1_runs'))+as_int(r.get('extras_2_runs')),
            'bowler_charged_runs':charged,'phase':phase,'batting_order_group':order_group,
            'team_runs_before':pre['runs_before'],'wickets_lost_before':pre['wickets_before'],
            'legal_balls_before':pre['legal_balls_before'],'legal_balls_remaining':pre['legal_balls_remaining_120'],
            'wickets_in_previous_12_legal_balls':pre['wickets_previous_12_legal'],
            'current_run_rate_before':current_rr,'target':target_value,'simple_target_candidate':target_candidate if inn==2 else '',
            'runs_needed_before':runs_needed,'required_run_rate_before':required_rate,
            'label_only_batting_side_won':side_label,'outcome_label_status':'WITHHELD_DLS_UNRESOLVED_TARGET' if mid in unresolved_target_ids else ('SOURCE_WINNER_ID_LABEL_ONLY' if winner else 'NO_SOURCE_WINNER'),
            'unresolved_dls_outcome_exception':str(ex).lower(),'target_status':target_status,
            'dls_exception_flag':'DLS_UNRESOLVED_TARGET' if mid in unresolved_target_ids else '',
            'dismissed_batter_id':dismissed,'dismissal_credit_class':credit,'bowler_credit_wicket':bowler_credit,
            'source_result_preserved':result,'source_win_team_id_preserved':winner})
        primary.append(row)
        extra.append({'match_id':mid,'innings':inn,'team_id':r['batting_team_id'],'player_id':r['striker_id'],'name':r.get('striker_name',''),'balls_faced':int(faced),'runs':as_int(r.get('runs')),'batting_order':order})
        extra.append({'match_id':mid,'innings':inn,'team_id':r['bowling_team_id'],'player_id':r['bowler_id'],'name':r.get('bowler_name',''),'legal_balls_bowled':int(legal),'deliveries_bowled':1,'bowler_charged_runs':charged,'bowler_credit_wicket':bowler_credit})
    # Interim materialization and processed clean tables.
    write_csv(INTERIM/'excluded_matches.csv',excluded)
    write_csv(INTERIM/'matches_scoped.csv',matches_primary)
    write_csv(INTERIM/'balls_primary.csv',primary)
    write_csv(PROCESSED/'matches_primary.csv',matches_primary)
    fields=list(primary[0]) if primary else []
    write_csv(PROCESSED/'balls_primary.csv',primary,fields)
    # players dimension, IDs are the join key; retain every observed name.
    names=defaultdict(set); teams_player=defaultdict(set)
    for r in balls:
        for idf,nf,tf in [('striker_id','striker_name','batting_team_id'),('non_striker_id','non_striker_name','batting_team_id'),('bowler_id','bowler_name','bowling_team_id'),('dismissed_player_id','striker_name','')]:
            pid=r.get(idf,'')
            if not is_null(pid) and not is_null(r.get(nf,'')):names[pid].add(r[nf])
            if not is_null(pid) and tf and not is_null(r.get(tf,'')):teams_player[pid].add(r[tf])
    for r in playing:
        if not is_null(r.get('player_id')):names[r['player_id']]
    for r in mapping:
        if not is_null(r.get('player_id')) and not is_null(r.get('player_name')):names[r['player_id']].add(r['player_name'])
    id_for_name=defaultdict(set)
    for pid,nset in names.items():
        for name in nset:id_for_name[name].add(pid)
    players_dim=[{'player_id':pid,'names':'|'.join(sorted(ns)),'name_ambiguous':any(len(id_for_name[n])>1 for n in ns),'team_ids_observed':'|'.join(sorted(teams_player.get(pid,set()),key=lambda x:int(x)))} for pid,ns in sorted(names.items(),key=lambda x:int(x[0]))]
    write_csv(PROCESSED/'players_dim.csv',players_dim,['player_id','names','name_ambiguous','team_ids_observed'])
    # Player-match includes playing-XI participants plus delivery-role participants.
    pm={}
    def get_pm(mid,pid,team):
        key=(mid,pid,team)
        if key not in pm:pm[key]={'match_id':mid,'player_id':pid,'team_id':team,'format':state[mid]['format'],'season':state[mid]['season'],'name':'','batting_order':'','balls_faced':0,'bat_runs':0,'dismissals_as_batter':0,'deliveries_bowled':0,'legal_balls_bowled':0,'bowler_charged_runs':0,'bowler_credit_wickets':0,'is_played':'','is_impact':'','is_impact_off':''}
        return pm[key]
    for p in playing:
        mid=p['match_id'];pid=p['player_id']
        if mid not in cohort_set:continue
        x=get_pm(mid,pid,p['team_id']);x.update({'batting_order':p.get('batting_order',''),'is_played':p.get('is_played',''),'is_impact':p.get('is_impact',''),'is_impact_off':p.get('is_impact_off','')})
    for r in primary:
        mid=r['match_id'];pid=r['striker_id'];team=r['batting_team_id'];x=get_pm(mid,pid,team)
        x['name']=r.get('striker_name','');x['balls_faced']+=int(r['faced']=='true');x['bat_runs']+=as_int(r['runs'])
        if not is_null(r.get('batting_order')):x['batting_order']=r['batting_order']
        if r['dismissed_batter_id']==pid and r['dismissal_type']:x['dismissals_as_batter']+=1
        pid=r['bowler_id'];team=r['bowling_team_id'];x=get_pm(mid,pid,team);x['name']=r.get('bowler_name','');x['deliveries_bowled']+=1;x['legal_balls_bowled']+=int(r['legal']=='true');x['bowler_charged_runs']+=as_int(r['bowler_charged_runs']);x['bowler_credit_wickets']+=as_int(r['bowler_credit_wicket'])
    write_csv(PROCESSED/'player_match.csv',list(pm.values()))
    # Exact exception table includes 48610 though it is excluded from primary because revised fields are present.
    exceptions=[]
    for mid in sorted(exception_ids,key=lambda x:int(x)):
        m=match_by[mid];comp=comp_by[m['comp_id']]
        reasons=state[mid]['reasons'] if mid in state else []
        owner_treatment=('Retain match and innings 1; exclude only innings 2 from chase-pressure calibration, validation, and chase-specific pressure-performance comparisons; flag both innings DLS_UNRESOLVED_TARGET.' if mid in unresolved_target_ids else 'Remain excluded by the approved revised-target rule; preserve source result/winner conflict without override.')
        remaining_decision=('No further treatment decision is open; the source-adjusted target and chase outcome remain unresolved and are not inferred.' if mid in unresolved_target_ids else 'No cohort-treatment decision is open; retain the source result/winner conflict without override.')
        exceptions.append({'match_id':mid,'comp_id':m['comp_id'],'competition':comp['comp_name'],'season':comp['season'],'included_in_primary':mid in cohort_set,
            'phase1_treatment':'included_flagged_target_withheld' if mid in cohort_set else 'excluded_by_revised_target_rule_flag_retained',
            'dls_exception_flag':'DLS_UNRESOLVED_TARGET' if mid in unresolved_target_ids else 'DLS_SOURCE_RESULT_CONFLICT_REVISED_TARGET',
            'owner_decision_status':'APPROVED_2026-11-18','owner_approved_treatment':owner_treatment,
            'chase_pressure_eligible':False if mid in unresolved_target_ids or mid in result_conflict_ids else True,
            'source_result':m.get('result',''),'source_win_team_id':m.get('win_team_id',''),'revised_target':m.get('revised_target',''),'first_inn_revised_overs':m.get('first_inn_revised_overs',''),'second_inn_revised_overs':m.get('second_inn_revised_overs',''),'exclusion_reasons':';'.join(reasons),
            'remaining_decision':remaining_decision})
    write_csv(REPORT/'unresolved_exceptions.csv',exceptions)
    # Exclusion funnel records row-level super-over innings exclusion, not match exclusion.
    scope_ids=[mid for mid,m in match_by.items() if source_format(comp_by.get(m['comp_id'],{}),cfg)]
    # Maintain a match cohort at every match-level gate, then a row-level innings/ball gate.
    non_ab=[mid for mid in scope_ids if not ('abandon' in match_by[mid].get('result','').lower() or 'no result' in match_by[mid].get('result','').lower() or 'no-result' in match_by[mid].get('result','').lower())]
    non_rev=[mid for mid in non_ab if not any(not is_null(match_by[mid].get(k,'')) for k in revised_fields)]
    both_ids=[mid for mid in non_rev if 1 in balls_by_inn_innings(mid) and 2 in balls_by_inn_innings(mid)]
    decided=[mid for mid in both_ids if not is_null(match_by[mid].get('win_team_id')) and as_int(match_by[mid].get('win_team_id'))!=0]
    stages=[{'stage':'all_matches','matches':len(matches),'delivery_rows':len(balls)},
        {'stage':'primary_competition_scope','matches':len(scope_ids),'delivery_rows':sum(len(balls_by_match[mid]) for mid in scope_ids)},
        {'stage':'exclude_super_over_innings_only','matches':len(scope_ids),'delivery_rows':sum(len(balls_by_inn[(mid,inn)]) for mid in scope_ids for inn in balls_by_inn_innings(mid) if inn<=2)},
        {'stage':'exclude_abandoned_no_result_matches','matches':len(non_ab),'delivery_rows':sum(len(balls_by_inn[(mid,inn)]) for mid in non_ab for inn in balls_by_inn_innings(mid) if inn<=2)},
        {'stage':'exclude_revised_target_field_matches','matches':len(non_rev),'delivery_rows':sum(len(balls_by_inn[(mid,inn)]) for mid in non_rev for inn in balls_by_inn_innings(mid) if inn<=2)},
        {'stage':'require_both_regular_innings','matches':len(both_ids),'delivery_rows':sum(len(balls_by_inn[(mid,inn)]) for mid in both_ids for inn in balls_by_inn_innings(mid) if inn<=2)},
        {'stage':'require_nonzero_winner','matches':len(decided),'delivery_rows':sum(len(balls_by_inn[(mid,inn)]) for mid in decided for inn in balls_by_inn_innings(mid) if inn<=2)},
        {'stage':'pre_delivery_legal_balls_below_120','matches':len(cohort_set),'delivery_rows':len(primary)}]
    write_csv(REPORT/'exclusion_funnel.csv',stages)
    # Exception label audit, no outcome inference for flagged rows.
    # A machine-readable summary for tests and the phase report.
    nonstriker_runouts=sum(1 for r in primary if r.get('dismissal_type')=='RunOut' and not is_null(r.get('dismissed_batter_id')) and r.get('dismissed_batter_id')!=r.get('striker_id'))
    nonbowler_dismissals=sum(1 for r in primary if r.get('dismissal_credit_class')=='not_bowler_credited' and not is_null(r.get('dismissed_batter_id')))
    superover_matches=[mid for mid in cohort if state[mid]['super_over']]
    summary={'primary_matches':len(matches_primary),'primary_deliveries':len(primary),'innings_1_deliveries':sum(as_int(r['innings'])==1 for r in primary),'innings_2_deliveries':sum(as_int(r['innings'])==2 for r in primary),'matches_marked_super_over_or_result_retained_regular_innings':len(superover_matches),'matches_with_super_over_innings':sum(state[x]['super_over_innings_present'] for x in cohort),'super_over_match_ids':superover_matches,'unresolved_exceptions_in_primary':[x for x in exception_ids if x in cohort_set],'unresolved_exceptions_excluded':[x for x in exception_ids if x not in cohort_set],'nonstriker_runouts':nonstriker_runouts,'nonbowler_dismissals':nonbowler_dismissals,'storage_format':'CSV (portable, no parquet writer selected)','raw_source_files_unchanged':'see data/raw/checksums.sha256'}
    write_json(REPORT/'validation_summary.json',summary)
    write_data_contract(cfg)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':prepare()
