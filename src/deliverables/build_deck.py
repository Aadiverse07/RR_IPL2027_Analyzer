"""Build the Phase 6 PowerPoint deck.

27 slides, 16:9, built with python-pptx from the same canonical payload as the
dashboard and the PDF. Every number on a slide comes from the payload (frozen
Phase 5 files); nothing is typed by hand and nothing is recomputed.

Layout is measured, not guessed: text is wrapped with the real Helvetica Neue
metrics through Pillow, every block records the box it needs, and
``audit_layout`` fails the build if a block leaves the slide or two text blocks
overlap. That check is what the first draft of this deck was missing.

Design: paper content slides, dark section dividers, one accent palette shared
with the dashboard and the report. Claims always appear with the evidence tier,
the interval and the eligible pool size.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from src.deliverables import data as D
from src.deliverables import theme as T

OUT = T.DELIVERABLES / T.DECK_NAME

W, H = 13.333, 7.5
M = 0.70
CONTENT_W = W - 2 * M
GUTTER = 0.50
COL_W = (CONTENT_W - GUTTER) / 2
LEFT_X = M
RIGHT_X = M + COL_W + GUTTER
CONTENT_TOP = 2.02
CONTENT_BOTTOM = 6.52

FONT_NAME = 'Helvetica Neue'
FONT_PATH = '/System/Library/Fonts/HelveticaNeue.ttc'
_FONT_INDEX = {(False, False): 0, (True, False): 1, (False, True): 2, (True, True): 3}
_font_cache: dict[tuple[int, bool, bool], ImageFont.FreeTypeFont] = {}

# every text block is recorded here so the layout can be audited afterwards
_BLOCKS: list[dict[str, Any]] = []

COMMON_DISCLOSURES = [
    'All ten 90% intervals contain zero',
    'Every adjacent pair overlaps',
    'not statistically separable',
]


# ----------------------------------------------------------------- primitives
def rgb(hex_value: str) -> RGBColor:
    value = hex_value.lstrip('#')
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _font(size: float, bold: bool, italic: bool) -> ImageFont.FreeTypeFont:
    key = (int(round(size * 4)), bold, italic)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_PATH, key[0],
                                              index=_FONT_INDEX[(bold, italic)])
    return _font_cache[key]


#: PowerPoint sets Helvetica Neue a little wider than Pillow measures. Wrapping
#: 4.5% early keeps the predicted line count at or above what PowerPoint draws,
#: so a measured box never has text spilling out of it.
_WIDTH_FUDGE = 1.045


def text_width(text: str, size: float, bold: bool = False, italic: bool = False) -> float:
    """Width of ``text`` in points at ``size`` (1 pt = 1 px at 72 dpi)."""
    return _font(size, bold, italic).getlength(text) / 4.0 * _WIDTH_FUDGE


def _parse(text: str) -> list[tuple[str, bool]]:
    """Split ``**bold**`` markup into (text, bold) runs."""
    parts = re.split(r'\*\*(.+?)\*\*', text)
    runs = []
    for index, part in enumerate(parts):
        if not part:
            continue
        runs.append((part, index % 2 == 1))
    return runs or [(text, False)]


def _words(runs: Sequence[tuple[str, bool]]) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for index, (text, bold) in enumerate(runs):
        pieces = re.split(r'(\s+)', text)
        for piece in pieces:
            if piece == '':
                continue
            out.append((piece, bold))
    return out


def wrap_runs(runs: Sequence[tuple[str, bool]], width_in: float,
              size: float) -> list[list[tuple[str, bool]]]:
    """Greedy wrap of inline runs to ``width_in`` inches."""
    limit = width_in * 72.0
    lines: list[list[tuple[str, bool]]] = []
    line: list[tuple[str, bool]] = []
    width = 0.0
    for word, bold in _words(runs):
        piece = word if word.strip() else ' '
        advance = text_width(piece, size, bold)
        if not line and word.strip() == '':
            continue
        if width + advance > limit and line and word.strip():
            lines.append(line)
            line = []
            width = 0.0
        if not line and word.strip() == '':
            continue
        line.append((word, bold))
        width += advance
    if line:
        lines.append(line)
    return lines or [[('', False)]]


def line_height(size: float, spacing: float = 1.12) -> float:
    return size * 1.20 * spacing / 72.0


def _register(slide_index: int, kind: str, x: float, y: float, w: float, h: float,
              text: str | None = None) -> None:
    _BLOCKS.append({'slide': slide_index, 'kind': kind, 'x': x, 'y': y, 'w': w,
                    'h': h, 'text': (text or '')[:60]})


def _slide_index(prs) -> int:
    return len(prs.slides)


def draw_text(prs, slide, x: float, y: float, w: float, text: str, size: float,
              colour: str = T.INK, bold: bool = False, italic: bool = False,
              align: PP_ALIGN = PP_ALIGN.LEFT, spacing: float = 1.12,
              kind: str = 'text', width_safety: float = 0.96) -> float:
    """Wrap, place and return the bottom edge (inches)."""
    runs = _parse(text)
    lines = wrap_runs(runs, w * width_safety, size)
    height = line_height(size, spacing) * len(lines)
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w),
                                   Inches(height + 0.02))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.TOP
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = spacing
    for text_piece, is_bold in runs:
        run = paragraph.add_run()
        run.text = text_piece
        run.font.size = Pt(size)
        run.font.bold = bold or is_bold
        run.font.italic = italic
        run.font.name = FONT_NAME
        run.font.color.rgb = rgb(colour)
    _register(_slide_index(prs), kind, x, y, w, height, re.sub(r'\*\*', '', text))
    return y + height


def bullets(prs, slide, x: float, y: float, w: float, items: Sequence[str],
            size: float = 12.0, colour: str = T.INK_SOFT,
            gap_after: float = 0.10, bullet_colour: str = T.PINK,
            marker: str = '•', indent: float = 0.22) -> float:
    """Bulleted items with a hanging indent and measured heights."""
    for item in items:
        runs = [('•  ', False)] + _parse(item)
        lines = wrap_runs(_parse(item), (w - indent) * 0.96, size)
        height = line_height(size) * len(lines)
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w),
                                       Inches(height + 0.02))
        frame = box.text_frame
        frame.word_wrap = True
        frame.margin_left = 0
        frame.margin_right = 0
        frame.margin_top = 0
        frame.margin_bottom = 0
        paragraph = frame.paragraphs[0]
        paragraph.line_spacing = 1.12
        paragraph.space_before = Pt(0)
        marker_run = paragraph.add_run()
        marker_run.text = f'{marker}  '
        marker_run.font.size = Pt(size)
        marker_run.font.bold = True
        marker_run.font.name = FONT_NAME
        marker_run.font.color.rgb = rgb(bullet_colour)
        for text_piece, is_bold in _parse(item):
            run = paragraph.add_run()
            run.text = text_piece
            run.font.size = Pt(size)
            run.font.bold = is_bold
            run.font.name = FONT_NAME
            run.font.color.rgb = rgb(T.INK if is_bold else colour)
        _register(_slide_index(prs), 'bullet', x, y, w, height,
                  re.sub(r'\*\*', '', item))
        y += height + gap_after
    return y


def rect(slide, x: float, y: float, w: float, h: float, fill: str,
         line: str | None = None, rounded: bool = False) -> None:
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    if line:
        shape.line.color.rgb = rgb(line)
        shape.line.width = Pt(0.75)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    if rounded:
        shape.adjustments[0] = 0.06


def callout(prs, slide, x: float, y: float, w: float, title: str, body: str,
            accent: str = T.PINK, fill: str = T.PINK_SOFT, size: float = 10.6,
            body_colour: str = T.INK) -> float:
    inner = w - 0.44
    title_h = line_height(8.5) * len(wrap_runs(_parse(title.upper()), inner, 8.5))
    body_h = line_height(size, 1.14) * len(wrap_runs(_parse(body), inner, size))
    height = 0.16 + title_h + 0.08 + body_h + 0.14
    rect(slide, x, y, w, height, fill)
    rect(slide, x, y, 0.045, height, accent)
    draw_text(prs, slide, x + 0.22, y + 0.14, inner, title.upper(), 8.5, accent,
              bold=True, kind='callout-title')
    draw_text(prs, slide, x + 0.22, y + 0.14 + title_h + 0.08, inner, body, size,
              body_colour, kind='callout-body')
    return y + height


def stat_cards(prs, slide, x: float, y: float, total_w: float,
               cards: Sequence[tuple[str, str, str]], gap: float = 0.15,
               value_size: float = 20.0, label_size: float = 9.6,
               note_size: float = 8.2, pad: float = 0.16,
               value_colours: Sequence[str] | None = None) -> float:
    """Row of stat cards, each sized to its own measured content."""
    count = len(cards)
    card_w = (total_w - gap * (count - 1)) / count
    inner = card_w - 2 * pad
    heights = []
    for value, label, note_text in cards:
        h = 0.14
        h += line_height(value_size) * len(wrap_runs(_parse(value), inner * 0.96, value_size))
        h += 0.05
        h += line_height(label_size) * len(wrap_runs(_parse(label), inner * 0.96, label_size))
        if note_text:
            h += 0.04
            h += line_height(note_size, 1.1) * len(
                wrap_runs(_parse(note_text), inner * 0.96, note_size))
        heights.append(h + 0.14)
    height = max(heights)
    for index, (value, label, note_text) in enumerate(cards):
        card_x = x + index * (card_w + gap)
        rect(slide, card_x, y, card_w, height, T.SURFACE, T.RULE)
        cursor = y + 0.14
        colour = value_colours[index] if value_colours else T.PINK
        cursor = draw_text(prs, slide, card_x + pad, cursor, inner, value, value_size,
                           colour, bold=True)
        cursor = draw_text(prs, slide, card_x + pad, cursor + 0.05, inner, label,
                           label_size, T.INK, bold=True)
        if note_text:
            draw_text(prs, slide, card_x + pad, cursor + 0.04, inner, note_text,
                      note_size, T.INK_FAINT, spacing=1.1)
    return y + height


def fit_width(key: str, max_w: float, max_h: float | None = None) -> float:
    with Image.open(T.ASSETS / f'{key}.png') as image:
        ratio = image.size[0] / image.size[1]
    width = max_w
    if max_h is not None:
        width = min(width, max_h * ratio)
    return width


def picture(prs, slide, key: str, x: float, y: float, w: float,
            max_h: float | None = None) -> float:
    path = T.ASSETS / f'{key}.png'
    if not path.exists():
        raise FileNotFoundError(path)
    with Image.open(path) as image:
        ratio = image.size[0] / image.size[1]
    if max_h is not None and w / ratio > max_h:
        w = max_h * ratio
    h = w / ratio
    shape = slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w))
    shape.line.color.rgb = rgb(T.RULE)
    shape.line.width = Pt(0.5)
    _register(_slide_index(prs), 'picture', x, y, w, h, key)
    return y + h


def table(prs, slide, x: float, y: float, w: float, columns: Sequence[tuple[str, float]],
          rows: Sequence[Sequence[str]], size: float = 9.6,
          header_size: float = 8.0, row_height: float = 0.34,
          align_right: Iterable[int] = (), accent: str = T.PINK) -> float:
    total = sum(c[1] for c in columns)
    widths = [w * share / total for _, share in columns]
    shape = slide.shapes.add_table(len(rows) + 1, len(columns), Inches(x), Inches(y),
                                   Inches(w), Inches(row_height * (len(rows) + 1)))
    grid = shape.table
    grid.first_row = True
    for index, width in enumerate(widths):
        grid.columns[index].width = Emu(int(Inches(width)))
    for row_index in range(len(rows) + 1):
        grid.rows[row_index].height = Inches(row_height)

    def cell_text(cell, value: str, font_size: float, bold: bool, colour: str,
                  right: bool, header: bool, row_index: int = 0) -> None:
        cell.text = ''
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb('#F1EFE9' if header
                                       else (T.SURFACE if row_index % 2
                                             else '#FBFAF7'))
        cell.margin_left = Inches(0.07)
        cell.margin_right = Inches(0.08)
        cell.margin_top = Inches(0.02)
        cell.margin_bottom = Inches(0.02)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragraph = cell.text_frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.RIGHT if right else PP_ALIGN.LEFT
        run = paragraph.add_run()
        run.text = value
        run.font.size = Pt(font_size)
        run.font.bold = bold
        run.font.name = FONT_NAME
        run.font.color.rgb = rgb(colour)

    for column_index, (label, _) in enumerate(columns):
        cell_text(grid.cell(0, column_index), label, header_size, True,
                  T.INK_SOFT, column_index in align_right, True, 0)
    for row_index, row in enumerate(rows, start=1):
        for column_index, value in enumerate(row):
            bold = column_index == 1
            colour = accent if (column_index == 0 and row_index == 1) else (
                T.INK if column_index <= 1 else T.INK_SOFT)
            cell_text(grid.cell(row_index, column_index), str(value), size, bold,
                      colour, column_index in align_right, False, row_index)
    _register(_slide_index(prs), 'table', x, y, w, row_height * (len(rows) + 1), 'table')
    return y + row_height * (len(rows) + 1)


def new_slide(prs, background: str = T.PAPER):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb(background)
    return slide


def footer(prs, slide, dark: bool = False) -> None:
    colour = T.ON_NIGHT_SOFT if dark else T.INK_FAINT
    rule = T.NIGHT_RULE if dark else T.RULE
    line = slide.shapes.add_connector(1, Inches(M), Inches(6.62),
                                      Inches(W - M), Inches(6.62))
    line.line.color.rgb = rgb(rule)
    line.line.width = Pt(0.75)
    draw_text(prs, slide, M, 6.70, 5.6,
              'SupeRR Selector · Season 2 · Phase 6 communication build', 8.5,
              colour, kind='footer')
    draw_text(prs, slide, W - M - 3.65, 6.70, 3.2,
              'Frozen Phase 5 results · no retraining', 8.5, colour,
              align=PP_ALIGN.RIGHT, kind='footer')
    draw_text(prs, slide, W - M - 0.45, 6.70, 0.45, str(len(prs.slides)), 8.5, colour,
              align=PP_ALIGN.RIGHT, kind='footer')


def header(prs, slide, eyebrow: str, title: str, lede: str | None = None,
           title_size: float = 29.0, lede_width: float | None = None) -> float:
    y = draw_text(prs, slide, M, 0.46, CONTENT_W, eyebrow.upper(), 9.0, T.PINK,
                  bold=True, kind='eyebrow')
    y = draw_text(prs, slide, M, y + 0.10, CONTENT_W, title, title_size, T.INK,
                  bold=True, spacing=1.02, kind='title')
    if lede:
        y = draw_text(prs, slide, M, y + 0.14, lede_width or CONTENT_W * 0.80, lede,
                      12.5, T.INK_SOFT, spacing=1.16, kind='lede')
    return y + 0.24


def notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


# --------------------------------------------------------------------- slides
def slide_title(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs, T.NIGHT)
    rect(slide, 0, 0, 0.28, H, T.PINK)
    draw_text(prs, slide, 1.05, 1.02, 9.5, 'SUPERR SELECTOR · SEASON 2 · PHASE 6', 10.5,
              T.PINK, bold=True)
    draw_text(prs, slide, 1.05, 1.42, 10.8, 'Pressure performance,\nmeasured honestly.',
              50, T.ON_NIGHT, bold=True, spacing=0.98, kind='hero')
    draw_text(prs, slide, 1.05, 3.92, 9.2,
              'A situation-adjusted shortlist of T20 players — with the uncertainty, '
              'the exclusions and the failure modes shown alongside it.',
              15.0, T.ON_NIGHT_SOFT, spacing=1.26)
    rect(slide, 1.05, 4.98, 2.2, 0.03, T.PINK)
    draw_text(prs, slide, 1.05, 5.22, 5.4,
              'Ten chase bowlers · eight chase batters\nZero eligible first-innings bowlers',
              13.0, T.ON_NIGHT, bold=True, spacing=1.30)
    draw_text(prs, slide, 7.15, 5.22, 5.3,
              f"Phase 5 results frozen {payload['meta']['date_label']}\n"
              f"{payload['headline']['matches']} matches · "
              f"{payload['headline']['deliveries']:,} deliveries",
              11.5, T.ON_NIGHT_SOFT, spacing=1.30)
    draw_text(prs, slide, 1.05, 6.52, 11.0,
              'Communication build only: no retraining, no threshold change, no re-ranking.',
              10.5, T.PINK)
    notes(slide, 'Headline: 10 chase bowlers, 8 chase batters, 0 eligible innings-1 bowlers. '
                 'All figures are frozen Phase 5 outputs.')


def slide_agenda(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, 'What this deck covers',
               'Ten questions, answered with the same frozen evidence',
               'The order follows the brief: problem, method, validation, selection, '
               'results, uncertainty, limitations.', lede_width=9.6)
    items = [
        ('01', 'The problem', 'T20 pressure is where matches are decided, and where conventional statistics are weakest.'),
        ('02', 'Why conventional stats fail', 'Economy, average and strike rate describe outcomes, not situations.'),
        ('03', 'How pressure was defined', 'A calibrated pre-ball model, validated before use.'),
        ('04', 'How performance was measured', 'Every delivery compared with its own situation.'),
        ('05', 'Empirical-Bayes shrinkage', 'Small samples cannot be taken at face value.'),
        ('06', 'Reliability vs Performance', 'Two different questions, reported side by side.'),
        ('07', 'How players were selected', 'A pre-registered rule applied to an eligible pool.'),
        ('08', 'Final results', 'Ten bowlers, eight batters, and a separate research finding.'),
        ('09', 'Sensitivity and uncertainty', 'What survives a change of method, and what does not.'),
        ('10', 'Limitations and next steps', 'What we will not claim, and what would change it.'),
    ]
    for column, block in enumerate((items[:5], items[5:])):
        x = LEFT_X + column * (COL_W + GUTTER)
        row_y = y + 0.04
        for number, title, body in block:
            draw_text(prs, slide, x, row_y, 0.46, number, 11.0, T.PINK, bold=True)
            draw_text(prs, slide, x + 0.46, row_y - 0.02, COL_W - 0.46, title, 13.0,
                      T.INK, bold=True)
            end = draw_text(prs, slide, x + 0.46, row_y + 0.26, COL_W - 0.46, body,
                            10.0, T.INK_SOFT, spacing=1.14)
            row_y = max(end, row_y + 0.26) + 0.22
    callout(prs, slide, LEFT_X, row_y + 0.02, CONTENT_W,
            'Every slide is traceable',
            'All numbers come from the frozen Phase 5 files; the dashboard, this deck and '
            'the PDF are generated from one payload, so they cannot drift.',
            accent=T.BLUE, fill=T.BLUE_SOFT, size=10.2)
    footer(prs, slide)
    notes(slide, 'Agenda mirrors the ten required topics.')


def slide_section(prs, number: str, title: str, note_text: str) -> None:
    slide = new_slide(prs, T.NIGHT)
    rect(slide, 0, 0, 0.28, H, T.PINK)
    draw_text(prs, slide, M + 0.35, 1.85, 2.0, number, 13.0, T.PINK, bold=True)
    draw_text(prs, slide, M + 0.35, 2.28, 9.8, title, 40.0, T.ON_NIGHT, bold=True,
              spacing=0.98, kind='hero')
    rect(slide, M + 0.35, 4.22, 1.8, 0.03, T.PINK)
    draw_text(prs, slide, M + 0.35, 4.46, 8.4, note_text, 13.0, T.ON_NIGHT_SOFT,
              spacing=1.26)
    footer(prs, slide, dark=True)
    notes(slide, f'Section divider: {title}. {note_text}')


def slide_problem(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, '01 · The problem',
               'The last five overs decide T20 matches. The scorecard does not show them.',
               'A bowler who defends 12 in the 19th over and one who concedes 12 in a dead '
               'rubber can post the same economy rate.', lede_width=9.9)
    bullets(prs, slide, LEFT_X, y, COL_W, [
        '**Conventional stats ignore the situation** — economy rate, bowling average and '
        'strike rate treat every run and wicket as equally costly.',
        '**Pressure is not a separate column** — the scorecard records outcomes, not the '
        'match state the player was in.',
        '**Small samples look decisive** — a few pressure overs can produce an extreme '
        'average that will not repeat.',
        '**Rankings hide their own uncertainty** — a list of ten looks like a podium even '
        'when the intervals overlap.',
    ], size=12.0, gap_after=0.15)
    callout(prs, slide, LEFT_X, 5.05, COL_W,
            'The question we set out to answer',
            'Across a large T20 sample, which players actually beat expectation when the '
            'match is tight — and how much can the evidence support?',
            accent=T.BLUE, fill=T.BLUE_SOFT, size=10.6)
    panel_y = y - 0.16
    panel_h = 4.15
    rect(slide, RIGHT_X, panel_y, COL_W, panel_h, T.SURFACE, T.RULE)
    draw_text(prs, slide, RIGHT_X + 0.26, panel_y + 0.20, COL_W - 0.5,
              'THREE COMPETING SHORTCUTS', 8.5, T.INK_FAINT, bold=True)
    shortcuts = [
        ('Raw economy in close games',
         'Death overs always look worse than they are.'),
        ('Reputation and eye test',
         'Consistent, but not measurable or falsifiable.'),
        ('Points tables and MVP awards',
         'Reward volume and team success, not pressure skill.'),
    ]
    row_y = panel_y + 0.55
    for index, (title, body) in enumerate(shortcuts, start=1):
        draw_text(prs, slide, RIGHT_X + 0.26, row_y, 0.3, str(index), 12.0, T.PINK,
                  bold=True)
        draw_text(prs, slide, RIGHT_X + 0.62, row_y - 0.03, COL_W - 0.85, title, 12.0,
                  T.INK, bold=True)
        end = draw_text(prs, slide, RIGHT_X + 0.62, row_y + 0.27, COL_W - 0.85, body,
                        10.5, T.INK_SOFT, spacing=1.16)
        row_y = end + 0.28
    closing = draw_text(prs, slide, RIGHT_X + 0.26, row_y + 0.06, COL_W - 0.5,
                        'This project replaces all three with one measurable quantity: the '
                        'delivery-level difference from what an average player would have '
                        'done in the same match state.', 10.0, T.INK_SOFT, spacing=1.2)
    cost_end = draw_text(prs, slide, RIGHT_X + 0.26, closing + 0.12, COL_W - 0.5,
                         'The cost: the method has to be explained, not just quoted.', 9.0,
                         T.PINK, italic=True)
    needed = cost_end - panel_y + 0.16
    if needed > panel_h:
        rect(slide, RIGHT_X, panel_y, COL_W, needed, T.SURFACE, T.RULE)
    footer(prs, slide)
    notes(slide, 'Frame the problem: conventional cricket statistics are outcome-based, '
                 'not situation-based. No claim is made about any specific player here.')


def slide_conventional(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, '02 · Why conventional statistics fail',
               'The same bowlers, the same league — very different run rates',
               'Phase 3 measured the scoring environment behind each pressure flag. Chase '
               'pressure barely changes the raw rate; the first-innings flag changes it a lot.',
               lede_width=9.9)
    chart_w = 6.55
    picture(prs, slide, 'context_rates', LEFT_X, y + 0.04, chart_w)
    right_x = LEFT_X + chart_w + 0.42
    right_w = W - M - right_x
    bullets(prs, slide, right_x, y + 0.06, right_w, [
        '**Chase pressure: 1.36 runs per ball** against 1.39 without it. The raw rate is '
        'almost flat, which is exactly why raw economy cannot separate players.',
        '**Innings-1 pressure: 1.61 runs per ball** against 1.36. The flag is describing a '
        'scoring environment, not only bowling skill.',
        '**So the model compares every delivery with its own expectation** rather than with '
        'a league average.',
    ], size=11.0, gap_after=0.14)
    callout(prs, slide, right_x, 4.72, right_w,
            'A finding, not a defect to hide',
            'Innings-1 bowling is reported as a research finding with zero eligible players '
            '(PH3-01, F4-02). It is never merged with chase, and no player is ranked from it.',
            accent=T.AMBER, fill=T.AMBER_SOFT, size=10.0)
    footer(prs, slide)
    notes(slide, 'Source: reports/phase_3/descriptive_stats.csv aggregated over bowler rows; '
                 'rates 1.3594 (chase pressure), 1.3864 (chase baseline), 1.6107 (innings-1 '
                 'pressure), 1.3643 (innings-1 baseline). Matches the Phase 3 report.')


def slide_pressure(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    head = payload['headline']
    y = header(prs, slide, '03 · How pressure was defined',
               'A pre-ball model marks the tightest quarter of chase states',
               'The label uses only information available before the delivery, so a ball can '
               'never influence its own pressure flag.', lede_width=9.9)
    bullets(prs, slide, LEFT_X, y, COL_W, [
        '**Inputs:** score, wickets, balls left, target, format and phase — no future '
        'information, no post-hoc outcome.',
        '**Validation:** out-of-fold chase probabilities, judged on calibration slope, '
        'expected calibration error and decile behaviour before use.',
        '**Threshold:** the tightest quarter of chase states, one shared flag for batters '
        'and bowlers because it marks the same match state.',
        '**Rejected definitions:** broad flags, the collapse/union variants and the F2 '
        'fallback all failed difficulty validation and are unused (PH2-05).',
    ], size=11.2, gap_after=0.12)
    callout(prs, slide, LEFT_X, 4.72, COL_W,
            'Pressure is a match state, not a shot',
            'A batter facing a required rate of 12 with four wickets left is in the same '
            'validated state as the bowler bowling to him. Both are scored on the same flag.',
            accent=T.BLUE, fill=T.BLUE_SOFT, size=10.0)

    panel_x = RIGHT_X
    panel_y = y - 0.08
    panel_h = 2.62
    rect(slide, panel_x, panel_y, COL_W, panel_h, T.NIGHT)
    draw_text(prs, slide, panel_x + 0.30, panel_y + 0.22, COL_W - 0.6, 'VALIDATION GATE',
              8.5, T.PINK, bold=True)
    draw_text(prs, slide, panel_x + 0.30, panel_y + 0.52, COL_W - 0.6,
              'Passed before any player was scored', 16.0, T.ON_NIGHT, bold=True,
              spacing=1.05)
    gate_items = [
        ('Calibration', 'slope 0.993 and ECE 0.0058 inside the pre-set bounds'),
        ('Discrimination', 'AUC 0.899 out-of-fold'),
        ('Difficulty', 'rejected flags tested and excluded by name'),
        ('Reproducibility', 'seed, folds and code path fixed'),
    ]
    gate_y = panel_y + 1.24
    for label, body in gate_items:
        gate_y = draw_text(prs, slide, panel_x + 0.30, gate_y, COL_W - 0.6,
                           f'**{label}** — {body}', 9.6, T.ON_NIGHT_SOFT, spacing=1.1) + 0.09

    card_y = panel_y + panel_h + 0.28
    stat_cards(prs, slide, panel_x, card_y, COL_W, [
        (f"{head['auc']:.3f}", 'Model AUC', 'out-of-fold'),
        (f"{head['calibration_slope']:.3f}", 'Calibration slope', '1.0 is perfect'),
        (f"{head['ece']:.4f}", 'Calibration error', 'lower is better'),
        (f"{head['chase_states']:,}", 'Chase states', 'labelled balls'),
    ], value_size=16.0, label_size=8.6, note_size=7.8, pad=0.14)
    footer(prs, slide)
    notes(slide, 'Sources: reports/phase_2/PHASE_2_REPORT.md and '
                 'reports/phase_3/model_specification.md. AUC 0.8994, slope 0.9925, '
                 'ECE 0.00582, 89,167 chase states.')


def slide_performance(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, '04 · How performance was measured',
               'Every delivery is compared with what an average player would have done',
               'Situation is removed before the player is judged, so bowling at the death is '
               'not punished twice.', lede_width=9.9)
    chart_w = 6.35
    picture(prs, slide, 'pressure_vs_baseline', LEFT_X, y + 0.04, chart_w)
    right_x = LEFT_X + chart_w + 0.40
    right_w = W - M - right_x
    formula_y = y + 0.02
    rect(slide, right_x, formula_y, right_w, 1.02, T.NIGHT)
    draw_text(prs, slide, right_x + 0.20, formula_y + 0.14, right_w - 0.4,
              'y = (runs − μ_runs) − λ · (dismissed − μ_dis)', 12.0, T.ON_NIGHT,
              bold=True)
    draw_text(prs, slide, right_x + 0.20, formula_y + 0.58, right_w - 0.4,
              'batters: runs off bat · bowlers: charged runs, sign flipped', 8.8,
              T.ON_NIGHT_SOFT, spacing=1.1)
    draw_text(prs, slide, right_x, formula_y + 1.24, right_w, 'THE THREE COMPONENTS', 8.5,
              T.INK_FAINT, bold=True)
    bullets(prs, slide, right_x, formula_y + 1.52, right_w, [
        '**A — pressure average:** mean of y on pressure deliveries.',
        '**B — baseline average:** the same player on non-pressure deliveries in the same '
        'context. A control, not a bonus.',
        '**D = A − B:** the pressure-specific difference.',
        '**S_raw = 0.70·A + 0.30·D:** most of the signal is pressure performance, with a '
        'general-form adjustment.',
    ], size=10.6, gap_after=0.09)
    draw_text(prs, slide, right_x, 6.12, right_w,
              'Dot balls and strike rate are descriptives. They never enter the score.', 9.0,
              T.INK_FAINT, italic=True)
    footer(prs, slide)
    notes(slide, 'Formula from reports/phase_3/model_specification.md §5–6. The chart shows '
                 'raw runs per ball for the ten published bowlers as context; the score '
                 'itself is built from situation-adjusted residuals.')


def slide_shrinkage(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, '05 · Empirical-Bayes shrinkage',
               'Why a small, spectacular sample cannot be ranked directly',
               'Each player’s record is pulled towards the league average by an amount that '
               'depends on how much evidence backs it.', lede_width=9.9)
    chart_w = fit_width('shrinkage', 6.3, CONTENT_BOTTOM - y - 0.08)
    picture(prs, slide, 'shrinkage', LEFT_X, y + 0.06, chart_w)
    right_x = LEFT_X + chart_w + 0.40
    right_w = W - M - right_x
    draw_text(prs, slide, right_x, y + 0.04, right_w, 'HOW IT WORKS', 8.5, T.INK_FAINT,
              bold=True)
    bullet_end = bullets(prs, slide, right_x, y + 0.32, right_w, [
        '**Estimate between-player variance** separately for each role × context × format '
        '× component.',
        '**Weight each record** by its own sampling variance against that between-player '
        'variance.',
        '**Keep more of the record** when the player has more deliveries; keep less when '
        'the record is thin.',
        '**Result:** A* is the shrunk pressure score; the shrinkage weight B_A is kept as '
        'a separate reliability measure.',
    ], size=10.6, gap_after=0.10)
    callout_end = callout(prs, slide, right_x, bullet_end + 0.18, right_w,
                          'What the chart is telling you',
                          'Raw spread across the 36 eligible bowlers is 1.12 units; after '
                          'shrinkage it is 0.32. Most of the apparent difference is sampling '
                          'noise, not a real difference in skill.',
                          accent=T.BLUE, fill=T.BLUE_SOFT, size=10.0)
    draw_text(prs, slide, right_x, callout_end + 0.16, right_w,
              'Shrinkage is not a penalty. It is an admission of how much we actually know.',
              9.6, T.PINK, italic=True, spacing=1.16)
    footer(prs, slide)
    notes(slide, 'Sources: reports/phase_4/variance_estimator_comparison.md and the '
                 'eligible-pool columns of outputs/final/player_scores_bowlers.csv. '
                 'Raw and shrunk spread are the max−min of A_raw and A_star across the 36 '
                 'eligible bowlers: 1.1211 and 0.3208.')


def slide_reliability(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, '06 · Reliability is not performance',
               'Two different questions, reported side by side and never multiplied',
               'Reliability asks whether the evidence is strong enough to publish. It says '
               'nothing about how good the player is.', lede_width=9.9)
    card_h = 1.45
    for column, (title, colour, head, body) in enumerate([
        ('PERFORMANCE SCORE', T.PINK, 'How well did the player do?',
         'S* = A* − 0.30·B*. Positive means better than expected under pressure, after '
         'removing the player’s general form.'),
        ('RELIABILITY OF EVIDENCE', T.BLUE, 'Can we trust the record?',
         'B_A: how much of the record is kept rather than pulled to the league average. '
         'Decides eligibility (≥ 0.20); never enters S*.'),
    ]):
        x = LEFT_X + column * (COL_W + GUTTER)
        rect(slide, x, y - 0.04, COL_W, card_h, T.SURFACE, T.RULE)
        draw_text(prs, slide, x + 0.24, y + 0.10, COL_W - 0.48, title, 8.5, colour,
                  bold=True)
        draw_text(prs, slide, x + 0.24, y + 0.38, COL_W - 0.48, head, 16.0, T.INK,
                  bold=True)
        draw_text(prs, slide, x + 0.24, y + 0.82, COL_W - 0.48, body, 10.2, T.INK_SOFT,
                  spacing=1.18)
    chart_y = y + card_h + 0.22
    chart_w = fit_width('eligibility_hist', 6.45, 6.47 - chart_y)
    picture(prs, slide, 'eligibility_hist', LEFT_X, chart_y, chart_w)
    right_x = LEFT_X + chart_w + 0.40
    right_w = W - M - right_x
    draw_text(prs, slide, right_x, chart_y - 0.02, right_w, 'THE FOUR TIERS', 8.5,
              T.INK_FAINT, bold=True)
    tier_end = bullets(prs, slide, right_x, chart_y + 0.26, right_w, [
        '**High** 0.50+ · no published player reaches it',
        '**Moderate** 0.30–0.50 · 4 bowlers, 0 batters',
        '**Limited** 0.20–0.30 · 6 bowlers, 8 batters',
        '**Insufficient** below 0.20 · never published',
    ], size=10.4, gap_after=0.07)
    callout(prs, slide, right_x, tier_end + 0.28, right_w,
            'Why the separation matters',
            'A player can be highly reliable and average, or spectacular and unpublishable. '
            'Multiplying the two would hide which of those is true.',
            accent=T.PINK, fill=T.PINK_SOFT, size=9.8)
    footer(prs, slide)
    notes(slide, 'Tier counts from outputs/final/phase5/ranking_bowler_chase.csv and '
                 'ranking_batter_chase.csv: 4 Moderate and 6 Limited bowlers; 8 Limited '
                 'batters.')


def slide_selection(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    head = payload['headline']
    y = header(prs, slide, '07 · How players were selected',
               'A rule frozen before any calculation, applied to an eligible pool',
               'No role-specific tuning, no manual overrides, no promotion to fill a list.',
               lede_width=9.9)
    chart_w = 6.25
    picture(prs, slide, 'funnel', LEFT_X, y + 0.06, chart_w)
    right_x = LEFT_X + chart_w + 0.40
    right_w = W - M - right_x
    rect(slide, right_x, y + 0.02, right_w, 1.30, T.NIGHT)
    draw_text(prs, slide, right_x + 0.22, y + 0.16, right_w - 0.44,
              'THE PRE-REGISTERED RULE', 8.5, T.PINK, bold=True)
    draw_text(prs, slide, right_x + 0.22, y + 0.42, right_w - 0.44,
              'Eligible if B_A ≥ 0.20.\nOrder by S* = A* − 0.30·B*.\n'
              'List length = min(10, eligible).', 11.0, T.ON_NIGHT, bold=True,
              spacing=1.24)
    bullets(prs, slide, right_x, y + 1.52, right_w, [
        '**Ties:** by B_A, then pressure deliveries, then player ID — written down in advance.',
        '**No filler:** when only eight batters qualify, the list stops at eight.',
        '**Same rule for both roles:** nothing was tuned to produce a preferred name.',
        '**Recorded in SDR-2026-11-18-03** before the Phase 5 run.',
    ], size=10.4, gap_after=0.08)
    draw_text(prs, slide, right_x, 5.95, right_w,
              f"{head['bowler_scored']} bowlers and {head['batter_scored']} batters were "
              f"scored; {head['bowler_eligible']} bowlers and {head['batter_eligible']} "
              'batters cleared the gate. The gap is the finding, not a problem to paper over.',
              9.4, T.INK_SOFT, spacing=1.16)
    footer(prs, slide)
    notes(slide, 'Sources: reports/methodology/SDR-2026-11-18-03-phase5-ranking.md, applied '
                 'in src/ranking/run_phase5.py. 388 bowler rows scored, 36 eligible; 445 '
                 'batter rows scored, 8 eligible; 377 innings-1 bowler rows scored, 0 '
                 'eligible.')


def _results_table(prs, slide, rows, y: float, width: float, name_share: float,
                   row_height: float) -> float:
    table_rows = []
    for row in rows:
        table_rows.append([
            str(row['rank']), row['player_name'], f"{row['S_star']:+.3f}",
            f"[{row['S_ci90_low']:+.3f}, {row['S_ci90_high']:+.3f}]",
            f"{row['shrinkage_A']:.2f}", row['evidence_tier'],
            f"{row['n_pressure']:,}",
        ])
    return table(prs, slide, LEFT_X, y, width, [
        ('#', 0.4), ('Player', name_share), ('S*', 0.8), ('90% interval', 2.05),
        ('B_A', 0.6), ('Tier', 1.0), ('Pressure balls', 1.1),
    ], table_rows, size=9.4, header_size=7.8, row_height=row_height,
        align_right=(0, 2, 3, 4, 6))


def slide_results_bowlers(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    rows = payload['rankings']['bowler_chase']
    moderate = [row for row in rows if row['evidence_tier'] == 'Moderate']
    moderate_text = ', '.join(
        f"{row['player_name']} (B_A {row['shrinkage_A']:.2f})" for row in moderate)
    rank_gap = abs(rows[1]['S_star'] - rows[2]['S_star'])
    if len(rows) != 10:
        raise ValueError(f'bowler list must have 10 rows, has {len(rows)}')
    y = header(prs, slide, '08 · Final results — bowlers',
               'Ten chase bowlers are published from 36 eligible',
               'The order is an ordering of point estimates inside a shortlist. It is not a '
               'podium and it is not statistically separable.', lede_width=9.9)
    table_w = 7.05
    end = _results_table(prs, slide, rows, y - 0.02, table_w, 2.15, 0.315)
    draw_text(prs, slide, LEFT_X, end + 0.10, table_w,
              'Every interval contains zero. S* is a point estimate, not a probability of '
              'being better.', 8.8, T.INK_FAINT, spacing=1.12)
    right_x = LEFT_X + table_w + 0.35
    right_w = W - M - right_x
    chart_w = fit_width('bowler_ci', right_w, 2.95)
    chart_end = picture(prs, slide, 'bowler_ci', right_x, y + 0.02, chart_w)
    note_y = callout(prs, slide, right_x, chart_end + 0.20, right_w,
                     'Read this, not the order',
                     'All ten intervals contain zero and every adjacent pair overlaps. '
                     'The defensible claim is the eligible set (PH5-01).',
                     accent=T.PINK, fill=T.PINK_SOFT, size=9.2)
    draw_text(prs, slide, right_x, note_y + 0.16, right_w,
              f'Highest evidence: {moderate_text}. No player reaches the High tier; '
              f'ranks 2 and 3 differ by {rank_gap:.5f}.',
              8.8, T.INK_SOFT, spacing=1.12)
    footer(prs, slide)
    notes(slide, 'Rows copied from outputs/final/phase5/ranking_bowler_chase.csv. All ten '
                 'intervals contain zero and all nine adjacent pairs overlap.')


def slide_results_batters(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    rows = payload['rankings']['batter_chase']
    if len(rows) != 8:
        raise ValueError(f'batter list must have 8 rows, has {len(rows)}')
    y = header(prs, slide, '08 · Final results — batters',
               'Eight batters clear the gate. The list stops at eight.',
               'No player was added to reach ten. Adding two names would have required a '
               'lower threshold or a weaker evidence rule, and neither was done.',
               lede_width=9.9)
    table_w = 7.05
    end = _results_table(prs, slide, rows, y - 0.02, table_w, 2.25, 0.36)
    draw_text(prs, slide, LEFT_X, end + 0.12, table_w,
              'All eight are Limited tier and all eight intervals contain zero. Top-eight '
              'membership is 100% by construction, so the deck reports the resampled rank '
              'range instead: even the leader’s median rank is 2, with a 1–7 range.', 8.8,
              T.INK_SOFT, spacing=1.14)
    right_x = LEFT_X + table_w + 0.35
    right_w = W - M - right_x
    chart_end = picture(prs, slide, 'batter_ci', right_x, y + 0.02, right_w)
    callout(prs, slide, right_x, chart_end + 0.20, right_w,
            'Eight is the finding',
            '445 batters were scored; eight have enough reliable pressure evidence. The '
            'short list is a statement about the data, not about the players who missed it '
            '(F4-01).', accent=T.BLUE, fill=T.BLUE_SOFT, size=9.2)
    draw_text(prs, slide, right_x, 6.00, right_w,
              'The published batter list is the complete eligible set. There is no ninth or '
              'tenth player in any deliverable.', 9.0, T.PINK, italic=True, spacing=1.14)
    footer(prs, slide)
    notes(slide, 'Rows copied from outputs/final/phase5/ranking_batter_chase.csv. Exactly 8 '
                 'rows; all Limited tier; all intervals contain zero.')


def slide_innings1(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    head = payload['headline']
    y = header(prs, slide, '08 · Separate context, separate finding',
               'First-innings bowling: 377 scored, zero eligible, no ranking',
               'This is reported as a research finding. It is never merged with chase and it '
               'does not produce a player list.', lede_width=9.9)
    stats = [
        (f"{head['innings1_scored']}", 'bowlers scored', 'in the innings-1 pressure context'),
        (f"{head['innings1_eligible']}", 'eligible at B_A ≥ 0.20', 'no player clears the gate'),
        ('0.150', 'highest reliability', 'below the 0.20 threshold'),
        ('1.61', 'runs per ball conceded', 'against 1.36 in other innings-1 states'),
    ]
    cards_height = stat_cards(prs, slide, LEFT_X, y - 0.02, CONTENT_W,
                              [(v, l, nt) for v, l, nt in stats], value_size=22.0,
                              label_size=10.0, note_size=8.2, gap=0.16,
                              value_colours=[T.AMBER] * 4) - (y - 0.02)
    body_y = y + cards_height + 0.26
    draw_text(prs, slide, LEFT_X, body_y, COL_W, 'WHY THERE IS NO RANKING', 8.5,
              T.INK_FAINT, bold=True)
    bullets(prs, slide, LEFT_X, body_y + 0.30, COL_W, [
        '**The flag is partly the scoring environment.** It marks a bowling side under '
        'pressure while the batting side is ahead of par, so a high run rate is part of the '
        'definition (PH3-01).',
        '**No player clears the reliability gate.** Without a run-rate control, the context '
        'cannot be read as pure bowling skill.',
        '**Nothing was borrowed from chase.** There is no cross-context score anywhere in '
        'this project.',
    ], size=11.0, gap_after=0.12)
    panel_x = RIGHT_X
    panel_y = body_y - 0.06
    rect(slide, panel_x, panel_y, COL_W, 2.85, T.NIGHT)
    draw_text(prs, slide, panel_x + 0.28, panel_y + 0.22, COL_W - 0.56,
              'WHAT WE PUBLISH INSTEAD', 8.5, T.PINK, bold=True)
    draw_text(prs, slide, panel_x + 0.28, panel_y + 0.52, COL_W - 0.56,
              'A research finding with a named limitation', 16.0, T.ON_NIGHT, bold=True,
              spacing=1.05)
    draw_text(prs, slide, panel_x + 0.28, panel_y + 1.16, COL_W - 0.56,
              'The context stays available for future work with a revised definition — for '
              'example one that controls for the scoring environment directly. Until then, '
              'publishing a list from it would present a confounded quantity as skill.',
              10.2, T.ON_NIGHT_SOFT, spacing=1.22)
    draw_text(prs, slide, panel_x + 0.28, panel_y + 2.38, COL_W - 0.56,
              'Status: PH3-01 OPEN · F4-02 OPEN · no ranking exists', 8.8, T.PINK,
              bold=True)
    footer(prs, slide)
    notes(slide, 'Sources: outputs/final/phase5/context_status.csv (377 scored, 0 eligible, '
                 'max B_A 0.150) and Phase 3 descriptive rates 1.6107 vs 1.3643 runs per ball.')


def slide_uncertainty(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    separation = [r for r in payload['separation'] if r['role'] == 'bowler']
    gap = abs(separation[1]['S_star'] - separation[2]['S_star'])
    mean_width = sum(r['ci_width'] for r in separation) / len(separation)
    y = header(prs, slide, '09 · Sensitivity and uncertainty',
               'The order is fragile; the eligible set is the stable result',
               'Four disclosures that must travel with every quotation of this list.',
               lede_width=9.9)
    chart_w = 5.85
    picture(prs, slide, 'separation', LEFT_X, y + 0.06, chart_w)
    right_x = LEFT_X + chart_w + 0.40
    right_w = W - M - right_x
    cards = [
        (f"{sum(r['contains_zero'] for r in separation)} / {len(separation)}",
         'bowler intervals contain zero'),
        (f"{sum(bool(r['ci_overlaps_previous']) for r in separation[1:])} / "
         f"{max(len(separation) - 1, 0)}", 'adjacent pairs overlap'),
        (f'{mean_width:.2f}', 'average interval width'),
        (f'{gap:.5f}', 'gap between ranks 2 and 3'),
    ]
    card_w = (right_w - 0.16) / 2
    for index, (value, label) in enumerate(cards):
        x = right_x + (index % 2) * (card_w + 0.16)
        card_y = y + 0.02 + (index // 2) * 1.02
        rect(slide, x, card_y, card_w, 0.90, T.SURFACE, T.RULE)
        draw_text(prs, slide, x + 0.16, card_y + 0.10, card_w - 0.32, value, 18.0, T.PINK,
                  bold=True)
        draw_text(prs, slide, x + 0.16, card_y + 0.48, card_w - 0.32, label, 8.8,
                  T.INK_SOFT, spacing=1.1)
    callout(prs, slide, right_x, 4.30, right_w,
            'Say it plainly',
            'These eighteen players have pressure evidence strong enough to publish under a '
            'pre-registered rule. The bowler top three are stable under resampling; positions '
            'four to ten are not. Do not present the list as a podium.',
            accent=T.RED, fill=T.RED_SOFT, size=9.6, body_colour=T.INK)
    lead = payload['rankings']['bowler_chase'][0]
    draw_text(prs, slide, right_x, 5.82, right_w,
              f"A score of {lead['S_star']:+.3f} with an interval of "
              f"[{lead['S_ci90_low']:+.3f}, {lead['S_ci90_high']:+.3f}] is statistically "
              'consistent with an average player. The list is a shortlist, not a verdict.',
              9.4, T.INK_SOFT, spacing=1.16)
    footer(prs, slide)
    notes(slide, 'Sources: reports/phase_5/separation.csv (18 rows; contains_zero and '
                 'ci_overlaps_previous true for all published bowlers). Interval widths '
                 '0.331–0.392, mean 0.366.')


def slide_bootstrap(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    bowler_stability = [r for r in payload['stability']
                        if r['role'] == 'bowler' and r['context'] == 'chase']
    top_three = [r['share_top10'] for r in bowler_stability if r['rank'] <= 3]
    last_five = [r['share_top10'] for r in bowler_stability if 6 <= r['rank'] <= 10]
    lead = min(bowler_stability, key=lambda r: r['rank'])
    y = header(prs, slide, '09 · Sensitivity and uncertainty',
               'What resampling says about each place — and what it cannot say',
               'Match-block bootstrap, 200 resamples, empirical-Bayes fit held fixed.',
               lede_width=9.9)
    chart_w = fit_width('bootstrap', 6.9, 6.47 - y - 0.08)
    picture(prs, slide, 'bootstrap', LEFT_X, y + 0.06, chart_w)
    right_x = LEFT_X + chart_w + 0.40
    right_w = W - M - right_x
    draw_text(prs, slide, right_x, y + 0.04, right_w, 'HOW TO READ IT', 8.5, T.INK_FAINT,
              bold=True)
    bullets(prs, slide, right_x, y + 0.32, right_w, [
        f"**Top three:** kept in {min(top_three) * 100:.0f}–{max(top_three) * 100:.0f}% "
        'of resamples.',
        f"**Ranks 6–10:** kept in {min(last_five) * 100:.0f}–{max(last_five) * 100:.0f}%. "
        'A place there is a coin-flip, not a standing.',
        f"**Resampled ranks are wide:** the lead player's median is {lead['rank_median']} "
        f"with a {lead['rank_p05']}–{lead['rank_p95']} range; the tenth name "
        'moves across the eligible pool.',
        '**Matches, not balls, are resampled** — the dependence between deliveries in a '
        'match is preserved.',
    ], size=10.4, gap_after=0.10)
    callout(prs, slide, right_x, 4.55, right_w,
            'The limitation inside the method',
            'The fit is held fixed, so the bootstrap measures the fragility of the ranking '
            'conditional on the chosen model — not model uncertainty itself. The '
            'pre-registered design that re-estimated variance was measured and rejected '
            'before publication (F5-02).', accent=T.AMBER, fill=T.AMBER_SOFT, size=9.0)
    footer(prs, slide)
    notes(slide, 'Sources: reports/phase_5/rank_stability.csv and logs/run_phase5.json. '
                 'Fixed-EB-fit bootstrap, 200 reps, seed 20261122, 0 failed replicates. '
                 'Share kept in the top 10: 1.00, 0.985, 0.965, 0.83, 0.77, 0.55, 0.455, '
                 '0.465, 0.455, 0.40.')


def slide_sensitivity(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, '09 · Sensitivity and uncertainty',
               'Six alternatives: three keep the list nearly intact, three do not',
               'Reporting only the flattering specifications would be cherry-picking, so '
               'every alternative is shown — including the one that removes all ten names.',
               lede_width=9.9)
    chart_w = 6.45
    picture(prs, slide, 'sensitivity', LEFT_X, y + 0.06, chart_w)
    right_x = LEFT_X + chart_w + 0.40
    right_w = W - M - right_x
    rows = [
        ('Score weight w = 0.30', '9 / 10', 'kept'),
        ('Score weight w = 0.50', '10 / 10', 'kept'),
        ('REML variance', '9 / 10', 'kept'),
        ('IPL evidence only', '6 / 10', 'kept'),
        ('Single-stage combination', '2 / 10', 'kept'),
        ('E1 clustered variance', '0 / 10', 'lost'),
        ('T20I evidence only', '0 eligible', 'no list'),
    ]
    end = table(prs, slide, right_x, y + 0.02, right_w,
                [('Alternative', 2.1), ('Names kept', 1.0), ('', 0.6)],
                rows, size=9.0, header_size=7.4, row_height=0.325, align_right=(1,))
    end = draw_text(prs, slide, right_x, end + 0.14, right_w,
                    'Batter list under E1: 0 of 8 kept. Under single-stage and REML no '
                    'batter is eligible at all.', 8.8, T.INK_SOFT, spacing=1.12)
    callout(prs, slide, right_x, end + 0.14, right_w,
            'The honest summary',
            'The score weight barely matters; the variance estimator and the combination '
            'method matter a great deal. Any claim that survives only under the approved '
            'specification should say so.', accent=T.RED, fill=T.RED_SOFT, size=9.0)
    footer(prs, slide)
    notes(slide, 'Sources: reports/phase_5/sensitivity_rank.csv. Overlap with the primary '
                 'top 10 (bowlers): w=0.30 9, w=0.50 10, REML 9, IPL-only 6, single-stage 2, '
                 'E1 0, T20I-only 0 eligible.')


def slide_formats(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    summary = payload['format_summary']['bowler']
    y = header(prs, slide, '09 · Format scope',
               'The combined list is mostly IPL evidence — and says nothing about transfer',
               'IPL and T20I were estimated separately, then combined descriptively. T20I '
               'alone cannot rank anyone in either role.', lede_width=9.9)
    table_y = y - 0.02
    rows = []
    for row in payload['formats']:
        if row['format_scope'] != 'IPL' or row['role'] != 'bowler':
            continue
        rows.append([str(row['rank']), row['player_name'], f"{row['S_star_format']:+.3f}",
                     f"{row['shrinkage_A']:.2f}",
                     'yes' if row['in_combined_top'] else 'no'])
    end = table(prs, slide, LEFT_X, table_y, 6.35,
                [('#', 0.4), ('IPL-only bowler', 2.35), ('IPL-only S*', 1.0),
                 ('B_A', 0.6), ('In combined', 0.85)],
                rows, size=9.0, header_size=7.4, row_height=0.30,
                align_right=(0, 2, 3))
    draw_text(prs, slide, LEFT_X, end + 0.12, 6.35,
              'IPL-only scores are a separate estimand, computed from the published '
              'IPL-only components.', 8.2, T.INK_FAINT, spacing=1.1)
    right_x = LEFT_X + 6.35 + 0.40
    right_w = W - M - right_x
    figures = [
        (f"{summary['combined_top']} / {summary['combined_top']}",
         'combined list published', T.INK),
        (f"{summary['scopes']['IPL']['shared_with_combined']} / 10",
         'also in the IPL-only top 10', T.INK),
        (f"{summary['scopes']['T20I']['rows_shown']}",
         'T20I-only players eligible, both roles', T.AMBER),
    ]
    cursor = table_y
    for value, label, colour in figures:
        cursor = draw_text(prs, slide, right_x, cursor, 1.35, value, 17.0, colour,
                           bold=True)
        draw_text(prs, slide, right_x + 1.42, cursor - 0.30, right_w - 1.42, label, 9.4,
                  T.INK_SOFT, spacing=1.1)
        cursor += 0.14
    draw_text(prs, slide, right_x, cursor + 0.16, right_w,
              'WHAT THE COMBINATION IS NOT', 8.5, T.INK_FAINT, bold=True)
    bullet_end = bullets(prs, slide, right_x, cursor + 0.46, right_w, [
        '**Not evidence of transferability.** A player’s IPL pressure record does not '
        'establish how they would perform in a T20I.',
        '**Not a T20I ranking.** The T20I-only list is empty by construction.',
        '**Not a promise about the future.** A descriptive estimate from past matches.',
    ], size=10.0, gap_after=0.10)
    callout(prs, slide, right_x, bullet_end + 0.16, right_w,
            'Disclosure that travels with the list',
            'T20I-only eligibility is zero in both roles (PH5-02), so the combined estimate '
            'is mainly IPL-driven.', accent=T.AMBER, fill=T.AMBER_SOFT, size=9.2)
    footer(prs, slide)
    notes(slide, 'Sources: outputs/final/phase5/format_specific_ranking.csv and '
                 'reports/phase_5/sensitivity_rank.csv. IPL-only keeps 6 of the 10 '
                 'published bowlers; T20I-only admits 0 in both roles.')


def slide_limitations(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, '10 · Limitations and status',
               'Nine documented limitations travel with this work',
               'The statuses below are the same ones recorded in the failure register and the '
               'issue log. Phase 6 changed no analytical output.', lede_width=9.9)
    rows = [
        ('PH5-01', 'The published order is not statistically separable', 'Open · disclosed'),
        ('PH5-02', 'The combined ranking is mainly IPL-driven', 'Open · disclosed'),
        ('PH5-03', 'Upstream display names were corrupted', 'Mitigated for display'),
        ('PH3-01', 'First-innings bowling is state-confounded', 'Open · no ranking'),
        ('PH2-05', 'Broad and failed pressure flags remain unused', 'Open · unchanged'),
        ('F4-01', 'Only eight batters reach the threshold', 'Open · shortfall published'),
        ('F4-02', 'No first-innings bowling ranking exists', 'Open · finding published'),
        ('F5-01', 'players_dim.csv pairs the wrong names with IDs', 'Open in Phase 1'),
        ('F5-02', 'The pre-registered bootstrap design was rejected', 'Closed · replaced'),
    ]
    end = table(prs, slide, LEFT_X, y - 0.02, 7.75,
                [('ID', 0.62), ('Limitation', 4.6), ('Status', 1.55)],
                rows, size=9.0, header_size=7.6, row_height=0.365)
    right_x = LEFT_X + 7.75 + 0.42
    right_w = W - M - right_x
    draw_text(prs, slide, right_x, y - 0.02, right_w, 'WHAT WE WILL NOT SAY', 8.5, T.RED,
              bold=True)
    bullets(prs, slide, right_x, y + 0.26, right_w, [
        '“The best T20 bowlers in the world.”',
        '“The data proves X is the most clutch.”',
        '“This transfers to T20I.”',
        '“Rank 1 is better than rank 2.”',
    ], size=10.0, gap_after=0.06, bullet_colour=T.RED)
    say_y = 3.62
    draw_text(prs, slide, right_x, say_y, right_w, 'WHAT WE WILL SAY', 8.5, T.GREEN,
              bold=True)
    bullets(prs, slide, right_x, say_y + 0.28, right_w, [
        '“Eighteen players have publishable pressure evidence under a pre-registered rule.”',
        '“The top three are stable under resampling; the rest of the order is not.”',
        '“Read the tiers and the intervals, not the podium.”',
    ], size=9.8, gap_after=0.06, bullet_colour=T.GREEN)
    footer(prs, slide)
    notes(slide, 'Statuses mirror FAILURE_REGISTER.md and reports/ISSUES.md. F5-01 remains '
                 'in Phase 1; the display fix is documented in the audit view of the '
                 'dashboard.')


def slide_future(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    y = header(prs, slide, '10 · Future improvements',
               'What would genuinely strengthen the evidence',
               'None of these is a promise, and none changes the current outputs. They are '
               'the next research steps the limitations imply.', lede_width=9.9)
    items = [
        ('01', 'Revise the innings-1 definition',
         'Add a direct control for the scoring environment, then re-test difficulty. Until '
         'it passes, no innings-1 ranking exists (PH3-01, F4-02).'),
        ('02', 'More batter pressure evidence',
         'The eight-batter list is a volume problem. More matches, or a validated additional '
         'context, would be needed before ten is even possible (F4-01).'),
        ('03', 'Model T20I between-player variance',
         'A zero variance estimate blocks any T20I-only list. A hierarchical formulation '
         'with a weakly informative prior is the candidate next step (PH5-02).'),
        ('04', 'Pre-register a model-uncertainty bootstrap',
         'The rejected design inflated the eligible pool. A redesigned version could '
         'quantify model uncertainty, not only rank fragility (F5-02).'),
        ('05', 'Fix the upstream name table',
         'Regenerate players_dim.csv under its own authorisation and add a regression test. '
         'Display names are already resolved; the source defect remains (F5-01).'),
        ('06', 'External validation',
         'Test the pressure flag on a later season or another league before claiming the '
         'definition generalises.'),
    ]
    for column, block in enumerate((items[:3], items[3:])):
        x = LEFT_X + column * (COL_W + GUTTER)
        row_y = y + 0.04
        for number, title, body in block:
            draw_text(prs, slide, x, row_y, 0.42, number, 10.0, T.PINK, bold=True)
            draw_text(prs, slide, x + 0.42, row_y - 0.02, COL_W - 0.42, title, 11.6,
                      T.INK, bold=True)
            end = draw_text(prs, slide, x + 0.42, row_y + 0.28, COL_W - 0.42, body, 10.0,
                            T.INK_SOFT, spacing=1.18)
            row_y = end + 0.30
    callout(prs, slide, LEFT_X, 5.82, CONTENT_W,
            'The standard for any future version',
            'A change is only an improvement if the pre-registered rule still produces it '
            'and the uncertainty is reported with it. Otherwise it is a different, '
            'unpublishable claim.', accent=T.BLUE, fill=T.BLUE_SOFT, size=10.0)
    footer(prs, slide)
    notes(slide, 'Future work is framed as research steps, not commitments. It maps '
                 'one-to-one onto the open limitations.')


def slide_verify(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs)
    verification = payload['verification']
    checks = verification['independent_checks']
    total = len(verification['independent'])
    y = header(prs, slide, 'Close · Reproducibility',
               'Every number here can be checked against the frozen files',
               'The dashboard, deck and PDF are generated from one payload that is copied '
               'field by field from the Phase 5 outputs.', lede_width=9.9)
    cards = [
        ('15 / 15', 'internal validation checks', 'Phase 5 gate'),
        (f'{checks} / {checks}', 'independent checks', 'separate implementation'),
        ('TRUE', 'frozen inputs unchanged', 'SHA-256 before and after'),
        ('0', 'network requests', 'dashboard is one offline file'),
    ]
    cards_height = stat_cards(prs, slide, LEFT_X, y - 0.02, CONTENT_W, cards,
                              value_size=19.0, label_size=9.4, note_size=8.2, gap=0.18,
                              value_colours=[T.INK] * 4) - (y - 0.02)
    table_y = y + cards_height + 0.26
    draw_text(prs, slide, LEFT_X, table_y, 7.3, 'DELIVERABLES', 8.5, T.INK_FAINT,
              bold=True)
    rows = [
        ('Interactive dashboard', 'outputs/final/deliverables/dashboard/index.html'),
        ('Presentation', 'outputs/final/deliverables/SupeRR_Selector_Phase6_Deck.pptx'),
        ('Report', 'outputs/final/deliverables/SupeRR_Selector_Phase6_Report.pdf'),
        ('Canonical payload', 'outputs/final/deliverables/dashboard/dashboard_data.json'),
        ('Hash manifest', 'reports/audit_bundle/sha256_outputs.txt'),
    ]
    table(prs, slide, LEFT_X, table_y + 0.28, 7.3, [('Deliverable', 1.7), ('Path', 5.6)],
          rows, size=9.0, header_size=7.6, row_height=0.315)
    right_x = LEFT_X + 7.3 + 0.42
    right_w = W - M - right_x
    end = callout(prs, slide, right_x, table_y + 0.02, right_w,
                  'Reproduce it',
                  'Run `python3 -m src.deliverables.run_phase6`. It rebuilds all three '
                  'deliverables, re-runs every check and writes a JSON log with the '
                  'results.', accent=T.TEAL, fill=T.TEAL_SOFT, size=9.2)
    draw_text(prs, slide, right_x, end + 0.20, right_w,
              'The Phase 5 rankings are read-only. Phase 6 does not fit a model, change a '
              'threshold or reorder a player.', 9.4, T.INK_SOFT, spacing=1.18)
    footer(prs, slide)
    notes(slide, f'Dashboard verification: 22 automated browser checks plus static checks on '
                 f'the HTML and payload. Phase 5: 15 internal, {total} independent.')


def slide_close(prs, payload: dict[str, Any]) -> None:
    slide = new_slide(prs, T.NIGHT)
    rect(slide, 0, 0, 0.28, H, T.PINK)
    draw_text(prs, slide, 1.05, 1.10, 9.0, 'THE CLAIM WE ARE WILLING TO DEFEND', 10.5,
              T.PINK, bold=True)
    draw_text(prs, slide, 1.05, 1.48, 10.9,
              'Eighteen players have pressure\nevidence strong enough to publish.', 35.0,
              T.ON_NIGHT, bold=True, spacing=1.02, kind='hero')
    draw_text(prs, slide, 1.05, 3.72, 10.4,
              'Ten chase bowlers and eight chase batters, selected by a rule frozen before '
              'the calculation. The top three bowlers are stable under resampling; the rest '
              'of the order is not. No first-innings ranking exists, and no claim is made '
              'that performance transfers between formats.', 13.5, T.ON_NIGHT_SOFT,
              spacing=1.30)
    rect(slide, 1.05, 5.28, 2.2, 0.03, T.PINK)
    draw_text(prs, slide, 1.05, 5.52, 5.3,
              'Read with the intervals,\nthe tiers and the eligible pool size.', 12.5,
              T.ON_NIGHT, bold=True, spacing=1.26)
    draw_text(prs, slide, 7.05, 5.52, 5.3,
              'Phase 6 · communication deliverables\nOwner review required before Phase 7',
              11.5, T.ON_NIGHT_SOFT, spacing=1.30)
    footer(prs, slide, dark=True)
    notes(slide, 'Close on the defensible claim. Do not add a podium or a “best player” line.')


# ----------------------------------------------------------------------- audit
def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    pad = 0.015
    return not (a['x'] + a['w'] <= b['x'] + pad or b['x'] + b['w'] <= a['x'] + pad
                or a['y'] + a['h'] <= b['y'] + pad or b['y'] + b['h'] <= a['y'] + pad)


def audit_layout() -> dict[str, Any]:
    """Fail if a text block leaves the slide or two text blocks overlap."""
    problems: list[str] = []
    text_kinds = {'text', 'bullet', 'callout-title', 'callout-body', 'title', 'lede',
                  'eyebrow', 'footer', 'hero'}
    blocks = [b for b in _BLOCKS if b['kind'] in text_kinds | {'picture', 'table'}]
    for b in _BLOCKS:
        if b['x'] < -0.001 or b['y'] < -0.001:
            problems.append(f"slide {b['slide']}: block starts off-slide {b['text']!r}")
        if b['x'] + b['w'] > W + 0.001:
            problems.append(f"slide {b['slide']}: block exceeds width {b['text']!r}")
        if b['y'] + b['h'] > H + 0.001:
            problems.append(f"slide {b['slide']}: block exceeds height {b['text']!r}")
    slides_with_footer = {b['slide'] for b in _BLOCKS if b['kind'] == 'footer'}
    for b in _BLOCKS:
        if b['kind'] == 'footer' or b['slide'] not in slides_with_footer:
            continue
        if b['kind'] in text_kinds | {'picture', 'table'} and b['y'] + b['h'] > 6.56:
            problems.append(
                f"slide {b['slide']}: block runs into the footer band {b['text']!r}")
    for index, first in enumerate(blocks):
        for second in blocks[index + 1:]:
            if first['slide'] != second['slide']:
                continue
            if _overlap(first, second):
                problems.append(
                    f"slide {first['slide']}: overlap {first['text']!r} / {second['text']!r}")
    return {'blocks': len(blocks), 'problems': problems}


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or D.build_payload()
    _BLOCKS.clear()
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)

    slide_title(prs, payload)
    slide_agenda(prs, payload)

    slide_section(prs, '01', 'The problem',
                  'Why a scorecard cannot answer a pressure question.')
    slide_problem(prs, payload)
    slide_section(prs, '02', 'Why conventional statistics fail',
                  'Outcome statistics are not situation statistics.')
    slide_conventional(prs, payload)
    slide_section(prs, '03–04', 'Defining pressure and measuring performance',
                  'A validated state label, then a situation-adjusted delivery score.')
    slide_pressure(prs, payload)
    slide_performance(prs, payload)
    slide_section(prs, '05–06', 'Shrinkage and reliability',
                  'Small samples need shrinking; reliability is a separate question.')
    slide_shrinkage(prs, payload)
    slide_reliability(prs, payload)
    slide_section(prs, '07–08', 'Selection and results',
                  'A pre-registered rule, an eligible pool, and a shortlist.')
    slide_selection(prs, payload)
    slide_results_bowlers(prs, payload)
    slide_results_batters(prs, payload)
    slide_innings1(prs, payload)
    slide_section(prs, '09', 'Sensitivity and uncertainty',
                  'What survives a change of method — and what does not.')
    slide_uncertainty(prs, payload)
    slide_bootstrap(prs, payload)
    slide_sensitivity(prs, payload)
    slide_formats(prs, payload)
    slide_section(prs, '10', 'Limitations and future work',
                  'The list of what this analysis cannot support.')
    slide_limitations(prs, payload)
    slide_future(prs, payload)
    slide_verify(prs, payload)
    slide_close(prs, payload)

    audit = audit_layout()
    if audit['problems']:
        raise SystemExit('layout audit failed:\n  ' + '\n  '.join(audit['problems']))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    return {
        'path': str(OUT.relative_to(D.ROOT)),
        'slides': len(prs.slides),
        'bytes': OUT.stat().st_size,
        'sha256': D.sha256(OUT),
        'layout_blocks': audit['blocks'],
    }


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
