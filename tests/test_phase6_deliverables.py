from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from src.deliverables import build_dashboard, build_report, data as D


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


def _render_report(payload):
    return build_report.Report(payload, None).build().render()


def test_report_tier_table_matches_frozen_context_status():
    payload = D.build_payload()
    context = list(csv.DictReader((D.PHASE5 / 'context_status.csv').open()))
    source = {r['role']: r for r in context if r['context'] == 'chase'}
    tiers = build_report.Report(payload, None)._tier_rows()
    assert [(r[0], r[2], r[3]) for r in tiers] == [
        ('High', source['bowler']['tier_high'], source['batter']['tier_high']),
        ('Moderate', source['bowler']['tier_moderate'], source['batter']['tier_moderate']),
        ('Limited', source['bowler']['tier_limited'], source['batter']['tier_limited']),
        ('Insufficient', source['bowler']['tier_insufficient'], source['batter']['tier_insufficient']),
    ]
    assert tiers[1][2] == '9' and tiers[2][2] == '27' and tiers[3][2] == '367'
    assert 'Of which published' in _render_report(payload)


def test_report_uses_recorded_phase6_pytest_pass_total():
    log = (D.ROOT / 'reports/phase_6/logs/pytest_phase6.txt').read_text()
    import re
    match = re.search(r'(\d+) passed(?:,\s*(\d+) failed)?', log)
    assert match
    passed = int(match.group(1))
    total = passed + int(match.group(2) or 0)
    assert build_report.phase6_pytest_count() == (passed, total)
    assert f'{passed} / {total}' in _render_report(D.build_payload())


def test_report_discloses_sensitivity_eligibility_from_frozen_csv():
    payload = D.build_payload()
    rows = {r['scenario']: r for r in csv.DictReader(
        (D.ROOT / 'reports/phase_5/sensitivity_rank.csv').open()) if r['role'] == 'batter'}
    assert rows['tau2_REML']['eligible'] == '0'
    assert rows['single_stage_combination']['eligible'] == '0'
    assert rows['variance_E1']['overlap_with_primary'] == '0'
    html = _render_report(payload)
    assert '0/8 batters survive' in html
    assert 'REML variance (0 eligible)' in html
    assert 'single-stage combination (0 eligible)' in html


def test_report_top_three_stability_comes_from_rank_stability_csv():
    payload = D.build_payload()
    rows = list(csv.DictReader((D.ROOT / 'reports/phase_5/rank_stability.csv').open()))
    top = [r for r in rows if r['role'] == 'bowler' and r['context'] == 'chase'][:3]
    assert int(float(top[2]['share_top10']) * 100) == 96
    html = _render_report(payload)
    assert 'under resampling (96–100%)' in html


def test_executive_page_lists_all_frozen_bowlers_and_batters():
    payload = D.build_payload()
    html = _render_report(payload)
    executive = re.search(r'<section class="page executive" data-page="3">(.*?)</section>',
                          html, re.S).group(1)
    for role in ('bowler', 'batter'):
        csv_path = D.PHASE5 / f'ranking_{role}_chase.csv'
        for row in csv.DictReader(csv_path.open()):
            assert row['player_name'] in executive
            for value in (f"{float(row['S_star']):+.3f}",
                          f"[{float(row['S_ci90_low']):+.3f}, {float(row['S_ci90_high']):+.3f}]"):
                assert value in executive
            assert row['evidence_tier'] in executive
