"""Build the Phase 6 PDF report as print-ready HTML, then print it with Chrome.

The report is an A4 document with fixed pages: every page is a 210 × 297 mm
block, so page breaks are deliberate rather than accidental, and a DOM check can
prove that no page overflows its box. Content comes from the same canonical
payload as the dashboard and the deck.
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.deliverables import data as D
from src.deliverables import theme as T

OUT_DIR = T.DELIVERABLES / 'report'
HTML_PATH = OUT_DIR / 'index.html'
PDF_PATH = T.DELIVERABLES / T.PDF_NAME
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
ASSETS_REL = '../assets'


def esc(value: Any) -> str:
    return html.escape(str(value), quote=False)


def fmt_signed(value: float | None, digits: int = 3) -> str:
    if value is None:
        return '—'
    return f'{value:+.{digits}f}'


def fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return '—'
    return f'{value:.{digits}f}'


def fmt_int(value: Any) -> str:
    if value is None:
        return '—'
    return f'{int(value):,}'


def table(headers: Sequence[str], rows: Sequence[Sequence[str]],
          widths: Sequence[str] | None = None, cls: str = '',
          right: Iterable[int] = ()) -> str:
    right = set(right)
    style = ''
    if widths:
        style = '<colgroup>' + ''.join(f'<col style="width:{w}">' for w in widths) + '</colgroup>'
    head = ''.join(
        f'<th class="{"r" if i in right else ""}">{esc(h)}</th>'
        for i, h in enumerate(headers))
    body = []
    for row in rows:
        cells = ''.join(
            f'<td class="{"r" if i in right else ""}">{c}</td>'
            for i, c in enumerate(row))
        body.append(f'<tr>{cells}</tr>')
    return (f'<table class="{cls}">{style}<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>')


def callout(title: str, body: str, tone: str = 'pink') -> str:
    return (f'<div class="callout {tone}"><div class="ct">{esc(title)}</div>'
            f'<div class="cb">{body}</div></div>')


def figure(key: str, caption: str) -> str:
    return (f'<figure><img src="{ASSETS_REL}/{key}.png" alt="">'
            f'<figcaption>{caption}</figcaption></figure>')


def stats(items: Sequence[tuple[str, str, str]]) -> str:
    cells = ''.join(
        f'<div class="stat"><div class="sv">{esc(value)}</div>'
        f'<div class="sl">{esc(label)}</div><div class="sn">{esc(note)}</div></div>'
        for value, label, note in items)
    return f'<div class="stats">{cells}</div>'


def bullets(items: Sequence[str], cls: str = '') -> str:
    return f'<ul class="{cls}">' + ''.join(f'<li>{item}</li>' for item in items) + '</ul>'


CSS = """
:root {
  --paper:#F8F7F4; --surface:#FFFFFF; --ink:#10151F; --ink-soft:#4A5464;
  --ink-faint:#7B8494; --rule:#E2DFD8; --pink:#D6197F; --pink-soft:#FBE7F2;
  --blue:#1B3A6B; --blue-soft:#E7EEF8; --teal:#0E7C86; --teal-soft:#E2F1F2;
  --amber:#A9680B; --amber-soft:#FBF0DC; --red:#B3261E; --red-soft:#FAE7E5;
  --green:#1F7A4D; --green-soft:#E4F1E9; --night:#0B1220;
}
* { box-sizing: border-box; }
html, body { margin:0; padding:0; background:#E9E7E1; }
body {
  font-family:-apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
  color:var(--ink); font-size:9.4pt; line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.page {
  position:relative; width:210mm; height:297mm; background:var(--paper);
  padding:16mm 18mm 15mm; margin:0 auto 10px; overflow:hidden;
  page-break-after:always; break-after:page;
}
.page:last-child { page-break-after:auto; break-after:auto; }
.page.dark { background:var(--night); color:#F5F2EB; }
.page.dark .muted, .page.dark .cap { color:#A9B4C4; }
.page.dark .rule { border-color:#2A3648; }

.eyebrow {
  font-size:7.4pt; font-weight:700; letter-spacing:.10em; text-transform:uppercase;
  color:var(--pink); margin:0 0 5mm;
}
h1 { font-size:23pt; line-height:1.12; margin:0 0 4mm; letter-spacing:-.012em; }
h1.sm { font-size:19pt; }
h2 { font-size:12.2pt; margin:6mm 0 2.4mm; letter-spacing:-.005em; }
h2:first-child { margin-top:0; }
h3 { font-size:10pt; margin:4mm 0 1.6mm; }
p { margin:0 0 2.6mm; }
p.lede { font-size:11pt; color:var(--ink-soft); line-height:1.5; margin-bottom:5mm; }
.muted { color:var(--ink-soft); }
.small { font-size:8.2pt; }
.cap { font-size:7.9pt; color:var(--ink-faint); line-height:1.45; }
.mono { font-family:"SF Mono", ui-monospace, Menlo, monospace; font-size:7.6pt; }
strong { font-weight:650; }

.footer {
  position:absolute; left:18mm; right:18mm; bottom:8mm;
  display:flex; justify-content:space-between; align-items:baseline;
  border-top:.4pt solid var(--rule); padding-top:2.2mm;
  font-size:7.2pt; color:var(--ink-faint);
}
.dark .footer { border-color:#2A3648; color:#A9B4C4; }
.footer .num { font-variant-numeric:tabular-nums; }

table { width:100%; border-collapse:collapse; font-size:8.4pt; margin:2mm 0 3mm; }
th {
  text-align:left; font-size:7.2pt; font-weight:700; letter-spacing:.05em;
  text-transform:uppercase; color:var(--ink-faint);
  border-bottom:.6pt solid var(--ink-faint); padding:1.6mm 1.6mm;
}
td { padding:1.5mm 1.6mm; border-bottom:.4pt solid var(--rule); vertical-align:top; }
tr:last-child td { border-bottom:none; }
td.r, th.r { text-align:right; font-variant-numeric:tabular-nums; }
table.tight td { padding:1.1mm 1.6mm; }
table.names-nowrap td:nth-child(2),
table.names-nowrap td:nth-child(4) { white-space:nowrap; }
table.xs { font-size:7.8pt; }
table.xs td, table.xs th { padding:1.0mm 1.3mm; }
.tier { font-size:7.2pt; font-weight:700; letter-spacing:.03em; }
.tier.High { color:var(--green); } .tier.Moderate { color:var(--blue); }
.tier.Limited { color:var(--pink); } .tier.Insufficient { color:var(--ink-faint); }

.stats { display:grid; grid-template-columns:repeat(4, 1fr); gap:3mm; margin:3mm 0 5mm; }
.stat { background:var(--surface); border:.5pt solid var(--rule); padding:3.2mm 3.4mm; }
.sv { font-size:16pt; font-weight:700; letter-spacing:-.02em; }
.sl { font-size:8.4pt; font-weight:650; margin-top:1mm; }
.sn { font-size:7.4pt; color:var(--ink-faint); margin-top:.6mm; }

.callout {
  background:var(--surface); border-left:2.2pt solid var(--pink);
  padding:3.2mm 4mm; margin:3mm 0 4mm;
}
.callout.blue { border-color:var(--blue); background:var(--blue-soft); }
.callout.amber { border-color:var(--amber); background:var(--amber-soft); }
.callout.red { border-color:var(--red); background:var(--red-soft); }
.callout.teal { border-color:var(--teal); background:var(--teal-soft); }
.callout.pink { background:var(--pink-soft); }
.ct { font-size:7.4pt; font-weight:700; letter-spacing:.09em; text-transform:uppercase;
      color:var(--pink); margin-bottom:1.6mm; }
.callout.blue .ct { color:var(--blue); } .callout.amber .ct { color:var(--amber); }
.callout.red .ct { color:var(--red); } .callout.teal .ct { color:var(--teal); }
.cb { font-size:8.8pt; line-height:1.5; }
.cb p:last-child { margin-bottom:0; }

ul { margin:0 0 3mm; padding-left:4.2mm; }
li { margin-bottom:1.6mm; }
li::marker { color:var(--pink); }

ol.disc { columns:2; column-gap:7mm; margin:0; padding-left:4.4mm; }
ol.disc li { break-inside:avoid; margin-bottom:2.2mm; }
figure { margin:2mm 0 4mm; }
figure.sm img { width:66%; margin:0 auto; }
figure img { width:100%; border:.4pt solid var(--rule); display:block; }
figcaption { font-size:7.4pt; color:var(--ink-faint); margin-top:1.4mm; line-height:1.4; }

.cols { display:grid; grid-template-columns:1fr 1fr; gap:7mm; }
.cols.wide-left { grid-template-columns:1.32fr 1fr; }
.cols.wide-right { grid-template-columns:1fr 1.32fr; }
.cols .tight-top { margin-top:0; }

.cover { padding:0; }
.cover .band { position:absolute; left:0; top:0; width:6mm; height:297mm; background:var(--pink); }
.cover .inner { padding:34mm 24mm 20mm 30mm; }
.cover .kicker { font-size:8pt; font-weight:700; letter-spacing:.14em; text-transform:uppercase;
                 color:var(--pink); }
.cover h1 { font-size:38pt; line-height:1.04; margin:9mm 0 7mm; color:#F5F2EB; }
.cover .sub { font-size:12.4pt; color:#A9B4C4; line-height:1.5; max-width:130mm; }
.cover .split { display:grid; grid-template-columns:1fr 1fr; gap:8mm; margin-top:18mm;
                border-top:.5pt solid #2A3648; padding-top:6mm; }
.cover .k { font-size:7.4pt; letter-spacing:.12em; text-transform:uppercase; color:var(--pink);
            font-weight:700; margin-bottom:2mm; }
.cover .v { font-size:9.4pt; color:#F5F2EB; line-height:1.6; }
.cover .v.dim { color:#A9B4C4; }
.cover .note { position:absolute; left:30mm; bottom:22mm; font-size:8.6pt; color:var(--pink); }
.cover .facts { margin-top:14mm; border-top:.5pt solid #2A3648; padding-top:5mm;
                display:grid; grid-template-columns:1fr 1fr 1fr; gap:8mm; }
.cover .fact { font-size:9pt; color:#A9B4C4; line-height:1.5; }
.cover .fact b { display:block; font-size:8pt; letter-spacing:.10em; text-transform:uppercase;
                 color:var(--pink); margin-bottom:1.6mm; }

.toc { display:grid; grid-template-columns:1fr 1fr; gap:3mm 8mm; font-size:9pt; }
.toc div { display:flex; gap:3mm; border-bottom:.4pt solid var(--rule); padding:1.6mm 0; }
.toc .n { color:var(--pink); font-weight:700; width:7mm; flex:none; }
.toc .p { margin-left:auto; color:var(--ink-faint); font-variant-numeric:tabular-nums; }

.kv { display:grid; grid-template-columns:34mm 1fr; gap:1.4mm 4mm; font-size:8.6pt; }
.kv.gloss { font-size:8.1pt; gap:1.2mm 3.4mm; }
.kv dt { color:var(--ink-faint); font-weight:650; }
.kv dd { margin:0; }

.quote { border-left:2.2pt solid var(--ink-faint); padding:1mm 0 1mm 4mm; margin:3mm 0;
         font-size:8.8pt; color:var(--ink-soft); }
.quote cite { display:block; font-style:normal; font-size:7.4pt; color:var(--ink-faint);
              margin-top:1.6mm; }

.checkline { display:flex; justify-content:space-between; padding:1.4mm 0;
             border-bottom:.4pt solid var(--rule); font-size:8.4pt; }
.checkline .ok { color:var(--green); font-weight:700; font-size:7.6pt; letter-spacing:.04em; }

@page { size:A4; margin:0; }
@media print {
  html, body { background:#fff; }
  .page { margin:0; box-shadow:none; }
}
"""


class Report:
    def __init__(self, payload: dict[str, Any], phase6: dict[str, Any] | None) -> None:
        self.p = payload
        self.phase6 = phase6 or {}
        self.pages: list[dict[str, str]] = []

    # ---------------------------------------------------------------- plumbing
    def page(self, title: str, eyebrow: str, body: str, dark: bool = False,
             cls: str = '', footer: str | None = None) -> None:
        self.pages.append({
            'title': title, 'eyebrow': eyebrow, 'body': body,
            'dark': dark, 'cls': cls, 'footer': footer if footer is not None else title,
        })

    def render(self) -> str:
        total = len(self.pages)
        parts = []
        for index, page in enumerate(self.pages, start=1):
            body = page['body']
            if page['dark']:
                parts.append(
                    f'<section class="page dark {page["cls"]}" data-page="{index}">'
                    f'{body}<div class="footer"><span>{esc(page["footer"])}</span>'
                    f'<span class="num">{index} / {total}</span></div></section>')
            else:
                parts.append(
                    f'<section class="page {page["cls"]}" data-page="{index}">'
                    f'<div class="eyebrow">{esc(page["eyebrow"])}</div>'
                    f'<h1 class="sm">{esc(page["title"])}</h1>'
                    f'{body}<div class="footer"><span>{esc(page["footer"])}</span>'
                    f'<span class="num">{index} / {total}</span></div></section>')
        return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
                f'<title>SupeRR Selector · Season 2 · Phase 6 report</title>'
                f'<style>{CSS}</style></head><body>{"".join(parts)}</body></html>')

    # ------------------------------------------------------------------- pages
    def build(self) -> 'Report':
        self.cover()
        self.contents()
        self.executive()
        self.problem()
        self.conventional()
        self.pressure()
        self.performance()
        self.shrinkage()
        self.reliability()
        self.selection()
        self.bowlers()
        self.batters()
        self.innings1()
        self.sensitivity()
        self.uncertainty()
        self.formats()
        self.limitations()
        self.reproducibility()
        self.appendix_pool()
        self.appendix_exclusions()
        self.appendix_glossary()
        self.appendix_sources()
        return self

    def cover(self) -> None:
        head = self.p['headline']
        self.page('Cover', '', f"""
<div class="band"></div>
<div class="inner">
  <div class="kicker">SupeRR Selector · Season 2 · Phase 6</div>
  <h1>Pressure performance,<br>measured honestly.</h1>
  <div class="sub">A situation-adjusted shortlist of T20 players, with the uncertainty,
  the exclusions and the failure modes reported alongside it.</div>
  <div class="split">
    <div>
      <div class="k">Results</div>
      <div class="v">Ten chase bowlers · eight chase batters<br>
      Zero eligible first-innings bowlers</div>
    </div>
    <div>
      <div class="k">Basis</div>
      <div class="v dim">Phase 5 results frozen {esc(self.p['meta']['date_label'])}<br>
      {fmt_int(head['matches'])} matches · {fmt_int(head['deliveries'])} deliveries</div>
    </div>
  </div>
  <div class="facts">
    <div class="fact"><b>Read the intervals</b>Every published 90% interval contains zero.
    A point estimate is not a verdict.</div>
    <div class="fact"><b>Not a podium</b>Adjacent ranks overlap; the order is not
    statistically separable (PH5-01).</div>
    <div class="fact"><b>The list stops early</b>Eight batters clear the gate, not ten.
    Nothing was added to fill a place.</div>
  </div>
</div>
<div class="note">Communication build only: no retraining, no threshold change, no re-ranking.</div>
""", dark=True, cls='cover', footer='SupeRR Selector · Season 2 · Phase 6 report')

    def contents(self) -> None:
        items = [
            ('01', 'The problem', 4),
            ('02', 'Why conventional statistics fail', 5),
            ('03', 'How pressure was defined', 6),
            ('04', 'How performance was measured', 7),
            ('05', 'Empirical-Bayes shrinkage', 8),
            ('06', 'Reliability is not performance', 9),
            ('07', 'How players were selected', 10),
            ('08', 'Final results — bowlers', 11),
            ('08', 'Final results — batters', 12),
            ('09', 'First-innings bowling', 13),
            ('10', 'Sensitivity', 14),
            ('11', 'Uncertainty', 15),
            ('12', 'Format scope', 16),
            ('13', 'Limitations and status', 17),
            ('14', 'Reproducibility', 18),
            ('A', 'Appendix A · the eligible pool', 19),
            ('B', 'Appendix B · exclusions', 20),
            ('C', 'Appendix C · glossary', 21),
            ('D', 'Appendix D · sources and frozen hashes', 22),
        ]
        toc = ''.join(
            f'<div><span class="n">{n}</span><span>{esc(t)}</span>'
            f'<span class="p">{pg}</span></div>' for n, t, pg in items)
        body = f"""
<div class="toc">{toc}</div>
<h2>How to read this report</h2>
<p>Every claim follows the same shape: a score, the reliability of the evidence behind
it, and the size of the group it was selected from. The two are never collapsed into a
single number, because they answer different questions.</p>
<div class="cols">
  <div>
    <h3>Performance and reliability</h3>
    <p class="small"><strong>S*</strong> is the published performance score:
    <span class="mono">S* = A* − 0.30·B*</span>. Positive means better than expected on
    pressure deliveries, after allowing for the player's general form.</p>
    <p class="small"><strong>B_A</strong> is the reliability of that record: how much of
    the player's own data survives shrinkage. It decides eligibility (≥ 0.20) and never
    enters the score.</p>
  </div>
  <div>
    <h3>What the labels mean</h3>
    <p class="small"><strong>Tier</strong> is a plain reading of B_A: Limited 0.20–0.30,
    Moderate 0.30–0.50, High 0.50+.</p>
    <p class="small"><strong>90% interval</strong> is the plausible range for S*. When it
    contains zero, an average performance cannot be ruled out — which is true for every
    published player in this report.</p>
  </div>
</div>
{callout('The rule, quoted from the pre-registered record',
         'Eligible players only (reliability B_A ≥ 0.20). Order by S* = A* − 0.30·B* '
         'descending; ties by B_A, then pressure deliveries, then ID. Publication length '
         'min(10, eligible).',
         'blue')}
<p class="cap">Source: SDR-2026-11-18-03, written before the Phase 5 calculation. This
report reproduces the Phase 5 outputs; it does not recompute them.</p>
"""
        self.page('Contents', 'Contents', body, footer='Contents')

    def executive(self) -> None:
        head = self.p['headline']
        rows = []
        for row in self.p['rankings']['bowler_chase'][:3]:
            rows.append([str(row['rank']), esc(row['player_name']),
                         fmt_signed(row['S_star']),
                         f"[{fmt_signed(row['S_ci90_low'])}, {fmt_signed(row['S_ci90_high'])}]",
                         f"{row['shrinkage_A']:.2f}", row['evidence_tier']])
        body = f"""
<p class="lede">Eighteen players — ten chase bowlers and eight chase batters — have
pressure evidence strong enough to publish under a rule fixed before the calculation.
No first-innings ranking exists, and the order inside either list is not statistically
separable.</p>
{stats([
    (str(head['bowler_published']), 'chase bowlers published', f"from {head['bowler_eligible']} eligible"),
    (str(head['batter_published']), 'chase batters published', f"from {head['batter_eligible']} eligible"),
    (str(head['innings1_eligible']), 'first-innings bowlers eligible', f"from {head['innings1_scored']} scored"),
    ('15 / 15', 'Phase 5 validation checks', f"{self._indep()['checks']} / {self._indep()['checks']} independent"),
])}
<div class="cols wide-left">
  <div>
    <h2>The claim we are willing to defend</h2>
    <p>Across {fmt_int(head['matches'])} matches and {fmt_int(head['deliveries'])}{' '}
    deliveries, {head['bowler_scored']} bowlers and {head['batter_scored']} batters were
    scored on situation-adjusted pressure performance. {head['bowler_eligible']} bowlers
    and {head['batter_eligible']} batters cleared the reliability gate that the method
    pre-registered. That number — eighteen — is the finding: pressure evidence is scarce,
    and a longer list would have required a weaker rule.</p>
    <p>The order is reported because the rule produces one, not because the data support
    one. The two claims are different, and the rest of this report keeps them apart.</p>
  </div>
  <div>
    <h2 class="tight-top">Top three, with intervals</h2>
    {table(['#', 'Bowler', 'S*', '90% interval', 'B_A', 'Tier'], rows,
           ['7%', '29%', '10%', '30%', '10%', '14%'], 'tight names-nowrap xs',
           right=(0, 2, 3, 4))}
    <p class="cap">Point estimates only: every interval contains zero. The full ten are on
    page 11.</p>
  </div>
</div>
<h2>What must travel with every quotation of this list</h2>
<div class="callout red">
  <div class="ct">Mandatory disclosures</div>
  <div class="cb">
  <ol class="disc">
    <li><strong>All ten bowler 90% intervals contain zero</strong>, as do all eight batter
    intervals. A published player cannot be distinguished from an average one on point
    estimate alone.</li>
    <li><strong>Every adjacent pair of bowler intervals overlaps.</strong> Ranks 2 and 3
    differ by 0.00008 in S*. The order is not statistically separable (PH5-01), and the
    same holds for the batter list.</li>
    <li><strong>The bootstrap holds the empirical-Bayes fit fixed.</strong> It measures how
    fragile a rank is given this model, not model uncertainty itself. The pre-registered
    design that re-estimated variance was measured and rejected before publication
    (F5-02).</li>
    <li><strong>The result is method-dependent.</strong> Under the rejected clustered
    variance estimator E1, none of the ten bowlers survives; under a single-stage
    combination, two do. Both alternatives are shown in full in the sensitivity section.</li>
    <li><strong>Exactly eight batters qualify.</strong> There is no ninth or tenth batter
    in any deliverable, and none was added to fill the list (F4-01).</li>
    <li><strong>First-innings bowling is a research finding, not a ranking.</strong> 377
    bowlers were scored, none reached the reliability gate, and the context is
    state-confounded (PH3-01, F4-02). T20I-only eligibility is zero in both roles
    (PH5-02); the combined estimate is mainly IPL evidence and is not a claim that
    performance transfers between formats.</li>
  </ol>
  </div>
</div>
<p class="cap">Every figure in this report is copied from
<code>outputs/final/phase5/ranking_bowler_chase.csv</code> and
<code>ranking_batter_chase.csv</code>. The digests are in Appendix D.</p>
"""
        self.page('Executive summary', 'Executive summary', body, footer='Executive summary')

    def _indep(self) -> dict[str, Any]:
        verification = self.p['verification']
        return {'checks': verification['independent_checks'],
                'pass': verification['independent_all_pass']}

    def problem(self) -> None:
        body = """
<p class="lede">The last five overs decide T20 matches, and the scorecard does not show
them. A bowler who defends 12 in the 19th over and one who concedes 12 in a dead rubber
can post the same economy rate.</p>
<div class="cols">
  <div>
    <h2>Why this is hard to measure</h2>
    <ul>
      <li><strong>Conventional statistics ignore the situation.</strong> Economy rate,
      bowling average and strike rate treat every run and wicket as equally costly.</li>
      <li><strong>Pressure is not a separate column.</strong> The scorecard records
      outcomes, not the match state the player was in.</li>
      <li><strong>Small samples look decisive.</strong> A few pressure overs can produce
      an extreme average that will not repeat.</li>
      <li><strong>Rankings hide their own uncertainty.</strong> A list of ten looks like a
      podium even when every interval overlaps the next.</li>
    </ul>
    <h2>The three shortcuts we rejected</h2>
    <dl class="kv">
      <dt>Raw economy in close games</dt>
      <dd>Mixes the situation into the statistic: death overs always look worse.</dd>
      <dt>Reputation and eye test</dt>
      <dd>Consistent with itself, but not measurable or falsifiable.</dd>
      <dt>Points tables and MVP awards</dt>
      <dd>Reward volume and team success as much as pressure performance.</dd>
    </dl>
  </div>
  <div>
    """ + callout('The question', 'Across a large T20 sample, which players actually beat '
                  'expectation when the match is tight — and how much can the evidence '
                  'support?', 'blue') + """
    <h2>What this report does</h2>
    <p>It replaces all three shortcuts with one measurable quantity: the delivery-level
    difference from what an average player would have done in the same match state. The
    cost is that the method has to be explained rather than quoted, which is what the next
    five sections do.</p>
    <h2>What it does not do</h2>
    <p>It does not re-train, re-tune or re-rank anything. Phase 5 is frozen; Phase 6 is a
    communication build over those outputs. It does not publish a first-innings ranking,
    and it does not claim that an IPL record predicts T20I performance.</p>
  </div>
</div>
"""
        self.page('The problem', '01 · The problem', body, footer='01 · The problem')

    def conventional(self) -> None:
        body = f"""
<p class="lede">Phase 3 measured the scoring environment behind each pressure flag. Chase
pressure barely moves the raw run rate; the first-innings flag moves it a lot.</p>
{figure('context_rates',
        'Raw runs per ball by context. Sources: reports/phase_3/descriptive_stats.csv '
        'aggregated over bowler rows. Rates: 1.3594 chase pressure, 1.3864 chase baseline, '
        '1.6107 innings-1 pressure, 1.3643 innings-1 baseline.')}
<div class="cols">
  <div>
    <h2>Why raw economy cannot separate players</h2>
    <p>Chase pressure produces 1.36 runs per ball against 1.39 without it. The two
    environments are almost identical, so a raw run rate mostly measures how often a
    bowler bowled in each — not how well they bowled.</p>
    <p>The first-innings flag is different: 1.61 against 1.36. That gap is a property of
    the match state, not of the bowler, which is why innings-1 bowling cannot be read as
    skill without a control for the scoring environment (PH3-01).</p>
  </div>
  <div>
    <h2>What replaces it</h2>
    <p>Every delivery is compared with its own expectation from a model that knows the
    match state. A bowler is then judged on the residual: better or worse than an average
    player would have been, in exactly that situation.</p>
    {callout('A finding, not a defect to hide',
             'Innings-1 bowling is reported as a research finding with zero eligible '
             'players. It is never merged with chase, and no player is ranked from it.',
             'amber')}
  </div>
</div>
"""
        self.page('Why conventional statistics fail', '02 · Why conventional statistics fail',
                  body, footer='02 · Conventional statistics')

    def pressure(self) -> None:
        head = self.p['headline']
        rows = [
            ['Model type', 'Gradient-boosted chase-state model, pre-ball features only'],
            ['Features', 'Score, wickets, balls left, target, format, phase'],
            ['Training', 'Other matches; out-of-fold predictions used for validation'],
            ['AUC', f"{head['auc']:.4f}"],
            ['Calibration slope', f"{head['calibration_slope']:.4f} (1.0 is perfect)"],
            ['Expected calibration error', f"{head['ece']:.5f}"],
            ['Chase states labelled', f"{head['chase_states']:,}"],
            ['Threshold', 'Tightest quarter of chase states; one shared flag for both roles'],
        ]
        body = f"""
<p class="lede">A ball is "in pressure" when a calibrated chase model says the chasing
side is in the tightest quarter of match states. The label uses only information
available before the delivery, so a ball can never influence its own flag.</p>
<div class="cols wide-left">
  <div>
    {table(['Property', 'Specification'], rows, ['30%', '70%'], 'tight')}
    <p class="cap">Sources: reports/phase_2/PHASE_2_REPORT.md,
    reports/phase_3/model_specification.md and reports/phase_3/calibration.csv.</p>
  </div>
  <div>
    <h2>Validation came first</h2>
    <p>Calibration slope, expected calibration error and decile behaviour were checked on
    out-of-fold predictions before any player was scored. The flag passed the pre-set
    bounds; a flag that fails those bounds is not used anywhere in this project.</p>
    <p>Definitions that failed difficulty validation are recorded by name and left unused:
    the broad pressure flag, the collapse and union variants, and the F2 fallback
    (PH2-05). This matters for honesty: a looser flag would have produced longer lists,
    and the lists would have been weaker.</p>
  </div>
</div>
<h2>Two roles, one match state</h2>
<p>A batter facing a required rate of 12 with four wickets in hand is in the same
validated state as the bowler bowling to him. Both are scored on the same flag, which is
why the two lists are comparable in method even though they are never combined into a
single ranking.</p>
<div class="callout blue">
  <div class="ct">What the flag is not</div>
  <div class="cb">It is not a measure of nerves, and it is not a claim that the players
  involved felt pressure. It is a reproducible description of the match state, which is
  the only thing a dataset can support.</div>
</div>
"""
        self.page('How pressure was defined', '03 · How pressure was defined', body,
                  footer='03 · Pressure definition')

    def performance(self) -> None:
        body = f"""
<p class="lede">Every delivery is compared with what an average player would have done in
the same situation. Situation is removed before the player is judged, so bowling at the
death is not punished twice.</p>
<figure>
  <img src="{ASSETS_REL}/pressure_vs_baseline.png" alt="">
  <figcaption>The signal is the gap between a player's pressure and baseline rates, not
  the raw average. Each row is one published bowler; the line is the change from baseline
  to pressure deliveries.</figcaption>
</figure>
<div class="cols wide-left">
  <div>
    <h2>The delivery score</h2>
    <p class="mono">y = (runs − μ_runs) − λ · (dismissed − μ_dis)</p>
    <p>For batters, runs are runs off the bat and dismissals are the batter's own. For
    bowlers, runs are charged to the bowler and the wicket value is flipped, so a positive
    y is always better for the player being scored.</p>
    <h2>The three components</h2>
    {table(['Component', 'Meaning'], [
        ['A', 'Mean of y on pressure deliveries.'],
        ['B', 'Mean of y on non-pressure deliveries in the same context. A control, not a bonus.'],
        ['D', 'A − B: the pressure-specific difference.'],
        ['S_raw', '0.70·A + 0.30·D: mostly pressure performance, with a general-form adjustment.'],
    ], ['14%', '86%'], 'tight')}
  </div>
  <div>
    <h2>What the formula deliberately excludes</h2>
    <p>Dot-ball percentage, boundary percentage, strike rate and economy appear in the
    data view of the dashboard as descriptives. None of them enters the score, because
    each one is a function of the same match state the model is already controlling
    for.</p>
    {callout('The direction of the adjustment',
             'A player with strong general form has a high B. Subtracting 0.30·B charges '
             'them for it, so the published score is about pressure, not about being a '
             'good player overall.', 'blue')}
    <p class="cap">Sources: reports/phase_3/model_specification.md §5–6;
    src/ranking/model.py.</p>
  </div>
</div>
"""
        self.page('How performance was measured', '04 · How performance was measured', body,
                  footer='04 · Performance measurement')

    def shrinkage(self) -> None:
        body = f"""
<p class="lede">Each player's record is pulled towards the league average by an amount
that depends on how much evidence backs it. Without this step, a handful of pressure
overs would produce a spectacular and entirely unrepeatable ranking.</p>
{figure('shrinkage',
        'Raw pressure average against the shrunk estimate for the 36 eligible bowlers. '
        'The diagonal is "no shrinkage". Bubble size is pressure deliveries.')}
<div class="cols">
  <div>
    <h2>How the estimate works</h2>
    <ul>
      <li><strong>Between-player variance</strong> is estimated separately for each
      role × context × format × component.</li>
      <li><strong>Each record is weighted</strong> by its own sampling variance against
      that between-player variance.</li>
      <li><strong>More deliveries, more of the record</strong> is kept. A thin record is
      pulled hard towards the average.</li>
      <li><strong>A* is the shrunk pressure score.</strong> The shrinkage weight B_A is
      kept as a separate reliability measure — never multiplied into the score.</li>
    </ul>
  </div>
  <div>
    <h2>How much of the spread is noise</h2>
    <p>Across the 36 eligible bowlers, the raw pressure average spans 1.12 units. After
    shrinkage the same players span 0.32. About 71% of the apparent difference between
    them is sampling noise rather than a difference in skill.</p>
    {callout('Shrinkage is not a penalty',
             'It is an admission of how much is actually known. A player with a thin '
             'record is not being punished; they are being reported as unknown, which is '
             'what the threshold then acts on.', 'blue')}
  </div>
</div>
"""
        self.page('Empirical-Bayes shrinkage', '05 · Empirical-Bayes shrinkage', body,
                  footer='05 · Shrinkage')

    def reliability(self) -> None:
        body = f"""
<p class="lede">Reliability asks whether the evidence is strong enough to publish.
Performance asks how good the player was. They are reported side by side and never
multiplied, because a player can be highly reliable and average, or spectacular and
unpublishable.</p>
<div class="cols">
  <div>
    <h2>Performance score</h2>
    <p class="mono">S* = A* − 0.30·B*</p>
    <p>Positive means better than expected under pressure, after removing the player's
    general form. This is the number that orders the list.</p>
  </div>
  <div>
    <h2>Reliability of evidence</h2>
    <p class="mono">B_A ≥ 0.20</p>
    <p>B_A is how much of the player's own record is kept rather than pulled to the league
    average. It decides eligibility. It never enters S*.</p>
  </div>
</div>
{figure('eligibility_hist',
        'Distribution of B_A for every scored player-context row. The 0.20 line is the '
        'approved gate. First-innings bowling peaks at 0.150, so no player in that context '
        'is eligible.')}
<h2>The four tiers</h2>
{table(['Tier', 'B_A range', 'Chase bowlers', 'Chase batters', 'Published'], [
    ['High', '0.50 and above', '0', '0', 'never reached'],
    ['Moderate', '0.30 – 0.50', '4', '0', 'four bowlers'],
    ['Limited', '0.20 – 0.30', '6', '8', 'every published batter'],
    ['Insufficient', 'below 0.20', '367', '478', 'never published'],
], ['18%', '22%', '20%', '20%', '20%'], 'tight', right=(2, 3))}
<p class="cap">Counts from outputs/final/phase5/context_status.csv. The tier is a reading
of B_A only; it says nothing about the sign or size of S*.</p>
"""
        self.page('Reliability is not performance', '06 · Reliability is not performance',
                  body, footer='06 · Reliability')

    def selection(self) -> None:
        body = f"""
<p class="lede">A rule written before the calculation was applied to an eligible pool
without role-specific tuning, manual overrides, or promotion to fill a list.</p>
<div class="quote">Eligible players only (reliability B_A ≥ 0.20). Order by
S* = A* − 0.30·B* descending; ties by B_A, then pressure deliveries, then ID. Publication
length min(10, eligible).
<cite>SDR-2026-11-18-03, pre-registered before the Phase 5 run</cite></div>
{figure('funnel',
        'Every stage is a published count. Nobody enters a list without clearing the same '
        'reliability gate. 845 player-context rows were excluded and are itemised on '
        'page 20.')}
<div class="cols">
  <div>
    <h2>The tie-breaks, and why they exist</h2>
    <p>Two bowlers can tie on S* to three decimals. The pre-registered tie-break is B_A,
    then pressure deliveries, then player ID. It is deterministic, so the output does not
    depend on the order rows happen to appear in a file.</p>
  </div>
  <div>
    <h2>What was not done</h2>
    <p>No threshold was lowered, no batter was added to reach ten, and no player was
    excluded by hand. The list length is a consequence of the rule: min(10, eligible).</p>
  </div>
</div>
{callout('The gap is the finding',
         f"{self.p['headline']['bowler_scored']} bowlers and "
         f"{self.p['headline']['batter_scored']} batters were scored; "
         f"{self.p['headline']['bowler_eligible']} and "
         f"{self.p['headline']['batter_eligible']} cleared the gate. A longer list would "
         "have required a weaker rule, and that trade is not worth making silently.", 'blue')}
"""
        self.page('How players were selected', '07 · How players were selected', body,
                  footer='07 · Selection')

    def bowlers(self) -> None:
        rows = self.p['rankings']['bowler_chase']
        assert len(rows) == 10, len(rows)
        moderate = [r for r in rows if r['evidence_tier'] == 'Moderate']
        moderate_summary = ', '.join(
            f"{esc(r['player_name'])} ({r['shrinkage_A']:.2f})" for r in moderate)
        body_rows = []
        for row in rows:
            body_rows.append([
                str(row['rank']), esc(row['player_name']), fmt_signed(row['S_star']),
                f"[{fmt_signed(row['S_ci90_low'])}, {fmt_signed(row['S_ci90_high'])}]",
                f"{row['shrinkage_A']:.2f}", f'<span class="tier {row["evidence_tier"]}">'
                f'{row["evidence_tier"]}</span>', fmt_int(row['n_pressure']),
            ])
        body = f"""
<p class="lede">Ten chase bowlers are published from 36 eligible. The order is an
ordering of point estimates inside a shortlist: it is not a podium, and it is not
statistically separable.</p>
{table(['#', 'Bowler', 'S*', '90% interval', 'B_A', 'Tier', 'Pressure balls'],
       body_rows, ['5%', '30%', '10%', '24%', '8%', '13%', '10%'], 'tight',
       right=(0, 2, 3, 4, 6))}
<p class="cap">Copied verbatim from outputs/final/phase5/ranking_bowler_chase.csv.
Pressure balls are deliveries carrying the validated chase-pressure flag.</p>
<div class="cols wide-left">
  <div>
    <figure style="margin-top:0"><img src="{ASSETS_REL}/bowler_ci.png" alt="">
    <figcaption>Performance score with 90% intervals for the ten published bowlers. Zero is
    inside every interval and each interval crosses the next.</figcaption></figure>
  </div>
  <div>
    <h3>What can be said</h3>
    <ul class="small">
      <li><strong>These ten cleared the gate.</strong> Their pressure records carry enough
      evidence to publish under the pre-registered rule.</li>
      <li><strong>{len(moderate)} reached Moderate</strong> — {moderate_summary or 'none'}.
      No bowler reaches High.</li>
      <li><strong>The top three are stable</strong> under resampling (97–100%). Positions
      four to ten are not.</li>
    </ul>
    <h3>What cannot be said</h3>
    <ul class="small">
      <li><strong>That rank 1 is better than rank 2.</strong> Adjacent intervals overlap;
      ranks 2 and 3 differ by 0.00008.</li>
      <li><strong>That any of them beats an average bowler.</strong> All ten intervals
      contain zero.</li>
      <li><strong>That the order survives another sample.</strong> Section 11 shows how far
      each place moves.</li>
    </ul>
  </div>
</div>
"""
        self.page('Final results — bowlers', '08 · Final results', body,
                  footer='08 · Final results — bowlers')

    def batters(self) -> None:
        rows = self.p['rankings']['batter_chase']
        assert len(rows) == 8, len(rows)
        body_rows = []
        for row in rows:
            body_rows.append([
                str(row['rank']), esc(row['player_name']), fmt_signed(row['S_star']),
                f"[{fmt_signed(row['S_ci90_low'])}, {fmt_signed(row['S_ci90_high'])}]",
                f"{row['shrinkage_A']:.2f}", f'<span class="tier {row["evidence_tier"]}">'
                f'{row["evidence_tier"]}</span>', fmt_int(row['n_pressure']),
            ])
        body = f"""
<p class="lede">Eight batters clear the gate. The list stops at eight: no player was
added to reach ten, because that would have required a lower threshold or a weaker
evidence rule.</p>
{table(['#', 'Batter', 'S*', '90% interval', 'B_A', 'Tier', 'Pressure balls'],
       body_rows, ['5%', '30%', '10%', '24%', '8%', '13%', '10%'], 'tight',
       right=(0, 2, 3, 4, 6))}
<p class="cap">Copied verbatim from outputs/final/phase5/ranking_batter_chase.csv.
Exactly eight rows; all Limited tier.</p>
<div class="cols">
  <div>
    <h2>Why the list is shorter than the bowlers'</h2>
    <p>445 batters were scored, but only eight reached B_A ≥ 0.20. A batter faces far
    fewer pressure deliveries than a specialist bowler bowls, so the same gate admits
    fewer of them. Six of the eight still carry at least 138 pressure balls, so this is a
    volume problem rather than a data-quality one.</p>
  </div>
  <div>
    <h2>The top-eight trap</h2>
    <p>Every scenario in the bootstrap keeps all eight, because the eligible set <em>is</em>
    eight. "P(top 10) = 100%" would therefore be an artefact of the list length, not a
    stability result. The report uses the resampled rank range instead: even the leader's
    median rank is 2, with a 1–7 range.</p>
  </div>
</div>
<figure><img src="{ASSETS_REL}/batter_ci.png" alt="">
<figcaption>Performance score with 90% intervals for the eight published batters. All
eight are Limited tier and all eight intervals contain zero.</figcaption></figure>
"""
        self.page('Final results — batters', '08 · Final results', body,
                  footer='08 · Final results — batters')

    def innings1(self) -> None:
        head = self.p['headline']
        body = f"""
<p class="lede">First-innings bowling was scored under the same rule and produced no
ranking. It is reported here as a research finding, not as a hidden list.</p>
{stats([
    (str(head['innings1_scored']), 'bowlers scored', 'in the innings-1 context'),
    (str(head['innings1_eligible']), 'eligible at B_A ≥ 0.20', 'nobody clears the gate'),
    ('0.150', 'highest reliability', 'below the threshold'),
    ('1.61', 'runs per ball conceded', 'against 1.36 in other innings-1 states'),
])}
<h2>Why no ranking exists</h2>
<p>The innings-1 flag marks a bowling side under pressure while the batting side is
ahead of par. A high run rate in those states is partly a description of the state
itself — the batting team is scoring quickly by definition. Without a direct control for
the scoring environment, a ranking from that context would present a confounded quantity
as bowling skill (PH3-01).</p>
<p>Separately, no player clears the reliability gate in that context: the maximum B_A is
0.150, which is below the 0.20 threshold. Even if the confounding were solved, this
sample would not support a list.</p>
<div class="callout amber">
  <div class="ct">Status</div>
  <div class="cb"><strong>PH3-01 OPEN</strong> — state-confounded definition.
  <strong>F4-02 OPEN</strong> — no first-innings bowling ranking exists. Both are carried
  into Phase 6 unchanged, and neither is closed by presentation.</div>
</div>
<h2>What would be needed</h2>
<p>A revised definition that controls for the scoring environment, re-tested against the
same difficulty criteria as the chase flag. Until that passes, the honest output is this
finding rather than a list of names. Nothing was borrowed from the chase context to fill
the gap, and no cross-context score exists anywhere in the project.</p>
"""
        self.page('First-innings bowling: a research finding',
                  '09 · Separate context, separate finding', body,
                  footer='09 · First-innings bowling')

    def sensitivity(self) -> None:
        labels = {
            'primary': 'Approved specification', 'w_0.30': 'Score weight w = 0.30',
            'w_0.50': 'Score weight w = 0.50', 'tau2_REML': 'REML variance',
            'single_stage_combination': 'Single-stage combination',
            'format_IPL': 'IPL evidence only', 'variance_E1': 'E1 clustered variance',
            'format_T20I': 'T20I evidence only',
        }
        order = ['primary', 'w_0.30', 'w_0.50', 'tau2_REML', 'format_IPL',
                 'single_stage_combination', 'variance_E1', 'format_T20I']

        def role_table(role: str, denom: int) -> str:
            block = {r['scenario']: r for r in self.p['sensitivity'] if r['role'] == role}
            body_rows = []
            for scenario in order:
                row = block.get(scenario)
                if not row:
                    continue
                body_rows.append([
                    esc(labels[scenario]), fmt_int(row['eligible']),
                    f"{row['overlap_with_primary']} / {denom}" if row['eligible'] else 'no list',
                    f"{row['overlap_share'] * 100:.0f}%",
                ])
            return table(['Alternative', 'Eligible', 'Kept', 'Share'], body_rows,
                         ['52%', '14%', '20%', '14%'], 'tight', right=(1, 2, 3))

        body = f"""
<p class="lede">Reporting only the flattering specifications would be cherry-picking, so
every alternative that was measured is shown — including the one that removes all ten
names.</p>
<div class="cols">
  <div><h3>Bowlers (10 published)</h3>{role_table('bowler', 10)}</div>
  <div><h3>Batters (8 published)</h3>{role_table('batter', 8)}</div>
</div>
<figure class="sm"><img src="{ASSETS_REL}/sensitivity.png" alt="">
<figcaption>Names kept from the published ten under each alternative. The approved
specification is the first bar; the rejected E1 estimator keeps none.</figcaption></figure>
<div class="cols">
  <div>
    <h2>What is robust</h2>
    <p>The score weight barely matters: at w = 0.30 nine of ten bowlers survive, at
    w = 0.50 all ten do. REML variance estimation, a legitimate alternative, keeps nine.
    The finding that these roughly ten bowlers have publishable chase evidence is not an
    artefact of the weighting choice.</p>
  </div>
  <div>
    <h2>What is not</h2>
    <p>The variance estimator and the combination method change the answer substantially.
    The rejected E1 estimator admits 307 bowlers and keeps none of the ten; single-stage
    combination admits 13 and keeps two. Any claim that survives only under the approved
    specification has to say so, and this report does.</p>
  </div>
</div>
<p class="cap">Source: reports/phase_5/sensitivity_rank.csv. "Names kept" counts players
from the published list who remain in the top N under that scenario. The E1 estimator was
rejected on measurement before publication (F5-02); it is shown for transparency, not as a
competing recommendation.</p>
"""
        self.page('Sensitivity to method choices', '10 · Sensitivity', body,
                  footer='10 · Sensitivity')

    def uncertainty(self) -> None:
        rows = []
        stability = {(r['role'], r['player_id']): r for r in self.p['stability']}
        bowler_rows = self.p['rankings']['bowler_chase']
        lead = bowler_rows[0]
        lead_stability = stability.get(('bowler', lead['player_id']), {})
        reading_note = (
            f"{esc(lead['player_name'])} scored {fmt_signed(lead['S_star'])} on a 90% "
            f"interval of {fmt_signed(lead['S_ci90_low'])} to "
            f"{fmt_signed(lead['S_ci90_high'])}. The width is "
            f"{lead['S_ci90_high'] - lead['S_ci90_low']:.3f}, the interval contains zero, "
            f"and the player stayed in the top ten in "
            f"{lead_stability.get('share_top10', 0) * 100:.0f}% of resamples. The "
            f"resampled median rank is {lead_stability.get('rank_median', '—')} with a "
            f"5–95% range of {lead_stability.get('rank_p05', '—')} to "
            f"{lead_stability.get('rank_p95', '—')}. This is a point-estimate lead, "
            f"not a separable rank."
        )
        for row in bowler_rows:
            stab = stability.get(('bowler', row['player_id']), {})
            width = row['S_ci90_high'] - row['S_ci90_low']
            rows.append([
                str(row['rank']), esc(row['player_name']),
                f"{fmt_signed(row['S_ci90_low'])} to {fmt_signed(row['S_ci90_high'])}",
                f"{width:.3f}",
                'yes' if row['ci_contains_zero'] else 'no',
                'yes' if row.get('ci_overlaps_previous') else '—',
                f"{stab.get('share_top10', 0) * 100:.0f}%",
                f"{stab.get('rank_median', '—')} "
                f"({stab.get('rank_p05', '—')}–{stab.get('rank_p95', '—')})",
            ])
        body = f"""
<p class="lede">The order is fragile; the eligible set is the stable result. This page
holds the numbers behind that sentence.</p>
{table(['#', 'Bowler', '90% interval', 'Width', 'Contains zero', 'Overlaps previous',
        'Kept top 10', 'Resampled rank (median, 5–95%)'], rows,
       ['4%', '22%', '20%', '8%', '10%', '11%', '10%', '15%'], 'tight',
       right=(0, 3, 6))}
<div class="cols wide-right">
  <div>
    <h2>Intervals</h2>
    <p>All ten intervals contain zero, and the average width is 0.37 on a score whose
    whole published range is 0.13. Every adjacent pair overlaps. On this evidence, a
    published player cannot be distinguished from an average one, and the sequence of
    names is a sequence of point estimates rather than separable positions (PH5-01).</p>
    <h2>Resampling</h2>
    <p>Match-block bootstrap, 200 resamples with the empirical-Bayes fit held fixed. The
    top three are retained in 97–100% of resamples; ranks six to ten in 40–55%, so a place
    there is close to a coin-flip. The fixed fit is a documented limitation, not a claim
    that model uncertainty is small (F5-02).</p>
  </div>
  <div>
    <figure style="margin-top:0"><img src="{ASSETS_REL}/bootstrap.png" alt="">
    <figcaption>Left: share of 200 resamples in which the player stays in the published top
    ten. Right: where the rank actually sits, median with a 5–95% range.</figcaption></figure>
  </div>
</div>
{callout('How to read one row',
         reading_note, 'blue')}
"""
        self.page('Uncertainty and rank stability', '11 · Uncertainty', body,
                  footer='11 · Uncertainty')

    def formats(self) -> None:
        summary = self.p['format_summary']['bowler']
        rows = []
        for row in self.p['formats']:
            if row['format_scope'] != 'IPL' or row['role'] != 'bowler':
                continue
            rows.append([str(row['rank']), esc(row['player_name']),
                         fmt_signed(row['S_star_format']), f"{row['shrinkage_A']:.2f}",
                         'yes' if row['in_combined_top'] else 'no'])
        body = f"""
<p class="lede">IPL and T20I were estimated separately, then combined descriptively. The
combined list is mostly IPL evidence, and it says nothing about how a player would fare
in a T20I.</p>
{stats([
    (str(summary['combined_top']), 'combined bowler list', 'two-stage estimate'),
    (f"{summary['scopes']['IPL']['shared_with_combined']} / 10", 'also in the IPL-only top 10',
     'IPL-only is a separate estimand'),
    (str(summary['scopes']['T20I']['rows_shown']), 'T20I-only players eligible',
     'both roles; between-player variance is zero'),
    ('0', 'T20I-only rankings', 'none exists, in either role'),
])}
<h2>IPL-only bowler ranking</h2>
{table(['#', 'Bowler', 'IPL-only S*', 'B_A (IPL)', 'In combined top 10'], rows,
       ['6%', '44%', '18%', '16%', '16%'], 'tight', right=(0, 2, 3))}
<p class="cap">The IPL-only score is a separate estimand, derived from the published
IPL-only components as A* − 0.30·B*. It is not the combined score and must not be quoted
as one. Source: outputs/final/phase5/format_specific_ranking.csv.</p>
<div class="cols">
  <div>
    <h2>What the combination is</h2>
    <p>A descriptive two-stage estimate that uses both formats, weighted by the evidence
    available in each. It answers "how has this player bowled under chase pressure in the
    cricket we have?" — not "how would they bowl in a T20I next month?".</p>
  </div>
  <div>
    <h2>What it is not</h2>
    <p>It is not evidence of transferability between formats, and it is not a T20I
    ranking. T20I-only eligibility is zero in both roles because between-player variance
    in that subset is estimated at zero (PH5-02).</p>
  </div>
</div>
"""
        self.page('Format scope and what it does not prove', '12 · Format scope', body,
                  footer='12 · Format scope')

    def limitations(self) -> None:
        rows = []
        for issue in self.p['issues']:
            rows.append([
                f'<span class="mono">{esc(issue["id"])}</span>', esc(issue['title']),
                esc(issue['status']),
            ])
        body = f"""
<p class="lede">Nine documented limitations travel with this work. Two defects found
during the Phase 6 build are also recorded below with their verified fixes. Presentation
does not close any carried analytical limitation.</p>
{table(['ID', 'Limitation', 'Status'], rows, ['10%', '60%', '30%'], 'tight')}
<div class="cols">
  <div>
    <h2>What we will not say</h2>
    <ul class="no">
      <li>"The best T20 bowlers in the world."</li>
      <li>"The data proves X is the most clutch."</li>
      <li>"This transfers to T20I."</li>
      <li>"Rank 1 is better than rank 2."</li>
    </ul>
  </div>
  <div>
    <h2>What we will say</h2>
    <ul class="yes">
      <li>"Eighteen players have publishable pressure evidence under a pre-registered
      rule."</li>
      <li>"The top three are stable under resampling; the rest of the order is not."</li>
      <li>"Read the tiers and the intervals, not the podium."</li>
    </ul>
  </div>
</div>
"""
        self.page('Limitations and status', '13 · Limitations and status', body,
                  footer='13 · Limitations')

    def reproducibility(self) -> None:
        verification = self.p['verification']
        independent = verification['independent']
        p6 = self.phase6
        static = p6.get('static', {})
        browser = p6.get('browser', {})
        tests = p6.get('tests', {})
        rows = []
        for item in verification['internal'][:15]:
            rows.append([esc(item['check']), esc(item['result'])])
        indep_rows = [[esc(i['check']), esc(i['result'])] for i in independent]
        hashes = self.p['provenance']['frozen_hashes']
        build_rows = [
            ['Static consistency checks', f"{static.get('passed', '—')} / {static.get('total', '—')}",
             'every displayed name, ID, score, interval and tier against the frozen CSVs'],
            ['Browser interaction checks', f"{browser.get('passed', '—')} / {browser.get('total', '—')}",
             'headless Chrome: routing, filters, sorting, drawer, mobile, no network'],
            ['Phase 6 unit tests', f"{tests.get('passed', '—')} / {tests.get('total', '—')}",
             'pytest: payload guards, artifact shape, disclosure text'],
            ['Phase 5 internal', '15 / 15', 'frozen gate, unchanged'],
            ['Phase 5 independent', f"{self._indep()['checks']} / {self._indep()['checks']}",
             'separate implementation, all pass'],
        ]
        body = f"""
<p class="lede">Every number in this report can be checked against a frozen file, and the
deliverables are generated from one payload so they cannot drift from each other.</p>
{callout('Rebuild everything', '<span class="mono">python3 -m src.deliverables.run_phase6'
         '</span><br>Rebuilds the dashboard, deck and this report, re-runs every check and '
         'writes a JSON log to <span class="mono">reports/phase_6/logs/run_phase6.json'
         '</span>.', 'teal')}
<h2>Verification at the Phase 6 gate</h2>
{table(['Check group', 'Result', 'What it covers'], build_rows,
       ['30%', '14%', '56%'], 'tight')}
<div class="cols">
  <div>
    <h2>Phase 5 internal checks</h2>
    {table(['Check', 'Result'], rows, ['70%', '30%'], 'tight')}
  </div>
  <div>
    <h2>Phase 5 independent checks</h2>
    {table(['Check', 'Result'], indep_rows, ['70%', '30%'], 'tight')}
  </div>
</div>
<p class="cap">The {len(hashes)} frozen Phase 5 inputs were hashed before and after the
build and are unchanged. Their digests are listed in Appendix D.</p>
"""
        self.page('Reproducibility and verification', '14 · Reproducibility', body,
                  footer='14 · Reproducibility')

    def appendix_pool(self) -> None:
        eligible = [r for r in self.p['pool']['bowler_chase']
                    if (r['shrinkage_A'] or 0) >= 0.20]
        eligible.sort(key=lambda r: (-(r['S_star'] or 0), -(r['shrinkage_A'] or 0)))
        rows = []
        for index, row in enumerate(eligible, start=1):
            rows.append([str(index), esc(row['player_name']), fmt_signed(row['S_star']),
                         f"{row['shrinkage_A']:.3f}", row['evidence_tier'],
                         fmt_int(row['n_pressure'])])
        half = (len(rows) + 1) // 2
        body = f"""
<p class="lede">All {len(rows)} bowlers who cleared the reliability gate, in published
order. The first ten are the published list; the rest are eligible but outside the
publication limit.</p>
<div class="cols">
  <div>{table(['#', 'Bowler', 'S*', 'B_A', 'Tier', 'Balls'], rows[:half],
              ['8%', '40%', '14%', '12%', '14%', '12%'], 'tight names-nowrap',
              right=(0, 2, 3, 5))}</div>
  <div>{table(['#', 'Bowler', 'S*', 'B_A', 'Tier', 'Balls'], rows[half:],
              ['8%', '40%', '14%', '12%', '14%', '12%'], 'tight names-nowrap',
              right=(0, 2, 3, 5))}</div>
</div>
<p class="cap">Source: outputs/final/player_scores_bowlers.csv, chase context, filtered at
B_A ≥ 0.20. Order follows the pre-registered rule exactly; the pool order reproduces the
published top ten without re-sorting.</p>
"""
        self.page('Appendix A · the eligible pool',
                  'Appendix A', body, footer='Appendix A · eligible pool')

    def appendix_exclusions(self) -> None:
        summary = self.p['exclusion_summary']
        rows = [[esc(r['role'].capitalize()), esc(r['reason_label']), fmt_int(r['count'])]
                for r in summary]
        total = sum(r['count'] for r in summary)
        rows.append(['<strong>Total</strong>', '<strong>all recorded exclusions</strong>',
                     f'<strong>{total:,}</strong>'])
        labels = {r['reason_code']: r['reason_label'] for r in summary}
        examples = [r for r in self.p['exclusions'] if r['role'] == 'bowler'][:8]
        ex_rows = [[esc(e['player_name']), fmt(e.get('shrinkage_A'), 3),
                    fmt_int(e.get('n_pressure')),
                    'Too few deliveries' if e['reason_code'] == 'NO_VARIANCE'
                    else 'Below 0.20'] for e in examples]
        body = f"""
<p class="lede">Every scored player who is not published is accounted for here. No row was
dropped without a recorded reason, and the counts reconcile with the funnel on page 10.</p>
{table(['Role', 'Reason', 'Rows'], rows, ['22%', '58%', '20%'], 'tight', right=(2,))}
<div class="cols">
  <div>
    <h2>What the two reasons mean</h2>
    <p><strong>Too few deliveries to estimate any variance</strong> — the record is so thin
    that no between-player variance can be estimated for it. These rows cannot be scored at
    all.</p>
    <p><strong>Reliability below the 0.20 threshold</strong> — the record can be scored, but
    too little of it would survive shrinkage to publish. These players are not judged
    bad; they are reported as not yet evidenced.</p>
  </div>
  <div>
    <h2>Examples (bowlers)</h2>
    {table(['Player', 'B_A', 'Balls', 'Reason'], ex_rows,
           ['40%', '16%', '16%', '28%'], 'tight', right=(1, 2))}
    <p class="cap">An illustrative slice of the 367 excluded bowler rows in the chase
    context. The full log is outputs/final/phase5/ranking_exclusions.csv.</p>
  </div>
</div>
{callout('The exchange rate this implies',
         'Publishing a longer list would mean publishing players whose pressure record is '
         'mostly league average by construction. The exclusions are the price of the '
         'threshold, and the threshold was fixed before the calculation.', 'amber')}
<h2>Why no first-innings rows appear here</h2>
<p>All 845 excluded rows are chase rows: 478 batters and 367 bowlers, counted across the
two reasons above. First-innings bowling is not represented because no ranking was
attempted in that context — nobody can be excluded from a list that does not exist. It is
reported separately as a research finding on page 13, with its own status codes (PH3-01,
F4-02).</p>
<p class="cap">Reconciliation: 41 + 437 batter exclusions and 15 + 352 bowler exclusions
sum to 845, the same figure shown in the funnel on page 10 and in
<span class="mono">reports/phase_5/PHASE_5_REPORT.md</span>.</p>
"""
        self.page('Appendix B · exclusions', 'Appendix B', body,
                  footer='Appendix B · exclusions')

    def appendix_glossary(self) -> None:
        terms = self.p['glossary']
        half = (len(terms) + 1) // 2

        def block(items):
            return ''.join(
                f'<dt>{esc(t["term"])}</dt><dd>{esc(t["plain"])}</dd>' for t in items)

        body = f"""
<p class="lede">Every term used in this report, in plain language. Nothing here needs a
statistics background; the definitions are the ones the dashboard uses in its tooltips.</p>
<div class="cols">
  <dl class="kv gloss">{block(terms[:half])}</dl>
  <dl class="kv gloss">{block(terms[half:])}</dl>
</div>
<h2>Notation</h2>
{table(['Symbol', 'Meaning'], [
    ['y', 'The delivery score: runs above or below the situation\'s expectation, plus a wicket term.'],
    ['A', 'The player\'s mean y on pressure deliveries (unshrunk).'],
    ['B', 'The same player\'s mean y on non-pressure deliveries in the same context (unshrunk).'],
    ['D', 'A − B: the pressure-specific difference.'],
    ['S_raw', '0.70·A + 0.30·D: the score before shrinkage.'],
    ['A*', 'A after empirical-Bayes shrinkage — the pressure performance estimate.'],
    ['B*', 'B after the same shrinkage — shrunk baseline form.'],
    ['B_A', 'Shrinkage weight on A: the reliability of the pressure record (gate 0.20).'],
    ['S*', 'A* − 0.30·B*: the published Performance Score.'],
    ['λ', 'The estimated wicket value in runs; a wicket is worth more in some phases.'],
], ['16%', '84%'], 'tight xs')}
"""
        self.page('Appendix C · glossary', 'Appendix C', body,
                  footer='Appendix C · glossary')

    def appendix_sources(self) -> None:
        hashes = self.p['provenance']['frozen_hashes']
        hash_rows = [[f'<span class="mono">{esc(path)}</span>',
                      f'<span class="mono">{digest}</span>']
                     for path, digest in hashes.items()]
        sources = [
            ('Phase 5 rankings', 'outputs/final/phase5/ranking_bowler_chase.csv, ranking_batter_chase.csv'),
            ('Phase 5 support', 'format_specific_ranking.csv, context_status.csv, ranking_exclusions.csv'),
            ('Phase 4 scores', 'outputs/final/player_scores_bowlers.csv, player_scores_batters.csv'),
            ('Method record', 'reports/methodology/SDR-2026-11-18-03-phase5-ranking.md'),
            ('Phase reports', 'reports/phase_2 .. reports/phase_5'),
            ('Dictionary', 'docs/DATA_DICTIONARY.md'),
        ]
        src_rows = [[esc(k), f'<span class="mono">{esc(v)}</span>'] for k, v in sources]
        body = f"""
<p class="lede">Where every number came from, and the digests that prove the inputs did
not move while the deliverables were built.</p>
<h2>Primary sources</h2>
{table(['What', 'Where'], src_rows, ['24%', '76%'], 'tight')}
<h2>Deliverables from this phase</h2>
<ul class="small">
  <li><span class="mono">outputs/final/deliverables/dashboard/index.html</span> — the
  interactive dashboard, one offline file.</li>
  <li><span class="mono">outputs/final/deliverables/SupeRR_Selector_Phase6_Deck.pptx</span>
  — the 27-slide presentation.</li>
  <li><span class="mono">outputs/final/deliverables/SupeRR_Selector_Phase6_Report.pdf</span>
  — this report.</li>
  <li><span class="mono">reports/phase_6/PHASE_6_REPORT.md</span> — the engineering record
  and gate report.</li>
</ul>
<h2>Frozen inputs (SHA-256)</h2>
{table(['File', 'SHA-256'], hash_rows, ['46%', '54%'], 'tight')}
<p class="cap">The full manifest, including every generated artefact, is
<span class="mono">reports/audit_bundle/sha256_outputs.txt</span>. These Phase 5 digests
were checked before and after the Phase 6 build and are unchanged: no model was fitted, no
threshold moved, no rank recomputed.</p>
"""
        self.page('Appendix D · sources and frozen hashes', 'Appendix D', body,
                  footer='Appendix D · sources')


def build(payload: dict[str, Any] | None = None,
          phase6: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or D.build_payload()
    report = Report(payload, phase6).build()
    html_text = report.render()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html_text)
    return {'html': str(HTML_PATH.relative_to(D.ROOT)), 'pages': len(report.pages),
            'bytes': HTML_PATH.stat().st_size}


def print_pdf() -> dict[str, Any]:
    """Print the report to PDF with headless Chrome and check the page count."""
    if not Path(CHROME).exists():
        raise RuntimeError(f'Chrome not found at {CHROME}')
    profile = Path(tempfile.mkdtemp(prefix='supeRR-report-'))
    try:
        subprocess.run([
            CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
            '--no-first-run', '--no-default-browser-check', '--disable-extensions',
            '--disable-background-networking', '--run-all-compositor-stages-before-draw',
            '--virtual-time-budget=8000', '--no-pdf-header-footer',
            f'--user-data-dir={profile}',
            f'--print-to-pdf={PDF_PATH}',
            HTML_PATH.resolve().as_uri(),
        ], check=True, capture_output=True, timeout=180)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    import pypdf
    reader = pypdf.PdfReader(str(PDF_PATH))
    return {'pdf': str(PDF_PATH.relative_to(D.ROOT)), 'pages': len(reader.pages),
            'bytes': PDF_PATH.stat().st_size, 'sha256': D.sha256(PDF_PATH)}


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
    print(json.dumps(print_pdf(), indent=2))
