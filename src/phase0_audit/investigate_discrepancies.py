"""Focused follow-up to Phase 0; read-only against data/raw."""
import csv
from collections import defaultdict, Counter
from pathlib import Path
R=Path('data/raw/Data Pack'); O=Path('reports/phase0_audit')
NULL={'','null','none','na','nan'}
def read(n):
    with (R/n).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def nn(x):return (x or '').strip().lower() not in NULL
def i(x):
    try:return int(float(x))
    except:return 0
def dump(path,fields,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
comps={r['comp_id']:r for r in read('competitions.csv')}; matches={r['match_id']:r for r in read('matches.csv')}; balls=read('ball_by_ball.csv')
by=defaultdict(lambda:defaultdict(list))
for r in balls:by[r['match_id']][i(r['innings'])].append(r)
# Four super-over matches excluded wholesale by the prior implementation, although only innings >2 are excluded by the written rule.
super_ids=sorted(mid for mid,ins in by.items() if any(inn>2 for inn in ins) and ((comps[matches[mid]['comp_id']]['comp_name'].startswith('IPL')) or comps[matches[mid]['comp_id']]['match_format']=='T20I'))
cohort=[]; match_summary=[]; added_total=0
for mid in super_ids:
    m=matches[mid]; c=comps[m['comp_id']]; added=0
    super_rows=sum(len(rs) for inn,rs in by[mid].items() if inn>2)
    for inn,rs in sorted(by[mid].items()):
        legal=0; eligible=0; team_total=0
        for r in rs:
            if inn in (1,2) and legal<120:eligible+=1
            team_total+=i(r['runs'])+i(r['extras1_runs'])+i(r['extras_2_runs'])
            if r['extras_type'].lower() not in {'wide','overstep'}:legal+=1
        delta=eligible if inn in (1,2) else 0
        added+=delta
        cohort.append({'match_id':mid,'comp_id':m['comp_id'],'competition':c['comp_name'],'match_format':c['match_format'],'season':c['season'],'exclusion_reason_in_prior_audit':'entire match removed because an innings >2 existed','written_rule_treatment':('keep regular innings delivery rows' if inn in (1,2) else 'exclude super-over innings'), 'innings':inn,'source_delivery_rows':len(rs),'legal_balls':legal,'team_total':team_total,'qualifying_rows_prelegal120':eligible,'rows_added_vs_prior_cohort':delta,'super_over_rows_for_match':super_rows if inn==1 else 0,'result':m['result'],'win_team_id':m['win_team_id']})
    added_total+=added
    match_summary.append({'match_id':mid,'comp_id':m['comp_id'],'competition':c['comp_name'],'format':c['match_format'],'season':c['season'],'reason':'super-over innings caused whole-match exclusion in prior audit','innings1_qualifying_rows':sum(1 for _ in []),'regular_rows_added':added,'super_over_rows_excluded':super_rows,'result':m['result']})
# patch innings 1 field
for ms in match_summary:
    mid=ms['match_id'];ms['innings1_qualifying_rows']=next(x['qualifying_rows_prelegal120'] for x in cohort if x['match_id']==mid and x['innings']==1);ms['innings2_qualifying_rows']=next(x['qualifying_rows_prelegal120'] for x in cohort if x['match_id']==mid and x['innings']==2)
dump(O/'cohort_mismatch_rows.csv',['match_id','comp_id','competition','match_format','season','exclusion_reason_in_prior_audit','written_rule_treatment','innings','source_delivery_rows','legal_balls','team_total','qualifying_rows_prelegal120','rows_added_vs_prior_cohort','super_over_rows_for_match','result','win_team_id'],cohort)
# Recalculate eligible counts both under old match-level and written innings-level super-over handling.
current=0; current_rows=0; corrected=0; corrected_rows=0
for mid,m in matches.items():
 c=comps[m['comp_id']]; scope=c['comp_name'].startswith('IPL') or c['match_format']=='T20I'; result=m['result'].lower()
 revised=any(nn(m[k]) for k in ['revised_target','first_inn_revised_overs','second_inn_revised_overs'])
 both=1 in by[mid] and 2 in by[mid]; winner=nn(m['win_team_id']) and i(m['win_team_id'])!=0
 if not(scope and not('abandon' in result or 'no result' in result) and not revised and both and winner):continue
 has_super=any(inn>2 for inn in by[mid].keys())
 rowct=sum(1 for inn in (1,2) for r in by[mid].get(inn,[]) if True) # per-delivery filter below
 eligible_rows=0
 for inn in (1,2):
  legal=0
  for r in by[mid].get(inn,[]):
   if legal<120:eligible_rows+=1
   if r['extras_type'].lower() not in {'wide','overstep'}:legal+=1
 if not has_super:current+=1;current_rows+=eligible_rows
 corrected+=1;corrected_rows+=eligible_rows
assert len(super_ids)==4 and added_total==1006
assert (current,current_rows)==(784,186962)
assert (corrected,corrected_rows)==(788,187968)
# Ten source-referenced disagreements; expected outcome is from winner ID and innings-2 batting team.
inn_total=defaultdict(lambda:defaultdict(int)); inn_bat=defaultdict(dict); legal_balls=defaultdict(lambda:defaultdict(int))
for r in balls:
    mid=r['match_id'];inn=i(r['innings'])
    inn_total[mid][inn]+=i(r['runs'])+i(r['extras1_runs'])+i(r['extras_2_runs'])
    inn_bat[mid].setdefault(inn,r['batting_team_id'])
    if r['extras_type'].lower() not in {'wide','overstep'}:legal_balls[mid][inn]+=1
mismatches=[]
for mid,m in matches.items():
    if 1 not in inn_total[mid] or 2 not in inn_total[mid]:continue
    target=inn_total[mid][1]+1;score=inn_total[mid][2];bat2=inn_bat[mid][2];winner=m['win_team_id']
    expected='chasing team won' if winner==bat2 else 'chasing team lost'
    calculated='chasing team won' if score>=target else 'chasing team lost'
    if expected==calculated:continue
    revvals={k:m[k] for k in ['revised_target','first_inn_revised_overs','second_inn_revised_overs']}
    has_rev=any(nn(v) for v in revvals.values()); result=m['result']; lower=result.lower(); c=comps[m['comp_id']]
    source_margin='win by runs' if 'won by' in lower and 'run' in lower else ('win by wickets' if 'won by' in lower and 'wicket' in lower else 'tie/other')
    if not has_rev:
        status='REQUIRES_OWNER_DECISION'; why='Result text says DLS but all revised-target/overs fields are blank. The simple formula is arithmetically correct, but source metadata does not provide the adjusted target; determine whether to flag/exclude based on DLS result.'
    elif mid=='48610':
        status='REQUIRES_OWNER_DECISION'; why='Revised target 115 and innings-2 total 125 plus win_team_id support a chasing win, but result string says "won by 11 runs"; reconcile contradictory outcome text/margin.'
    else:
        status='EXPLAINED'; why=f'Revised target/overs are populated; simple target {target} is not the DLS target. Innings-2 score {score} compared with revised_target {m["revised_target"]} agrees with win_team_id.'
    mismatches.append({'match_id':mid,'comp_id':m['comp_id'],'competition':c['comp_name'],'match_format':c['match_format'],'season':c['season'],'expected_result_from_win_team_id':expected,'calculated_result_using_innings1_plus_1':calculated,'innings1_total':inn_total[mid][1],'simple_derived_target':target,'innings2_total':score,'innings2_batting_team_id':bat2,'win_team_id':winner,'source_result':result,'source_result_margin_phrase':source_margin,'revised_target':revvals['revised_target'],'first_inn_revised_overs':revvals['first_inn_revised_overs'],'second_inn_revised_overs':revvals['second_inn_revised_overs'],'innings1_legal_balls':legal_balls[mid][1],'innings2_legal_balls':legal_balls[mid][2],'dls_mentioned_in_result':'yes' if 'dls' in lower or 'd/l' in lower else 'no','classification':status,'likely_explanation':why})
assert len(mismatches)==10
fields=list(mismatches[0].keys());dump(O/'chase_outcome_mismatches.csv',fields,mismatches)
# Readable investigation report
lines=['# Phase 0 discrepancy investigation','', '**Scope:** focused follow-up only. Raw files were opened read-only. No Phase 0 rerun, raw-data modification, pressure flag, score, ranking or dashboard was produced. The Phase 0 PASS_WITH_NOTES gate is retained pending owner review of two DLS metadata gaps and one conflicting result string.','', '## 1. Primary cohort mismatch — RESOLVED (prior audit implementation error)','', 'The previous cohort code treated `any innings > 2` as a reason to discard the whole match. The written rule excludes super-over innings (innings > 2), while retaining eligible innings 1 and 2 from otherwise qualifying IPL/T20I matches. The exact four matches are below. They contribute 1,006 qualifying regular-innings delivery rows; their super-over delivery rows remain excluded. Applying the written row-level rule yields **788 matches and 187,968 delivery rows**, exactly the exploratory reference, without changing scope or methodology.','', '| Match | Competition | Innings 1 qualifying rows | Innings 2 qualifying rows | Added rows | Super-over rows excluded |','|---:|---|---:|---:|---:|---:|']
for m in match_summary: lines.append(f"| {m['match_id']} | {m['competition']} | {m['innings1_qualifying_rows']} | {m['innings2_qualifying_rows']} | {m['regular_rows_added']} | {m['super_over_rows_excluded']} |")
lines += ['',f"**Total:** {len(super_ids)} matches and {added_total} qualifying regular-innings delivery rows. The per-innings breakdown, including innings 3/4 rows that remain excluded, is in `cohort_mismatch_rows.csv`.",'', 'Breakdown by competition: India in Sri Lanka T20I Series 2024 = 1 match / 252 rows; IPL 2025 = 1 / 252; Asia Cup 2025 (match_format T20I) = 1 / 252; IPL 2026 = 1 / 250. All four were otherwise in scope, had innings 1 and 2, a nonzero winner, and no revised-target flags. Their sole prior exclusion reason was a super-over innings in the same match. The difference is therefore a **match-vs-innings exclusion error**, not a scope-definition difference or a source-data error. Do not remove whole matches when implementing the approved exclusion.','', '## 2. Chase outcome disagreements','', 'The Phase 0 check compares (a) source winner ID against the innings-2 batting team and (b) innings-2 total against innings-1 total + 1. It is a valid simple-target check only when the target was not revised. All ten source result strings mention DLS/D/L. Eight have a revised target and/or revised-overs field populated; the remaining two have DLS result text but all three revision fields blank.','', '| Match | Expected from winner ID | Simple-target calculation | Revised target / overs | Classification |','|---:|---|---|---|---|']
for x in mismatches: lines.append(f"| {x['match_id']} | {x['expected_result_from_win_team_id']} | {x['calculated_result_using_innings1_plus_1']} | {x['revised_target']} / {x['first_inn_revised_overs']} / {x['second_inn_revised_overs']} | {x['classification']} |")
lines += ['', 'Seven cases are **EXPLAINED**: 16754, 21586, 28046, 34428, 40749, 41851, and 48611. Their revised target/overs fields explain why innings-1 total + 1 does not match the source outcome; the innings-2 score compared with `revised_target` agrees with the winner ID. These are definition differences, not arithmetic errors.','', 'Three cases **REQUIRE_OWNER_DECISION**:','', '- **24822 and 28334:** the source result text explicitly says DLS, but `revised_target`, `first_inn_revised_overs`, and `second_inn_revised_overs` are blank. The arithmetic uses the approved simple formula correctly, but the adjusted target is unavailable. The explicit marker-based exclusion rule does not currently identify these matches. Decide whether to flag/exclude DLS-result matches with missing revised fields or retain them with an explicit data-quality exception.','- **48610:** revision fields indicate a revised target of 115 and innings-2 score is 125; `win_team_id` is the innings-2 batting team, so those fields support a chase win. However, `result` says “England Won by 11 runs,” which conflicts with a chasing-side win by wickets/target attainment. Decide which source field should control result-text validation; this match is already marked revised by its structured fields.','', 'For all ten, `chase_outcome_mismatches.csv` includes match/competition/season, expected and calculated outcomes, raw innings totals, simple target, innings-2 batting team, winner ID, result text, all revised fields, legal-ball counts, classification and explanation. The mismatch count is 10; it is not evidence of a calculation bug in the simple formula. It shows that the formula is inapplicable to DLS cases and that some structured/result metadata need review.','', '## Gate and recommendation','', 'The cohort mismatch is **RESOLVED** as an earlier implementation error; the written scope is validated by the exact 788 / 187,968 result when super-over innings alone are excluded. The chase mismatches are definition/metadata issues: seven EXPLAINED, three REQUIRES_OWNER_DECISION. Retain Phase 0 **PASS_WITH_NOTES**. Phase 1 may proceed with the row-level super-over exclusion and the already-approved revised-field exclusions; carry matches 24822 and 28334 as flagged metadata exceptions and do not invent revised targets. Resolve the owner decisions before pressure-state validation or any use of these outcomes as validation labels. No subsequent phase was started here.','']
(O/'discrepancy_investigation.md').write_text('\n'.join(lines),encoding='utf-8')
print(f'current cohort=784 / 186962; corrected row-level cohort={corrected} / {corrected_rows}; delta={len(super_ids)} matches / {added_total} rows')
print('super-over match IDs:',','.join(super_ids))
print('chase mismatch classifications:',dict(Counter(x['classification'] for x in mismatches)))
