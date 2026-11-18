"""Charts shared by the deck and the PDF report.

Every series is read from the Phase 6 payload, which is itself copied from the
frozen Phase 5 files. The only derived series is the league runs-per-ball panel,
computed from the published Phase 3 descriptive table and checked against the
figures quoted in the Phase 3 report (1.61 and 1.36 runs per ball).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

from src.deliverables import theme as T  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DPI = 220


def _font() -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in ('Helvetica Neue', 'Helvetica', 'Arial', 'DejaVu Sans'):
        if name in available:
            return name
    return 'DejaVu Sans'


FONT = _font()

plt.rcParams.update({
    'font.family': FONT,
    'font.size': 9,
    'axes.edgecolor': T.RULE,
    'axes.labelcolor': T.INK_SOFT,
    'axes.titlecolor': T.INK,
    'xtick.color': T.INK_FAINT,
    'ytick.color': T.INK_FAINT,
    'text.color': T.INK,
    'figure.facecolor': T.SURFACE,
    'axes.facecolor': T.SURFACE,
    'savefig.facecolor': T.SURFACE,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.grid': False,
    'legend.frameon': False,
})


def _out(name: str) -> Path:
    T.ASSETS.mkdir(parents=True, exist_ok=True)
    return T.ASSETS / name


def _save(fig, name: str) -> str:
    path = _out(name)
    fig.savefig(path, dpi=DPI, bbox_inches='tight', pad_inches=0.14,
                metadata={'Software': 'SupeRR Selector Phase 6'})
    plt.close(fig)
    return str(path.relative_to(ROOT))


def _clean(ax, grid_axis: str | None = None) -> None:
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color(T.RULE)
    if grid_axis:
        ax.grid(axis=grid_axis, color=T.RULE, linewidth=0.8, alpha=0.9)
        ax.set_axisbelow(True)


def _title(fig, title: str, subtitle: str | None = None) -> None:
    fig.text(0.0, 1.0, title, fontsize=13, fontweight='bold', color=T.INK,
             ha='left', va='bottom')
    if subtitle:
        fig.text(0.0, 1.0, subtitle, fontsize=8.6, color=T.INK_FAINT,
                 ha='left', va='bottom', transform=fig.transFigure)


# ------------------------------------------------------------------- figures

def fig_context_rates() -> tuple[str, dict[str, float]]:
    """League runs per ball by context and side (Phase 3 descriptive table)."""
    rows = list(csv.DictReader(
        (ROOT / 'reports/phase_3/descriptive_stats.csv').open(newline='', encoding='utf-8')))
    agg: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        if row['role'] != 'bowler':
            continue
        key = (row['context'], row['side'])
        bucket = agg.setdefault(key, [0.0, 0.0])
        bucket[0] += float(row['deliveries'])
        bucket[1] += float(row['runs'])
    rates = {f'{k[0]}|{k[1]}': v[1] / v[0] for k, v in agg.items()}

    labels = ['Chase\npressure', 'Chase\nbaseline',
              'Innings 1\npressure', 'Innings 1\nbaseline']
    keys = ['chase|pressure', 'chase|baseline',
            'innings1_ahead_par|pressure', 'innings1_ahead_par|baseline']
    values = [rates[k] for k in keys]
    colours = [T.PINK, T.PINK_SOFT, T.AMBER, T.BLUE_SOFT]

    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bars = ax.bar(range(4), values, color=colours, width=0.62,
                  edgecolor=[T.PINK, T.PINK, T.AMBER, T.BLUE], linewidth=1.0)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.025, f'{value:.2f}',
                ha='center', va='bottom', fontsize=10, fontweight='bold', color=T.INK)
    ax.set_xticks(range(4))
    ax.set_xticklabels(labels, fontsize=8.4, color=T.INK_SOFT)
    ax.set_ylim(0, 1.95)
    ax.set_ylabel('Runs conceded per ball', fontsize=8.6)
    _clean(ax, 'y')
    ax.axhline(1.386, color=T.INK_FAINT, linewidth=0.9, linestyle=(0, (4, 3)))
    ax.text(3.42, 1.405, 'chase baseline 1.39', fontsize=7.2, color=T.INK_FAINT, ha='right')
    ax.annotate('+18% vs baseline\n(PH3-01: state-confounded)', xy=(2, 1.62),
                xytext=(2.05, 1.86), fontsize=7.6, color=T.AMBER, ha='center')
    fig.suptitle('')
    fig.text(0.0, 1.02, 'Raw runs per ball barely move under chase pressure',
             fontsize=12.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 0.975, 'Same bowlers, same league, different match states. Economy rate hides this.',
             fontsize=8.4, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, 'context_rates.png'), rates


def fig_funnel(payload: dict[str, Any]) -> str:
    head = payload['headline']
    stages = [
        ('Matches in scope', f"{head['matches']:,}", 'IPL and T20I, super overs and abandoned matches removed'),
        ('Deliveries analysed', f"{head['deliveries']:,}", 'every ball of those matches'),
        ('Chase states modelled', f"{head['chase_states']:,}", 'information available before each ball'),
        ('Players scored', f"{head['batter_scored']} batters · {head['bowler_scored']} bowlers",
         'enough deliveries for a pressure and a baseline estimate'),
        ('Eligible on reliability', f"{head['batter_eligible']} batters · {head['bowler_eligible']} bowlers",
         'reliability B_A ≥ 0.20, the unchanged Phase 4 rule'),
        ('Published', f"{head['batter_published']} batters · {head['bowler_published']} bowlers",
         'length min(10, eligible) — no filler'),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(stages) * 1.15)
    ax.axis('off')
    for index, (label, value, note) in enumerate(stages):
        y = (len(stages) - index - 1) * 1.15
        highlight = index >= 4
        face = T.PINK_SOFT if index == 5 else (T.BLUE_SOFT if highlight else '#F1EFE9')
        edge = T.PINK if index == 5 else (T.BLUE if highlight else T.RULE)
        ax.add_patch(Rectangle((0.05, y + 0.12), 9.9, 0.86, facecolor=face,
                               edgecolor=edge, linewidth=1.0))
        ax.text(0.3, y + 0.72, label, fontsize=9.2, fontweight='bold', color=T.INK)
        ax.text(0.3, y + 0.40, note, fontsize=7.4, color=T.INK_SOFT)
        ax.text(9.72, y + 0.55, value, fontsize=11.4, fontweight='bold',
                color=T.PINK if index == 5 else T.INK, ha='right', va='center')
        if index < len(stages) - 1:
            ax.add_patch(FancyArrowPatch((5.0, y + 0.12), (5.0, y - 0.03),
                                         arrowstyle='-|>', mutation_scale=9,
                                         color=T.INK_FAINT, linewidth=0.9))
    fig.text(0.0, 1.015, 'From 187,968 balls to 18 published players',
             fontsize=12.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 0.972, 'Every stage is a published count. Nobody enters a list without clearing the same reliability gate.',
             fontsize=8.2, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, 'funnel.png')


def _ci_figure(rows: list[dict[str, Any]], title: str, subtitle: str,
               filename: str, height: float = 4.5) -> str:
    fig, ax = plt.subplots(figsize=(7.3, height))
    n = len(rows)
    ys = list(range(n))[::-1]
    for y, row in zip(ys, rows):
        colour = T.TIER_COLOURS.get(row['evidence_tier'], T.INK_FAINT)
        ax.plot([row['S_ci90_low'], row['S_ci90_high']], [y, y],
                color=colour, linewidth=2.6, alpha=0.32, solid_capstyle='round')
        ax.plot([row['S_ci90_low'], row['S_ci90_high']], [y, y],
                color=colour, linewidth=0.9, alpha=0.7)
        for edge in (row['S_ci90_low'], row['S_ci90_high']):
            ax.plot([edge, edge], [y - 0.16, y + 0.16], color=colour, linewidth=0.9, alpha=0.7)
        ax.scatter([row['S_star']], [y], s=62, color=colour, zorder=5,
                   edgecolor='white', linewidth=1.2)
        ax.text(row['S_ci90_high'] + 0.012, y, f"{row['S_star']:+.3f}",
                fontsize=8.2, va='center', color=T.INK, fontweight='bold')
    ax.axvline(0, color=T.INK, linewidth=1.0)
    ax.text(0.004, -0.62, 'zero = average in pressure', fontsize=7.2, color=T.INK_SOFT)
    ax.set_yticks(ys)
    ax.set_yticklabels([
        f"{row['rank']}. {row['player_name']} · {row['evidence_tier']}"
        for row in rows
    ], fontsize=8.4, color=T.INK)
    span_low = min(r['S_ci90_low'] for r in rows)
    span_high = max(r['S_ci90_high'] for r in rows)
    ax.set_xlim(span_low - 0.03, span_high + 0.10)
    ax.set_ylim(-0.7, n - 0.2)
    ax.set_xlabel('Performance Score S* with 90% interval', fontsize=8.4)
    _clean(ax, 'x')
    fig.text(0.0, 1.015, title, fontsize=12.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 0.972, subtitle, fontsize=8.2, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, filename)


def fig_bowler_ci(payload: dict[str, Any]) -> str:
    return _ci_figure(
        payload['rankings']['bowler_chase'],
        'Every published bowler interval contains zero',
        'Dot = point estimate. Bar = 90% interval. All ten intervals overlap their neighbours, so the order is not a ranking of superiority.',
        'bowler_ci.png', height=4.5,
    )


def fig_batter_ci(payload: dict[str, Any]) -> str:
    return _ci_figure(
        payload['rankings']['batter_chase'],
        'Eight batters clear the reliability gate — and no more',
        'The list stops at eight. Nobody was added to reach ten, and every interval still contains zero.',
        'batter_ci.png', height=3.9,
    )


def fig_pressure_vs_baseline(payload: dict[str, Any]) -> str:
    """Dumbbell: each published bowler under pressure vs in the same context."""
    rows = payload['rankings']['bowler_chase']
    ys = list(range(len(rows)))[::-1]
    values = ([r['pressure_runs_per_ball'] for r in rows]
              + [r['baseline_runs_per_ball'] for r in rows])
    low, high = min(values), max(values)
    pad = (high - low) * 0.30
    label_x = high + pad * 2.2

    fig, ax = plt.subplots(figsize=(7.3, 4.2))
    for y, row in zip(ys, rows):
        pressure = row['pressure_runs_per_ball']
        baseline = row['baseline_runs_per_ball']
        better = pressure < baseline
        ax.plot([baseline, pressure], [y, y], color=T.RULE, linewidth=2.6, zorder=1)
        ax.scatter([baseline], [y], s=46, color=T.BLUE, zorder=3,
                   edgecolor='white', linewidth=1.0)
        ax.scatter([pressure], [y], s=54, color=T.PINK if better else T.AMBER, zorder=4,
                   edgecolor='white', linewidth=1.0)
        delta = (pressure - baseline) / baseline * 100
        ax.text(label_x, y, f'{delta:+.0f}%', fontsize=8, ha='right', va='center',
                color=T.PINK if better else T.AMBER, fontweight='bold')
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{r['rank']}. {r['player_name']}" for r in rows], fontsize=8.6)
    ax.set_xlim(low - pad, label_x + pad * 0.4)
    ax.set_ylim(-0.7, len(rows) - 0.25)
    ax.set_xlabel('Runs conceded per ball (lower is better)', fontsize=8.4)
    ax.text(label_x, len(rows) - 0.55, 'change', fontsize=7.0,
            color=T.INK_FAINT, ha='right')
    _clean(ax, 'x')
    ax.scatter([], [], s=46, color=T.BLUE, label='Baseline (non-pressure, same context)')
    ax.scatter([], [], s=54, color=T.PINK, label='Pressure deliveries')
    ax.legend(loc='upper left', fontsize=7.6)
    fig.text(0.0, 1.015, 'The signal is the gap, not the average',
             fontsize=12.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 0.972, 'Raw runs per ball for the ten published bowlers. Negative change = better under pressure. The score adjusts for the situation, so this gap is context, not the score itself.',
             fontsize=7.6, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, 'pressure_vs_baseline.png')


def fig_bootstrap(payload: dict[str, Any]) -> str:
    rows = payload['rankings']['bowler_chase']
    names = [f"{r['rank']}. {r['player_name']}" for r in rows]
    share = [r['bootstrap_share_top10'] for r in rows]
    median = [r['bootstrap_rank_median'] for r in rows]
    p05 = [r['bootstrap_rank_p05'] for r in rows]
    p95 = [r['bootstrap_rank_p95'] for r in rows]
    ys = list(range(len(rows)))[::-1]

    fig, (left, right) = plt.subplots(1, 2, figsize=(7.6, 4.3), sharey=True,
                                      gridspec_kw={'width_ratios': [1.15, 1]})
    left.barh(ys, share, height=0.55, color=[T.PINK if s >= 0.9 else T.PINK_SOFT for s in share],
              edgecolor=T.PINK, linewidth=0.8)
    for y, value in zip(ys, share):
        left.text(min(value + 0.015, 1.0), y, f'{value * 100:.0f}%', fontsize=8,
                  va='center', color=T.INK, fontweight='bold')
    left.set_xlim(0, 1.13)
    left.set_yticks(ys)
    left.set_yticklabels(names, fontsize=8.4)
    left.set_xlabel('Share of 200 resamples kept in the top 10', fontsize=7.8)
    left.set_title('How often the place survives', fontsize=9, loc='left', color=T.INK)

    for y, low, high, mid in zip(ys, p05, p95, median):
        right.plot([low, high], [y, y], color=T.BLUE, linewidth=2.2, alpha=0.3,
                   solid_capstyle='round')
        for edge in (low, high):
            right.plot([edge, edge], [y - 0.15, y + 0.15], color=T.BLUE, linewidth=0.9, alpha=0.7)
        right.scatter([mid], [y], s=31, color=T.BLUE, edgecolor='white', linewidth=1.0, zorder=4)
    right.set_xlim(0, 36)
    right.set_xlabel('Resampled rank: median with 5–95% range', fontsize=7.8)
    right.set_title('Where the place actually sits', fontsize=9, loc='left', color=T.INK)
    for ax in (left, right):
        _clean(ax, 'x')
    fig.text(0.0, 1.02, 'The top three are stable; the rest of the list is not',
             fontsize=12.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 0.975, 'Match-block bootstrap, 200 resamples, fixed empirical-Bayes fit. Resampling is at match level, not ball level.',
             fontsize=8.0, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, 'bootstrap.png')


def fig_shrinkage(payload: dict[str, Any]) -> str:
    pool = [r for r in payload['pool']['bowler_chase'] if r['pool_order']]
    raw = [r['A_raw'] for r in pool]
    shrunk = [r['A_star'] for r in pool]
    vols = [r['pressure_balls'] or 0 for r in pool]
    tiers = [r['evidence_tier'] for r in pool]
    sizes = [18 + (v / max(vols)) * 170 for v in vols]

    fig, ax = plt.subplots(figsize=(6.9, 4.4))
    mean_shrunk = sum(shrunk) / len(shrunk)
    ax.axhspan(mean_shrunk - 0.03, mean_shrunk + 0.03, color=T.BLUE_SOFT, zorder=0)
    ax.text(-0.66, mean_shrunk + 0.045, 'league average, ±0.03', fontsize=7.2,
            color=T.BLUE, ha='left')
    for tier in ('Moderate', 'Limited'):
        xs = [x for x, t in zip(raw, tiers) if t == tier]
        ys2 = [y for y, t in zip(shrunk, tiers) if t == tier]
        ss = [s for s, t in zip(sizes, tiers) if t == tier]
        ax.scatter(xs, ys2, s=ss, color=T.TIER_COLOURS[tier], alpha=0.55,
                   edgecolor='white', linewidth=0.9, label=f'{tier} evidence', zorder=3)
    ax.plot([-0.7, 0.7], [-0.7, 0.7], color=T.INK_FAINT, linewidth=0.9,
            linestyle=(0, (4, 3)), label='no shrinkage (y = x)')
    ax.text(0.10, 0.215, 'no shrinkage', fontsize=7.0, color=T.INK_FAINT, rotation=33)
    ax.axhline(0, color=T.RULE, linewidth=0.8, zorder=1)
    ax.set_xlim(-0.70, 0.55)
    ax.set_ylim(-0.18, 0.27)
    ax.set_xlabel('Raw pressure average A (unshrunk, y units per delivery)', fontsize=8.2)
    ax.set_ylabel('Shrunk pressure score A*', fontsize=8.2)
    lead = payload['rankings']['bowler_chase'][0]
    ax.annotate('', xy=(lead['A_raw'], lead['A_star'] + 0.004),
                xytext=(lead['A_raw'], 0.245),
                arrowprops=dict(arrowstyle='-|>', color=T.PINK, lw=1.1, alpha=0.9))
    raw_span = max(raw) - min(raw)
    shrunk_span = max(shrunk) - min(shrunk)
    ax.text(-0.68, 0.245,
            f'Raw spread {raw_span:.2f}, shrunk spread {shrunk_span:.2f}\n'
            f'{100 * (1 - shrunk_span / raw_span):.0f}% of the raw spread is sampling noise',
            fontsize=8.2, color=T.INK, va='top', linespacing=1.8)
    ax.text(-0.68, 0.175,
            f"Arrow: {lead['player_name']}\nraw {lead['A_raw']:.2f}, shrunk to {lead['A_star']:.2f}",
            fontsize=7.6, color=T.PINK, va='top', linespacing=1.6, fontweight='bold')
    ax.legend(loc='lower right', fontsize=7.6)
    _clean(ax, 'y')
    fig.text(0.0, 1.015, 'Why raw pressure averages cannot be ranked directly',
             fontsize=12.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 0.972, 'Each dot is one of the 36 eligible bowlers; bubble size is pressure deliveries. Shrinkage pulls every record toward the league average.',
             fontsize=7.7, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, 'shrinkage.png')


def fig_eligibility_hist(payload: dict[str, Any]) -> str:
    panels = [
        ('Bowler · chase', payload['pool']['bowler_chase'], 36, 'a top 10 is published'),
        ('Batter · chase', payload['pool']['batter_chase'], 8, 'eight clear the gate'),
        ('Bowler · innings 1', payload['pool']['bowler_innings1'], 0, 'none clear the gate'),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(7.6, 3.1), sharey=True)
    for ax, (label, rows, eligible, note) in zip(axes, panels):
        values = [r['shrinkage_A'] for r in rows if r['shrinkage_A'] is not None]
        ax.hist(values, bins=[i / 40 for i in range(0, 25)], color=T.BLUE_SOFT,
                edgecolor=T.BLUE, linewidth=0.6)
        ax.set_yscale('log')
        ax.set_ylim(1, 900)
        ax.axvline(0.20, color=T.PINK, linewidth=1.4)
        ax.set_title(label, fontsize=9, loc='left')
        ax.text(0.26, 0.92, f'{eligible} eligible', fontsize=8.4,
                color=T.PINK, fontweight='bold', transform=ax.transAxes,
                bbox=dict(facecolor='white', edgecolor='none', pad=1.2))
        ax.text(0.26, 0.80, note, fontsize=7.0, color=T.INK_FAINT,
                transform=ax.transAxes,
                bbox=dict(facecolor='white', edgecolor='none', pad=1.0))
        ax.set_xlabel('Reliability B_A', fontsize=7.8)
        ax.set_xlim(0, 0.60)
        _clean(ax, 'y')
    axes[0].set_ylabel('Players (log scale)', fontsize=8.2)
    fig.text(0.0, 1.05, 'The reliability gate is what makes the lists short',
             fontsize=12.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 1.0, 'Pink line = approved 0.20 threshold. Innings-1 bowling stops at 0.150, so no ranking exists for it.',
             fontsize=8.0, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, 'eligibility_hist.png')


def fig_separation(payload: dict[str, Any]) -> str:
    rows = payload['rankings']['bowler_chase']
    pairs = []
    for upper, lower in zip(rows, rows[1:]):
        pairs.append((f"#{upper['rank']}–#{lower['rank']}", lower['gap_from_previous']))
    widths = [r['S_ci90_high'] - r['S_ci90_low'] for r in rows]
    mean_width = sum(widths) / len(widths)
    fig, ax = plt.subplots(figsize=(6.8, 3.5))
    xs = range(len(pairs))
    gaps = [max(g, 0) for _, g in pairs]
    ax.bar(xs, gaps, color=T.PINK, width=0.6)
    for x, (_, gap) in zip(xs, pairs):
        ax.text(x, max(gap, 0) + 0.0018, f'{gap:.4f}', fontsize=7.2, ha='center',
                color=T.INK_SOFT)
    ax.axhline(mean_width, color=T.BLUE, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.text(len(pairs) - 0.6, mean_width * 0.93,
            f'average interval width = {mean_width:.2f}', fontsize=7.6, color=T.BLUE, ha='right')
    ax.set_xticks(list(xs))
    ax.set_xticklabels([p[0] for p in pairs], fontsize=7.6)
    ax.set_ylim(0, mean_width * 1.05)
    ax.set_ylabel('Gap in S* between adjacent ranks', fontsize=8.2)
    _clean(ax, 'y')
    fig.text(0.0, 1.02, 'Adjacent ranks are separated by a hair, not by evidence',
             fontsize=12.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 0.975, 'Ranks 2 and 3 differ by 0.00008. The smallest gap the data could resolve is many times larger.',
             fontsize=8.0, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, 'separation.png')


def fig_sensitivity(payload: dict[str, Any]) -> str:
    rows = payload['sensitivity']
    scenarios = ['primary', 'w_0.30', 'w_0.50', 'tau2_REML',
                 'single_stage_combination', 'format_IPL', 'variance_E1']
    labels = {
        'primary': 'Approved', 'w_0.30': 'w = 0.30', 'w_0.50': 'w = 0.50',
        'tau2_REML': 'REML τ²', 'single_stage_combination': 'Single stage',
        'format_IPL': 'IPL only', 'variance_E1': 'E1 variance',
    }
    # One facet, drawn at the size it is displayed, so the labels stay readable.
    # The batter outcomes travel in the caption instead of a second cramped facet.
    batter = {r['scenario']: r for r in rows if r['role'] == 'batter'}
    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    selected = [r for s in scenarios for r in rows
                if r['role'] == 'bowler' and r['scenario'] == s]
    ys = list(range(len(selected)))[::-1]
    values = [r['overlap_with_primary'] / 10 for r in selected]
    colours = [T.RED if r['scenario'] == 'variance_E1' else T.PINK for r in selected]
    ax.barh(ys, values, height=0.6, color=colours, alpha=0.92)
    for y, r, value in zip(ys, selected, values):
        ax.text(value + 0.018, y,
                f"{r['overlap_with_primary']}/10 kept  ·  {r['eligible']} eligible",
                fontsize=8.6, va='center', color=T.INK_SOFT)
    ax.set_yticks(ys)
    ax.set_yticklabels([labels[r['scenario']] for r in selected], fontsize=9.4)
    ax.set_xlim(0, 1.45)
    ax.set_xlabel('Names kept from the published 10 bowlers', fontsize=8.8)
    _clean(ax, 'x')
    fig.text(0.0, 1.06, 'What survives a change of method — and what does not',
             fontsize=13.5, fontweight='bold', color=T.INK, ha='left')
    fig.text(0.0, 1.015,
             'Bowlers: 10 published. The score weight barely moves the list; the rejected E1 '
             'variance estimator replaces all of it.',
             fontsize=8.6, color=T.INK_FAINT, ha='left')
    fig.text(0.0, -0.10,
             'Batters: 8/8 kept under both score weights, 6/8 with IPL evidence only, 0/8 under '
             'E1; no batter is eligible under REML or the single-stage combination.',
             fontsize=8.6, color=T.INK_FAINT, ha='left')
    fig.tight_layout()
    return _save(fig, 'sensitivity.png')


def fig_headline(payload: dict[str, Any]) -> str:
    """Small three-card figure used on the deck's results opener."""
    head = payload['headline']
    cards = [
        ('Bowler chase', f"{head['bowler_published']}", f"published from {head['bowler_eligible']} eligible", T.PINK),
        ('Batter chase', f"{head['batter_published']}", f"eligible — the list stops here", T.BLUE),
        ('Innings-1 bowling', '0', f"{head['innings1_scored']} scored, none reliable enough", T.AMBER),
    ]
    fig, ax = plt.subplots(figsize=(7.6, 2.1))
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 1)
    ax.axis('off')
    for index, (label, value, note, colour) in enumerate(cards):
        ax.add_patch(Rectangle((index + 0.02, 0.05), 0.96, 0.9, facecolor=T.PAPER,
                               edgecolor=T.RULE, linewidth=1.0))
        ax.add_patch(Rectangle((index + 0.02, 0.05), 0.96, 0.055, facecolor=colour, edgecolor='none'))
        ax.text(index + 0.10, 0.78, label, fontsize=8.4, color=T.INK_SOFT, fontweight='bold')
        ax.text(index + 0.10, 0.44, value, fontsize=30, color=colour, fontweight='bold')
        ax.text(index + 0.10, 0.20, note, fontsize=7.2, color=T.INK_SOFT)
    fig.tight_layout()
    return _save(fig, 'headline_cards.png')


def build_all(payload: dict[str, Any]) -> dict[str, Any]:
    outputs: dict[str, Any] = {'font': FONT, 'dpi': DPI, 'files': {}}
    path, rates = fig_context_rates()
    outputs['files']['context_rates'] = path
    outputs['derived'] = {'league_runs_per_ball': rates}
    outputs['files']['funnel'] = fig_funnel(payload)
    outputs['files']['bowler_ci'] = fig_bowler_ci(payload)
    outputs['files']['batter_ci'] = fig_batter_ci(payload)
    outputs['files']['pressure_vs_baseline'] = fig_pressure_vs_baseline(payload)
    outputs['files']['bootstrap'] = fig_bootstrap(payload)
    outputs['files']['shrinkage'] = fig_shrinkage(payload)
    outputs['files']['eligibility_hist'] = fig_eligibility_hist(payload)
    outputs['files']['separation'] = fig_separation(payload)
    outputs['files']['sensitivity'] = fig_sensitivity(payload)
    outputs['files']['headline_cards'] = fig_headline(payload)
    return outputs


if __name__ == '__main__':
    from src.deliverables import data as D
    print(json.dumps(build_all(D.build_payload()), indent=2))
