from __future__ import annotations

import csv
import json
from pathlib import Path

from src.deliverables import build_dashboard, data as D


def test_payload_uses_frozen_rankings_and_preserves_counts():
    payload = D.build_payload()
    for role in ('bowler', 'batter'):
        rows = payload['rankings'][f'{role}_chase']
        source = list(csv.DictReader((D.PHASE5 / f'ranking_{role}_chase.csv').open()))
        assert len(rows) == len(source)
        assert [(r['player_id'], r['S_star']) for r in rows] == [
            (r['player_id'], float(r['S_star'])) for r in source
        ]
    assert payload['headline']['bowler_published'] == 10
    assert payload['headline']['batter_published'] == 8
    assert payload['headline']['innings1_eligible'] == 0


def test_context_and_role_boundaries_hold():
    payload = D.build_payload()
    rows = payload['rankings']['bowler_chase'] + payload['rankings']['batter_chase']
    assert all(r['context'] == 'chase' for r in rows)
    assert all(r['role'] == 'bowler' for r in payload['rankings']['bowler_chase'])
    assert all(r['role'] == 'batter' for r in payload['rankings']['batter_chase'])
    assert payload['contexts'][2]['ranking_published'] is False


def test_required_limitations_remain_open_and_visible():
    payload = D.build_payload()
    issues = {r['id']: r for r in payload['issues']}
    for issue_id in ('PH5-01', 'PH5-02', 'PH5-03', 'F4-01', 'F4-02',
                     'PH3-01', 'PH2-05', 'F5-01', 'F5-02', 'F6-01', 'F6-02'):
        assert issue_id in issues
    assert 'OPEN' in issues['PH3-01']['status']
    assert 'OPEN' in issues['PH2-05']['status']
    assert '8 clear' in issues['F4-01']['detail']


def test_dashboard_is_offline_and_embeds_the_canonical_payload():
    payload = D.build_payload()
    html_path = D.ROOT / 'outputs/final/deliverables/dashboard/index.html'
    data_path = D.ROOT / 'outputs/final/deliverables/dashboard/dashboard_data.json'
    html = html_path.read_text(encoding='utf-8')
    assert build_dashboard._external_requests(html) == []
    assert 'https://' not in html and 'http://' not in html
    embedded = json.loads(data_path.read_text(encoding='utf-8'))
    assert [r['player_id'] for r in embedded['rankings']['bowler_chase']] == [
        r['player_id'] for r in payload['rankings']['bowler_chase']
    ]
    assert len(embedded['rankings']['batter_chase']) == 8


def test_pdf_source_carries_notation_and_uncertainty_reading_note():
    source = (D.ROOT / 'src/deliverables/build_report.py').read_text(encoding='utf-8')
    assert "self.page('Appendix C · glossary'" in source
    for symbol in ("['S_raw'", "['A*'", "['B*'", "['B_A'", "['S*'", "['λ'"):
        assert symbol in source
    assert "callout('How to read one row'" in source
    assert 'The fixed fit is a' in source


def test_frozen_inputs_have_recorded_hashes():
    payload = D.build_payload()
    assert set(payload['provenance']['frozen_hashes']) == set(D.FROZEN)
    assert payload['verification']['independent_all_pass'] is True
    assert payload['verification']['frozen_inputs_unchanged'] is True
