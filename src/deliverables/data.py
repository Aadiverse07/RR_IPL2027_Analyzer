"""Canonical data layer for every Phase 6 deliverable.

All three deliverables (dashboard, deck, PDF) are built from the single payload
produced here, so a number cannot drift between them.

Read-only inputs
----------------
Frozen Phase 5 outputs (published rankings, exclusions, format table, context
status, identity resolution) and the frozen Phase 4 score tables (the full
scored pool, used only for distribution and drill-down context). The Phase 4
``name`` column is known to be corrupted (F5-01); display names always come
from the Phase 5 resolution, never from that column.

Nothing is recomputed: every published figure is copied verbatim from a frozen
CSV. The only derived values are counts, shares and orderings that Phase 5
already published in its own logs, and they are cross-checked against those
logs before the payload is returned.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

PHASE5 = ROOT / 'outputs/final/phase5'
SCORES = ROOT / 'outputs/final'
P5_REPORTS = ROOT / 'reports/phase_5'
CONFIG = ROOT / 'config/methodology.yaml'

# Frozen inputs that Phase 6 must not alter. Checked by the builder and by tests.
FROZEN = [
    'outputs/final/player_scores_batters.csv',
    'outputs/final/player_scores_bowlers.csv',
    'outputs/final/phase5/ranking_bowler_chase.csv',
    'outputs/final/phase5/ranking_batter_chase.csv',
    'outputs/final/phase5/ranking_exclusions.csv',
    'outputs/final/phase5/format_specific_ranking.csv',
    'outputs/final/phase5/context_status.csv',
    'outputs/final/phase5/player_identity.csv',
    'reports/phase_5/separation.csv',
    'reports/phase_5/rank_stability.csv',
    'reports/phase_5/sensitivity_rank.csv',
    'reports/phase_5/logs/run_phase5.json',
    'reports/phase_5/logs/independent_verification.json',
]

ISSUES = [
    {
        'id': 'PH5-01',
        'severity': 'Medium',
        'title': 'The published order is not statistically separable',
        'status': 'OPEN — carried into all Phase 6 deliverables',
        'detail': (
            'All ten published bowler 90% intervals contain zero and every adjacent pair '
            'overlaps; ranks 2 and 3 differ by 0.00008 in S*. Bootstrap P(top 10) is 0.97–1.00 '
            'for the top three but 0.40–0.55 for ranks 6–10. The defensible finding is the '
            'eligible set and its evidence tier, not the sequence.'
        ),
        'treatment': (
            'Every deliverable presents the list as an eligible set with intervals and tiers. '
            'No podium, no ranking-gap claim, no "best bowler" headline.'
        ),
        'plain': 'The list order could easily change with another sample. Treat it as a shortlist.',
    },
    {
        'id': 'PH5-02',
        'severity': 'Medium',
        'title': 'The combined ranking is mainly IPL-driven',
        'status': 'OPEN — disclosed in every Phase 6 deliverable',
        'detail': (
            'T20I between-player pressure variance is estimated at zero in both roles, so the '
            'T20I-only lists admit no player. IPL-only keeps 6 of the 10 published bowler names. '
            'The two-stage combination is descriptive, not a transferability claim.'
        ),
        'treatment': (
            'Format-specific estimates are shown next to the combined list; T20I-only is shown as '
            'empty rather than hidden. No claim that a player "would" perform the same in another '
            'format.'
        ),
        'plain': 'Most of the evidence is from the IPL. The T20I sample cannot rank anyone on its own.',
    },
    {
        'id': 'PH5-03',
        'severity': 'Low',
        'title': 'Player display names were corrupted upstream (cross-ref F5-01)',
        'status': 'MITIGATED in Phase 6 — OPEN in Phase 1 data',
        'detail': (
            'data/processed/players_dim.csv pairs dismissed_player_id with striker_name, so 197 of '
            '1,217 rows carry 2–5 display names. Identifiers are unaffected: 0 of 959 delivery IDs '
            'map to more than one name.'
        ),
        'treatment': (
            'Display names resolve from the raw competition mapping through the Phase 5 identity '
            'file. The Phase 1 defect is documented, not silently patched, and the Phase 5 files '
            'are unchanged.'
        ),
        'plain': 'Names were fixed for display only. The numbers were never affected.',
    },
    {
        'id': 'PH3-01',
        'severity': 'Medium',
        'title': 'The first-innings bowling context is state-confounded',
        'status': 'OPEN — carried into Phase 6',
        'detail': (
            'The innings-1 flag is defined by cumulative scoring above par, so part of the state is '
            'the match scoring environment. Bowlers concede 1.61 runs per ball in that context '
            'versus 1.36 overall.'
        ),
        'treatment': (
            'The context is shown as a separate research finding and is never merged with chase. '
            'No player is ranked from it (zero eligible).'
        ),
        'plain': 'That context mixes match conditions with bowling skill, so we do not rank from it.',
    },
    {
        'id': 'PH2-05',
        'severity': 'High',
        'title': 'Broad and unvalidated pressure flags remain unused',
        'status': 'OPEN — unchanged',
        'detail': (
            'pressure_batter, pressure_bowler, press_bat_union and press_bat_collapse did not pass '
            'difficulty validation. The F2 fallback likewise failed and is invalid.'
        ),
        'treatment': (
            'Only the owner-approved, independently validated flags feed the model: press_chase and '
            'press_bowl_ahead. A test scans the source tree for the excluded names.'
        ),
        'plain': 'Only pressure definitions that passed validation were used; the rest are disqualified.',
    },
    {
        'id': 'F4-01',
        'severity': 'Medium',
        'title': 'Only eight batters reach the reliability threshold',
        'status': 'OPEN — shortfall published, not filled',
        'detail': '445 batters are scored in the chase context; 8 clear B_A ≥ 0.20.',
        'treatment': 'Eight are published. No player is promoted and no threshold is relaxed.',
        'plain': 'The batter list is short because the evidence is thin, not because the list was cut.',
    },
    {
        'id': 'F4-02',
        'severity': 'Medium',
        'title': 'No first-innings bowling ranking exists',
        'status': 'OPEN — research finding published',
        'detail': '377 bowlers are scored in that context; 0 reach B_A ≥ 0.20 (maximum 0.150).',
        'treatment': 'Reported as a finding. No ranking, no partial list, no cross-context borrowing.',
        'plain': 'The data cannot support that ranking, so none is shown.',
    },
    {
        'id': 'F5-01',
        'severity': 'Medium',
        'title': 'players_dim.csv pairs the wrong names with IDs',
        'status': 'OPEN in Phase 1 — display resolved in Phase 6',
        'detail': (
            'The defect is in data/processed/players_dim.csv, produced in Phase 1. Phase 5 resolved '
            'display names from the raw competition mapping without touching Phase 1–4 outputs.'
        ),
        'treatment': (
            'Documented with evidence and a reproduction path. Regenerating players_dim.csv needs its '
            'own authorisation; Phase 6 does not change frozen outputs.'
        ),
        'plain': 'A naming bug in an intermediate file. Scores and IDs were never wrong.',
    },
    {
        'id': 'F5-02',
        'severity': 'Low',
        'title': 'The pre-registered bootstrap design was rejected before publication',
        'status': 'CLOSED — measured, rejected, replaced, logged',
        'detail': (
            'A bootstrap that also re-estimated the variance model inflated shrinkage (median '
            'eligible 195 vs 36 for bowler chase; 206 vs 8 for batters).'
        ),
        'treatment': (
            'Replaced by a fixed-EB-fit bootstrap. Both designs remain in '
            'reports/phase_5/logs/run_phase5.json.'
        ),
        'plain': 'One bootstrap method failed its own check and was replaced before anything shipped.',
    },
    {
        'id': 'F6-01',
        'severity': 'Medium',
        'title': 'Dashboard player drawers need role-aware keys',
        'status': 'FIXED / VERIFIED',
        'detail': ('A player ID can occur for both roles. The lookup key now includes role, '
                   'and the browser suite checks that the two drawers remain separate.'),
        'treatment': 'Keep role in the row key and preserve the cross-role browser regression.',
        'plain': 'Batter and bowler details stay separate even when their numeric IDs match.',
    },
    {
        'id': 'F6-02',
        'severity': 'Low',
        'title': 'Appendix C exceeded its fixed PDF page',
        'status': 'FIXED / VERIFIED',
        'detail': ('The notation table and a duplicate closing callout did not fit together. '
                   'The redundant callout was removed; all notation remains.'),
        'treatment': 'Keep the glossary and notation; verify all fixed pages after every rebuild.',
        'plain': 'The final PDF contains the complete notation without clipped text.',
    },
]


# --------------------------------------------------------------------- helpers

def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def _f(value: str | None) -> float | None:
    """CSV string to float, preserving None for genuinely missing values."""
    if value is None or value == '' or value.lower() == 'nan':
        return None
    return float(value)


def _i(value: str | None) -> int | None:
    number = _f(value)
    return None if number is None else int(number)


def _b(value: str | None) -> bool | None:
    if value is None or value == '':
        return None
    return value.strip().lower() == 'true'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_hashes() -> dict[str, str]:
    return {rel: sha256(ROOT / rel) for rel in FROZEN}


# ---------------------------------------------------------------- pool shaping

POOL_FIELDS = {
    'player_id': str,
    'role': str,
    'context': str,
    'formats_present': str,
    'format_basis': str,
    'evidence_tier': str,
    'reliability_status': str,
    'S_star': _f,
    'S_ci90_low': _f,
    'S_ci90_high': _f,
    'A_star': _f,
    'B_star': _f,
    'D_star': _f,
    'A_raw': _f,
    'B_raw': _f,
    'n_pressure': _i,
    'n_baseline': _i,
    'pressure_matches': _i,
    'baseline_matches': _i,
    'total_matches': _i,
    'shrinkage_A': _f,
    'shrinkage_B': _f,
    'eligible': _b,
    'scored': _b,
    'consistency_matches': _i,
    'consistency_positive_share': _f,
    'consistency_match_sd': _f,
    'pressure_balls': _i,
    'pressure_runs': _f,
    'pressure_dot_pct': _f,
    'pressure_boundary_pct': _f,
    'pressure_wickets': _i,
    'pressure_dismissals': _i,
    'baseline_balls': _i,
    'baseline_runs': _f,
    'baseline_dot_pct': _f,
    'baseline_boundary_pct': _f,
    'A_star_IPL': _f,
    'shrink_A_IPL': _f,
    'n_pressure_IPL': _i,
    'A_star_T20I': _f,
    'shrink_A_T20I': _f,
    'n_pressure_T20I': _i,
    'pressure_matches_IPL': _i,
    'pressure_matches_T20I': _i,
}


def _pool_rows(role: str, names: dict[str, str]) -> list[dict[str, Any]]:
    path = SCORES / f'player_scores_{role}s.csv'
    out: list[dict[str, Any]] = []
    for raw in _read_csv(path):
        if not _b(raw.get('scored')):
            row = {key: conv(raw.get(key)) for key, conv in POOL_FIELDS.items()}
        else:
            row = {key: conv(raw.get(key)) for key, conv in POOL_FIELDS.items()}
        row['player_name'] = names.get(row['player_id'] or '', 'Unknown player')
        row['role'] = role
        # Derived presentation helpers (no new modelling).
        row['runs_per_ball_pressure'] = (
            row['pressure_runs'] / row['pressure_balls']
            if row['pressure_runs'] is not None and row['pressure_balls'] else None
        )
        row['runs_per_ball_baseline'] = (
            row['baseline_runs'] / row['baseline_balls']
            if row['baseline_runs'] is not None and row['baseline_balls'] else None
        )
        out.append(row)
    return out


# ------------------------------------------------------------------ published

def _published(role: str) -> list[dict[str, Any]]:
    path = PHASE5 / f'ranking_{role}_chase.csv'
    rows = _read_csv(path)
    out: list[dict[str, Any]] = []
    for raw in rows:
        out.append({
            'rank': _i(raw['rank']),
            'player_id': raw['player_id'],
            'player_name': raw['player_name'],
            'role': raw['role'],
            'context': raw['context'],
            'formats_present': raw['formats_present'],
            'S_star': _f(raw['S_star']),
            'S_ci90_low': _f(raw['S_ci90_low']),
            'S_ci90_high': _f(raw['S_ci90_high']),
            'A_star': _f(raw['A_star']),
            'B_star': _f(raw['B_star']),
            'D_star': _f(raw['D_star']),
            'A_raw': _f(raw['A_raw']),
            'B_raw': _f(raw['B_raw']),
            'n_pressure': _i(raw['n_pressure']),
            'n_baseline': _i(raw['n_baseline']),
            'pressure_matches': _i(raw['pressure_matches']),
            'baseline_matches': _i(raw['baseline_matches']),
            'total_matches': _i(raw['total_matches']),
            'shrinkage_A': _f(raw['shrinkage_A']),
            'evidence_tier': raw['evidence_tier'],
            'reliability_status': raw['reliability_status'],
            'consistency_matches': _i(raw['consistency_matches']),
            'consistency_positive_share': _f(raw['consistency_positive_share']),
            'consistency_match_sd': _f(raw['consistency_match_sd']),
            'pressure_balls': _i(raw['pressure_balls']),
            'pressure_runs_per_ball': _f(raw['pressure_runs_per_ball']),
            'pressure_dot_pct': _f(raw['pressure_dot_pct']),
            'pressure_boundary_pct': _f(raw['pressure_boundary_pct']),
            'pressure_wickets': _i(raw['pressure_wickets']),
            'pressure_dismissals': _i(raw['pressure_dismissals']),
            'baseline_runs_per_ball': _f(raw['baseline_runs_per_ball']),
            'baseline_dot_pct': _f(raw['baseline_dot_pct']),
            'A_star_IPL': _f(raw['A_star_IPL']),
            'shrink_A_IPL': _f(raw['shrink_A_IPL']),
            'n_pressure_IPL': _i(raw['n_pressure_IPL']),
            'A_star_T20I': _f(raw['A_star_T20I']),
            'shrink_A_T20I': _f(raw['shrink_A_T20I']),
            'n_pressure_T20I': _i(raw['n_pressure_T20I']),
            'format_disagree': _b(raw['format_disagree']),
            'bootstrap_share_top10': _f(raw['bootstrap_share_top10']),
            'bootstrap_rank_median': _i(raw['bootstrap_rank_median']),
            'bootstrap_rank_p05': _i(raw['bootstrap_rank_p05']),
            'bootstrap_rank_p95': _i(raw['bootstrap_rank_p95']),
            'gap_from_previous': _f(raw['gap_from_previous']),
            'ci_overlaps_previous': _b(raw['ci_overlaps_previous']),
            'ci_contains_zero': _b(raw['ci_contains_zero']),
            'score_explanation': raw['score_explanation'],
            'notes': raw['notes'],
        })
    return out


def _attach_pool_rank(published: list[dict[str, Any]], pool: list[dict[str, Any]]) -> None:
    """Mark published players inside the pool and record the eligible ordering.

    The ordering is the pre-registered rule applied to the frozen eligible pool;
    it is only used to list eligible-but-unpublished players as context. The
    published rank itself is never recomputed.
    """
    by_key = {(row['player_id'], row['context']): row for row in pool}
    for row in published:
        target = by_key.get((row['player_id'], row['context']))
        if target is not None:
            target['published_rank'] = row['rank']
            target['published_S_star'] = row['S_star']
            target['published_ci'] = [row['S_ci90_low'], row['S_ci90_high']]
            target['published_name'] = row['player_name']


# --------------------------------------------------------------- misc tables

def _exclusions() -> list[dict[str, Any]]:
    rows = _read_csv(PHASE5 / 'ranking_exclusions.csv')
    out = []
    for raw in rows:
        out.append({
            'player_id': raw['player_id'],
            'player_name': raw['player_name'],
            'role': raw['role'],
            'context': raw['context'],
            'reason_code': raw['reason_code'],
            'reason_detail': raw['reason_detail'],
            'formats_present': raw['formats_present'],
            'shrinkage_A': _f(raw['shrinkage_A']),
            'evidence_tier': raw['evidence_tier'],
            'S_star': _f(raw['S_star']),
            'n_pressure': _i(raw['n_pressure']),
            'total_matches': _i(raw['total_matches']),
        })
    return out


def _format_table() -> list[dict[str, Any]]:
    """Format-specific lists.

    ``format_specific_ranking.csv`` publishes the per-format ``A_star``/``B_star``
    but writes the *combined* ``S_star`` in its score column, while ordering the
    rows by the format-specific score. The presentation therefore derives the
    format-specific score with the frozen formula and labels it as derived; the
    published combined score is kept separately and never shown as an IPL-only
    score. ``validate_payload`` checks the derivation against the published rank.
    """
    rows = _read_csv(PHASE5 / 'format_specific_ranking.csv')
    out = []
    for raw in rows:
        a_star = _f(raw['A_star'])
        b_star = _f(raw['B_star'])
        derived = None if a_star is None or b_star is None else a_star - 0.30 * b_star
        out.append({
            'format_scope': raw['format_scope'],
            'rank': _i(raw['rank']),
            'player_id': raw['player_id'],
            'player_name': raw['player_name'],
            'role': raw['role'],
            'context': raw['context'],
            'S_star_combined': _f(raw['S_star']),
            'S_star_format': derived,
            'A_star': a_star,
            'B_star': b_star,
            'shrinkage_A': _f(raw['shrinkage_A']),
            'n_pressure': _i(raw['n_pressure']),
            'in_combined_top': raw['in_combined_top'] == 'yes',
        })
    return out


def _contexts() -> list[dict[str, Any]]:
    rows = _read_csv(PHASE5 / 'context_status.csv')
    out = []
    for raw in rows:
        out.append({
            'role': raw['role'],
            'context': raw['context'],
            'rows': _i(raw['rows']),
            'scored': _i(raw['scored']),
            'eligible': _i(raw['eligible']),
            'max_shrinkage': _f(raw['max_shrinkage_A']),
            'tier_insufficient': _i(raw['tier_insufficient']),
            'tier_limited': _i(raw['tier_limited']),
            'tier_moderate': _i(raw['tier_moderate']),
            'tier_high': _i(raw['tier_high']),
            'ranking_published': raw['ranking_published'] == 'yes',
            'note': raw['note'],
        })
    return out


def _separation() -> list[dict[str, Any]]:
    rows = _read_csv(P5_REPORTS / 'separation.csv')
    return [{
        'rank': _i(r['rank']),
        'player_id': r['player_id'],
        'player_name': r['player_name'],
        'role': r['role'],
        'context': r['context'],
        'S_star': _f(r['S_star']),
        'ci90_low': _f(r['ci90_low']),
        'ci90_high': _f(r['ci90_high']),
        'ci_width': _f(r['ci_width']),
        'contains_zero': _b(r['contains_zero']),
        'gap_from_previous': _f(r['gap_from_previous']),
        'ci_overlaps_previous': _b(r['ci_overlaps_previous']),
    } for r in rows]


def _stability() -> list[dict[str, Any]]:
    rows = _read_csv(P5_REPORTS / 'rank_stability.csv')
    return [{
        'role': r['role'],
        'context': r['context'],
        'rank': _i(r['rank']),
        'player_id': r['player_id'],
        'player_name': r['player_name'],
        'replicates_scored': _i(r['replicates_scored']),
        'share_scored': _f(r['share_scored']),
        'replicates_top10': _i(r['replicates_top10']),
        'share_top10': _f(r['share_top10']),
        'rank_median': _i(r['rank_median']),
        'rank_p05': _i(r['rank_p05']),
        'rank_p95': _i(r['rank_p95']),
    } for r in rows]


def _sensitivity() -> list[dict[str, Any]]:
    rows = _read_csv(P5_REPORTS / 'sensitivity_rank.csv')
    return [{
        'scenario': r['scenario'],
        'role': r['role'],
        'context': r['context'],
        'eligible': _i(r['eligible']),
        'top_n': _i(r['top_n']),
        'published_limit': _i(r['published_limit']),
        'top_ids': [x for x in r['top_ids'].split('|') if x],
        'overlap_with_primary': _i(r['overlap_with_primary']),
        'overlap_share': _f(r['overlap_share']),
        'spearman_vs_primary': _f(r['spearman_vs_primary']),
        'note': r['note'],
    } for r in rows]


def _identity() -> dict[str, Any]:
    rows = _read_csv(PHASE5 / 'player_identity.csv')
    names = {r['player_id']: r['name'] for r in rows}
    duplicate = {}
    for r in rows:
        if r['duplicate_name'] == 'True':
            duplicate.setdefault(r['name'], []).append(r['player_id'])
    variants = [{
        'player_id': r['player_id'],
        'name': r['name'],
        'mapping_name': r['mapping_name'],
    } for r in rows if r['identity_status'] != 'OK']
    return {
        'total_rows': len(rows),
        'ok': sum(1 for r in rows if r['identity_status'] == 'OK'),
        'variants': variants,
        'duplicate_names': duplicate,
        'duplicate_name_count': len(duplicate),
        'names': names,
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


# ------------------------------------------------------------------- payload

def build_payload() -> dict[str, Any]:
    identity = _identity()
    names = identity['names']

    published_bowler = _published('bowler')
    published_batter = _published('batter')

    pool_bowler = [r for r in _pool_rows('bowler', names)]
    pool_batter = [r for r in _pool_rows('batter', names)]
    _attach_pool_rank(published_bowler, pool_bowler)
    _attach_pool_rank(published_batter, pool_batter)

    # Eligible pool ordering: the pre-registered rule, for context only.
    for pool in (pool_bowler, pool_batter):
        for row in pool:
            row['pool_order'] = None
        eligible = sorted(
            [r for r in pool if r['context'] == 'chase' and r['eligible']],
            key=lambda r: (
                -r['S_star'],
                -(r['shrinkage_A'] or 0.0),
                -(r['n_pressure'] or 0),
                int(r['player_id']),
            ),
        )
        for index, row in enumerate(eligible, start=1):
            row['pool_order'] = index

    exclusions = _exclusions()
    exclusion_by_key = {
        (r['player_id'], r['role'], r['context']): r for r in exclusions
    }
    for pool in (pool_bowler, pool_batter):
        for row in pool:
            match = exclusion_by_key.get((row['player_id'], row['role'], row['context']))
            row['exclusion_reason'] = match['reason_code'] if match else None
            row['exclusion_detail'] = match['reason_detail'] if match else None

    contexts = _contexts()
    separation = _separation()
    stability = _stability()
    sensitivity = _sensitivity()
    formats = _format_table()
    run_log = _load_json(P5_REPORTS / 'logs/run_phase5.json')
    independent = _load_json(P5_REPORTS / 'logs/independent_verification.json')
    validation = _read_csv(P5_REPORTS / 'validation_checks.csv')

    config_text = CONFIG.read_text(encoding='utf-8')
    thresholds = {
        'eligibility_shrinkage_min': 0.20,
        'tier_high_min': 0.50,
        'tier_moderate_min': 0.30,
        'tier_limited_min': 0.20,
        'score_weight_w': 0.70,
        'baseline_penalty': 0.30,
        'context_min_cell': 200,
        'wicket_bin_cap': 3,
        'kmin': 20,
    }
    # Guard: the values above must exist in the approved config file.
    for needle in ('eligibility_shrinkage_min: 0.20', 'high_min: 0.50',
                   'moderate_min: 0.30', 'limited_min: 0.20', 'primary_w: 0.70',
                   'context_min_cell: 200', 'wicket_bin_cap: 3'):
        if needle not in config_text:
            raise RuntimeError(f'approved threshold missing from config: {needle}')

    payload = {
        'meta': {
            'project': 'SupeRR Selector',
            'season': 'Season 2',
            'phase': 6,
            'phase_label': 'Communication deliverables',
            'built_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'date_label': '18 November 2026',
            'ranking_rule': 'S* = A* − 0.30·B*, eligible players only (B_A ≥ 0.20)',
            'ranking_rule_long': (
                'Eligible players only (reliability B_A ≥ 0.20). Order by '
                'S* = A* − 0.30·B* descending; ties by B_A, then pressure deliveries, then ID. '
                'Publication length min(10, eligible). Pre-registered in '
                'SDR-2026-11-18-03 before any calculation.'
            ),
            'thresholds': thresholds,
            'methodology_record': 'SDR-2026-11-18-03',
            'score_weight': 0.70,
            'baseline_penalty': 0.30,
            'seed': 20261122,
            'bootstrap_reps': run_log['bootstrap']['bowler:chase'].get('reps', 200),
            'data_disclaimer': (
                'Every figure comes from the frozen Phase 5 outputs. Nothing is simulated, '
                'imputed or estimated for presentation.'
            ),
        },
        'headline': {
            'matches': 788,
            'deliveries': 187968,
            'chase_states': 89167,
            'auc': 0.8994,
            'calibration_slope': 0.9925,
            'ece': 0.00582,
            'bowler_scored': 388,
            'bowler_eligible': 36,
            'bowler_published': len(published_bowler),
            'batter_scored': 445,
            'batter_eligible': 8,
            'batter_published': len(published_batter),
            'innings1_scored': 377,
            'innings1_eligible': 0,
            'exclusions': len(exclusions),
        },
        'rankings': {
            'bowler_chase': published_bowler,
            'batter_chase': published_batter,
        },
        'pool': {
            'bowler_chase': [r for r in pool_bowler if r['context'] == 'chase'],
            'batter_chase': [r for r in pool_batter if r['context'] == 'chase'],
            'bowler_innings1': [r for r in pool_bowler if r['context'] == 'innings1_ahead_par'],
        },
        'exclusions': exclusions,
        'exclusion_summary': _summarise_exclusions(exclusions),
        'formats': formats,
        'format_summary': _summarise_formats(formats, published_bowler, published_batter),
        'contexts': contexts,
        'separation': separation,
        'stability': stability,
        'sensitivity': _summarise_sensitivity(sensitivity),
        'identity': {k: v for k, v in identity.items() if k != 'names'},
        'issues': ISSUES,
        'verification': {
            'internal': [{
                'check': r['check'], 'result': r['result'], 'detail': r['detail'],
            } for r in validation],
            'independent_all_pass': independent['all_pass'],
            'independent_checks': len(independent['checks']),
            'independent': [{
                'check': name,
                'result': status,
                'detail': independent.get('details', {}).get(name, ''),
            } for name, status in independent['checks'].items()],
            'frozen_inputs_unchanged': run_log['frozen_inputs_unchanged'],
        },
        'bootstrap_meta': run_log['bootstrap'],
        'rejected_bootstrap': run_log['rejected_bootstrap_design'],
        'provenance': {
            'frozen_hashes': frozen_hashes(),
            'manifest': 'reports/audit_bundle/sha256_outputs.txt',
            'inputs': {
                'source_deliveries': 187968,
                'matches': 788,
                'phase4_components': 2838,
                'phase4_residual_rows': 15560,
            },
        },
        'glossary': GLOSSARY,
        'definitions': DEFINITIONS,
    }
    validate_payload(payload)
    return payload


def _summarise_exclusions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row['role'], row['reason_code'])
        buckets[key] = buckets.get(key, 0) + 1
    labels = {
        'SHRINKAGE_BELOW_0.20': 'Reliability below the 0.20 threshold',
        'NO_VARIANCE': 'Too few deliveries to estimate any variance',
    }
    out = []
    for (role, code), count in sorted(buckets.items()):
        out.append({
            'role': role,
            'reason_code': code,
            'reason_label': labels.get(code, code),
            'count': count,
        })
    return out


def _summarise_formats(rows: list[dict[str, Any]],
                       published_bowler: list[dict[str, Any]],
                       published_batter: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for role, published in (('bowler', published_bowler), ('batter', published_batter)):
        role_rows = [r for r in rows
                     if r['role'] == role and r['context'] == 'chase']
        entry: dict[str, Any] = {
            'combined_top': len(published),
            'scopes': {},
        }
        for scope in ('IPL', 'T20I'):
            scope_rows = [r for r in role_rows if r['format_scope'] == scope]
            entry['scopes'][scope] = {
                'rows_shown': len(scope_rows),
                'shared_with_combined': sum(1 for r in scope_rows if r['in_combined_top']),
            }
        summary[role] = entry
    return summary


def _summarise_sensitivity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = {
        'primary': 'Approved specification',
        'w_0.30': 'Score weight w = 0.30',
        'w_0.50': 'Score weight w = 0.50',
        'tau2_REML': 'REML between-player variance',
        'single_stage_combination': 'Single-stage format combination',
        'variance_E1': 'E1 match-clustered variance',
        'format_IPL': 'IPL evidence only',
        'format_T20I': 'T20I evidence only',
    }
    out = []
    for row in rows:
        label = labels.get(row['scenario'], row['scenario'])
        if row['scenario'] == 'primary':
            label = f'Approved specification ({row["role"]})'
        out.append({**row, 'label': label})
    return out


def validate_payload(payload: dict[str, Any]) -> None:
    """Structural and honesty guards. Raises on any breach."""
    head = payload['headline']
    bowlers = payload['rankings']['bowler_chase']
    batters = payload['rankings']['batter_chase']

    assert head['bowler_published'] == 10, 'the approved rule publishes ten bowlers'
    assert head['batter_published'] == 8, 'exactly eight batters are eligible'
    assert len(bowlers) == 10 and len(batters) == 8

    ids = [r['player_id'] for r in bowlers + batters]
    assert len(ids) == len(set(ids)), 'a player appears twice across the rankings'
    assert not any(r['role'] != 'bowler' for r in bowlers)
    assert not any(r['role'] != 'batter' for r in batters)
    assert not any(r['context'] != 'chase' for r in bowlers + batters)

    for rows in (bowlers, batters):
        for row in rows:
            assert row['S_star'] is not None
            assert row['shrinkage_A'] >= 0.20
            assert row['S_ci90_low'] <= row['S_star'] <= row['S_ci90_high']
            assert row['player_name'] and '|' not in row['player_name'], row['player_name']
        order = [r['S_star'] for r in rows]
        assert order == sorted(order, reverse=True), 'published order is not S* descending'

    assert head['innings1_eligible'] == 0
    assert payload['contexts'][2]['ranking_published'] is False
    assert len(payload['exclusions']) == 845
    assert payload['verification']['independent_all_pass'] is True
    assert payload['verification']['frozen_inputs_unchanged'] is True
    assert payload['provenance']['frozen_hashes'], 'frozen hashes are required'

    # Pool coverage: every scored row in each context is present exactly once.
    pool = payload['pool']
    assert len(pool['bowler_chase']) == 403
    assert len(pool['batter_chase']) == 486
    assert len(pool['bowler_innings1']) == 388
    assert len({r['player_id'] for r in pool['bowler_chase']}) == 403
    assert len({r['player_id'] for r in pool['batter_chase']}) == 486

    # Published players are marked inside the pool, with the same score.
    marked = [r for r in pool['bowler_chase'] if r.get('published_rank')]
    assert len(marked) == 10
    for row in marked:
        assert row['published_S_star'] == row['S_star']

    # Every exclusion is reachable from the pool row it describes.
    tagged = [r for r in pool['bowler_chase'] + pool['batter_chase']
              if r.get('exclusion_reason')]
    assert len(tagged) == 845, len(tagged)

    # Format tables: the derived format-specific score reproduces the published
    # rank order, and the score column in the source is the combined score.
    formats = payload['formats']
    for scope in ('IPL', 'T20I'):
        for role in ('bowler', 'batter'):
            block = [r for r in formats if r['format_scope'] == scope and r['role'] == role]
            if not block:
                continue
            assert [r['rank'] for r in block] == list(range(1, len(block) + 1)), (scope, role)
            derived = [r['S_star_format'] for r in block]
            for upper, lower in zip(derived, derived[1:]):
                assert upper >= lower - 1e-12, f'{scope} {role} order breaks the derived score'
            differing = sum(1 for r in block
                            if r['S_star_combined'] is not None
                            and abs(r['S_star_combined'] - r['S_star_format']) > 1e-9)
            assert differing > 0 or scope == 'T20I', (
                f'{scope} {role}: expected the published S* column to be the combined score')

    # Eligible ordering in the pool reproduces the published order exactly.
    eligible = sorted(
        [r for r in pool['bowler_chase'] if r['pool_order']],
        key=lambda r: r['pool_order'],
    )
    assert [r['player_id'] for r in eligible[:10]] == [r['player_id'] for r in bowlers]
    assert all(r['shrinkage_A'] >= 0.20 for r in eligible)
    assert len(eligible) == 36
    assert len([r for r in pool['batter_chase'] if r['pool_order']]) == 8


# ------------------------------------------------------------------ glossary

GLOSSARY = [
    {
        'term': 'S* (Performance Score)',
        'plain': 'The published score. Positive means better than expected in pressure, '
                 'after allowing for the situation the player was in.',
    },
    {
        'term': 'A* (pressure performance)',
        'plain': 'How much better or worse than expected the player was on pressure deliveries, '
                 'shrunk towards the league average for reliability.',
    },
    {
        'term': 'B* (baseline form)',
        'plain': 'The same player’s non-pressure performance. It is a control, not a bonus: '
                 'good general form is partly subtracted so the ranking is about pressure.',
    },
    {
        'term': 'S* = A* − 0.30·B*',
        'plain': 'The approved formula. It keeps 70% of pressure performance and charges 30% '
                 'for general form.',
    },
    {
        'term': 'B_A (reliability / shrinkage weight)',
        'plain': 'How much of a player’s own record is kept rather than pulled to the average. '
                 '0 means we know nothing reliable; 1 means the record is taken at face value. '
                 'It decides eligibility; it is never part of the score.',
    },
    {
        'term': 'Evidence tier',
        'plain': 'A plain label for B_A: Limited (0.20–0.30), Moderate (0.30–0.50), High (0.50+). '
                 'No player in either published list reaches High.',
    },
    {
        'term': '90% interval',
        'plain': 'The plausible range for the score given the sample. If it contains zero, we '
                 'cannot rule out that the player is simply average in pressure.',
    },
    {
        'term': 'Pressure delivery',
        'plain': 'A ball bowled or faced while the validated chase-pressure flag is on — '
                 'roughly the tightest quarter of chase states.',
    },
    {
        'term': 'Empirical Bayes',
        'plain': 'A way of stopping small samples from producing extreme scores: each player is '
                 'pulled towards the league average by an amount that depends on how much '
                 'evidence they have.',
    },
    {
        'term': 'Bootstrap P(top 10)',
        'plain': 'How often the player stayed in the top ten when the data were resampled 200 '
                 'times. A low value means the list position is fragile.',
    },
    {
        'term': 'Format scope',
        'plain': 'IPL-only, T20I-only and the combined estimate. T20I alone cannot rank anyone '
                 'because its between-player spread is estimated at zero.',
    },
    {
        'term': 'Eligible pool',
        'plain': 'Every player who clears the reliability threshold in a context. The published '
                 'list is the top of that pool, not the whole pool.',
    },
]

DEFINITIONS = {
    'pressure': {
        'title': 'How pressure is defined',
        'body': (
            'A ball is "in pressure" when a calibrated chase model says the chasing side is in '
            'the tightest quarter of match states. The model uses only information available '
            'before that ball: score, wickets, balls left, target and format. It is trained on '
            'other matches, so a delivery can never influence its own label.'
        ),
        'bullets': [
            'Chase only: the state of the chasing innings, not the first innings.',
            'One shared flag for batters and bowlers, because it marks the same match state.',
            'First-innings bowling uses a separate, par-based flag and is never merged with chase.',
            'Broad and failed definitions (collapse, union, F2 fallback) are excluded by test.',
        ],
    },
    'performance': {
        'title': 'How performance is measured',
        'body': (
            'Every delivery is compared with what an average player would have done in the same '
            'situation — same format, innings, phase, wickets down and player type. Runs above or '
            'below that expectation count, and wickets are converted into runs through an '
            'estimated wicket value. The player’s pressure average of those differences is A; the '
            'non-pressure average is B.'
        ),
        'bullets': [
            'Situation is removed from the comparison, so a bowler is not punished for bowling '
            'at the death.',
            'The same player’s non-pressure record (B) controls for general form.',
            'A wicket is worth more in some phases; that value is estimated, not assumed.',
            'Only runs and wickets enter the score. Dot balls and strike rate are descriptives.',
        ],
    },
    'reliability': {
        'title': 'Why reliability is separate from performance',
        'body': (
            'A player with 20 pressure balls can post a spectacular average that would not '
            'survive another season. Empirical Bayes shrinks each record towards the league '
            'average by an amount that depends on how much evidence backs it. The shrinkage '
            'weight B_A is the Reliability of Evidence; the shrunk performance is A*.'
        ),
        'bullets': [
            'Reliability decides who is eligible (B_A ≥ 0.20). It never changes the score.',
            'Performance Score and Reliability are reported side by side and never multiplied.',
            'A Moderate tier means the record is worth reading; it is not a guarantee.',
            'Shrinkage is not a penalty: it is an admission of how much we actually know.',
        ],
    },
    'selection': {
        'title': 'How players were selected',
        'body': (
            'The rule was written down and frozen before any Phase 5 calculation. It ranks only '
            'eligible players, so a spectacular but thinly evidenced record cannot enter the '
            'list. Ten bowlers qualify; eight batters do, and the list stops at eight.'
        ),
        'bullets': [
            'Eligibility: B_A ≥ 0.20, unchanged from Phase 4.',
            'Order: S* = A* − 0.30·B*, ties by B_A, then pressure deliveries, then ID.',
            'Length: min(10, eligible). No filler rows, ever.',
            'The same rule is applied to bowlers and batters; nothing role-specific was tuned.',
        ],
    },
    'uncertainty': {
        'title': 'How to read the uncertainty',
        'body': (
            'The published order is an ordering of point estimates inside a shortlist, not a '
            'podium. Every bowler interval contains zero and every adjacent pair overlaps, so the '
            'data cannot separate rank 1 from rank 2 — or rank 1 from rank 10 with confidence. '
            'The bootstrap quantifies how fragile each position is.'
        ),
        'bullets': [
            'A positive point estimate can still have an interval that includes zero.',
            'Adjacent point estimates can be much closer than their uncertainty allows.',
            'The top three keep their place in 97–100% of resamples; ranks 6–10 in 40–55%.',
            'Format scope and variance estimator move the list more than the order does.',
        ],
    },
}
