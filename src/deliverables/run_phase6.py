"""Build and verify the Phase 6 communication deliverables.

The driver reads frozen Phase 5 files through the canonical payload, runs the
Phase 6 acceptance tests and browser checks, then builds the dashboard, deck,
and print-ready PDF. It never runs an analytical model or ranking pipeline.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pptx import Presentation

from src.deliverables import browser_check, build_dashboard, build_deck
from src.deliverables import build_report, charts, data as D, theme as T
from src.deliverables import check_report_layout

REPORTS = D.ROOT / 'reports/phase_6'
LOGS = REPORTS / 'logs'


def _run_tests() -> dict[str, Any]:
    LOGS.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'pytest', '-q', 'tests/test_phase6_deliverables.py']
    result = subprocess.run(command, cwd=D.ROOT, text=True, capture_output=True)
    output = result.stdout + result.stderr
    (LOGS / 'pytest_phase6.txt').write_text(output, encoding='utf-8')
    match = re.search(r'(\d+) passed(?:,\s*(\d+) failed)?', output)
    passed = int(match.group(1)) if match else 0
    failed = int(match.group(2) or 0) if match else (0 if result.returncode == 0 else 1)
    return {
        'command': ' '.join(command), 'exit_code': result.returncode,
        'passed': passed, 'failed': failed, 'output': output.strip(),
    }


def _build_charts(payload: dict[str, Any]) -> list[str]:
    made = []
    context_path, rates = charts.fig_context_rates()
    if (abs(rates['innings1_ahead_par|pressure'] - 1.61) > 0.02
            or abs(rates['innings1_ahead_par|baseline'] - 1.36) > 0.02):
        expected = {'innings1_ahead_par|pressure': 1.61,
                    'innings1_ahead_par|baseline': 1.36}
        raise RuntimeError(f'context rate guard failed: {rates}; expected {expected}')
    made.append(context_path)
    for func, args in (
        (charts.fig_funnel, (payload,)),
        (charts.fig_bowler_ci, (payload,)),
        (charts.fig_batter_ci, (payload,)),
        (charts.fig_pressure_vs_baseline, (payload,)),
        (charts.fig_bootstrap, (payload,)),
        (charts.fig_shrinkage, (payload,)),
        (charts.fig_eligibility_hist, (payload,)),
        (charts.fig_separation, (payload,)),
        (charts.fig_sensitivity, (payload,)),
        (charts.fig_headline, (payload,)),
    ):
        made.append(func(*args))
    return made


def _verify_deck(path: Path) -> dict[str, Any]:
    deck = Presentation(str(path))
    if len(deck.slides) != 27:
        raise RuntimeError(f'expected 27 deck slides, got {len(deck.slides)}')
    text = '\n'.join(
        shape.text for slide in deck.slides for shape in slide.shapes
        if getattr(shape, 'has_text_frame', False)
    )
    required = ('Ten chase bowlers', 'Eight batters clear the gate',
                'PH3-01', 'T20I', 'not statistically separable')
    missing = [phrase for phrase in required if phrase.lower() not in text.lower()]
    if missing:
        raise RuntimeError(f'deck is missing required disclosures: {missing}')
    return {'slides': len(deck.slides), 'required_disclosures': len(required)}


def _verify_pdf(path: Path) -> dict[str, Any]:
    pdf = PdfReader(str(path))
    if len(pdf.pages) != 22:
        raise RuntimeError(f'expected 22 PDF pages, got {len(pdf.pages)}')
    page15 = pdf.pages[14].extract_text() or ''
    appendix_c = pdf.pages[20].extract_text() or ''
    if 'how to read one row' not in page15.casefold():
        raise RuntimeError('page 15 is missing the uncertainty reading note')
    for token in ('Notation', 'S_raw', 'B_A', 'S*', 'λ'):
        if token not in appendix_c:
            raise RuntimeError(f'Appendix C is missing {token}')
    return {
        'pages': len(pdf.pages), 'page15_reading_note': True,
        'appendix_c_notation': True,
        'appendix_c_chars': len(appendix_c),
    }


def run() -> dict[str, Any]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    frozen_before = D.frozen_hashes()
    payload = D.build_payload()
    D.validate_payload(payload)

    tests = _run_tests()
    if tests['exit_code'] or tests['failed'] or not tests['passed']:
        raise RuntimeError(f'Phase 6 tests failed: {tests}')

    chart_paths = _build_charts(payload)
    dashboard = build_dashboard.build(payload)
    if dashboard['external_requests']:
        raise RuntimeError(f'dashboard depends on network assets: {dashboard["external_requests"]}')
    browser = browser_check.run_checks(T.DELIVERABLES / 'dashboard/index.html')
    (LOGS / 'browser_checks.json').write_text(json.dumps(browser, indent=2) + '\n')
    if not browser['all_pass']:
        raise RuntimeError(f'dashboard browser checks failed: {browser}')

    deck = build_deck.build(payload)
    deck_check = _verify_deck(D.ROOT / deck['path'])

    static = {
        'passed': sum(1 for row in payload['verification']['internal']
                      if row['result'].upper() == 'PASS'),
        'total': len(payload['verification']['internal']),
    }
    phase6 = {'static': static, 'browser': browser, 'tests': tests}
    report = build_report.build(payload, phase6)
    layout = check_report_layout.scan(T.DELIVERABLES / 'report/index.html')
    (LOGS / 'report_layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    if not layout['passed']:
        raise RuntimeError(f'report layout check failed: {layout["problems"]}')
    pdf = build_report.print_pdf()
    pdf_check = _verify_pdf(D.ROOT / pdf['pdf'])

    frozen_after = D.frozen_hashes()
    if frozen_before != frozen_after:
        changed = [key for key in frozen_before if frozen_before[key] != frozen_after[key]]
        raise RuntimeError(f'frozen Phase 5 inputs changed during Phase 6: {changed}')

    result = {
        'phase': 6,
        'status': 'PASS_WITH_NOTES',
        'completed_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'analytical_pipeline_run': False,
        'rankings_regenerated': False,
        'frozen_inputs_unchanged': True,
        'frozen_input_hashes': frozen_after,
        'phase6_tests': {k: v for k, v in tests.items() if k != 'output'},
        'phase5_static_checks': static,
        'dashboard': dashboard,
        'browser_checks': browser,
        'deck': {**deck, **deck_check},
        'report_html': report,
        'report_layout': {'pages': layout['pages'], 'clean': layout['clean'],
                          'problems': len(layout['problems'])},
        'pdf': {**pdf, **pdf_check},
        'charts': chart_paths,
        'limitations': [
            'Phase 5 ordering uncertainty and sensitivity remain unchanged.',
            'No T20I-only players meet eligibility in either role.',
            'First-innings bowling remains state-confounded and has zero eligible players.',
            'The batter shortlist contains eight players.',
            'No Phase 7, publication or deployment was performed.',
        ],
    }
    (LOGS / 'run_phase6.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
