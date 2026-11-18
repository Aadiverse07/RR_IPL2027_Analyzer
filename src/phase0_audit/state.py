"""Pure pre-delivery state derivation used only for Phase 0 leakage checks."""
def legal(row):
    return str(row.get('extras_type','')).strip().lower() not in {'wide','overstep'}
def as_int(v):
    try: return int(float(v))
    except (TypeError,ValueError): return 0
def is_wicket(row):
    return str(row.get('is_wicket','')).strip().lower() in {'true','1','yes'}
def pre_delivery_state(previous_rows):
    """Derive state from rows strictly before next delivery; caller passes no current row."""
    total=sum(as_int(r.get('runs'))+as_int(r.get('extras1_runs'))+as_int(r.get('extras_2_runs')) for r in previous_rows)
    wickets=sum(is_wicket(r) for r in previous_rows)
    legal_rows=[r for r in previous_rows if legal(r)]
    return {'runs_before':total,'wickets_before':wickets,'legal_balls_before':len(legal_rows),
            'legal_balls_remaining_120':max(0,120-len(legal_rows)),
            'wickets_previous_12_legal':sum(is_wicket(r) for r in legal_rows[-12:])}

def iter_pre_delivery_states(rows):
    """Yield state before each row, then update accumulators with that row's outcome."""
    runs=wickets=legal_balls=0
    legal_wicket_window=[]
    for current in rows:
        yield {'runs_before':runs,'wickets_before':wickets,'legal_balls_before':legal_balls,
               'legal_balls_remaining_120':max(0,120-legal_balls),
               'wickets_previous_12_legal':sum(legal_wicket_window[-12:])}
        runs += as_int(current.get('runs'))+as_int(current.get('extras1_runs'))+as_int(current.get('extras_2_runs'))
        wickets += int(is_wicket(current))
        if legal(current):
            legal_balls+=1
            legal_wicket_window.append(int(is_wicket(current)))
