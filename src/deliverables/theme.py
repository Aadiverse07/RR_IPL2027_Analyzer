"""Shared design tokens for the Phase 6 dashboard, deck and PDF report.

One palette and one type scale across all three deliverables. The deck uses the
dark variant for title and section slides; the report and dashboard stay on
paper so tables remain readable when printed.
"""
from __future__ import annotations

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / 'outputs/final/deliverables/assets'

PAPER = '#F8F7F4'
SURFACE = '#FFFFFF'
INK = '#10151F'
INK_SOFT = '#4A5464'
INK_FAINT = '#7B8494'
RULE = '#E2DFD8'

PINK = '#D6197F'
PINK_SOFT = '#FBE7F2'
BLUE = '#1B3A6B'
BLUE_SOFT = '#E7EEF8'
TEAL = '#0E7C86'
TEAL_SOFT = '#E2F1F2'
AMBER = '#A9680B'
AMBER_SOFT = '#FBF0DC'
RED = '#B3261E'
RED_SOFT = '#FAE7E5'
GREEN = '#1F7A4D'
GREEN_SOFT = '#E4F1E9'

NIGHT = '#0B1220'
NIGHT_SURFACE = '#141D2C'
NIGHT_RULE = '#2A3648'
ON_NIGHT = '#F5F2EB'
ON_NIGHT_SOFT = '#A9B4C4'

TIER_COLOURS = {
    'High': GREEN,
    'Moderate': BLUE,
    'Limited': PINK,
    'Insufficient': INK_FAINT,
}

ROLE_COLOURS = {'bowler': PINK, 'batter': BLUE}

FONT_STACK_HTML = (
    '-apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif'
)
FONT_MONO = '"SF Mono", ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace'

PDF_NAME = 'SupeRR_Selector_Phase6_Report.pdf'
DECK_NAME = 'SupeRR_Selector_Phase6_Deck.pptx'

DELIVERABLES = Path(__file__).resolve().parents[2] / 'outputs/final/deliverables'
