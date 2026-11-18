"""Regression tests for the corrected chase-flag validation rule (MDR-2026-11-18-01)."""
import csv, json
from pathlib import Path
import yaml

import pytest
from src.pressure.validate_chase_v2 import evaluate, rule_from_config

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / 'config/methodology.yaml').read_text())
V2 = ROOT / 'reports/phase_2/validation_v2'
SUMMARY = json.loads((V2 / 'chase_validation_v2_summary.json').read_text())
LEGACY = list(csv.DictReader((ROOT / 'reports/phase_2/difficulty_validation.csv').open()))


def test_rule_is_versioned_and_owner_approved():
    rule = CFG['validation']['chase_direction_rule']
    assert rule['version'] == '2026-11-18.v2'
    assert rule['approved_by'] == 'owner'
    assert (ROOT / rule['decision_record']).exists()


def test_shared_flag_directions_follow_chasing_side_semantics():
    rule = CFG['validation']['chase_direction_rule']
    expected = rule['expected_direction']
    assert expected['batter_runs'] == 'lower'
    assert expected['bowler_runs'] == 'lower'
    assert expected['batter_dot'] == 'higher'
    assert expected['batter_dismissal'] == 'reported'
    # The contradiction this rule replaced: one shared flag cannot require lower
    # runs and higher runs conceded on the same delivery.
    assert expected['batter_runs'] == expected['bowler_runs']
    assert set(rule['mandatory_metrics']) == {'batter_runs', 'bowler_runs'}


def test_corrected_validation_passes_on_mandatory_metrics():
    assert SUMMARY['verdict'] == 'PASS_WITH_DISCLOSED_LIMITATION'
    assert SUMMARY['mandatory_failures'] == []
    assert SUMMARY['mandatory_inconclusive'] == []
    for key, row in SUMMARY['mandatory_metrics'].items():
        assert row['status'] == 'PASS', key
        assert float(row['ci_high']) < 0, key
    assert SUMMARY['directionally_consistent_failures'] == []
    assert SUMMARY['reversed_gating_cells'] == []


def test_dismissal_is_reported_as_disclosed_limitation():
    limitation = SUMMARY['disclosed_limitation']
    assert limitation['metric'] == 'batter dismissal'
    assert limitation['status'] == 'REPORTED'
    assert 'not gated' in limitation['note']


def test_estimator_and_flags_were_not_changed():
    unchanged = SUMMARY['estimator_unchanged']
    assert unchanged['match'] is True
    assert unchanged['max_abs_estimate_delta'] == 0.0
    assert unchanged['rows_compared'] == 282


def test_pooled_sample_sizes_are_true_delivery_counts():
    counts = SUMMARY['sample_size_counts']['per_role']
    for role, rec in counts.items():
        assert rec['legacy_inflation_factor'] == 3.0
        assert rec['actual_flagged_deliveries'] == rec['legacy_reported_n_flagged'] // 3
        assert int(SUMMARY['mandatory_metrics'][f'{role}_runs']['n_flagged']) == rec['actual_flagged_deliveries']


def test_f2_fallback_stays_invalid_under_the_corrected_rule():
    """F2 must not be rescued by the rule change: batter runs are significantly higher
    than ordinary under a flag that claims chasing-side pressure."""
    cells = [r for r in LEGACY
             if r['definition'] == 'press_chase_fallback_f2'
             and r['role'] == 'batter' and r['outcome_metric'] == 'runs'
             and r['group_level'] == 'phase_wickets_format'
             and int(r['n_flagged']) >= 500]
    reversed_cells = [r for r in cells if float(r['ci_low']) > 0]
    assert len(reversed_cells) >= 1
    pooled = [r for r in LEGACY
              if r['definition'] == 'press_chase_fallback_f2'
              and r['group_level'] == 'pooled_wickets_stratified'
              and r['role'] == 'batter' and r['outcome_metric'] == 'runs'][0]
    assert float(pooled['difference']) > 0


def test_corrected_rule_does_not_touch_superseded_outputs():
    snap = ROOT / 'reports/phase_2/revisions/2026-11-18_pre_chase_direction_v2/reports/difficulty_validation.csv'
    assert snap.exists()
    legacy_rule = json.loads(
        (ROOT / 'reports/phase_2/revisions/2026-11-18_pre_chase_direction_v2/reports/difficulty_validation_summary.json').read_text())
    assert legacy_rule['validation_pass'] is False


def _pooled_rule_fixture(batter_dot, ci_low, ci_high):
    """Minimal pooled metrics so the batter-dot gate determines acceptance."""
    def row(role, metric, estimate, low, high):
        return {
            'role': role,
            'outcome_metric': metric,
            'group_level': 'pooled_wickets_stratified',
            'difference': str(estimate),
            'ci_low': str(low),
            'ci_high': str(high),
            'n_flagged': '1000',
            'n_ordinary': '3000',
        }
    return [
        row('batter', 'runs', -0.05, -0.08, -0.02),
        row('bowler', 'runs', -0.05, -0.08, -0.02),
        row('batter', 'dot', batter_dot, ci_low, ci_high),
        row('batter', 'dismissal', 0.0, -0.01, 0.01),
    ]


@pytest.mark.parametrize(
    ('point', 'ci_low', 'ci_high', 'expected_status', 'expected_verdict'),
    [
        (0.01, -0.01, 0.03, 'INCONCLUSIVE', 'PASS_WITH_DISCLOSED_LIMITATION'),
        (0.0, -0.01, 0.02, 'INCONCLUSIVE', 'PASS_WITH_DISCLOSED_LIMITATION'),
        (-0.001, -0.01, 0.02, 'FAIL', 'FAIL'),
        (-0.01, -0.03, -0.002, 'FAIL', 'FAIL'),
        (0.005, -0.02, -0.001, 'FAIL', 'FAIL'),
    ],
    ids=[
        'positive-point-inconclusive-ci-accepted',
        'zero-point-equality-accepted',
        'negative-point-inconclusive-ci-rejected',
        'negative-point-significant-reversal-rejected',
        'positive-point-significant-ci-reversal-rejected',
    ],
)
def test_batter_dot_point_and_confidence_interval_gates_are_separate(
        point, ci_low, ci_high, expected_status, expected_verdict):
    rule = rule_from_config(CFG)
    evaluated = evaluate(rule, _pooled_rule_fixture(point, ci_low, ci_high))
    result = next(r for r in evaluated if r['metric_key'] == 'batter_dot')
    assert result['metric_status'] == expected_status
    # A significant CI reversal remains a separate blocker. For the negative
    # inconclusive case, failure comes from the point estimate alone.
    assert result['significant_reversed_direction'] == str(ci_high < 0).lower()

    from src.pressure.validate_chase_v2 import summarise
    summary = summarise(rule, evaluated)
    assert summary['verdict'] == expected_verdict
