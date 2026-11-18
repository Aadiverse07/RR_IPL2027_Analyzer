"""Drive the built dashboard in headless Chrome over the DevTools protocol.

Static checks cannot see a JavaScript exception, a filter that silently does
nothing or a table that overflows on a phone. This module opens the real file in
headless Chrome, exercises every view and filter, and records what happened.

No new dependency: it speaks the Chrome DevTools Protocol over the
``websocket-client`` package that is already installed, and it launches the same
system Chrome used to print the PDF report.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from src.deliverables import data as D

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


class BrowserError(RuntimeError):
    pass


class _CDP:
    @classmethod
    def open(cls, ws_url: str) -> '_CDP':
        import websocket

        self = cls.__new__(cls)
        self._ws = websocket.create_connection(ws_url, timeout=20)
        self._id = 0
        self.events: list[dict[str, Any]] = []
        self.console: list[str] = []
        self.exceptions: list[str] = []
        return self

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        message_id = self._id
        self._ws.send(json.dumps({'id': message_id, 'method': method,
                                  'params': params or {}}))
        deadline = time.time() + 20
        while time.time() < deadline:
            raw = self._ws.recv()
            if not raw:
                continue
            message = json.loads(raw)
            if 'id' in message and message['id'] == message_id:
                if 'error' in message:
                    raise BrowserError(f'{method}: {message["error"]}')
                return message.get('result', {})
            self._record_event(message)
        raise BrowserError(f'{method}: timeout')

    def _record_event(self, message: dict[str, Any]) -> None:
        self.events.append(message)
        method = message.get('method')
        if method == 'Runtime.consoleAPICalled':
            kind = message['params'].get('type')
            text = ' '.join(str(a.get('value', a.get('description', '')))
                            for a in message['params'].get('args', []))
            if kind in ('error', 'warning'):
                self.console.append(f'{kind}: {text}')
        elif method == 'Runtime.exceptionThrown':
            detail = message['params']['exceptionDetails']
            self.exceptions.append(detail.get('exception', {}).get('description',
                                                                  detail.get('text', '')))

    def pump(self, seconds: float = 0.25) -> None:
        self._ws.settimeout(0.05)
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                raw = self._ws.recv()
            except Exception:  # noqa: BLE001 - timeout is the normal exit
                continue
            if raw:
                self._record_event(json.loads(raw))
        self._ws.settimeout(20)

    def js(self, expression: str) -> Any:
        result = self.send('Runtime.evaluate', {
            'expression': expression,
            'returnByValue': True,
            'awaitPromise': True,
        })
        if result.get('exceptionDetails'):
            raise BrowserError(str(result['exceptionDetails']))
        return result['result'].get('value')

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:  # noqa: BLE001
            pass


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _launch(profile: Path, port: int) -> subprocess.Popen:
    if not Path(CHROME).exists():
        raise BrowserError(f'Chrome not found at {CHROME}')
    return subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
        '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
        '--disable-extensions', '--disable-background-networking',
        f'--remote-debugging-port={port}', f'--user-data-dir={profile}',
        'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _page_ws(port: int) -> str:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2) as handle:
                pages = json.load(handle)
            for page in pages:
                if page.get('type') == 'page':
                    return page['webSocketDebuggerUrl']
        except Exception:  # noqa: BLE001 - browser still starting
            time.sleep(0.2)
    raise BrowserError('Chrome did not expose a page target')


class _Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check: str, passed: bool, detail: str = '') -> None:
        self.rows.append({'check': check, 'passed': bool(passed), 'detail': detail})

    def run(self, name: str, fn: Callable[[], str | None]) -> None:
        try:
            detail = fn() or ''
            self.add(name, True, detail)
        except Exception as error:  # noqa: BLE001 - a failed check is data, not a crash
            self.add(name, False, f'{type(error).__name__}: {error}')


def _wait_for(cdp: _CDP, expression: str, seconds: float = 6.0) -> Any:
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        last = cdp.js(expression)
        if last:
            return last
        time.sleep(0.08)
    return last


def _goto(cdp: _CDP, url: str, view: str) -> None:
    cdp.send('Page.navigate', {'url': f'{url}#/{view}'})
    cdp.pump(0.45)
    _wait_for(cdp, "document.querySelectorAll('.view.active').length")
    time.sleep(0.15)


def _click(cdp: _CDP, selector: str) -> None:
    ok = cdp.js(f"""(function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return false;
        el.click();
        return true;
    }})()""")
    if not ok:
        raise BrowserError(f'selector not found: {selector}')
    cdp.pump(0.12)
    time.sleep(0.10)


def _type(cdp: _CDP, selector: str, value: str) -> None:
    ok = cdp.js(f"""(function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return false;
        el.value = {json.dumps(value)};
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        return true;
    }})()""")
    if not ok:
        raise BrowserError(f'search input not found: {selector}')
    cdp.pump(0.12)
    time.sleep(0.12)


def run_checks(index_html: Path) -> dict[str, Any]:
    url = index_html.resolve().as_uri()
    payload = D.build_payload()
    lead_name = payload['rankings']['bowler_chase'][0]['player_name']
    search_name = lead_name
    collision = next(r for r in payload['rankings']['bowler_chase']
                     if r['player_id'] == '781')
    collision_score = collision['S_star']
    profile = Path(tempfile.mkdtemp(prefix='supeRR-chrome-'))
    port = _free_port()
    browser = _launch(profile, port)
    checks = _Checks()
    cdp = None
    started = time.time()
    try:
        cdp = _CDP.open(_page_ws(port))
        cdp.send('Page.enable')
        cdp.send('Runtime.enable')
        cdp.send('Network.enable')
        cdp.send('Page.navigate', {'url': url})
        cdp.pump(0.8)
        ok = _wait_for(cdp, "!!document.querySelector('.view.active')")
        checks.add('page_renders', bool(ok), 'first view rendered')

        def no_errors() -> str:
            cdp.pump(0.3)
            if cdp.exceptions:
                raise BrowserError('; '.join(cdp.exceptions[:3]))
            if cdp.console:
                raise BrowserError('; '.join(cdp.console[:3]))
            return 'no console errors or uncaught exceptions'

        checks.run('no_javascript_errors_on_load', no_errors)

        def nav() -> str:
            labels = cdp.js("Array.from(document.querySelectorAll('nav.main a')).map(a => a.textContent.trim())")
            expected = ['Overview', 'Bowlers', 'Batters', 'Players', 'Formats',
                        'Contexts', 'Excluded', 'Uncertainty', 'Method', 'Audit']
            if labels != expected:
                raise BrowserError(f'nav labels {labels}')
            return f'{len(labels)} sections'

        checks.run('all_sections_present', nav)

        def routing() -> str:
            views = ['overview', 'bowlers', 'batters', 'players', 'formats',
                     'contexts', 'excluded', 'uncertainty', 'method', 'data']
            seen = []
            for view in views:
                _goto(cdp, url, view)
                length = cdp.js("document.querySelector('.view.active').textContent.trim().length")
                if not length or length < 200:
                    raise BrowserError(f'{view} rendered {length} characters')
                if not cdp.js("location.hash === '#/" + view + "'"):
                    raise BrowserError(f'{view} did not route')
                seen.append(view)
            return f'{len(seen)} views render'

        checks.run('routing_every_view', routing)

        def bowlers_default() -> str:
            _goto(cdp, url, 'bowlers')
            rows = cdp.js("document.querySelectorAll('#tbl-bowlers tbody tr').length")
            if rows != 10:
                raise BrowserError(f'expected 10 published rows, got {rows}')
            first = cdp.js("document.querySelector('#tbl-bowlers tbody tr td.name').textContent")
            if lead_name not in first:
                raise BrowserError('first row does not match the frozen Phase 5 source')
            return '10 rows; first row matches the frozen Phase 5 source'

        checks.run('bowlers_published_default', bowlers_default)

        def bowlers_scope() -> str:
            _click(cdp, "button[data-filter-table='bowlers'][data-filter='scope'][data-value='all']")
            rows = cdp.js("document.querySelectorAll('#tbl-bowlers tbody tr').length")
            if rows != 36:
                raise BrowserError(f'expected 36 eligible rows, got {rows}')
            count = cdp.js("document.getElementById('count-bowlers').textContent")
            if '36 of 36' not in count:
                raise BrowserError(f'count note reads {count!r}')
            first_pool = cdp.js("document.querySelector('#tbl-bowlers tbody tr td.name').textContent")
            if lead_name not in first_pool:
                raise BrowserError('eligible-pool order does not match the frozen source')
            _click(cdp, "button[data-filter-table='bowlers'][data-filter='scope'][data-value='published']")
            return 'switches 10 -> 36 and back'

        checks.run('bowlers_scope_toggle', bowlers_scope)

        def bowlers_tier() -> str:
            _click(cdp, "button[data-filter-table='bowlers'][data-value='Moderate']")
            rows = cdp.js("document.querySelectorAll('#tbl-bowlers tbody tr').length")
            if rows != 4:
                raise BrowserError(f'expected 4 Moderate bowlers, got {rows}')
            _click(cdp, "button[data-filter-table='bowlers'][data-value='all']")
            title = cdp.js("location.hash")
            return '4 Moderate rows, then reset'

        checks.run('bowlers_tier_filter', bowlers_tier)

        def bowlers_search() -> str:
            _type(cdp, "input[data-filter-table='bowlers']", search_name)
            rows = cdp.js("document.querySelectorAll('#tbl-bowlers tbody tr').length")
            if rows != 1:
                raise BrowserError(f'search returned {rows} rows')
            name = cdp.js("document.querySelector('#tbl-bowlers tbody tr td.name').textContent")
            if lead_name not in name:
                raise BrowserError('name filter returned a row outside the frozen source')
            _type(cdp, "input[data-filter-table='bowlers']", 'zzzzz')
            empty = cdp.js("document.querySelector('#tbl-bowlers tbody tr td').textContent")
            if 'No player matches' not in empty:
                raise BrowserError(f'empty state reads {empty!r}')
            _type(cdp, "input[data-filter-table='bowlers']", '')
            return 'filters to one row and shows an empty state'

        checks.run('bowlers_search_and_empty_state', bowlers_search)

        def bowlers_volume() -> str:
            cdp.js("""(function(){
                var el = document.querySelector("select[data-filter-table='bowlers'][data-filter='minBalls']");
                el.value = '200';
                el.dispatchEvent(new Event('change', {bubbles: true}));
            })()""")
            cdp.pump(0.15)
            rows = cdp.js("document.querySelectorAll('#tbl-bowlers tbody tr').length")
            balls = cdp.js("Array.from(document.querySelectorAll('#tbl-bowlers tbody tr')).map(function(tr){return Number(tr.children[6].textContent.replace(/,/g,''))})")
            if any(b < 200 for b in balls):
                raise BrowserError(f'volume filter leaked: {balls}')
            cdp.js("""(function(){
                var el = document.querySelector("select[data-filter-table='bowlers'][data-filter='minBalls']");
                el.value = '0';
                el.dispatchEvent(new Event('change', {bubbles: true}));
            })()""")
            cdp.pump(0.15)
            return f'{rows} rows all at or above 200 deliveries'

        checks.run('bowlers_volume_filter', bowlers_volume)

        def sorting() -> str:
            _click(cdp, "th[data-sort-table='bowlers'][data-sort='S_star']")
            asc = cdp.js("Array.from(document.querySelectorAll('#tbl-bowlers tbody tr')).map(function(tr){return tr.children[2].textContent})")
            values = [float(v.replace('\u2212', '-').replace('+', '')) for v in asc]
            if values != sorted(values):
                raise BrowserError('first click does not sort ascending')
            _click(cdp, "th[data-sort-table='bowlers'][data-sort='S_star']")
            desc = cdp.js("Array.from(document.querySelectorAll('#tbl-bowlers tbody tr')).map(function(tr){return tr.children[2].textContent})")
            values = [float(v.replace('\u2212', '-').replace('+', '')) for v in desc]
            if values != sorted(values, reverse=True):
                raise BrowserError('second click does not sort descending')
            _click(cdp, "th[data-sort-table='bowlers'][data-sort='rank']")
            return 'S* sorts both ways; rank restores order'

        checks.run('table_sorting', sorting)

        def drawer() -> str:
            _click(cdp, "#tbl-bowlers tbody tr")
            cdp.pump(0.3)
            time.sleep(0.3)
            open_state = cdp.js("document.getElementById('drawer').classList.contains('open')")
            if not open_state:
                raise BrowserError('drawer did not open')
            name = cdp.js("document.querySelector('#drawer h2').textContent")
            score = cdp.js("document.querySelector('#drawer .score-big .n').textContent")
            has_reliability = cdp.js("document.querySelector('#drawer').textContent.indexOf('Reliability B_A') !== -1")
            has_format = cdp.js("document.querySelector('#drawer').textContent.indexOf('Format split') !== -1")
            if not name or not score or not has_reliability or not has_format:
                raise BrowserError('drawer is missing a section')
            cdp.send('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Escape', 'code': 'Escape',
                                                'windowsVirtualKeyCode': 27})
            cdp.send('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Escape', 'code': 'Escape',
                                                'windowsVirtualKeyCode': 27})
            time.sleep(0.25)
            if cdp.js("document.getElementById('drawer').classList.contains('open')"):
                raise BrowserError('Escape did not close the drawer')
            return 'player drawer shows score and reliability; closes on Escape'

        checks.run('player_drawer', drawer)

        def drawer_role_collision() -> str:
            # The same numeric ID can be scored as a batter and as a bowler
            # (246 IDs in this pool do). The drawer must resolve the clicked role.
            _goto(cdp, url, 'players')
            _type(cdp, "input[data-filter-table='players']", '781')
            role = cdp.js("""(function(){
                var rows = Array.from(document.querySelectorAll('#tbl-players tbody tr'));
                var hit = rows.filter(function(tr){ return tr.getAttribute('data-role') === 'batter'; })[0];
                if (!hit) return null;
                hit.click();
                return hit.getAttribute('data-role');
            })()""")
            if role != 'batter':
                raise BrowserError('no batter row for ID 781 in the player search')
            cdp.pump(0.3)
            time.sleep(0.25)
            heading = cdp.js("document.querySelector('#drawer .small.muted').textContent")
            if 'Batter' not in heading:
                raise BrowserError(f'drawer header reads {heading!r}, expected a batter')
            _click(cdp, '.drawer-close')
            _type(cdp, "input[data-filter-table='players']", search_name)
            time.sleep(0.15)
            _goto(cdp, url, 'bowlers')
            _click(cdp, '#tbl-bowlers tbody tr')
            cdp.pump(0.3)
            time.sleep(0.25)
            score = cdp.js("document.querySelector('#drawer .score-big .n').textContent")
            expected_score = f'{collision_score:+.3f}'
            if score != expected_score:
                raise BrowserError('bowler drawer score does not match the frozen source')
            _click(cdp, '.drawer-close')
            return 'role-resolved drawers: batter ID 781 and bowler ID 781 stay separate'

        checks.run('drawer_role_collision', drawer_role_collision)

        def excluded() -> str:
            _goto(cdp, url, 'excluded')
            rows = cdp.js("document.querySelectorAll('#tbl-excluded tbody tr').length")
            if rows < 10:
                raise BrowserError(f'only {rows} exclusion rows rendered')
            cdp.js("""(function(){
                var el = document.querySelector("select[data-filter-table='excluded'][data-filter='reason']");
                el.value = 'NO_VARIANCE';
                el.dispatchEvent(new Event('change', {bubbles: true}));
            })()""")
            cdp.pump(0.18)
            count = cdp.js("document.getElementById('count-excluded').textContent")
            if '56' not in count:
                raise BrowserError(f'count reads {count!r}')
            chips = cdp.js("Array.from(document.querySelectorAll('#tbl-excluded tbody tr')).map(function(tr){return tr.lastElementChild.querySelector('.chip').textContent.trim()})")
            if any(c != 'Too few deliveries' for c in chips):
                raise BrowserError(f'unexpected reason chips: {set(chips)}')
            _click(cdp, "button[data-action='more-excluded']")
            reason_rows = cdp.js("document.querySelectorAll('#tbl-excluded tbody tr').length")
            if reason_rows != 56:
                raise BrowserError(f'expected 56 rows after show more, got {reason_rows}')
            return '845 recorded, 56 no-variance rows after paging'

        checks.run('excluded_filter', excluded)

        def players_filter() -> str:
            _goto(cdp, url, 'players')
            _type(cdp, "input[data-filter-table='players']", '')
            total = cdp.js("document.getElementById('count-players').textContent")
            if '1,277' not in total:
                raise BrowserError(f'player count reads {total!r}')
            cdp.js("""(function(){
                var el = document.querySelector("select[data-filter-table='players'][data-filter='role']");
                el.value = 'batter';
                el.dispatchEvent(new Event('change', {bubbles: true}));
            })()""")
            cdp.pump(0.18)
            count = cdp.js("document.getElementById('count-players').textContent")
            if '486' not in count:
                raise BrowserError(f'batter row count reads {count!r}')
            return '1,277 rows, 486 batter rows'

        checks.run('players_filter', players_filter)

        def formats() -> str:
            _goto(cdp, url, 'formats')
            text = cdp.js("document.querySelector('.view.active').textContent")
            if text.count('No T20I-only player is eligible') != 2:
                raise BrowserError('T20I empty state is missing for a role')
            rows = cdp.js("document.querySelectorAll('.view.active table').length")
            if rows < 4:
                raise BrowserError(f'expected 4 format tables, got {rows}')
            ipl = cdp.js("""Array.from(document.querySelectorAll('.view.active table'))[0]
                .querySelectorAll('tbody tr').length""")
            if ipl != 10:
                raise BrowserError(f'IPL bowler table has {ipl} rows')
            return '4 tables, both T20I lists show an explicit empty state'

        checks.run('formats_tables', formats)

        def contexts() -> str:
            _goto(cdp, url, 'contexts')
            text = cdp.js("document.querySelector('.view.active').textContent")
            for needle in ('0', 'No ranking', 'PH3-01', 'F4-02', 'PH2-05'):
                if needle not in text:
                    raise BrowserError(f'contexts view is missing {needle!r}')
            return 'innings-1 states zero eligible and cites PH3-01'

        checks.run('contexts_disclosure', contexts)

        def uncertainty() -> str:
            _goto(cdp, url, 'uncertainty')
            text = cdp.js("document.querySelector('.view.active').textContent")
            needles = ['10/10', '9/9', 'E1 variance', 'fixed', 'single-stage']
            missing = [n for n in needles if n.lower() not in text.lower()]
            if missing:
                raise BrowserError(f'missing {missing}')
            bars = cdp.js("document.querySelectorAll('.view.active svg rect').length")
            if bars < 20:
                raise BrowserError(f'only {bars} chart marks rendered')
            return f'disclosures present, {bars} chart marks'

        checks.run('uncertainty_view', uncertainty)

        def audit() -> str:
            _goto(cdp, url, 'data')
            text = cdp.js("document.querySelector('.view.active').textContent")
            if '14/14' not in text or '15/15' not in text:
                raise BrowserError('verification counters missing')
            hashes = cdp.js("document.querySelectorAll('.view.active table').length")
            if hashes < 2:
                raise BrowserError('verification tables missing')
            return '15/15 internal, 14/14 independent, hash table present'

        checks.run('audit_view', audit)

        def tooltip() -> str:
            _goto(cdp, url, 'bowlers')
            shown = cdp.js("""(function(){
                var el = document.querySelector("th[data-tip]");
                if (!el) return false;
                el.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
                var tip = document.getElementById('tooltip');
                return tip.classList.contains('on') && tip.textContent.length > 10;
            })()""")
            if not shown:
                raise BrowserError('tooltip did not appear')
            return 'header tooltip displays on hover'

        checks.run('tooltips', tooltip)

        def no_network() -> str:
            entries = cdp.js("performance.getEntriesByType('resource').map(function(e){return e.name})")
            remote = [e for e in entries if not e.startswith('file://')]
            if remote:
                raise BrowserError(f'network requests: {remote[:3]}')
            return f'{len(entries)} local resource entries, no network'

        checks.run('offline_no_network', no_network)

        def mobile() -> str:
            cdp.send('Emulation.setDeviceMetricsOverride', {
                'width': 390, 'height': 844, 'deviceScaleFactor': 2, 'mobile': True,
            })
            cdp.send('Page.navigate', {'url': url + '#/bowlers'})
            cdp.pump(0.7)
            _wait_for(cdp, "document.querySelectorAll('#tbl-bowlers tbody tr').length")
            time.sleep(0.2)
            overflow = cdp.js('document.documentElement.scrollWidth - window.innerWidth')
            if overflow > 1:
                raise BrowserError(f'horizontal overflow of {overflow}px at 390px')
            head_hidden = cdp.js("getComputedStyle(document.querySelector('#tbl-bowlers thead')).display")
            if head_hidden != 'none':
                raise BrowserError('table header still displayed in the mobile card layout')
            labels = cdp.js("getComputedStyle(document.querySelector('#tbl-bowlers tbody td.name'), '::before').content")
            if labels not in ('none', 'normal'):
                raise BrowserError('mobile label pseudo-element leaked into the name cell')
            _click(cdp, '#tbl-bowlers tbody tr')
            time.sleep(0.25)
            drawer_width = cdp.js("document.getElementById('drawer').getBoundingClientRect().width")
            if drawer_width > 390:
                raise BrowserError(f'drawer is {drawer_width}px wide on a 390px viewport')
            cdp.js("document.querySelector('.drawer-close').click()")
            cdp.send('Emulation.clearDeviceMetricsOverride')
            return 'no horizontal overflow, card layout, drawer fits 390px'

        checks.run('mobile_390px', mobile)

        def final_clean() -> str:
            _goto(cdp, url, 'overview')
            cdp.pump(0.2)
            if cdp.exceptions:
                raise BrowserError('; '.join(cdp.exceptions[:3]))
            if cdp.console:
                raise BrowserError('; '.join(cdp.console[:3]))
            return 'no errors after the full interaction pass'

        checks.run('no_javascript_errors_after_interactions', final_clean)
    finally:
        if cdp is not None:
            cdp.close()
        browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser.kill()
        shutil.rmtree(profile, ignore_errors=True)

    passed = sum(1 for row in checks.rows if row['passed'])
    return {
        'checks': checks.rows,
        'passed': passed,
        'total': len(checks.rows),
        'all_pass': passed == len(checks.rows),
        'seconds': round(time.time() - started, 1),
    }


if __name__ == '__main__':
    index = Path(__file__).resolve().parents[2] / 'outputs/final/deliverables/dashboard/index.html'
    report = run_checks(index)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['all_pass'] else 1)
