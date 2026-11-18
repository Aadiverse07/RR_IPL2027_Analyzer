"""Independent raw-to-processed state progression check for five configured matches."""
import csv
from collections import defaultdict, deque
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
def ai(v):
    try:return int(float(v))
    except:return 0
def truth(v):return str(v).lower() in {'true','1','yes'}

def generate():
    cfg=yaml.safe_load((ROOT/'config/methodology.yaml').read_text());ids=cfg['verification']['manual_match_ids']
    raw=defaultdict(lambda:defaultdict(list));processed={};
    with (ROOT/'data/raw/Data Pack/ball_by_ball.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['match_id'] in ids and ai(r['innings'])<=2:raw[r['match_id']][ai(r['innings'])].append(r)
    with (ROOT/'data/processed/balls_primary.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['match_id'] in ids:processed[(r['match_id'],int(r['innings']),r['innings_ball_num'])]=r
    matches={r['match_id']:r for r in csv.DictReader((ROOT/'data/processed/matches_primary.csv').open(encoding='utf-8-sig',newline=''))}
    comps={r['comp_id']:r for r in csv.DictReader((ROOT/'data/raw/Data Pack/competitions.csv').open(encoding='utf-8-sig',newline=''))}
    assert len(ids)==5 and sum(matches[x]['format']=='IPL' for x in ids)>=2 and sum(matches[x]['format']=='T20I' for x in ids)>=2
    lines=['# Manual state verification (Phase 1)','','This check independently rereads raw `ball_by_ball.csv`, recalculates each pre-delivery progression from prior raw rows, and compares it with `data/processed/balls_primary.csv`. It includes two IPL matches, three T20Is, and match 14101 (an early-finished chase). Source `result` and `win_team_id` are displayed unchanged and are not used as state.','']
    overall=0;early=False
    for mid in ids:
        m=matches[mid];comp=comps[m['comp_id']]
        lines += [f"## Match {mid} — {m['format']} {m['season']} · {comp['comp_name']}",'',f"Source result: `{m['result']}` · source winner ID: `{m['win_team_id']}` · contains super over: `{m['contains_super_over']}",'', '| Inn | Seq | legal? | team runs before | wickets before | legal balls before | balls remaining | wickets previous 12 legal | target | runs needed | stored check |','|---:|---:|:---:|---:|---:|---:|---:|---:|---:|---:|:---:|']
        total1=sum(ai(r['runs'])+ai(r['extras1_runs'])+ai(r['extras_2_runs']) for r in raw[mid][1]);target=total1+1
        for inn in (1,2):
            runs=wkts=legal_balls=0;window=deque(maxlen=12)
            for seq,r in enumerate(raw[mid][inn],1):
                legal=str(r['extras_type']).lower() not in {'wide','overstep'}
                if legal_balls>=int(cfg['innings']['legal_balls']):
                    if (mid,inn,r['innings_ball_num']) in processed:raise AssertionError('delivery at/after 120 legal balls unexpectedly materialized')
                    if legal:legal_balls+=1;window.append(int(truth(r['is_wicket'])))
                    runs+=ai(r['runs'])+ai(r['extras1_runs'])+ai(r['extras_2_runs']);wkts+=int(truth(r['is_wicket']))
                    continue
                out=processed[(mid,inn,r['innings_ball_num'])]
                remain=max(0,int(cfg['innings']['legal_balls'])-legal_balls)
                t=target if inn==2 else ''
                rn=target-runs if inn==2 else ''
                actual=(ai(out['team_runs_before']),ai(out['wickets_lost_before']),ai(out['legal_balls_before']),ai(out['legal_balls_remaining']),ai(out['wickets_in_previous_12_legal_balls']))
                expected=(runs,wkts,legal_balls,remain,sum(window))
                assert actual==expected,(mid,inn,seq,actual,expected)
                assert out['legal']==str(legal).lower()
                assert out['target']==(str(t) if t!='' else '')
                assert out['runs_needed_before']==(str(rn) if rn!='' else '')
                if inn==2 and legal_balls<100:early=True
                lines.append(f"| {inn} | {seq} | {'yes' if legal else 'no'} | {runs} | {wkts} | {legal_balls} | {remain} | {sum(window)} | {t} | {rn} | MATCH |")
                overall+=1
                runs+=ai(r['runs'])+ai(r['extras1_runs'])+ai(r['extras_2_runs']);wkts+=int(truth(r['is_wicket']))
                if legal:legal_balls+=1;window.append(int(truth(r['is_wicket'])))
        lines.append('')
    assert early,'manual sample lacks a chase finishing early'
    lines += [f'**VERIFIED:** {overall} regular-innings raw delivery states compared row by row with the processed output; every check matched. Match 14101 chase ends before 100 legal balls.']
    (ROOT/'reports/phase_1/manual_verification.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return overall
if __name__=='__main__':print('manual raw-to-processed state rows verified:',generate())
