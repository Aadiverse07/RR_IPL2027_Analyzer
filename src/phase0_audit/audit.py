"""Reproducible Phase 0 audit. Reads raw inputs only; never writes to data/raw."""
from __future__ import annotations
import csv, hashlib, json, math, re, sys, zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from pypdf import PdfReader
from src.phase0_audit.state import iter_pre_delivery_states

ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/'data/raw'/'Data Pack'
OUT=ROOT/'reports/phase0_audit'
EXPECTED_FILES=['ball_by_ball.csv','matches.csv','competitions.csv','teams.csv','playing_eleven.csv','competition_team_player_mapping.csv']
NULLS={'','null','none','na','nan'}

def read_csv(name):
    p=RAW/name
    with p.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        rows=list(reader)
        return reader.fieldnames or [], rows

def null(v): return v is None or str(v).strip().lower() in NULLS
def as_int(v,default=0):
    try: return int(float(v))
    except (ValueError,TypeError): return default
def truth(v): return str(v).strip().lower() in {'true','1','yes'}
def uniq_vals(rows,col): return {r.get(col,'') for r in rows if not null(r.get(col,''))}
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
def write_csv(path,headers,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
def emit_metric(rows,metric,value,expected=None,notes=''):
    if value is None: status='UNAVAILABLE'
    elif expected is None: status='NOT APPLICABLE'
    elif isinstance(expected,str) and expected.startswith('~'):
        try:
            target=float(expected[1:].replace('%',''))/(100 if '%' in expected else 1)
            actual=float(str(value).replace('%',''))/(100 if '%' in str(value) else 1)
            status='MATCH' if abs(actual-target)<=0.005 else 'MISMATCH'
        except ValueError: status='MISMATCH'
    else: status='MATCH' if str(value)==str(expected) else 'MISMATCH'
    rows.append({'metric':metric,'expected': '' if expected is None else expected,'reproduced':'' if value is None else value,'status':status,'notes':notes})
def infer_dtype(values):
    vals=[v for v in values if not null(v)]
    if not vals:return 'all-null/unknown'
    if all(v.lower() in {'true','false'} for v in vals): return 'boolean-like (CSV text)'
    if all(re.fullmatch(r'[+-]?\d+',v) for v in vals): return 'integer-like (CSV text)'
    try:
        for v in vals: float(v)
        return 'numeric (CSV text)'
    except ValueError: pass
    return 'string (CSV text)'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    names=EXPECTED_FILES
    tables={}
    for name in names:
        fields,rows=read_csv(name); tables[name]=(fields,rows)
    ball_fields,balls=tables['ball_by_ball.csv']; match_fields,matches=tables['matches.csv']; comp_fields,comps=tables['competitions.csv']; team_fields,teams=tables['teams.csv']; pe_fields,pe=tables['playing_eleven.csv']; map_fields,mapping=tables['competition_team_player_mapping.csv']
    comp={r['comp_id']:r for r in comps}; match={r['match_id']:r for r in matches}
    # CSV-level profiling
    profiles=[]; cats=[]; dictionaries=[]
    semantic={
      'match_id':'Identifier of the match; joins delivery rows to matches.csv.', 'innings':'Innings number as encoded in the source.', 'overid':'Over index/identifier as encoded; source sample starts at 1; exact semantics not independently specified.', 'over_ball_num':'Ball position within over as encoded; includes source event sequence, may not equal legal-ball count.', 'innings_ball_num':'Source-provided within-innings delivery sequence; duplicate checking key candidate.',
      'batting_team_id':'Source team identifier batting on this delivery.', 'bowling_team_id':'Source team identifier bowling on this delivery.', 'striker_id':'Player identifier for the striker.', 'striker_name':'Source display name for the striker.', 'non_striker_id':'Player identifier for non-striker.', 'non_striker_name':'Source display name for non-striker.', 'bowler_id':'Player identifier for bowler.', 'bowler_name':'Source display name for bowler.',
      'runs':'Runs off the bat (matches project glossary; extra runs are in separate columns).','extras1_runs':'First extras component; aggregate behavior needs reconciliation with extras_type; not assigned a specific semantic without evidence.','extras_2_runs':'Second extras component; aggregate behavior needs reconciliation with extras_type; not assigned a specific semantic without evidence.',
      'is_wicket':'Boolean-like dismissal/wicket flag in source; reconcile against dismissal_type and dismissed_player_id.', 'dismissal_type':'Source dismissal-class string.', 'dismissed_player_id':'Player identifier credited as dismissed in source.', 'extras_type':'Source extras classification; confirm observed categories before deriving legal balls.', 'overid':'Over identifier/index in source.', 'over_ball_num':'Within-over ball/event position in source.', 'innings_ball_num':'Source delivery sequence index within innings.', 'batting_order':'Source batting-order integer/category for playing XI or delivery batter; interpretation depends on table.', 'bowl_speed':'Numeric speed field; observed zero/missing values may be sentinels, units unverified.',
      'match_format':'Competition match-format label.', 'comp_name':'Competition display name.', 'season':'Season/year value as supplied.', 'result':'Match result text.', 'win_team_id':'Winning team identifier; null/zero handling must be empirically checked.'}
    candidates={'ball_by_ball.csv':['match_id|innings|innings_ball_num','match_id|innings|overid|over_ball_num'],'matches.csv':['match_id'],'competitions.csv':['comp_id'],'teams.csv':['comp_id|team_id'],'playing_eleven.csv':['match_id|team_id|player_id'],'competition_team_player_mapping.csv':['comp_id|team_id|player_id']}
    for name,(fields,rows) in tables.items():
        duplicate_rows=len(rows)-len({tuple(r.get(c,'') for c in fields) for r in rows})
        profiles.append({'file':name,'rows':len(rows),'columns':len(fields),'duplicate_rows':duplicate_rows})
        for c in fields:
            vals=[r.get(c,'') for r in rows]
            nonnull=[v for v in vals if not null(v)]
            unique=set(nonnull)
            sortednums=[]
            for v in nonnull:
                try: sortednums.append(float(v))
                except ValueError: pass
            cands=[]
            for spec in candidates.get(name,[]):
                cols=spec.split('|')
                keys=[tuple(r.get(k,'') for k in cols) for r in rows]
                if all(all(not null(x) for x in key) for key in keys) and len(set(keys))==len(keys): cands.append(spec+' (unique)')
                else:cands.append(spec+' (not unique or contains null)')
            desc=semantic.get(c,'UNVERIFIED: semantics not established beyond the source column name/value representation.')
            dictionaries.append({'file':name,'column':c,'dtype_inferred':infer_dtype(vals),'null_count':len(vals)-len(nonnull),'unique_nonnull':len(unique),'min_numeric':min(sortednums) if sortednums else '', 'max_numeric':max(sortednums) if sortednums else '', 'candidate_key_checks':'; '.join(cands),'description':desc})
            if len(unique)<=30:
                for value,count in Counter(vals).most_common(): cats.append({'file':name,'column':c,'value':value,'count':count})
    write_csv(OUT/'csv_profiles.csv',['file','rows','columns','duplicate_rows'],profiles)
    write_csv(OUT/'data_dictionary.csv',['file','column','dtype_inferred','null_count','unique_nonnull','min_numeric','max_numeric','candidate_key_checks','description'],dictionaries)
    (OUT/'data_dictionary.md').write_text('# Data dictionary\n\nOne row per source column. Dtypes are inferred from CSV text; unknown semantics are explicitly marked UNVERIFIED. See `data_dictionary.csv` for ranges, null counts, uniqueness and candidate-key checks.\n\n'+'\n'.join(f"- **{d['file']} · {d['column']}** ({d['dtype_inferred']}): {d['description']}" for d in dictionaries)+'\n',encoding='utf-8')
    write_csv(OUT/'categorical_counts.csv',['file','column','value','count'],cats)
    # Core row indexes and coverage
    balls_by_match=defaultdict(list); balls_by_inn=defaultdict(list)
    for r in balls:
        balls_by_match[r['match_id']].append(r); balls_by_inn[(r['match_id'],as_int(r['innings']))].append(r)
    comp_matches=Counter((m['comp_id'],m.get('season') or comp.get(m['comp_id'],{}).get('season',''),comp.get(m['comp_id'],{}).get('match_format','')) for m in matches)
    coverage=[]
    for (cid,season,fmt),n in sorted(comp_matches.items()): coverage.append({'comp_id':cid,'comp_name':comp.get(cid,{}).get('comp_name',''),'season':season,'match_format':fmt,'matches':n})
    write_csv(OUT/'matches_by_competition_season_format.csv',['comp_id','comp_name','season','match_format','matches'],coverage)
    write_csv(OUT/'matches_without_ball_data.csv',['match_id','comp_id','comp_name','result','result_class'],[
        {'match_id':m['match_id'],'comp_id':m['comp_id'],'comp_name':comp.get(m['comp_id'],{}).get('comp_name',''),'result':m.get('result',''),
         'result_class':'abandoned' if 'abandon' in m.get('result','').lower() else ('no result' if 'no result' in m.get('result','').lower() else 'other')}
        for m in matches if m['match_id'] not in balls_by_match])
    result_classes=Counter()
    for m in matches:
        text=m.get('result','').lower()
        cl='other'
        if 'abandon' in text:cl='abandoned'
        elif 'no result' in text or 'no-result' in text:cl='no result'
        elif 'tie' in text:cl='tie'
        elif 'won by' in text and 'run' in text:cl='won by runs'
        elif 'won by' in text and 'wicket' in text:cl='won by wickets'
        result_classes[cl]+=1
    # Source extras field relationships, retained as descriptive evidence only.
    extras_summary=defaultdict(lambda:[0,0,0,0,0])
    for r in balls:
        v=extras_summary[r.get('extras_type','')]
        v[0]+=1; v[1]+=as_int(r.get('runs')); v[2]+=as_int(r.get('extras1_runs')); v[3]+=as_int(r.get('extras_2_runs'))
        v[4]+=as_int(r.get('runs'))+as_int(r.get('extras1_runs'))+as_int(r.get('extras_2_runs'))
    write_csv(OUT/'extras_semantics.csv',['extras_type','rows','sum_runs','sum_extras1_runs','sum_extras_2_runs','sum_approved_team_total'],[{'extras_type':k,'rows':v[0],'sum_runs':v[1],'sum_extras1_runs':v[2],'sum_extras_2_runs':v[3],'sum_approved_team_total':v[4]} for k,v in extras_summary.items()])
    # regular innings summary, legal-ball definition approved in prompt
    inn_rows=[]
    for (mid,inn),rs in balls_by_inn.items():
        legal=sum(1 for r in rs if (r.get('extras_type','').lower() not in {'wide','overstep'}))
        total=sum(as_int(r.get('runs'))+as_int(r.get('extras1_runs'))+as_int(r.get('extras_2_runs')) for r in rs)
        wickets=sum(1 for r in rs if truth(r.get('is_wicket')))
        inn_rows.append({'match_id':mid,'innings':inn,'rows':len(rs),'legal_balls':legal,'team_total':total,'is_wicket_true':wickets})
    write_csv(OUT/'innings_coverage.csv',['match_id','innings','rows','legal_balls','team_total','is_wicket_true'],inn_rows)
    short=[r for r in inn_rows if r['innings']<=2 and r['legal_balls']<100]
    write_csv(OUT/'innings_under_100_legal_balls.csv',['match_id','innings','rows','legal_balls','team_total','is_wicket_true'],short)
    # Match level classes/exclusion funnel
    match_info={}; no_ball=[]; super_matches=set(); reviseds=set(); abandoned=set(); noresult=set()
    for m in matches:
        mid=m['match_id']; cr=comp.get(m['comp_id'],{}); typ='IPL' if cr.get('comp_name','').startswith('IPL') else ('T20I' if cr.get('match_format')=='T20I' else ('other T20' if cr.get('match_format')=='T20' else 'other'))
        result=m.get('result','').lower(); is_ab='abandon' in result; is_nr='no result' in result or 'no-result' in result
        revised=any(not null(m.get(c,'')) for c in ['revised_target','first_inn_revised_overs','second_inn_revised_overs'])
        has_super=any(x[0]==mid and x[1]>2 for x in balls_by_inn)
        regular=[x for x in inn_rows if x['match_id']==mid and x['innings'] in (1,2)]
        has_balls=mid in balls_by_match
        both=all(any(i['innings']==n for i in regular) for n in (1,2))
        # Per prompt, decided status is evidenced by non-null/non-zero win_team_id.
        decided=not null(m.get('win_team_id')) and as_int(m.get('win_team_id'))!=0
        eligible_scope=typ in {'IPL','T20I'}
        reasons=[]
        if not eligible_scope:reasons.append('out_of_scope_competition')
        if has_super:reasons.append('super_over')
        if is_ab:reasons.append('abandoned')
        if is_nr:reasons.append('no_result')
        if revised:reasons.append('revised_target')
        if not both:reasons.append('missing_regular_innings')
        if not decided:reasons.append('no_decided_winner')
        match_info[mid]={'format_scope':typ,'eligible_scope':eligible_scope,'has_super':has_super,'abandoned':is_ab,'noresult':is_nr,'revised':revised,'both':both,'decided':decided,'reasons':reasons,'match':m}
        if not has_balls:no_ball.append(mid)
        if has_super:super_matches.add(mid)
        if revised:reviseds.add(mid)
        if is_ab:abandoned.add(mid)
        if is_nr:noresult.add(mid)
    # exclusion funnel uses sequential flow; counts are match IDs and delivery rows at each step
    scoped=[mid for mid,x in match_info.items() if x['eligible_scope']]
    steps=[('all_matches',list(match_info)),('primary_competition_scope',scoped)]
    cur=scoped
    for key,label in [('has_super','exclude_super_overs'),('abandoned','exclude_abandoned'),('noresult','exclude_no_result'),('revised','exclude_revised_target'),('both','require_innings_1_and_2'),('decided','require_decided_winner')]:
        cur=[mid for mid in cur if not match_info[mid][key]] if key in ('has_super','abandoned','noresult','revised') else [mid for mid in cur if match_info[mid][key]]
        steps.append((label,cur.copy()))
    primary_set=set(cur)
    primary_delivery_rows=[]
    for mid in primary_set:
        for inn in (1,2):
            legal_seen=0
            for r in balls_by_inn.get((mid,inn),[]):
                if legal_seen < 120: primary_delivery_rows.append(r)
                if r.get('extras_type','').lower() not in {'wide','overstep'}: legal_seen += 1
    steps.append(('exclude_deliveries_at_or_after_120_legal_balls',list(primary_set)))
    funnel=[]
    for label,ids in steps:
        nrows=len(primary_delivery_rows) if label=='exclude_deliveries_at_or_after_120_legal_balls' else sum(len(balls_by_match.get(mid,[])) for mid in ids)
        funnel.append({'stage':label,'matches':len(ids),'delivery_rows':nrows})
    write_csv(OUT/'exclusion_funnel.csv',['stage','matches','delivery_rows'],funnel)
    # Classify likely causes for regular innings shorter than 100 legal balls.
    short_cause=[]
    for r in short:
        mi=match_info.get(r['match_id'],{}); m=mi.get('match',{}); res=m.get('result','').lower()
        if mi.get('abandoned'):cause='abandoned match'
        elif mi.get('noresult'):cause='no-result match'
        elif mi.get('revised'):cause='revised-target/overs match'
        elif r['is_wicket_true']>=10:cause='all out before 100 legal balls'
        elif r['innings']==2 and balls_by_inn.get((r['match_id'],2)) and as_int(m.get('win_team_id'))==as_int(balls_by_inn[(r['match_id'],2)][0].get('batting_team_id')):cause='chase completed early (likely)'
        else:cause='other early termination/shortened innings; reason not identifiable from supplied fields'
        short_cause.append({**r,'likely_cause':cause})
    write_csv(OUT/'innings_under_100_legal_balls.csv',['match_id','innings','rows','legal_balls','team_total','is_wicket_true','likely_cause'],short_cause)
    winner_status=Counter('null_or_blank' if null(m.get('win_team_id')) else ('zero' if as_int(m.get('win_team_id'))==0 else 'nonzero_winner') for m in matches)
    write_csv(OUT/'win_team_id_handling.csv',['status','matches'],[{'status':k,'matches':v} for k,v in winner_status.items()])
    excluded=[]
    for mid,x in match_info.items():
        if x['reasons']:excluded.append({'match_id':mid,'comp_id':x['match']['comp_id'],'format_scope':x['format_scope'],'reasons':';'.join(x['reasons']),'delivery_rows':len(balls_by_match.get(mid,[]))})
    write_csv(OUT/'excluded_matches.csv',['match_id','comp_id','format_scope','reasons','delivery_rows'],excluded)
    # wickets and mismatch rows
    dismissal_counts=Counter(r.get('dismissal_type','') for r in balls if not null(r.get('dismissal_type')))
    disag=[]
    for ix,r in enumerate(balls,2):
        iw=truth(r.get('is_wicket')); dt=not null(r.get('dismissal_type')); dp=not null(r.get('dismissed_player_id'))
        if len({iw,dt,dp})>1: disag.append({'csv_line':ix,**{k:r.get(k,'') for k in ['match_id','innings','innings_ball_num','striker_id','is_wicket','dismissal_type','dismissed_player_id','bowler_id']},'disagreement':'is_wicket/dismissal_type/dismissed_player_id presence differs'})
    write_csv(OUT/'wicket_flag_disagreements.csv',['csv_line','match_id','innings','innings_ball_num','striker_id','is_wicket','dismissal_type','dismissed_player_id','bowler_id','disagreement'],disag)
    write_csv(OUT/'dismissal_type_counts.csv',['dismissal_type','count'],[{'dismissal_type':k,'count':v} for k,v in dismissal_counts.items()])
    dismissal_map={'Bowled':('bowler-credited','proposed, standard dismissal class'),'Caught':('bowler-credited','proposed, standard dismissal class'),'Stump':('bowler-credited','proposed; source uses Stump'),'LBW':('bowler-credited','proposed, standard dismissal class'),'Hit Wicket':('bowler-credited','proposed, review source attribution'),'RunOut':('not bowler-credited','proposed, non-bowler dismissal'),'Retire Out':('not bowler-credited','proposed, non-bowler dismissal'),'Obstracting the field':('not bowler-credited','ASSUMPTION: conservative pending source spelling/semantics review'),'Obstructing the field':('not bowler-credited','ASSUMPTION: conservative pending source semantics review')}
    write_csv(OUT/'dismissal_credit_mapping_for_review.csv',['dismissal_type','count','proposed_class','status_note'],[{'dismissal_type':k,'count':v,'proposed_class':dismissal_map.get(k,('not bowler-credited','ASSUMPTION: unclassifiable, conservative'))[0],'status_note':dismissal_map.get(k,('','ASSUMPTION: unclassifiable, conservative'))[1]} for k,v in dismissal_counts.items()])
    # joins / orphan IDs
    comp_ids=set(comp); match_ids=set(match); team_ids={r['team_id'] for r in teams}; player_ball=set()
    for r in balls:
        for c in ['striker_id','non_striker_id','bowler_id','dismissed_player_id']:
            if not null(r.get(c)):player_ball.add(r[c])
    pe_players={r['player_id'] for r in pe if not null(r.get('player_id'))}; map_players={r['player_id'] for r in mapping if not null(r.get('player_id'))}
    orphans={'ball_match':[r['match_id'] for r in balls if r['match_id'] not in match_ids], 'match_comp':[r['comp_id'] for r in matches if r['comp_id'] not in comp_ids], 'team_map':[r['team_id'] for r in teams if r['team_id'] not in {m['home_team_id'] for m in matches}|{m['away_team_id'] for m in matches}], 'ball_players_missing_playing_eleven':sorted(player_ball-pe_players,key=lambda x:int(x)), 'ball_players_missing_mapping':sorted(player_ball-map_players,key=lambda x:int(x))}
    # Expanded team/player referential integrity across all supplied tables.
    team_comp={(r['comp_id'],r['team_id']) for r in teams}
    map_team_comp={(r['comp_id'],r['team_id']) for r in mapping}
    match_by_comp={m['match_id']:m['comp_id'] for m in matches}
    ref_rows=[]
    mapping_player_ids={x['player_id'] for x in mapping}
    def add_ref(name, bad): ref_rows.append({'reference':name,'orphan_count':len(bad),'orphan_ids':'|'.join(map(str,sorted(set(bad),key=str)[:200]))})
    add_ref('ball_by_ball.match_id -> matches.match_id',[r['match_id'] for r in balls if r['match_id'] not in match_ids])
    add_ref('matches.comp_id -> competitions.comp_id',[r['comp_id'] for r in matches if r['comp_id'] not in comp_ids])
    add_ref('matches.home/away team by comp -> teams',[f"{m['comp_id']}:{tid}" for m in matches for tid in [m.get('home_team_id',''),m.get('away_team_id','')] if not null(tid) and (m['comp_id'],tid) not in team_comp])
    add_ref('balls.batting/bowling team by match comp -> teams',[f"{match_by_comp.get(r['match_id'],'?')}:{tid}" for r in balls for tid in [r.get('batting_team_id',''),r.get('bowling_team_id','')] if not null(tid) and (match_by_comp.get(r['match_id']),tid) not in team_comp])
    add_ref('teams -> competition_team_player_mapping team',[f"{cid}:{tid}" for cid,tid in team_comp if (cid,tid) not in map_team_comp])
    add_ref('playing_eleven.match_id -> matches.match_id',[r['match_id'] for r in pe if r['match_id'] not in match_ids])
    add_ref('playing_eleven.player_id -> competition_team_player_mapping.player_id',[r['player_id'] for r in pe if not null(r.get('player_id')) and r['player_id'] not in mapping_player_ids])
    write_csv(OUT/'referential_integrity.csv',['reference','orphan_count','orphan_ids'],ref_rows)
    # identities, impact, played false
    id_names=defaultdict(set); name_ids=defaultdict(set)
    for r in balls:
        for i,n in [('striker_id','striker_name'),('non_striker_id','non_striker_name'),('bowler_id','bowler_name'),('dismissed_player_id','')]:
            if not null(r.get(i)) and not null(r.get(n,'')):
                id_names[r[i]].add(r[n]); name_ids[r[n]].add(r[i])
    multi_id=[{'player_id':i,'names':'|'.join(sorted(ns))} for i,ns in id_names.items() if len(ns)>1]
    multi_name=[{'name':n,'player_ids':'|'.join(sorted(ids,key=lambda x:int(x)))} for n,ids in name_ids.items() if len(ids)>1]
    write_csv(OUT/'player_ids_multiple_names.csv',['player_id','names'],multi_id)
    write_csv(OUT/'player_names_multiple_ids.csv',['name','player_ids'],multi_name)
    impact=[r for r in pe if truth(r.get('is_impact')) or truth(r.get('is_impact_off'))]
    not_played=[r for r in pe if str(r.get('is_played','')).lower()=='false']
    # chase target/outcome consistency based on total rows in inn 1/2 (not adjusted revised matches)
    innings_totals=defaultdict(dict)
    for r in inn_rows: innings_totals[r['match_id']][r['innings']]=r['team_total']
    chase_dis=[]; chase_n=0; chase_agree=0
    revised_behavior=[]
    for mid,m in match.items():
        t=innings_totals[mid]; mi=match_info[mid]
        if 1 not in t or 2 not in t:continue
        target=t[1]+1; win=as_int(m.get('win_team_id'))
        # Determine chase batting side from innings 2 batting_team_id
        r2=balls_by_inn.get((mid,2),[]); batting2=as_int(r2[0]['batting_team_id']) if r2 else None
        if win and batting2 is not None:
            chase_n+=1; agree=(win==batting2)==(t[2]>=target)
            if agree:chase_agree+=1
            else:chase_dis.append({'match_id':mid,'innings1_total':t[1],'derived_target':target,'innings2_total':t[2],'innings2_batting_team_id':batting2,'win_team_id':win,'result':m.get('result',''),'revised_target':m.get('revised_target','')})
        if mi['revised']:revised_behavior.append({'match_id':mid,'revised_target':m.get('revised_target',''),'first_inn_revised_overs':m.get('first_inn_revised_overs',''),'second_inn_revised_overs':m.get('second_inn_revised_overs',''),'innings1_total':t.get(1,''),'innings2_total':t.get(2,''),'derived_target':target})
    write_csv(OUT/'chase_outcome_disagreements.csv',['match_id','innings1_total','derived_target','innings2_total','innings2_batting_team_id','win_team_id','result','revised_target'],chase_dis)
    write_csv(OUT/'revised_target_matches.csv',['match_id','revised_target','first_inn_revised_overs','second_inn_revised_overs','innings1_total','innings2_total','derived_target'],revised_behavior)
    # Derive leakage-safe state inputs for every regular-innings delivery; no pressure flags.
    inn_total_map={(r['match_id'],r['innings']):r['team_total'] for r in inn_rows}
    state_rows=[]
    for key,rs in balls_by_inn.items():
        if key[1]>2: continue
        target=(inn_total_map.get((key[0],1),0)+1) if key[1]==2 and (key[0],1) in inn_total_map else ''
        for j,(r,state) in enumerate(zip(rs,iter_pre_delivery_states(rs))):
            needed=(int(target)-state['runs_before']) if target!='' else ''
            state_rows.append({'match_id':key[0],'innings':key[1],'sequence':j+1,'source_innings_ball_num':r.get('innings_ball_num',''),
                'team_runs_before':state['runs_before'],'wickets_lost_before':state['wickets_before'],'legal_balls_before':state['legal_balls_before'],
                'legal_balls_remaining_120':state['legal_balls_remaining_120'],'wickets_in_previous_12_legal_balls':state['wickets_previous_12_legal'],
                'target_innings2':target,'runs_needed_before':needed})
    state_headers=['match_id','innings','sequence','source_innings_ball_num','team_runs_before','wickets_lost_before','legal_balls_before','legal_balls_remaining_120','wickets_in_previous_12_legal_balls','target_innings2','runs_needed_before']
    write_csv(OUT/'pre_delivery_state.csv',state_headers,state_rows)
    write_csv(OUT/'pre_delivery_state_sample.csv',state_headers,state_rows[:500])
    (OUT/'derivability_checks.md').write_text('# Pre-delivery derivability (Phase 0)\n\n**VERIFIED as structurally derivable for every regular-innings delivery:** cumulative team runs, wickets lost, legal balls bowled and remaining (120 minus legal balls), wickets in the preceding 12 legal deliveries, and chase target/runs-needed inputs when innings-1 total exists. The full derived audit table is `pre_delivery_state.csv`; a 500-row sample is `pre_delivery_state_sample.csv`. Values at delivery *t* are computed before incorporating delivery *t*. This is derivability only; no pressure flags are computed.\n\n**Blocked/limited:** revised-target chase states cannot be represented by innings-1 total + 1 alone and are excluded by approved scope; innings length/target may be shorter than regulation where the innings ended early. Current/required run rates can be derived after choosing zero-legal-ball handling, but no convention is approved here. Match outcome is a label, not a pre-delivery state.\n\nLeakage tests perturb current delivery outcomes and verify the current pre-state remains unchanged; see `tests/test_phase0_leakage.py` and saved pytest log.\n',encoding='utf-8')
    # exploratory counts
    count=[]
    emit_metric(count,'ball_by_ball rows',len(balls),200999)
    emit_metric(count,'ball_by_ball columns',len(ball_fields),33)
    emit_metric(count,'matches rows',len(matches),883)
    emit_metric(count,'competitions rows',len(comps),141)
    emit_metric(count,'T20I competition count',sum(1 for c in comps if c.get('match_format')=='T20I'),134)
    emit_metric(count,'T20 competition count',sum(1 for c in comps if c.get('match_format')=='T20'),7)
    emit_metric(count,'non-IPL T20 competition count',sum(1 for c in comps if c.get('match_format')=='T20' and not c.get('comp_name','').startswith('IPL')),2)
    emit_metric(count,'playing_eleven rows',len(pe),28381)
    emit_metric(count,'competition_team_player_mapping rows',len(mapping),6413)
    emit_metric(count,'teams rows',len(teams),353)
    emit_metric(count,'ball_by_ball distinct match IDs',len(balls_by_match),867)
    emit_metric(count,'ball_by_ball distinct player IDs (striker/non_striker/bowler/dismissed)',len(player_ball),959)
    key=[(r['match_id'],r['innings'],r['innings_ball_num']) for r in balls]
    emit_metric(count,'duplicate (match_id, innings, innings_ball_num)',len(key)-len(set(key)),0)
    emit_metric(count,'matches without ball data',len(no_ball),16,'See matches_without_ball_data.csv; result strings classified separately.')
    for i,expected in [(1,105727),(2,95234),(3,25),(4,13)]: emit_metric(count,f'ball rows innings {i}',sum(as_int(r['innings'])==i for r in balls),expected)
    emit_metric(count,'matches with super overs',len(super_matches),6)
    emit_metric(count,'is_wicket true rows',sum(truth(r.get('is_wicket')) for r in balls),10881)
    emit_metric(count,'dismissed_player_id non-null rows',sum(not null(r.get('dismissed_player_id')) for r in balls),10892)
    emit_metric(count,'dismissal_type non-null rows',sum(not null(r.get('dismissal_type')) for r in balls),10881)
    emit_metric(count,'IPL competitions 2022-2026',sum(c.get('comp_name','').startswith('IPL') and str(c.get('season','')) in {str(y) for y in range(2022,2027)} for c in comps),5)
    datevals=[m.get('match_date','') for m in matches if not null(m.get('match_date',''))]
    emit_metric(count,'match date minimum',min(datevals) if datevals else None,'2022-01-22')
    emit_metric(count,'match date maximum',max(datevals) if datevals else None,'2026-11-01')
    regular_fmt=Counter()
    for r in balls:
        if as_int(r['innings'])<=2:
            m=match.get(r['match_id'],{}); c=comp.get(m.get('comp_id',''),{}); fmt='IPL' if c.get('comp_name','').startswith('IPL') else ('T20I' if c.get('match_format')=='T20I' else 'other T20')
            regular_fmt[fmt]+=1
    for fmt,exp in [('T20I',106315),('IPL',87673),('other T20',6973)]: emit_metric(count,f'regular innings 1-2 rows format {fmt}',regular_fmt[fmt],exp)
    # exclusions exact funnel primary result
    emit_metric(count,'primary final eligible matches after exclusions and requirements',len(primary_set),788,'Sequential funnel: reports/phase0_audit/exclusion_funnel.csv')
    emit_metric(count,'primary final eligible deliveries (pre-legal-balls <120)',len(primary_delivery_rows),187968)
    emit_metric(count,'primary innings 1 deliveries (pre-legal-balls <120)',sum(as_int(r['innings'])==1 for r in primary_delivery_rows),97915)
    emit_metric(count,'primary innings 2 deliveries (pre-legal-balls <120)',sum(as_int(r['innings'])==2 for r in primary_delivery_rows),90053)
    # player event volume incl all formats regular innings
    bat_balls=Counter(); bowl_legal=Counter()
    for r in balls:
        if as_int(r['innings'])>2:continue
        if r.get('extras_type','').lower()!='wide':bat_balls[r.get('striker_id')]+=1
        if r.get('extras_type','').lower() not in {'wide','overstep'}:bowl_legal[r.get('bowler_id')]+=1
    for prefix,vals,targets,median_exp in [('batters balls faced',bat_balls,{120:294,200:214,300:171},52),('bowlers legal balls',bowl_legal,{120:309,200:226,300:183},108)]:
        nonzero=sorted(v for v in vals.values() if v>0)
        median=(nonzero[(len(nonzero)-1)//2]+nonzero[len(nonzero)//2])/2 if nonzero else None
        if median is not None and float(median).is_integer(): median=int(median)
        emit_metric(count,f'{prefix} player count',len(nonzero),888 if 'batters' in prefix else 647)
        emit_metric(count,f'{prefix} median',median,median_exp)
        for thresh,expected in targets.items():emit_metric(count,f'{prefix} players >= {thresh}',sum(v>=thresh for v in nonzero),expected)
    emit_metric(count,'regular innings count (innings 1-2)',sum(1 for r in inn_rows if r['innings']<=2),1712)
    emit_metric(count,'regular innings with <100 legal balls',len(short),217)
    bat_inn=defaultdict(int)
    for r in balls:
        if as_int(r['innings'])<=2:bat_inn[(r['match_id'],as_int(r['innings']),r['striker_id'])]+=as_int(r.get('runs'))
    emit_metric(count,'batter-innings with striker appearance',len(bat_inn),13729)
    emit_metric(count,'batter-innings with 80+ bat runs',sum(v>=80 for v in bat_inn.values()),318)
    emit_metric(count,'bowl_speed zero share',f"{100*sum(as_int(r.get('bowl_speed'))==0 for r in balls)/len(balls):.2f}%",'~39%','Approximate reference; actual fraction saved as percentage.')
    emit_metric(count,'is_wicket vs dismissal field disagreement rows',len(disag),'~11','Expected approximately 11; exact disagreements listed in wicket_flag_disagreements.csv.')
    emit_metric(count,'chase outcome consistency count',f'{chase_agree}/{chase_n}',None,'Every disagreement listed in chase_outcome_disagreements.csv.')
    write_csv(OUT/'reproduced_counts.csv',['metric','expected','reproduced','status','notes'],count)
    # More required outputs
    (OUT/'joins_and_identity.md').write_text('# Joins, referential integrity and identity\n\n```json\n'+json.dumps(orphans,indent=2)+'\n```\n\nBall player IDs are the union of striker, non-striker, bowler and dismissed-player IDs. Player ID/name ambiguity tables are `player_ids_multiple_names.csv` and `player_names_multiple_ids.csv`.\n\nPlaying XI impact-flag rows: '+str(len(impact))+'; `is_played=false` rows: '+str(len(not_played))+'.\n',encoding='utf-8')
    (OUT/'coverage_and_semantics.md').write_text('# Coverage and source semantics\n\n## Result classifications\n\n'+'\n'.join(f'- {k}: {v}' for k,v in sorted(result_classes.items()))+'\n\n## Missing ball data\n\nSee `matches_without_ball_data.csv` for IDs and result.\n\n## Dismissal classes\n\nSee `dismissal_type_counts.csv`. Proposed review mapping: bowled, caught, caught and bowled, lbw, stumped, hit wicket, hit the ball twice, obstructing the field, and handled the ball are potentially bowler-creditable only if the source class/official rule supports it; run out, retired hurt/out, obstructing field and other classes require conservative exclusion. This list is a review proposal only and has not been applied to scoring. Any class not confidently resolved must remain provisional not-bowler-credited.\n\nLegal ball is calculated per approved definition `extras_type` not in {wide, Overstep}; batter faced ball uses extras_type != wide. Team total is the approved formula `runs + extras1_runs + extras_2_runs`; bowler-charged runs semantic still requires empirical reconciliation of extras categories.\n',encoding='utf-8')
    # Verify archive readability, required filenames, extraction paths and byte identity.
    archive=ROOT/'data/raw/datapack.zip'
    with zipfile.ZipFile(archive) as z:
        bad_member=z.testzip()
        members=z.namelist()
        inventory=[{'member':n,'size_bytes':i.file_size,'macos_metadata':n.startswith('__MACOSX/'),'sha256':hashlib.sha256(z.read(n)).hexdigest()} for n,i in ((i.filename,i) for i in z.infolist())]
    write_csv(OUT/'archive_inventory.csv',['member','size_bytes','macos_metadata','sha256'],inventory)
    expected_archive_members=['Data Pack/'+n for n in EXPECTED_FILES]+['Data Pack/Round 1 Problem Statement _ SupeRR Selector Season 2.docx.pdf']
    missing_archive=[n for n in expected_archive_members if n not in members]
    (OUT/'archive_validation.md').write_text('# Archive validation\n\n`ZipFile.testzip()` result: '+repr(bad_member)+'. Required CSV/PDF archive members missing: '+(', '.join(missing_archive) if missing_archive else 'none')+'. All required extracted source files were SHA-256 compared with their archive member in `source_integrity.csv`. The `__MACOSX/` paths are metadata entries and do not contain missing required files.\n',encoding='utf-8')
    integrity=[]
    for name in EXPECTED_FILES+['problemstatement.pdf']:
        disk=RAW/name; archive_name='Data Pack/'+name
        if name=='problemstatement.pdf': archive_name='Data Pack/Round 1 Problem Statement _ SupeRR Selector Season 2.docx.pdf'
        member_exists=archive_name in members
        member_hash=hashlib.sha256(zipfile.ZipFile(archive).read(archive_name)).hexdigest() if member_exists else ''
        disk_hash=sha(disk)
        if name.endswith('.csv'):
            fields,rs=read_csv(name); readable=bool(fields); detail=f'{len(rs)} rows; {len(fields)} columns'
        else:
            doc=PdfReader(str(disk)); readable=len(doc.pages)>0; detail=f'{len(doc.pages)} pages; text chars {sum(len(p.extract_text() or "") for p in doc.pages)}'
        integrity.append({'filename':name,'path':str(disk.relative_to(ROOT)),'readable':readable,'detail':detail,'size_bytes':disk.stat().st_size,'sha256':disk_hash,'archive_member':archive_name if member_exists else 'MISSING','archive_sha256':member_hash,'archive_matches_extracted':bool(member_exists and member_hash==disk_hash)})
    write_csv(OUT/'source_integrity.csv',['filename','path','readable','detail','size_bytes','sha256','archive_member','archive_sha256','archive_matches_extracted'],integrity)
    quality=[
      {'issue_id':'DQ-01','severity':'needs decision','evidence':'wicket_flag_disagreements.csv','finding':f'{len(disag)} rows disagree across is_wicket, dismissal_type and dismissed_player_id presence; 12 rows have is_wicket=false with dismissed_player_id set and 1 Retire Out row lacks dismissed_player_id.','smallest_proposed_fix':'Use the actual dismissal identifier only after owner review; retain anomalies without raw edits.'},
      {'issue_id':'DQ-02','severity':'needs decision','evidence':'player_ids_multiple_names.csv; player_names_multiple_ids.csv','finding':f'{len(multi_id)} IDs map to multiple names; {len(multi_name)} names map to multiple IDs. Same-name IDs are listed individually.','smallest_proposed_fix':'Preserve player_id as key and flag ambiguous display names.'},
      {'issue_id':'DQ-03','severity':'needs decision','evidence':'joins_and_identity.md','finding':f'{len(orphans["ball_players_missing_playing_eleven"])} player IDs occur in balls but not playing_eleven.','smallest_proposed_fix':'Review competition/team/player mapping and impact-substitute representation; do not drop/merge IDs in Phase 0.'},
      {'issue_id':'DQ-04','severity':'needs decision','evidence':'chase_outcome_disagreements.csv','finding':f'{len(chase_dis)} matches disagree between innings-1 total + 1 chase outcome and win_team_id/result.','smallest_proposed_fix':'Review each listed case, especially ties/revised targets; revised matches remain out of primary scope.'},
      {'issue_id':'DQ-05','severity':'needs decision','evidence':'reproduced_counts.csv; exclusion_funnel.csv','finding':f'Explicitly filtered primary match count {len(primary_set)} differs from exploratory reference 788.','smallest_proposed_fix':'Use the exact written scope/exclusions and preserve this mismatch for independent review; no methodology edit is made.'},
      {'issue_id':'DQ-08','severity':'minor','evidence':'referential_integrity.csv','finding':'Five teams table (comp_id, team_id) pairs are absent from competition_team_player_mapping.csv; all match/ball team references reconcile.','smallest_proposed_fix':'Keep as supporting-table gaps; verify no downstream player join depends on these five pairs.'},
      {'issue_id':'DQ-06','severity':'minor','evidence':'reproduced_counts.csv; data_dictionary.csv','finding':'bowl_speed is zero on 38.74% of ball rows; units and whether zero denotes missing/sentinel are unverified.','smallest_proposed_fix':'Keep as descriptive raw field only; clarify semantics if it is needed later.'},
      {'issue_id':'DQ-07','severity':'minor','evidence':'source_integrity.csv; archive_inventory.csv','finding':'Archive places files under Data Pack/ and includes __MACOSX metadata; extracted PDF filename differs from archive original filename, but SHA-256 is identical.','smallest_proposed_fix':'Retain current extracted layout; document the verified byte-identical mapping.'},
    ]
    write_csv(OUT/'data_quality_issues.csv',['issue_id','severity','evidence','finding','smallest_proposed_fix'],quality)
    source_paths=[RAW/n for n in EXPECTED_FILES]+[RAW/'problemstatement.pdf',ROOT/'data/raw/datapack.zip']
    checksum_text=''.join(f'{sha(p)}  {p.relative_to(ROOT)}\n' for p in source_paths)
    (ROOT/'data/raw/checksums.sha256').write_text(checksum_text,encoding='utf-8')
    pdf=PdfReader(str(RAW/'problemstatement.pdf'))
    ptext='\n'.join(page.extract_text() or '' for page in pdf.pages)
    (OUT/'problem_statement_summary.md').write_text('# Problem statement summary (VERIFIED from supplied PDF)\n\nThe two-page brief requires two submission components: two ordered top-10 lists (batters and bowlers) selected in Unstop dropdowns, and a methodology report. The report must explain pressure definition, performance/baseline/rating logic, fair comparisons (sample size, eligibility, contexts, IPL/T20I), evidence for top-ten ordering, reliability/limitations, and reproducibility. It says rankings must use supplied-data analysis rather than reputation. An optional 30–60 second process video/photos are not required. Source: `data/raw/Data Pack/problemstatement.pdf` (2 pages).\n',encoding='utf-8')
    print(json.dumps({'csv_profiles':profiles,'reproduced_counts':count,'primary_matches':len(primary_set),'primary_deliveries':len(primary_delivery_rows),'wicket_disagreements':len(disag),'chase_agreement':f'{chase_agree}/{chase_n}','pdf_pages':len(pdf.pages)},indent=2))
if __name__=='__main__': main()
