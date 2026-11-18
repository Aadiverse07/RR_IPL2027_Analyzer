"""Layout scan for the fixed-page PDF report.

Every page of the report is a 210 × 297 mm block with ``overflow: hidden``, so a
page that needs more room silently loses content instead of re-flowing. This
check opens the built HTML in headless Chrome, measures each ``.page`` against
its own box, and reports the elements that cross the bottom or side edges.

Used by ``run_phase6`` and by the Phase 6 verification suite: a report page that
overflows is a defect, not a cosmetic issue.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from src.deliverables import browser_check as B

#: The pink spine on the cover is intentionally full-bleed.
IGNORED_SELECTORS = {'DIV.band'}

SCAN_JS = """
(function () {
  var out = [];
  document.querySelectorAll('.page').forEach(function (pg) {
    var box = pg.getBoundingClientRect();
    var footer = pg.querySelector('.footer');
    var limit = footer ? footer.getBoundingClientRect().top - box.top - 4
                       : box.bottom - box.top - 8;
    var bad = [];
    pg.querySelectorAll('*').forEach(function (el) {
      if (el.closest('.footer')) return;
      var r = el.getBoundingClientRect();
      if (r.height === 0 && r.width === 0) return;
      if (r.bottom - box.top > limit || r.right > box.right + 1 || r.left < box.left - 1) {
        bad.push({
          tag: el.tagName + (el.className ? '.' + String(el.className).split(' ')[0] : ''),
          bottom: Math.round(r.bottom - box.top),
          right: Math.round(r.right - box.left)
        });
      }
    });
    bad = bad.filter(function (item) {
      return !(item.tag === 'DIV.band');
    });
    out.push({
      page: Number(pg.getAttribute('data-page')),
      footer: (pg.querySelector('.footer span') || {}).textContent || '',
      scrollHeight: pg.scrollHeight,
      clientHeight: pg.clientHeight,
      offenders: bad.slice(0, 6)
    });
  });
  return out;
})()
"""


def scan(html_path: Path) -> dict[str, Any]:
    """Return the measured layout status of every report page."""
    html_path = Path(html_path).resolve()
    profile = Path(tempfile.mkdtemp(prefix='superr-report-scan-'))
    port = B._free_port()
    proc = None
    cdp = None
    try:
        proc = B._launch(profile, port)
        cdp = B._CDP.open(B._page_ws(port))
        cdp.send('Runtime.enable')
        cdp.send('Page.enable')
        cdp.send('Emulation.setDeviceMetricsOverride', {
            'width': 794, 'height': 1123, 'deviceScaleFactor': 1, 'mobile': False})
        cdp.send('Page.navigate', {'url': html_path.as_uri()})
        cdp.pump(1.6)
        pages = cdp.js(SCAN_JS)
    finally:
        if cdp is not None:
            cdp.close()
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)

    problems = []
    for page in pages:
        if page['offenders']:
            problems.append(page)
    return {
        'pages': len(pages),
        'problems': problems,
        'clean': len(pages) - len(problems),
        'passed': not problems,
        'detail': pages,
    }


if __name__ == '__main__':
    from src.deliverables import build_report as R

    result = scan(R.HTML_PATH)
    print(f"pages {result['pages']} clean {result['clean']} problems {len(result['problems'])}")
    for page in result['problems']:
        print(f"  page {page['page']} ({page['footer']}): "
              f"{[(o['tag'], o['bottom']) for o in page['offenders']]}")
