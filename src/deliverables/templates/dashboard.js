/* SupeRR Selector — Phase 6 dashboard
   Reads one embedded payload built from the frozen Phase 5 outputs.
   No network access, no libraries, no animation beyond CSS transitions. */
(function () {
  'use strict';

  var DATA = JSON.parse(document.getElementById('supeRR-data').textContent);
  var app = document.getElementById('app');
  var hero = document.getElementById('hero');
  var nav = document.querySelector('nav.main');
  var tooltip = document.getElementById('tooltip');
  var drawer = document.getElementById('drawer');
  var scrim = document.getElementById('scrim');
  var drawerBody = document.getElementById('drawer-body');
  var state = { view: 'overview', tables: {} };
  var lastFocus = null;

  /* ------------------------------------------------------------ formatting */
  var MINUS = '\u2212';
  function num(v, d) {
    if (v === null || v === undefined || (typeof v === 'number' && !isFinite(v))) return '—';
    d = d === undefined ? 0 : d;
    return Number(v).toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function signed(v, d) {
    if (v === null || v === undefined) return '—';
    d = d === undefined ? 3 : d;
    var s = Math.abs(v).toFixed(d);
    return (v < 0 ? MINUS : '+') + s;
  }
  function pct(v, d) {
    if (v === null || v === undefined) return '—';
    d = d === undefined ? 0 : d;
    return (v * 100).toFixed(d) + '%';
  }
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function ciText(row) {
    return '[' + signed(row.S_ci90_low) + ', ' + signed(row.S_ci90_high) + ']';
  }
  function tierColour(t) {
    return { High: 'var(--green)', Moderate: 'var(--blue)', Limited: 'var(--pink)' }[t] || 'var(--ink-faint)';
  }
  function tierChip(t) {
    return '<span class="chip ' + esc(t) + '">' + esc(t) + '</span>';
  }
  function formatChip(f) {
    return '<span class="chip plain">' + esc(f || '—') + '</span>';
  }
  function roleName(r) { return r === 'bowler' ? 'Bowler' : 'Batter'; }
  function contextName(c) {
    return c === 'chase' ? 'Chase' : c === 'innings1_ahead_par' ? 'Innings 1, ahead of par' : c;
  }

  /* ------------------------------------------------------------- data prep */
  /* Player IDs are unique per role, not globally: the same numeric ID can name a
     bowler and a batter. Every lookup is therefore keyed by role as well. */
  var byId = {};
  DATA.pool.bowler_chase.concat(DATA.pool.batter_chase, DATA.pool.bowler_innings1)
    .forEach(function (r) { byId[r.player_id + '|' + r.role + '|' + r.context] = r; });

  var stabilityById = {};
  DATA.stability.forEach(function (r) { stabilityById[r.role + '|' + r.player_id] = r; });

  function poolWithPublished(key, published) {
    var map = {};
    published.forEach(function (p) { map[p.player_id] = p; });
    return DATA.pool[key].filter(function (r) { return r.pool_order; }).map(function (r) {
      var pub = map[r.player_id] || null;
      return Object.assign({}, r, {
        published: pub,
        published_rank: pub ? pub.rank : null,
        bootstrap_share_top10: pub ? pub.bootstrap_share_top10 : null
      });
    });
  }
  var eligibleBowlers = poolWithPublished('bowler_chase', DATA.rankings.bowler_chase);
  var eligibleBatters = poolWithPublished('batter_chase', DATA.rankings.batter_chase);

  DATA.rankings.bowler_chase.forEach(function (p) {
    if (!byId[p.player_id + '|bowler|chase']) byId[p.player_id + '|bowler|chase'] = p;
  });
  DATA.rankings.batter_chase.forEach(function (p) {
    if (!byId[p.player_id + '|batter|chase']) byId[p.player_id + '|batter|chase'] = p;
  });

  var exclusionByKey = {};
  DATA.exclusions.forEach(function (r) {
    exclusionByKey[r.player_id + '|' + r.role + '|' + r.context] = r;
  });

  /* ---------------------------------------------------------------- charts */
  function scaleLinear(d0, d1, r0, r1) {
    var span = d1 - d0 || 1;
    return function (v) { return r0 + (v - d0) * (r1 - r0) / span; };
  }

  function ciCell(row, domain) {
    var w = 168, h = 20, pad = 4;
    var x = scaleLinear(domain[0], domain[1], pad, w - pad);
    var colour = tierColour(row.evidence_tier);
    var y = h / 2;
    return '<svg class="ci-svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h +
      '" role="img" aria-label="90 percent interval ' + esc(ciText(row)) + '">' +
      '<line x1="' + x(domain[0] < 0 && domain[1] > 0 ? 0 : domain[0]) + '" y1="' + y + '" x2="' +
      x(domain[0] < 0 && domain[1] > 0 ? 0 : domain[0]) + '" y2="' + y + '" stroke="var(--rule-strong)" stroke-width="1"/>' +
      '<line x1="' + x(row.S_ci90_low) + '" y1="' + y + '" x2="' + x(row.S_ci90_high) + '" y2="' + y +
      '" stroke="' + colour + '" stroke-opacity=".35" stroke-width="6" stroke-linecap="round"/>' +
      '<line x1="' + x(row.S_ci90_low) + '" y1="' + y + '" x2="' + x(row.S_ci90_high) + '" y2="' + y +
      '" stroke="' + colour + '" stroke-width="1"/>' +
      '<circle cx="' + x(row.S_star) + '" cy="' + y + '" r="3.4" fill="' + colour + '" stroke="#fff" stroke-width="1.2"/>' +
      '</svg>';
  }

  function intervalChart(rows, opts) {
    opts = opts || {};
    var width = 900;
    var rowH = opts.rowH || 32;
    var labelW = opts.labelW || 210;
    var rightPad = 66;
    var top = 26;
    var height = top + rows.length * rowH + 26;
    var domain = [Math.min.apply(null, rows.map(function (r) { return r.S_ci90_low; })),
                  Math.max.apply(null, rows.map(function (r) { return r.S_ci90_high; }))];
    domain[0] = Math.min(domain[0], 0) - 0.02;
    domain[1] = domain[1] + 0.06;
    var x = scaleLinear(domain[0], domain[1], labelW, width - rightPad);
    var out = '<svg class="chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Performance scores with 90 percent intervals">';
    // gridlines
    var step = 0.1;
    for (var g = Math.ceil(domain[0] / step) * step; g <= domain[1]; g += step) {
      out += '<line class="gridline" x1="' + x(g) + '" y1="' + (top - 10) + '" x2="' + x(g) + '" y2="' + (height - 22) + '"/>' +
        '<text class="axis-tick" x="' + x(g) + '" y="' + (height - 8) + '" text-anchor="middle">' + signed(g, 1).replace('+', '') + '</text>';
    }
    // zero line
    if (domain[0] < 0 && domain[1] > 0) {
      out += '<line x1="' + x(0) + '" y1="' + (top - 10) + '" x2="' + x(0) + '" y2="' + (height - 22) + '" stroke="var(--ink)" stroke-width="1.2"/>' +
        '<text class="axis-tick" x="' + (x(0) + 6) + '" y="' + (top - 12) + '" fill="var(--ink-soft)">zero = average</text>';
    }
    rows.forEach(function (r, i) {
      var y = top + i * rowH + rowH / 2;
      var colour = tierColour(r.evidence_tier);
      out += '<text class="mark-label" x="' + (labelW - 14) + '" y="' + (y + 4) + '" text-anchor="end">' +
        (opts.showRank === false ? '' : (r.displayRank || '') + '. ') + esc(r.player_name) + '</text>';
      out += '<line x1="' + x(r.S_ci90_low) + '" y1="' + y + '" x2="' + x(r.S_ci90_high) + '" y2="' + y +
        '" stroke="' + colour + '" stroke-opacity=".32" stroke-width="7" stroke-linecap="round"/>';
      out += '<line x1="' + x(r.S_ci90_low) + '" y1="' + y + '" x2="' + x(r.S_ci90_high) + '" y2="' + y +
        '" stroke="' + colour + '" stroke-width="1"/>';
      out += '<line x1="' + x(r.S_ci90_low) + '" y1="' + (y - 5) + '" x2="' + x(r.S_ci90_low) + '" y2="' + (y + 5) + '" stroke="' + colour + '" stroke-width="1"/>';
      out += '<line x1="' + x(r.S_ci90_high) + '" y1="' + (y - 5) + '" x2="' + x(r.S_ci90_high) + '" y2="' + (y + 5) + '" stroke="' + colour + '" stroke-width="1"/>';
      out += '<circle cx="' + x(r.S_star) + '" cy="' + y + '" r="4.6" fill="' + colour + '" stroke="#fff" stroke-width="1.4"/>';
      out += '<text class="mark-label" x="' + (width - rightPad + 8) + '" y="' + (y + 4) + '">' + signed(r.S_star) + '</text>';
    });
    out += '</svg>';
    return out;
  }

  function scatterChart(rows) {
    var width = 640, height = 380;
    var padL = 52, padR = 22, padT = 20, padB = 46;
    var xs = rows.map(function (r) { return r.S_star; });
    var ys = rows.map(function (r) { return r.shrinkage_A; });
    var x0 = Math.min.apply(null, xs) - 0.02, x1 = Math.max.apply(null, xs) + 0.02;
    var y0 = 0.18, y1 = Math.max.apply(null, ys) + 0.03;
    var x = scaleLinear(x0, x1, padL, width - padR);
    var y = scaleLinear(y0, y1, height - padB, padT);
    var out = '<svg class="chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Reliability against performance score">';
    for (var gy = 0.2; gy <= y1; gy += 0.1) {
      out += '<line class="gridline" x1="' + padL + '" y1="' + y(gy) + '" x2="' + (width - padR) + '" y2="' + y(gy) + '"/>' +
        '<text class="axis-tick" x="' + (padL - 8) + '" y="' + (y(gy) + 3.5) + '" text-anchor="end">' + gy.toFixed(1) + '</text>';
    }
    for (var gx = Math.ceil(x0 * 10) / 10; gx <= x1; gx += 0.1) {
      out += '<text class="axis-tick" x="' + x(gx) + '" y="' + (height - padB + 16) + '" text-anchor="middle">' + signed(gx, 1).replace('+', '') + '</text>';
    }
    out += '<line x1="' + x(0) + '" y1="' + (height - padB) + '" x2="' + x(0) + '" y2="' + padT + '" stroke="var(--ink)" stroke-width="1" stroke-dasharray="3 3"/>';
    out += '<line x1="' + padL + '" y1="' + y(0.20) + '" x2="' + (width - padR) + '" y2="' + y(0.20) + '" stroke="var(--pink)" stroke-width="1.4"/>';
    out += '<text class="axis-tick" x="' + (width - padR) + '" y="' + (y(0.20) - 6) + '" text-anchor="end" fill="var(--pink)">eligibility 0.20</text>';
    rows.forEach(function (r) {
      out += '<circle cx="' + x(r.S_star) + '" cy="' + y(r.shrinkage_A) + '" r="' + (4 + Math.min(6, (r.n_pressure || 0) / 55)) +
        '" fill="' + tierColour(r.evidence_tier) + '" fill-opacity=".55" stroke="#fff" stroke-width="1"/>';
    });
    out += '<text class="axis-label" x="' + (width / 2) + '" y="' + (height - 6) + '" text-anchor="middle">Performance Score S*</text>';
    out += '<text class="axis-label" x="14" y="' + (height / 2) + '" text-anchor="middle" transform="rotate(-90 14 ' + (height / 2) + ')">Reliability B_A</text>';
    out += '</svg>';
    return out;
  }

  function histogramSvg(values, threshold) {
    var width = 640, height = 240;
    var padL = 40, padR = 14, padT = 14, padB = 34;
    var bins = 24, max = 0.6;
    var counts = new Array(bins).fill(0);
    values.forEach(function (v) {
      if (v === null || v === undefined) return;
      var idx = Math.min(bins - 1, Math.max(0, Math.floor(v / max * bins)));
      counts[idx] += 1;
    });
    var peak = Math.max.apply(null, counts) || 1;
    var x = scaleLinear(0, max, padL, width - padR);
    var y = scaleLinear(0, peak, height - padB, padT);
    var bw = (width - padL - padR) / bins;
    var out = '<svg class="chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Distribution of reliability">';
    counts.forEach(function (c, i) {
      if (!c) return;
      out += '<rect x="' + (padL + i * bw + 0.5) + '" y="' + y(c) + '" width="' + (bw - 1) + '" height="' +
        (height - padB - y(c)) + '" fill="var(--blue-soft)" stroke="var(--blue)" stroke-width=".7"/>';
    });
    out += '<line x1="' + x(threshold) + '" y1="' + padT + '" x2="' + x(threshold) + '" y2="' + (height - padB) + '" stroke="var(--pink)" stroke-width="1.6"/>';
    out += '<text class="axis-tick" x="' + (x(threshold) + 6) + '" y="' + (padT + 10) + '" fill="var(--pink)">0.20 threshold</text>';
    [0, 0.2, 0.4, 0.6].forEach(function (t) {
      out += '<text class="axis-tick" x="' + x(t) + '" y="' + (height - padB + 15) + '" text-anchor="middle">' + t.toFixed(1) + '</text>';
    });
    out += '<text class="axis-label" x="' + (width / 2) + '" y="' + (height - 4) + '" text-anchor="middle">Reliability B_A</text>';
    out += '</svg>';
    return out;
  }

  function bootstrapSvg(rows) {
    var width = 900, rowH = 30, top = 18, labelW = 170;
    var height = top + rows.length * rowH + 34;
    var out = '<svg class="chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Bootstrap stability of each published rank">';
    var xShare = scaleLinear(0, 1, labelW, labelW + 300);
    rows.forEach(function (r, i) {
      var y = top + i * rowH + rowH / 2;
      out += '<text class="mark-label" x="' + (labelW - 10) + '" y="' + (y + 4) + '" text-anchor="end">' + esc(r.player_name) + '</text>';
      out += '<rect x="' + labelW + '" y="' + (y - 7) + '" width="300" height="14" fill="#f1efea" rx="3"/>';
      out += '<rect x="' + labelW + '" y="' + (y - 7) + '" width="' + (300 * (r.bootstrap_share_top10 || 0)) +
        '" height="14" fill="var(--pink)" fill-opacity="' + (r.bootstrap_share_top10 >= 0.9 ? '.95' : '.35') + '" rx="3"/>';
      out += '<text class="mark-label" x="' + (labelW + 310) + '" y="' + (y + 4) + '">' + pct(r.bootstrap_share_top10) + '</text>';
    });
    out += '<text class="axis-label" x="' + (labelW + 150) + '" y="' + (height - 8) + '" text-anchor="middle">share of 200 resamples kept in the top 10</text>';
    out += '</svg>';
    return out;
  }

  function sensitivitySvg(rows) {
    var width = 900, rowH = 30, top = 16, labelW = 230;
    var height = top + rows.length * rowH + 42;
    var out = '<svg class="chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Sensitivity of the published list">';
    var barMax = 420;
    var x = scaleLinear(0, 1, labelW, labelW + barMax);
    rows.forEach(function (r, i) {
      var y = top + i * rowH + rowH / 2;
      var share = r.overlap_with_primary / r.denominator;
      var colour = r.scenario === 'variance_E1' ? 'var(--red)' : 'var(--pink)';
      out += '<text class="mark-label" x="' + (labelW - 10) + '" y="' + (y + 4) + '" text-anchor="end">' + esc(r.label) + '</text>';
      out += '<rect x="' + labelW + '" y="' + (y - 7) + '" width="' + (barMax * share) + '" height="14" fill="' + colour + '" rx="3"/>';
      out += '<text class="mark-label" x="' + (labelW + barMax * share + 8) + '" y="' + (y + 4) + '">' +
        r.overlap_with_primary + '/' + r.denominator + ' kept · ' + r.eligible + ' eligible</text>';
    });
    out += '<text class="axis-label" x="' + (labelW + barMax / 2) + '" y="' + (height - 10) + '" text-anchor="middle">names kept from the published list</text>';
    out += '</svg>';
    return out;
  }

  /* ---------------------------------------------------------------- tables */
  function sorter(key, dir) {
    return function (a, b) {
      var va = a[key], vb = b[key];
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      if (typeof va === 'string') return va.localeCompare(vb) * dir;
      return (va - vb) * dir;
    };
  }

  function tableState(name, defaults) {
    if (!state.tables[name]) state.tables[name] = Object.assign({ page: 1 }, defaults);
    return state.tables[name];
  }

  function sortButton(name, key, label, cls, tip) {
    var t = state.tables[name];
    var active = t.sort === key;
    return '<th class="sortable ' + (cls || '') + '" data-sort-table="' + name + '" data-sort="' + key +
      '"' + (tip ? ' data-tip="' + esc(tip) + '"' : '') + '>' + label +
      '<span class="arrow">' + (active ? (t.dir === 1 ? '▲' : '▼') : '↕') + '</span></th>';
  }

  function filtersBar(name, opts) {
    var t = state.tables[name];
    var out = '<div class="filters">';
    out += '<label class="search"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>' +
      '<input type="search" data-keep="' + name + '-search" data-filter-table="' + name + '" data-filter="q" placeholder="' + esc(opts.placeholder) + '" value="' + esc(t.q || '') + '" aria-label="Search players"></label>';
    if (opts.tiers) {
      out += '<div class="seg" role="group" aria-label="Evidence tier">' +
        ['all', 'Moderate', 'Limited'].map(function (v) {
          return '<button data-filter-table="' + name + '" data-filter="tier" data-value="' + v + '" aria-pressed="' +
            ((t.tier || 'all') === v) + '">' + (v === 'all' ? 'All tiers' : v) + '</button>';
        }).join('') + '</div>';
    }
    if (opts.formats) {
      out += '<select class="select" data-filter-table="' + name + '" data-filter="format" aria-label="Format">' +
        ['all', 'IPL', 'IPL+T20I'].map(function (v) {
          return '<option value="' + v + '"' + ((t.format || 'all') === v ? ' selected' : '') + '>' +
            (v === 'all' ? 'All formats' : v === 'IPL+T20I' ? 'IPL + T20I' : 'IPL only') + '</option>';
        }).join('') + '</select>';
    }
    if (opts.minBalls) {
      out += '<select class="select" data-filter-table="' + name + '" data-filter="minBalls" aria-label="Minimum pressure deliveries">' +
        [0, 100, 150, 200].map(function (v) {
          return '<option value="' + v + '"' + (Number(t.minBalls || 0) === v ? ' selected' : '') + '>' +
            (v === 0 ? 'Any volume' : v + '+ pressure balls') + '</option>';
        }).join('') + '</select>';
    }
    if (opts.segmented) {
      out += '<div class="seg" role="group" aria-label="' + esc(opts.segmentedLabel) + '">' +
        opts.segmented.map(function (o) {
          return '<button data-filter-table="' + name + '" data-filter="' + o.filter + '" data-value="' + o.value + '" aria-pressed="' +
            (String(t[o.filter]) === String(o.value)) + '">' + esc(o.label) + '</button>';
        }).join('') + '</div>';
    }
    out += '<div class="count-note" id="count-' + name + '"></div>';
    out += '</div>';
    return out;
  }

  function applyFilters(rows, t) {
    var q = (t.q || '').trim().toLowerCase();
    return rows.filter(function (r) {
      if (q && String(r.player_name).toLowerCase().indexOf(q) === -1 && String(r.player_id).indexOf(q) === -1) return false;
      if (t.tier && t.tier !== 'all' && r.evidence_tier !== t.tier) return false;
      if (t.format && t.format !== 'all' && r.formats_present !== t.format) return false;
      if (t.minBalls && (r.n_pressure || 0) < Number(t.minBalls)) return false;
      if (t.reason && t.reason !== 'all' && r.reason_code !== t.reason) return false;
      if (t.role && t.role !== 'all' && r.role !== t.role) return false;
      return true;
    });
  }

  /* ----------------------------------------------------------------- views */
  var NAV = [
    ['overview', 'Overview'],
    ['bowlers', 'Bowlers'],
    ['batters', 'Batters'],
    ['players', 'Players'],
    ['formats', 'Formats'],
    ['contexts', 'Contexts'],
    ['excluded', 'Excluded'],
    ['uncertainty', 'Uncertainty'],
    ['method', 'Method'],
    ['data', 'Audit']
  ];

  function renderNav() {
    nav.innerHTML = NAV.map(function (n) {
      return '<a href="#/' + n[0] + '"' + (state.view === n[0] ? ' class="active" aria-current="page"' : '') + '>' + n[1] + '</a>';
    }).join('');
  }

  function renderHero() {
    var h = DATA.headline;
    if (state.view === 'overview') {
      hero.innerHTML =
        '<div class="eyebrow">Pressure performance · final selection</div>' +
        '<h1>Ten bowlers and eight batters clear the bar. The order inside each list does not.</h1>' +
        '<p class="lede">A pressure-performance shortlist built from ' + num(h.deliveries) + ' deliveries across ' +
        num(h.matches) + ' matches. Every player is scored against what an average player would have done in the same situation, ' +
        'then filtered by how much the evidence can actually support. Reliability is reported next to performance and never folded into it.</p>' +
        '<div class="hero-meta">' +
        '<span class="pill"><b>' + h.bowler_published + '</b> chase bowlers published</span>' +
        '<span class="pill"><b>' + h.batter_published + '</b> chase batters — the full eligible set</span>' +
        '<span class="pill"><b>0</b> innings-1 bowlers eligible</span>' +
        '<span class="pill">Ranking rule frozen before calculation</span>' +
        '</div>';
    } else {
      var item = NAV.filter(function (n) { return n[0] === state.view; })[0];
      hero.innerHTML = '<div class="eyebrow">SupeRR Selector · ' + item[1] + '</div>' +
        '<h1 style="font-size:clamp(26px,3.2vw,38px)">' + heroTitle(state.view) + '</h1>' +
        '<p class="lede" style="font-size:15.5px;margin-top:12px">' + heroLede(state.view) + '</p>';
    }
  }

  function heroTitle(view) {
    return {
      bowlers: 'Chase bowling shortlist',
      batters: 'Chase batting shortlist',
      players: 'Every player we scored',
      formats: 'What the formats actually support',
      contexts: 'Two contexts, never merged',
      excluded: 'Why a player is not on the list',
      uncertainty: 'How uncertain this is',
      method: 'How the scores were built',
      data: 'Provenance and verification'
    }[view];
  }

  function heroLede(view) {
    return {
      bowlers: 'Ten published from 36 eligible. All ten intervals contain zero and every adjacent pair overlaps, so this is a shortlist with an order, not a podium.',
      batters: 'Exactly eight batters clear the reliability gate. The list stops at eight because the evidence does, not because the list was cut.',
      players: 'Search all 1,277 player-context rows — published, eligible but unpublished, and not eligible — and inspect the components behind any score.',
      formats: 'IPL and T20I were estimated separately before being combined. T20I alone cannot rank anyone, and the combination is descriptive — not evidence of transferability.',
      contexts: 'Chase pressure and first-innings bowling pressure are separate estimands. The innings-1 context is a research finding with zero eligible players.',
      excluded: '845 chase players did not clear the reliability threshold. Each one has a recorded reason, and no threshold was relaxed to include anyone.',
      uncertainty: 'Intervals, bootstrap stability and seven alternative specifications. The list is more fragile than a headline number suggests.',
      method: 'Pressure definition, situation-adjusted performance, empirical-Bayes shrinkage and a pre-registered selection rule.',
      data: 'Frozen input hashes, the independent verification log, the failure register and the known upstream defects.'
    }[view];
  }

  /* ---------------------------------------------------------------- overview */
  function viewOverview() {
    var h = DATA.headline;
    var top = DATA.rankings.bowler_chase.slice(0, 3);
    return '' +
      '<section class="section"><div class="grid cols-4">' +
      card('stat', '<div class="value pink">10</div><div class="label">chase bowlers published</div><div class="note">from 36 eligible</div>') +
      card('stat', '<div class="value blue">8</div><div class="label">chase batters published</div><div class="note">the complete eligible set</div>') +
      card('stat', '<div class="value amber">0</div><div class="label">innings-1 bowlers eligible</div><div class="note">377 scored, max B_A 0.150</div>') +
      card('stat', '<div class="value">' + num(h.matches) + '</div><div class="label">matches in scope</div><div class="note">' + num(h.deliveries) + ' deliveries</div>') +
      '</div></section>' +

      '<section class="section"><div class="grid cols-2">' +
      '<div class="card"><h4>What this is</h4><h3 style="margin-top:6px">A shortlist of players whose pressure record is strong enough to publish</h3>' +
      '<p class="small mt-2">Each player is compared with the league expectation for the exact situation they bowled or batted in — format, innings, phase, wickets down and player type. The score rewards beating that expectation under pressure, and it removes general form so the list is not simply the best players again.</p>' +
      '<ul class="list small"><li><b>Bowler chase:</b> 10 of 36 eligible.</li><li><b>Batter chase:</b> 8 of 8 eligible — no filler.</li><li><b>Innings-1 bowling:</b> presented as a finding, not a ranking.</li></ul></div>' +
      '<div class="card"><h4>What this is not</h4><h3 style="margin-top:6px">A claim that rank 1 is better than rank 2</h3>' +
      '<p class="small mt-2">Every published bowler’s 90% interval contains zero and every adjacent pair overlaps. Ranks 2 and 3 differ by 0.00008 in S*. The top three survive resampling; the rest of the list does not reliably.</p>' +
      '<ul class="list small"><li>Not a transferability claim between IPL and T20I.</li><li>Not a judgement on players who fell below the reliability gate.</li><li>Not an innings-1 batting ranking — no validated context exists.</li></ul></div>' +
      '</div></section>' +

      '<section class="section"><div class="section-head"><div><h2>The three results</h2>' +
      '<p>Open any row to see the score components and the reliability evidence behind it.</p></div>' +
      '<a class="pill" href="#/uncertainty">Read the uncertainty first →</a></div>' +
      '<div class="grid cols-3">' +
      resultCard('Bowler · chase', DATA.rankings.bowler_chase, 'pink', '10 published from 36 eligible') +
      resultCard('Batter · chase', DATA.rankings.batter_chase, 'blue', '8 published — every eligible batter') +
      '<div class="card"><h4>Bowler · innings 1</h4><div class="stat" style="margin-top:8px"><div class="value amber">0</div>' +
      '<div class="label">eligible at B_A ≥ 0.20</div><div class="note">377 scored · maximum 0.150</div></div>' +
      '<p class="small mt-2">No ranking is published. The context is defined by the batting side being ahead of par, so part of the signal is the scoring environment rather than bowling skill (PH3-01).</p>' +
      '<a class="small" href="#/contexts">Why this is a research finding →</a></div>' +
      '</div></section>' +

      '<section class="section"><div class="callout blue"><h4>The claim we are willing to defend</h4>' +
      '<p>Under the pre-registered rule, these eighteen players have pressure evidence strong enough to publish. The top three bowlers are stable under resampling; positions four to ten are not. Any use of this list should quote the eligible set, the evidence tier and the interval — not the sequence alone.</p></div></section>' +

      '<section class="section"><div class="grid cols-3">' +
      quick('How pressure was defined', 'A calibrated chase model marks the tightest quarter of chase states, using only pre-ball information.', 'method') +
      quick('Why reliability is separate', 'Shrinkage decides who is eligible. It never enters the score, and the two are never multiplied.', 'method') +
      quick('What moves the list', 'Score weight barely matters; the rejected E1 variance estimator replaces every name.', 'uncertainty') +
      '</div></section>';
  }

  function card(cls, html) {
    return '<div class="card ' + cls + '">' + html + '</div>';
  }

  function quick(title, body, view) {
    return '<a class="card" style="text-decoration:none;color:inherit" href="#/' + view + '"><h3>' + title + '</h3>' +
      '<p class="small mt-1">' + body + '</p><span class="small" style="color:var(--blue)">Open →</span></a>';
  }

  function resultCard(label, rows, colour, note) {
    var out = '<div class="card"><h4>' + label + '</h4><div class="stat" style="margin-top:8px">' +
      '<div class="value ' + colour + '">' + rows.length + '</div><div class="label">' + note + '</div></div>' +
      '<ol class="list small mt-2" style="padding-left:20px">';
    rows.slice(0, 5).forEach(function (r) {
      out += '<li><b>' + esc(r.player_name) + '</b> · ' + signed(r.S_star) + ' <span class="muted">(' + esc(r.evidence_tier) + ')</span></li>';
    });
    out += '</ol><p class="small muted mb-0">First five shown. All ' + rows.length + ' in the full table.</p></div>';
    return out;
  }

  /* ------------------------------------------------------------- ranking UI */
  function rankingTable(role, name, opts) {
    var t = tableState(name, { sort: 'rank', dir: 1, q: '', tier: 'all', format: 'all', minBalls: 0, scope: 'published' });
    var all = role === 'bowler' ? eligibleBowlers : eligibleBatters;
    if (role === 'bowler' && t.scope === 'all') {
      all = all.slice();
    } else {
      all = all.filter(function (r) { return r.published_rank; });
    }
    var rows = applyFilters(all, t).map(function (r) {
      return Object.assign({}, r, {
        displayRank: r.published_rank || '',
        rank: r.published_rank || r.pool_order
      });
    });
    rows.sort(sorter(t.sort, t.dir));

    var domain = [
      Math.min.apply(null, all.map(function (r) { return r.S_ci90_low; })),
      Math.max.apply(null, all.map(function (r) { return r.S_ci90_high; }))
    ];
    domain[0] = Math.min(domain[0], 0) - 0.02;
    domain[1] = domain[1] + 0.02;

    var header = '<thead><tr>' +
      sortButton(name, 'rank', role === 'bowler' && t.scope === 'all' ? 'Pool' : 'Rank', 'num', 'Published position under the pre-registered rule') +
      sortButton(name, 'player_name', 'Player') +
      sortButton(name, 'S_star', 'S*', 'num', 'S* = A* − 0.30·B*. Positive means better than expected in pressure, after removing general form.') +
      '<th data-tip="90% interval for S*. If it contains zero, average performance cannot be ruled out.">90% interval</th>' +
      sortButton(name, 'shrinkage_A', 'Reliability B_A', 'num', 'How much of the player’s own record is kept rather than pulled to the league average. Decides eligibility; never enters the score.') +
      '<th data-tip="Limited 0.20–0.30 · Moderate 0.30–0.50 · High 0.50+. No published player reaches High.">Tier</th>' +
      sortButton(name, 'n_pressure', 'Pressure balls', 'num', 'Deliveries bowled or faced while the validated chase-pressure flag is on.') +
      sortButton(name, 'total_matches', 'Matches', 'num', 'Matches contributing evidence in this context.') +
      '<th class="hide-sm">Format</th>' +
      (role === 'bowler'
        ? sortButton(name, 'bootstrap_share_top10', 'P(top 10)', 'num', 'Share of 200 match-block resamples in which the player stayed in the top 10. Fixed empirical-Bayes fit.')
        : '<th class="num" data-tip="Median resampled rank with its 5–95% range. Top-10 membership is 100% for every eligible batter by construction (only eight are eligible), so it is not shown.">Resampled rank</th>') +
      '</tr></thead>';

    var body = '<tbody>';
    if (!rows.length) {
      body += '<tr><td colspan="10" class="muted" style="padding:26px 12px">No player matches these filters.</td></tr>';
    }
    rows.forEach(function (r) {
      var rankLabel = role === 'bowler' && t.scope === 'all'
        ? (r.pool_order || '—')
        : (r.published_rank || '—');
      body += '<tr class="clickable" data-player="' + esc(r.player_id) + '" data-context="chase" data-role="' + role + '" tabindex="0">' +
        '<td class="num"><span class="rank' + (String(rankLabel) === '1' ? ' top' : '') + '">' + rankLabel + '</span></td>' +
        '<td class="name" data-label="Player">' + esc(r.player_name) + '<span class="sub">ID ' + esc(r.player_id) +
        (r.published_rank ? '' : ' · eligible, not published') + '</span></td>' +
        '<td class="num" data-label="S*"><span class="' + (r.S_star >= 0 ? 'score-pos' : 'score-neg') + '">' + signed(r.S_star) + '</span></td>' +
        '<td class="ci-cell" data-label="90% interval">' + ciCell(r, domain) + '</td>' +
        '<td class="num" data-label="Reliability B_A">' + num(r.shrinkage_A, 3) + '</td>' +
        '<td data-label="Tier">' + tierChip(r.evidence_tier) + '</td>' +
        '<td class="num" data-label="Pressure balls">' + num(r.n_pressure) + '</td>' +
        '<td class="num" data-label="Matches">' + num(r.total_matches) + '</td>' +
        '<td class="hide-sm" data-label="Format">' + formatChip(r.formats_present) + '</td>' +
        '<td class="num" data-label="' + (role === 'bowler' ? 'P(top 10)' : 'Resampled rank') + '">' + stabilityCell(r, role) + '</td>' +
        '</tr>';
    });
    body += '</tbody>';

    var shell = '';
    if (role === 'bowler') {
      shell += filtersBar(name, {
        placeholder: 'Search the 36 eligible bowlers',
        tiers: true, formats: true, minBalls: true,
        segmented: [{ filter: 'scope', value: 'published', label: 'Published (10)' },
                    { filter: 'scope', value: 'all', label: 'All eligible (36)' }],
        segmentedLabel: 'Scope'
      });
    } else {
      shell += filtersBar(name, {
        placeholder: 'Search the 8 eligible batters',
        tiers: true, formats: true, minBalls: true
      });
    }
    shell += '<div class="table-wrap"><table class="responsive" id="tbl-' + name + '">' + header + body + '</table></div>';
    return shell;
  }

  function stabilityCell(row, role) {
    var stab = stabilityById[role + '|' + row.player_id];
    if (role === 'bowler') {
      if (row.bootstrap_share_top10 === null || row.bootstrap_share_top10 === undefined) return '<span class="muted">—</span>';
      return pct(row.bootstrap_share_top10);
    }
    if (!stab) return '<span class="muted">—</span>';
    return stab.rank_median + ' <span class="muted">(' + stab.rank_p05 + '–' + stab.rank_p95 + ')</span>';
  }

  function viewBowlers() {
    return '<section class="section">' + rankingTable('bowler', 'bowlers') + '</section>' +
      '<section class="section"><div class="chart-card"><h3>All ten intervals contain zero</h3>' +
      '<p class="cap">Dot = point estimate · bar = 90% interval · vertical line = league average in pressure.</p>' +
      intervalChart(DATA.rankings.bowler_chase.map(function (r) { return Object.assign({}, r, { displayRank: r.rank }); })) +
      '<p class="small muted">Every interval crosses zero and every adjacent pair overlaps. Read the set, not the order.</p></div></section>' +
      '<section class="section"><div class="grid cols-2">' +
      '<div class="chart-card"><h3>Reliability is not merit</h3><p class="cap">The 36 eligible bowlers: performance on one axis, reliability on the other. Bubble size = pressure deliveries.</p>' +
      scatterChart(eligibleBowlers) +
      '<p class="small muted">A high reliability only means the record is more trustworthy; it says nothing about how good the player was. This is why the two are reported separately.</p></div>' +
      '<div class="card"><h4>How to read the table</h4>' +
      '<p class="small mt-2"><b>S*</b> is the published score. <b>A*</b> is shrunk pressure performance and <b>B*</b> is the same player’s baseline; the formula keeps 70% of pressure performance and charges 30% for general form.</p>' +
      '<p class="small"><b>B_A</b> answers a different question: how much of this record survives shrinkage? It decides eligibility and never enters the score. A player can be highly reliable and still average.</p>' +
      '<p class="small"><b>P(top 10)</b> is the share of 200 match-level resamples in which the player stayed in the top ten. It measures the fragility of the place, not the quality of the player.</p>' +
      '<p class="small muted mb-0">Click any row for the full breakdown, including the pressure-versus-baseline rates and the format split.</p></div>' +
      '</div></section>' +
      '<section class="section"><div class="callout amber"><h4>Why 36 eligible but only 10 published</h4>' +
      '<p>The published length is fixed at min(10, eligible) by the pre-registered rule, so the next 26 eligible bowlers are not "excluded" — they are simply outside the publication window. Switch the scope control above to <b>All eligible (36)</b> to see them, with the same filters and intervals.</p></div></section>';
  }

  function viewBatters() {
    return '<section class="section">' + rankingTable('batter', 'batters') +
      '<p class="small muted mt-1">Top-10 membership is 100% for every eligible batter by construction, because only eight are eligible — so the table shows the resampled rank range instead. It is wide: even the leader’s resampled rank spans 1–7.</p></section>' +
      '<section class="section"><div class="chart-card"><h3>Eight, and no more</h3>' +
      '<p class="cap">Every eligible batter is published. No player was promoted to reach ten.</p>' +
      intervalChart(DATA.rankings.batter_chase.map(function (r) { return Object.assign({}, r, { displayRank: r.rank }); }), { rowH: 34 }) +
      '<p class="small muted">All eight intervals contain zero and all eight are Limited tier. The list is a shortlist of the best-evidenced batter records, not a set of proven match-winners.</p></div></section>' +
      '<section class="section"><div class="card"><h4>Why the batter list is short</h4><h3 style="margin-top:6px">445 scored, 8 eligible</h3>' +
      '<p class="small mt-2">A batter needs a reliable pressure record, and reliability depends on volume and on how much the league varies between batters. Batter pressure variance is thinner than bowler pressure variance, so far fewer batters clear 0.20.</p>' +
      '<ul class="list small"><li>437 batters fall below the threshold; 41 have too few deliveries to estimate variance at all.</li>' +
      '<li>No batter reaches the Moderate tier.</li>' +
      '<li>Batter evidence is chase-only: no validated innings-1 batting pressure context exists.</li></ul>' +
      '<p class="small muted mb-0">Adding two more names would have required either a lower threshold or a weaker evidence rule. Neither was done.</p></div></section>' +
      '<section class="section"><div class="callout red"><h4>Do not describe this as a top 10</h4>' +
      '<p>Eight players are eligible. Publishing ten would mean publishing two names the rule does not support. Every deliverable — this dashboard, the deck and the PDF — states eight.</p></div></section>';
  }

  /* --------------------------------------------------------------- players */
  function viewPlayers() {
    var t = tableState('players', { sort: 'S_star', dir: -1, q: '', role: 'all', reason: 'all', page: 1 });
    var rows = [];
    DATA.pool.bowler_chase.concat(DATA.pool.batter_chase, DATA.pool.bowler_innings1).forEach(function (r) {
      rows.push(Object.assign({}, r));
    });
    var filtered = applyFilters(rows, t);
    filtered.sort(sorter(t.sort, t.dir));
    var limit = 60 * (t.page || 1);
    var shown = filtered.slice(0, limit);
    var header = '<thead><tr>' +
      sortButton('players', 'player_name', 'Player') +
      '<th>Role</th><th>Context</th>' +
      sortButton('players', 'S_star', 'S*', 'num') +
      sortButton('players', 'shrinkage_A', 'Reliability', 'num') +
      '<th>Tier</th><th>Status</th>' +
      sortButton('players', 'n_pressure', 'Pressure balls', 'num') +
      '</tr></thead>';
    var body = '<tbody>';
    shown.forEach(function (r) {
      var status = r.published_rank ? '<span class="chip good">Published #' + r.published_rank + '</span>'
        : (r.eligible ? '<span class="chip plain">Eligible, not published</span>'
          : '<span class="chip warn">Not eligible</span>');
      body += '<tr class="clickable" data-player="' + esc(r.player_id) + '" data-context="' + esc(r.context) + '" data-role="' + esc(r.role) + '" tabindex="0">' +
        '<td class="name" data-label="Player">' + esc(r.player_name) + '<span class="sub">ID ' + esc(r.player_id) + '</span></td>' +
        '<td data-label="Role">' + roleName(r.role) + '</td>' +
        '<td data-label="Context">' + contextName(r.context) + '</td>' +
        '<td class="num" data-label="S*">' + (r.S_star === null ? '—' : signed(r.S_star)) + '</td>' +
        '<td class="num" data-label="Reliability">' + num(r.shrinkage_A, 3) + '</td>' +
        '<td data-label="Tier">' + tierChip(r.evidence_tier) + '</td>' +
        '<td data-label="Status">' + status + '</td>' +
        '<td class="num" data-label="Pressure balls">' + num(r.n_pressure) + '</td>' +
        '</tr>';
    });
    body += '</tbody>';
    var more = filtered.length > shown.length
      ? '<button class="load-more" data-action="more-players">Show more (' + (filtered.length - shown.length) + ' remaining)</button>' : '';
    return '<section class="section">' +
      '<div class="filters">' +
      '<label class="search"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>' +
      '<input type="search" data-keep="players-search" data-filter-table="players" data-filter="q" placeholder="Search by name or player ID" value="' + esc(t.q || '') + '" aria-label="Search all players"></label>' +
      '<select class="select" data-filter-table="players" data-filter="role" aria-label="Role">' +
      ['all', 'bowler', 'batter'].map(function (v) {
        return '<option value="' + v + '"' + (t.role === v ? ' selected' : '') + '>' + (v === 'all' ? 'Both roles' : roleName(v)) + '</option>';
      }).join('') + '</select>' +
      '<div class="count-note" id="count-players">' + num(filtered.length) + ' rows</div></div>' +
      '<div class="table-wrap"><table class="responsive" id="tbl-players">' + header + body + '</table>' + more + '</div>' +
      '<p class="small muted mt-1">Includes every player-context row in all three contexts (1,277), including the 26 with too few deliveries to estimate variance. Click any row for the full breakdown.</p>' +
      '</section>';
  }

  /* --------------------------------------------------------------- formats */
  function viewFormats() {
    var f = DATA.format_summary;
    var iplBowlers = DATA.formats.filter(function (r) { return r.format_scope === 'IPL' && r.role === 'bowler'; });
    var iplBatters = DATA.formats.filter(function (r) { return r.format_scope === 'IPL' && r.role === 'batter'; });
    var t20 = DATA.formats.filter(function (r) { return r.format_scope === 'T20I'; });

    function mini(rows, role, scope) {
      var out = '<div class="table-wrap"><table class="responsive"><thead><tr>' +
        '<th class="num">#</th><th>Player</th>' +
        '<th class="num" data-tip="' + scope + '-only score: A* − 0.30·B* computed from the published ' + scope + '-only components.">' + scope + '-only S*</th>' +
        '<th class="num" data-tip="Reliability of the ' + scope + '-only pressure record. Decides eligibility for this list.">B_A (' + scope + ')</th>' +
        '<th data-tip="Whether the player also appears in the published combined list.">In combined</th>' +
        '<th class="num">' + scope + ' pressure balls</th></tr></thead><tbody>';
      if (!rows.length) out += '<tr><td colspan="6" class="muted" style="padding:20px 12px">No ' + scope + '-only player is eligible: between-player pressure variance is estimated at zero.</td></tr>';
      rows.forEach(function (r) {
        out += '<tr class="clickable" data-player="' + esc(r.player_id) + '" data-context="chase" data-role="' + role + '" tabindex="0">' +
          '<td class="num">' + r.rank + '</td><td class="name" data-label="Player">' + esc(r.player_name) + '</td>' +
          '<td class="num" data-label="' + scope + '-only S*">' + signed(r.S_star_format) + '</td>' +
          '<td class="num" data-label="B_A (' + scope + ')">' + num(r.shrinkage_A, 3) + '</td>' +
          '<td data-label="In combined">' + (r.in_combined_top ? '<span class="chip good">Yes</span>' : '<span class="chip plain">No</span>') + '</td>' +
          '<td class="num" data-label="' + scope + ' pressure balls">' + num(r.n_pressure) + '</td></tr>';
      });
      return out + '</tbody></table></div>';
    }

    return '<section class="section"><div class="grid cols-3">' +
      card('stat', '<div class="value pink">' + f.bowler.combined_top + '</div><div class="label">combined bowler list</div><div class="note">two-stage, format-aware</div>') +
      card('stat', '<div class="value">' + f.bowler.scopes.IPL.shared_with_combined + '/' + f.bowler.combined_top + '</div><div class="label">also in the IPL-only top 10</div><div class="note">' + f.bowler.scopes.IPL.rows_shown + ' IPL-only rows shown</div>') +
      card('stat', '<div class="value amber">0</div><div class="label">T20I-only players eligible</div><div class="note">in both roles</div>') +
      '</div></section>' +
      '<section class="section"><div class="callout amber"><h4>What the combination does and does not mean</h4>' +
      '<p>IPL and T20I were shrunk and validated separately, then combined by inverse-variance weights. The result is a <b>descriptive</b> combined estimate: it uses each player’s evidence in both formats but makes no claim that performance transfers between them. Because T20I between-player variance is estimated at zero in both roles, the T20I-only lists admit nobody and the combined list is mainly IPL-driven.</p></div></section>' +
      '<section class="section"><div class="section-head"><div><h2>Bowler · IPL only</h2><p>Ten rows published under the same rule restricted to IPL evidence. Six of these ten also appear in the combined list.</p></div></div>' +
      mini(iplBowlers, 'bowler', 'IPL') + '<p class="small muted mt-1">Ranked under the same rule applied to IPL-only components. Scores are a separate estimand and are not the combined scores shown elsewhere.</p></section>' +
      '<section class="section"><div class="section-head"><div><h2>Bowler · T20I only</h2><p>No eligible players. The estimate is not missing; it is empty because the between-player spread is zero.</p></div></div>' +
      mini(t20.filter(function (r) { return r.role === 'bowler'; }), 'bowler', 'T20I') + '</section>' +
      '<section class="section"><div class="section-head"><div><h2>Batter · IPL only</h2><p>Ten rows from 16 eligible. Six of these ten appear in the published eight.</p></div></div>' +
      mini(iplBatters, 'batter', 'IPL') + '<p class="small muted mt-1">Ranked under the same rule applied to IPL-only components. Scores are a separate estimand and are not the combined scores shown elsewhere.</p></section>' +
      '<section class="section"><div class="section-head"><div><h2>Batter · T20I only</h2><p>No eligible players, for the same reason.</p></div></div>' +
      mini(t20.filter(function (r) { return r.role === 'batter'; }), 'batter', 'T20I') + '</section>';
  }

  /* -------------------------------------------------------------- contexts */
  function viewContexts() {
    var bowlChase = DATA.pool.bowler_chase;
    var batChase = DATA.pool.batter_chase;
    var bowlInn = DATA.pool.bowler_innings1;
    var status = DATA.contexts;
    return '<section class="section"><div class="grid cols-3">' +
      status.map(function (c) {
        var colour = c.eligible ? (c.role === 'bowler' ? 'pink' : 'blue') : 'amber';
        return '<div class="card"><h4>' + roleName(c.role) + ' · ' + contextName(c.context) + '</h4>' +
          '<div class="stat" style="margin-top:8px"><div class="value ' + colour + '">' + c.eligible + '</div>' +
          '<div class="label">eligible of ' + num(c.scored) + ' scored</div>' +
          '<div class="note">' + (c.ranking_published ? 'Ranking published' : 'No ranking') + ' · max B_A ' + num(c.max_shrinkage, 3) + '</div></div>' +
          '<p class="small mt-2">' + esc(c.note) + '</p></div>';
      }).join('') + '</div></section>' +
      '<section class="section"><div class="grid cols-2">' +
      '<div class="chart-card"><h3>Reliability distribution · bowlers, chase</h3><p class="cap">' + num(bowlChase.length) + ' player rows, ' + num(DATA.headline.bowler_scored) + ' with a defined score. The 0.20 line is the approved gate.</p>' + histogramSvg(bowlChase.map(function (r) { return r.shrinkage_A; }), 0.20) + '</div>' +
      '<div class="chart-card"><h3>Reliability distribution · bowlers, innings 1</h3><p class="cap">' + num(bowlInn.length) + ' player rows, ' + num(DATA.headline.innings1_scored) + ' with a defined score. Nothing reaches the gate; the maximum is 0.150.</p>' + histogramSvg(bowlInn.map(function (r) { return r.shrinkage_A; }), 0.20) + '</div>' +
      '</div></section>' +
      '<section class="section"><div class="grid cols-2">' +
      '<div class="card"><h4>Innings-1 bowling</h4><h3 style="margin-top:6px">A finding, not a ranking</h3>' +
      '<p class="small mt-2">The flag marks the bowling side under pressure while the batting side is ahead of par. That definition is partly a description of the scoring environment: the same bowlers concede 1.61 runs per ball in this state versus 1.36 in others (Phase 3). Without a run-rate control the context cannot be read as pure bowling skill.</p>' +
      '<p class="small">The context is therefore kept separate, never merged with chase, and no player is ranked from it. It remains available for future work with a revised definition.</p>' +
      '<span class="chip warn">PH3-01 · state confounding</span> <span class="chip plain">F4-02 · no ranking</span></div>' +
      '<div class="card"><h4>Chase batting</h4><h3 style="margin-top:6px">One context, one role</h3>' +
      '<p class="small mt-2">Batters have exactly one validated pressure context: the chase. There is no validated innings-1 batting flag — the candidate union and collapse definitions failed difficulty validation and remain unused.</p>' +
      '<p class="small">The 445 scored batters and 8 eligible batters in this dashboard all come from that single context. No batter score mixes contexts.</p>' +
      '<span class="chip warn">PH2-05 · broad flags unused</span> <span class="chip plain">F4-01 · 8 eligible</span></div>' +
      '</div></section>' +
      '<section class="section"><div class="callout blue"><h4>Never merged</h4>' +
      '<p>There is no cross-context score anywhere in this project. A bowler’s chase score and innings-1 score are separate rows with separate populations, separate shrinkage and separate eligibility. The audit enforces this: a test scans the source tree for any cross-context combination.</p></div></section>';
  }

  /* -------------------------------------------------------------- excluded */
  function viewExcluded() {
    var t = tableState('excluded', { sort: 'shrinkage_A', dir: -1, q: '', role: 'all', reason: 'all', page: 1 });
    var rows = DATA.exclusions.slice();
    var filtered = applyFilters(rows, t);
    filtered.sort(sorter(t.sort, t.dir));
    var limit = 40 * (t.page || 1);
    var shown = filtered.slice(0, limit);

    var summary = DATA.exclusion_summary;
    var cards = summary.map(function (s) {
      return '<div class="card tight"><h4>' + roleName(s.role) + '</h4><div class="stat" style="margin-top:6px">' +
        '<div class="value" style="font-size:30px">' + num(s.count) + '</div>' +
        '<div class="label">' + esc(s.reason_label) + '</div></div>' +
        '<p class="small muted mt-1 mb-0">Reason code <code>' + esc(s.reason_code) + '</code></p></div>';
    }).join('');

    var header = '<thead><tr>' +
      sortButton('excluded', 'player_name', 'Player') +
      '<th>Role</th>' +
      sortButton('excluded', 'shrinkage_A', 'Reliability B_A', 'num') +
      sortButton('excluded', 'S_star', 'S*', 'num') +
      sortButton('excluded', 'n_pressure', 'Pressure balls', 'num') +
      '<th>Reason</th></tr></thead>';
    var body = '<tbody>';
    shown.forEach(function (r) {
      body += '<tr class="clickable" data-player="' + esc(r.player_id) + '" data-context="' + esc(r.context) + '" data-role="' + esc(r.role) + '" tabindex="0">' +
        '<td class="name" data-label="Player">' + esc(r.player_name) + '<span class="sub">ID ' + esc(r.player_id) + '</span></td>' +
        '<td data-label="Role">' + roleName(r.role) + '</td>' +
        '<td class="num" data-label="Reliability B_A">' + num(r.shrinkage_A, 3) + '</td>' +
        '<td class="num" data-label="S*">' + (r.S_star === null ? '—' : signed(r.S_star)) + '</td>' +
        '<td class="num" data-label="Pressure balls">' + num(r.n_pressure) + '</td>' +
        '<td data-label="Reason"><span class="chip ' + (r.reason_code === 'NO_VARIANCE' ? 'warn' : 'plain') + '">' +
        esc(r.reason_code === 'NO_VARIANCE' ? 'Too few deliveries' : 'Below 0.20') + '</span>' +
        '<div class="small muted mt-1">' + esc(r.reason_detail) + '</div></td></tr>';
    });
    body += '</tbody>';
    var more = filtered.length > shown.length
      ? '<button class="load-more" data-action="more-excluded">Show more (' + (filtered.length - shown.length) + ' remaining)</button>' : '';

    return '<section class="section"><div class="grid cols-4">' + cards + '</div></section>' +
      '<section class="section"><div class="callout blue"><h4>Exclusion is not a verdict on the player</h4>' +
      '<p>The threshold asks one question: is there enough evidence to publish a pressure score? A player below 0.20 may be excellent; the record simply cannot support a claim. The rule was fixed in Phase 4 and reused unchanged in Phase 5. Nothing here is a list of "bad" players.</p></div></section>' +
      '<section class="section">' +
      '<div class="filters">' +
      '<label class="search"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>' +
      '<input type="search" data-keep="excluded-search" data-filter-table="excluded" data-filter="q" placeholder="Search ' + DATA.exclusions.length + ' excluded players" value="' + esc(t.q || '') + '" aria-label="Search excluded players"></label>' +
      '<select class="select" data-filter-table="excluded" data-filter="role" aria-label="Role">' +
      ['all', 'bowler', 'batter'].map(function (v) {
        return '<option value="' + v + '"' + (t.role === v ? ' selected' : '') + '>' + (v === 'all' ? 'Both roles' : roleName(v)) + '</option>';
      }).join('') + '</select>' +
      '<select class="select" data-filter-table="excluded" data-filter="reason" aria-label="Reason">' +
      '<option value="all"' + (t.reason === 'all' ? ' selected' : '') + '>All reasons</option>' +
      '<option value="SHRINKAGE_BELOW_0.20"' + (t.reason === 'SHRINKAGE_BELOW_0.20' ? ' selected' : '') + '>Below 0.20 reliability</option>' +
      '<option value="NO_VARIANCE"' + (t.reason === 'NO_VARIANCE' ? ' selected' : '') + '>Too few deliveries</option>' +
      '</select>' +
      '<div class="count-note" id="count-excluded">' + num(filtered.length) + ' players</div></div>' +
      '<div class="table-wrap"><table class="responsive" id="tbl-excluded">' + header + body + '</table>' + more + '</div>' +
      '<p class="small muted mt-1">Exclusion reasons are recorded for the chase context only. The innings-1 context has no eligible players at all, so it is covered in Contexts instead.</p>' +
      '</section>';
  }

  /* ----------------------------------------------------------- uncertainty */
  function viewUncertainty() {
    var sep = DATA.separation.filter(function (r) { return r.role === 'bowler'; });
    var boot = DATA.rankings.bowler_chase;
    var sensitivityRows = DATA.sensitivity.filter(function (r) {
      return r.role === 'bowler' && ['primary', 'w_0.30', 'w_0.50', 'tau2_REML', 'single_stage_combination', 'format_IPL', 'variance_E1'].indexOf(r.scenario) !== -1;
    }).map(function (r) { return Object.assign({}, r, { denominator: 10 }); });
    return '' +
      '<section class="section"><div class="grid cols-4">' +
      card('stat', '<div class="value pink">10/10</div><div class="label">intervals contain zero</div><div class="note">no bowler is separated from average</div>') +
      card('stat', '<div class="value pink">9/9</div><div class="label">adjacent pairs overlap</div><div class="note">ranks 2 and 3 differ by 0.00008</div>') +
      card('stat', '<div class="value blue">0.37</div><div class="label">average interval width</div><div class="note">gaps between ranks are 0.001–0.077</div>') +
      card('stat', '<div class="value">40–100%</div><div class="label">bootstrap P(top 10)</div><div class="note">top three 96–100%, ranks 6–10 40–55%</div>') +
      '</div></section>' +

      '<section class="section"><div class="grid cols-2">' +
      '<div class="chart-card"><h3>Adjacent ranks are separated by a hair</h3><p class="cap">Gap in S* between neighbouring ranks against the average 90% interval width.</p>' + separationSvg(sep) + '</div>' +
      '<div class="chart-card"><h3>What resampling does to each place</h3><p class="cap">Match-block bootstrap, 200 resamples, empirical-Bayes fit held fixed. Bars show the share kept in the top 10.</p>' + bootstrapSvg(boot) + '</div>' +
      '</div></section>' +

      '<section class="section"><div class="grid cols-2">' +
      '<div class="chart-card"><h3>What survives a change of method</h3><p class="cap">Names retained from the published ten under each alternative specification.</p>' + sensitivitySvg(sensitivityRows) +
      '<p class="small muted">The score weight barely moves the list. The rejected E1 variance estimator admits 307 bowlers and replaces all ten names; the single-stage combination keeps two.</p></div>' +
      '<div class="card"><h4>How to state this honestly</h4>' +
      '<p class="small mt-2"><b>Say:</b> “These eighteen players have pressure evidence strong enough to publish under a pre-registered rule. The bowler top three are stable under resampling; the rest of the order is not.”</p>' +
      '<p class="small"><b>Do not say:</b> “The best T20 bowlers in the world”, “the data proves X is the most clutch”, or present the list as a podium.</p>' +
      '<p class="small"><b>Always attach:</b> the evidence tier, the 90% interval, the eligible pool size, and the note that the score is situation-adjusted rather than raw economy.</p>' +
      '<p class="small muted mb-0">The bootstrap uses a fixed empirical-Bayes fit: it measures the fragility of the ranking conditional on the chosen model, not model uncertainty itself. That limitation is disclosed in the deck and the PDF.</p></div>' +
      '</div></section>' +

      '<section class="section"><div class="callout amber"><h4>Sensitivity cuts both ways</h4>' +
      '<p>Two changes leave the list almost intact (score weight, REML). Three do not (single-stage combination, IPL-only, E1 variance). Reporting only the first group would be cherry-picking. All seven specifications are shown, including the one that removes every published name.</p></div></section>';
  }

  /* ---------------------------------------------------------------- method */
  function viewMethod() {
    var defs = DATA.definitions;
    var order = ['pressure', 'performance', 'reliability', 'selection', 'uncertainty'];
    var cards = order.map(function (key) {
      var d = defs[key];
      return '<div class="card"><h4>' + esc(d.title) + '</h4><p class="small mt-2">' + esc(d.body) + '</p><ul class="list small">' +
        d.bullets.map(function (b) { return '<li>' + esc(b) + '</li>'; }).join('') + '</ul></div>';
    }).join('');
    return '<section class="section"><div class="formula">S* = <b>A*</b> − 0.30 · B* &nbsp;&nbsp;|&nbsp;&nbsp; eligible if <b>B_A</b> ≥ 0.20 &nbsp;&nbsp;|&nbsp;&nbsp; length = min(10, eligible)</div>' +
      '<p class="small muted mt-1">A* = shrunk pressure performance · B* = same player’s non-pressure baseline · B_A = reliability of the pressure record. Reliability is never multiplied into the score.</p></section>' +
      '<section class="section"><div class="grid cols-2">' + cards + '</div></section>' +
      '<section class="section"><div class="section-head"><div><h2>Thresholds and settings</h2><p>All values are the approved Phase 4 settings, unchanged in Phase 5 and Phase 6.</p></div></div>' +
      '<div class="table-wrap"><table><tbody>' +
      row('Eligibility threshold', 'B_A ≥ 0.20') +
      row('Evidence tiers', 'Limited 0.20–0.30 · Moderate 0.30–0.50 · High ≥ 0.50') +
      row('Performance score', 'S* = A* − 0.30·B* (score weight w = 0.70)') +
      row('Context model minimum cell', '200 observations, with a fixed back-off hierarchy') +
      row('Wicket bin cap', '3+ wickets treated as one bin') +
      row('Between-player variance', 'DerSimonian–Laird, fitted separately per role × context × format × component') +
      row('Shrinkage sample floor', '20 deliveries (KMIN)') +
      row('Bootstrap', '200 match-block resamples, seed 20261122, fixed EB fit') +
      row('Eligibility rule origin', 'Phase 4 (SDR-2026-11-18-02), reused unchanged') +
      row('Ranking rule origin', 'Pre-registered before calculation (SDR-2026-11-18-03)') +
      '</tbody></table></div></section>' +
      '<section class="section"><div class="section-head"><div><h2>Known limitations</h2><p>Every one of these is carried into the deck and the PDF, with the same status.</p></div></div>' +
      DATA.issues.map(issueCard).join('') + '</section>';
  }

  function row(k, v) {
    return '<tr><td style="width:34%;color:var(--ink-soft)">' + esc(k) + '</td><td>' + esc(v) + '</td></tr>';
  }

  function issueCard(i) {
    var cls = i.severity === 'High' ? 'bad' : i.severity === 'Medium' ? 'warn' : 'plain';
    return '<div class="issue"><div class="issue-head"><span class="issue-id">' + esc(i.id) + '</span>' +
      '<span class="chip ' + cls + '">' + esc(i.severity) + '</span>' +
      '<span class="small muted">' + esc(i.status) + '</span></div>' +
      '<h3 style="font-size:15px">' + esc(i.title) + '</h3>' +
      '<p class="mt-1">' + esc(i.detail) + '</p>' +
      '<p class="plain">In plain words: ' + esc(i.plain) + '</p>' +
      '<p class="small muted mb-0">Treatment: ' + esc(i.treatment) + '</p></div>';
  }

  /* ------------------------------------------------------------------ data */
  function viewData() {
    var v = DATA.verification;
    var internal = v.internal.map(function (c) {
      return '<tr><td class="mono" style="font-size:12px">' + esc(c.check) + '</td><td><span class="chip ' +
        (c.result === 'PASS' ? 'good' : 'bad') + '">' + esc(c.result) + '</span></td><td class="small muted">' + esc(c.detail || '') + '</td></tr>';
    }).join('');
    var independent = v.independent.map(function (c) {
      return '<tr><td class="mono" style="font-size:12px">' + esc(c.check || c.name || '') + '</td><td><span class="chip ' +
        ((c.passed === false || c.result === 'FAIL') ? 'bad' : 'good') + '">' + esc(c.result || 'PASS') + '</span></td><td class="small muted">' + esc(c.detail || '') + '</td></tr>';
    }).join('');
    var hashes = Object.keys(DATA.provenance.frozen_hashes).map(function (k) {
      return '<tr><td class="mono" style="font-size:12px;word-break:break-all">' + esc(k) + '</td><td class="mono small" style="word-break:break-all">' +
        esc(DATA.provenance.frozen_hashes[k].slice(0, 16)) + '…</td></tr>';
    }).join('');
    return '' +
      '<section class="section"><div class="grid cols-3">' +
      card('stat', '<div class="value" style="font-size:30px">15/15</div><div class="label">internal validation checks</div><div class="note">Phase 5 gate</div>') +
      card('stat', '<div class="value" style="font-size:30px">' + v.independent_checks + '/' + v.independent_checks + '</div><div class="label">independent checks</div><div class="note">separate implementation, no project imports</div>') +
      card('stat', '<div class="value" style="font-size:30px">' + (v.frozen_inputs_unchanged ? 'TRUE' : 'FALSE') + '</div><div class="label">frozen inputs unchanged</div><div class="note">SHA-256 before and after the Phase 5 run</div>') +
      '</div></section>' +
      '<section class="section"><div class="callout green"><h4>How every number here can be checked</h4>' +
      '<p>The dashboard reads a single generated payload. That payload is copied field by field from the frozen Phase 5 CSVs, and a test recomputes every displayed ranking from those CSVs and compares it with this page’s data. Nothing on this page is typed by hand.</p></div></section>' +
      '<section class="section"><div class="section-head"><div><h2>Phase 5 verification</h2><p>15 internal checks on the published files and 14 independent checks against a separate implementation.</p></div></div>' +
      '<div class="table-wrap"><table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead><tbody>' + internal + '</tbody></table></div></section>' +
      '<section class="section"><div class="table-wrap"><table><thead><tr><th>Independent check</th><th>Result</th><th>Detail</th></tr></thead><tbody>' + independent + '</tbody></table></div></section>' +
      '<section class="section"><div class="section-head"><div><h2>Player identity (F5-01)</h2><p>The upstream name defect and how display names were resolved without touching frozen scores.</p></div></div>' +
      '<div class="grid cols-2"><div class="card"><h4>The defect</h4><p class="small mt-2"><code>data/processed/players_dim.csv</code> pairs <code>dismissed_player_id</code> with <code>striker_name</code>, so some rows carry multiple display names. A Phase 4 name column can therefore show several names for one ID.</p>' +
      '<p class="small">Identifiers were never affected: 0 of 959 delivery IDs map to more than one name, and the raw competition mapping gives exactly one name per ID.</p></div>' +
      '<div class="card"><h4>The treatment</h4><p class="small mt-2">Display names resolve from <code>data/raw/Data Pack/competition_team_player_mapping.csv</code> through the Phase 5 identity file (' +
      num(DATA.identity.total_rows) + ' rows, ' + DATA.identity.ok + ' OK, ' + DATA.identity.variants.length + ' name variant). Phase 4 score files and Phase 5 rankings are unchanged.</p>' +
      '<p class="small">Seven display names are carried by two IDs each in the source (' + DATA.identity.duplicate_name_count + ' names, ' + (DATA.identity.duplicate_name_count * 2) + ' IDs). None appears in a published ranking. The Phase 1 fix needs its own authorisation and was not attempted here.</p></div></div>' +
      '<p class="small muted mt-1">Name variant: ' + DATA.identity.variants.map(function (x) { return esc(x.name) + ' (ID ' + esc(x.player_id) + ')'; }).join(', ') + ' — mapping name differs from the scorecard spelling.</p>' +
      '</section>' +
      '<section class="section"><div class="section-head"><div><h2>Frozen input hashes</h2><p>Prefixes shown; full SHA-256 values are in <code>reports/audit_bundle/sha256_outputs.txt</code>.</p></div></div>' +
      '<div class="table-wrap"><table><thead><tr><th>File</th><th>SHA-256</th></tr></thead><tbody>' + hashes + '</tbody></table></div></section>' +
      '<section class="section"><div class="grid cols-2"><div class="card"><h4>What was rejected</h4><p class="small mt-2">The F2 fallback and the broad pressure flags were not used anywhere: they failed difficulty validation. A broad “pressure batter” flag also failed, so batter evidence is chase-only.</p></div>' +
      '<div class="card"><h4>Bootstrap designs</h4><p class="small mt-2">The pre-registered bootstrap that re-estimated the variance model was measured and rejected: it inflated eligible players to a median of 195 bowlers and 206 batters. The accepted design holds the empirical-Bayes fit fixed and resamples matches.</p></div></div></section>';
  }

  function separationSvg(rows) {
    var width = 640, height = 300;
    var padL = 48, padR = 16, padT = 24, padB = 48;
    var gaps = rows.slice(1).map(function (r) { return { label: '#' + (r.rank - 1) + '–#' + r.rank, gap: Math.max(r.gap_from_previous, 0) }; });
    var widths = rows.map(function (r) { return r.ci90_high - r.ci90_low; });
    var mean = widths.reduce(function (a, b) { return a + b; }, 0) / widths.length;
    var maxGap = Math.max.apply(null, gaps.map(function (g) { return g.gap; }).concat([mean]));
    var x = scaleLinear(-0.5, gaps.length - 0.5, padL, width - padR);
    var y = scaleLinear(0, maxGap * 1.08, height - padB, padT);
    var bw = (width - padL - padR) / gaps.length * 0.62;
    var out = '<svg class="chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Gaps between adjacent ranks">';
    gaps.forEach(function (g, i) {
      var cx = x(i);
      out += '<rect x="' + (cx - bw / 2) + '" y="' + y(g.gap) + '" width="' + bw + '" height="' + (height - padB - y(g.gap)) + '" fill="var(--pink)" rx="2"/>';
      out += '<text class="axis-tick" x="' + cx + '" y="' + (y(g.gap) - 5) + '" text-anchor="middle">' + g.gap.toFixed(4) + '</text>';
      out += '<text class="axis-tick" x="' + cx + '" y="' + (height - padB + 15) + '" text-anchor="middle">' + g.label + '</text>';
    });
    out += '<line x1="' + padL + '" y1="' + y(mean) + '" x2="' + (width - padR) + '" y2="' + y(mean) + '" stroke="var(--blue)" stroke-width="1.2" stroke-dasharray="4 3"/>';
    out += '<text class="axis-tick" x="' + (width - padR) + '" y="' + (y(mean) - 6) + '" text-anchor="end" fill="var(--blue)">average interval width ' + mean.toFixed(2) + '</text>';
    out += '<text class="axis-label" x="' + (width / 2) + '" y="' + (height - 8) + '" text-anchor="middle">adjacent rank pair</text>';
    out += '<text class="axis-label" x="13" y="' + (height / 2) + '" text-anchor="middle" transform="rotate(-90 13 ' + (height / 2) + ')">gap in S*</text>';
    out += '</svg>';
    return out;
  }

  /* ----------------------------------------------------------------- router */
  var VIEWS = {
    overview: viewOverview,
    bowlers: viewBowlers,
    batters: viewBatters,
    players: viewPlayers,
    formats: viewFormats,
    contexts: viewContexts,
    excluded: viewExcluded,
    uncertainty: viewUncertainty,
    method: viewMethod,
    data: viewData
  };

  function render() {
    state.view = (location.hash.replace('#/', '') || 'overview');
    if (!VIEWS[state.view]) state.view = 'overview';
    renderNav();
    renderHero();
    app.innerHTML = '<div class="view active">' + VIEWS[state.view]() + '</div>';
    updateCounts();
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }

  function updateCounts() {
    var t = state.tables;
    if (state.view === 'bowlers' && t.bowlers) {
      setCount('bowlers', countRanking(eligibleBowlers, t.bowlers));
    }
    if (state.view === 'batters' && t.batters) {
      setCount('batters', countRanking(eligibleBatters, t.batters));
    }
    if (state.view === 'players' && t.players) {
      var rows = DATA.pool.bowler_chase.concat(DATA.pool.batter_chase, DATA.pool.bowler_innings1);
      setCount('players', num(applyFilters(rows, t.players).length) + ' rows');
    }
    if (state.view === 'excluded' && t.excluded) {
      setCount('excluded', num(applyFilters(DATA.exclusions, t.excluded).length) + ' players');
    }
  }
  function countRanking(all, t) {
    var rows = all.filter(function (r) { return t.scope === 'all' || r.published_rank; });
    return num(applyFilters(rows, t).length) + ' of ' + num(rows.length) + ' shown';
  }
  function setCount(name, text) {
    var node = document.getElementById('count-' + name);
    if (node) node.textContent = text;
  }

  /* ----------------------------------------------------------------- events */
  function rerenderKeepFocus() {
    var active = document.activeElement;
    var keep = active && active.getAttribute('data-keep');
    var pos = active && active.selectionStart;
    render();
    if (keep) {
      var next = document.querySelector('[data-keep="' + keep + '"]');
      if (next) {
        next.focus();
        try { next.setSelectionRange(pos, pos); } catch (e) { /* not a text input */ }
      }
    }
  }

  document.addEventListener('click', function (event) {
    var sortEl = event.target.closest('[data-sort]');
    if (sortEl) {
      var tname = sortEl.getAttribute('data-sort-table');
      var key = sortEl.getAttribute('data-sort');
      var t = state.tables[tname];
      if (t.sort === key) t.dir = -t.dir; else { t.sort = key; t.dir = 1; }
      if (tname === 'excluded' || tname === 'players') t.page = 1;
      render();
      return;
    }
    var filterEl = event.target.closest('[data-filter]');
    if (filterEl && filterEl.tagName === 'BUTTON') {
      var ft = state.tables[filterEl.getAttribute('data-filter-table')];
      ft[filterEl.getAttribute('data-filter')] = filterEl.getAttribute('data-value');
      ft.page = 1;
      render();
      return;
    }
    var actionEl = event.target.closest('[data-action]');
    if (actionEl) {
      var action = actionEl.getAttribute('data-action');
      if (action === 'more-players') { state.tables.players.page += 1; render(); }
      if (action === 'more-excluded') { state.tables.excluded.page += 1; render(); }
      return;
    }
    var rowEl = event.target.closest('[data-player]');
    if (rowEl) {
      openPlayer(rowEl.getAttribute('data-player'), rowEl.getAttribute('data-context'), rowEl.getAttribute('data-role'), rowEl);
      return;
    }
    if (event.target.id === 'scrim' || event.target.closest('.drawer-close')) closeDrawer();
  });

  document.addEventListener('change', function (event) {
    var el = event.target.closest('[data-filter]');
    if (!el) return;
    var t = state.tables[el.getAttribute('data-filter-table')];
    t[el.getAttribute('data-filter')] = el.value;
    t.page = 1;
    render();
  });

  document.addEventListener('input', function (event) {
    var el = event.target.closest('input[data-filter]');
    if (!el) return;
    var t = state.tables[el.getAttribute('data-filter-table')];
    t[el.getAttribute('data-filter')] = el.value;
    t.page = 1;
    rerenderKeepFocus();
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closeDrawer();
    if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[data-player]')) {
      event.preventDefault();
      openPlayer(event.target.getAttribute('data-player'), event.target.getAttribute('data-context'),
        event.target.getAttribute('data-role'), event.target);
    }
  });

  window.addEventListener('hashchange', render);

  /* ----------------------------------------------------------------- drawer */
  function findRow(id, context, role) {
    var base = byId[id + '|' + role + '|' + context];
    if (base) return base;
    var pool = role === 'bowler'
      ? DATA.pool.bowler_chase.concat(DATA.pool.bowler_innings1)
      : DATA.pool.batter_chase;
    return pool.filter(function (r) {
      return r.player_id === id && r.role === role && r.context === context;
    })[0];
  }

  function openPlayer(id, context, role, trigger) {
    var row = findRow(id, context, role);
    if (!row) return;
    var pub = null;
    DATA.rankings.bowler_chase.concat(DATA.rankings.batter_chase).forEach(function (p) {
      if (p.player_id === id && p.context === context) pub = p;
    });
    var stab = stabilityById[role + '|' + id] || null;
    var excl = exclusionByKey[id + '|' + role + '|' + context] || null;
    var isBatter = role === 'batter';
    var statusChip = pub ? '<span class="chip good">Published #' + pub.rank + '</span>'
      : (row.eligible ? '<span class="chip plain">Eligible · outside published length</span>'
        : '<span class="chip warn">Not eligible</span>');
    var html = '<div class="drawer-head"><div>' +
      '<div class="small muted">' + roleName(role) + ' · ' + contextName(context) + ' · ID ' + esc(id) + '</div>' +
      '<h2>' + esc(row.player_name) + '</h2>' +
      '<div class="meta">' + formatChip(row.formats_present) + ' ' + statusChip + '</div></div>' +
      '<button class="drawer-close" aria-label="Close" data-action="close">×</button></div>';

    if (row.S_star !== null && row.S_star !== undefined) {
      html += '<div class="score-big"><span class="n" style="color:' + (row.S_star >= 0 ? 'var(--pink)' : 'var(--ink)') + '">' +
        signed(row.S_star) + '</span><span class="small">Performance Score S*<br>90% interval ' + ciText(row) + '</span></div>' +
        '<p class="small">' + esc(pub ? pub.score_explanation : buildExplanation(row)) + '</p>';
      html += '<div class="grid-mini">' +
        miniStat('A* pressure', signed(row.A_star)) +
        miniStat('B* baseline', signed(row.B_star)) +
        miniStat('D* = A* − B*', signed(row.D_star)) +
        miniStat('Tier', tierChip(row.evidence_tier)) +
        '</div>';
    } else {
      html += '<div class="callout amber mt-2"><p>' + esc(row.exclusion_detail || 'This player has no publishable pressure score in this context.') + '</p></div>';
    }

    html += '<h4>Reliability of evidence</h4><div class="grid-mini">' +
      miniStat('Reliability B_A', num(row.shrinkage_A, 3)) +
      miniStat('Pressure deliveries', num(row.n_pressure)) +
      miniStat('Pressure matches', num(row.pressure_matches)) +
      miniStat('Total matches', num(row.total_matches)) +
      miniStat('Match consistency', row.consistency_matches ? pct(row.consistency_positive_share) + ' of ' + row.consistency_matches + ' matches' : '—') +
      miniStat('Status', esc(row.reliability_status || '—')) +
      '</div>';

    html += '<h4>Under pressure vs baseline</h4><div class="grid-mini">' +
      miniStat(isBatter ? 'Runs per ball' : 'Runs conceded per ball',
        num(row.pressure_runs_per_ball, 2) + ' vs ' + num(row.runs_per_ball_baseline, 2)) +
      miniStat('Dot ball %', num(row.pressure_dot_pct, 1) + '% vs ' + num(row.baseline_dot_pct, 1) + '%') +
      miniStat(isBatter ? 'Dismissals' : 'Wickets', num(isBatter ? row.pressure_dismissals : row.pressure_wickets)) +
      miniStat('Boundary %', num(row.pressure_boundary_pct, 1) + '% vs ' + num(row.baseline_boundary_pct, 1) + '%') +
      '</div><p class="small muted">Raw descriptive rates. The score itself uses situation-adjusted residuals, not these rates.</p>';

    html += '<h4>Format split</h4><div class="grid-mini">' +
      miniStat('IPL · A*', row.A_star_IPL === null ? '—' : signed(row.A_star_IPL)) +
      miniStat('IPL · pressure balls', num(row.n_pressure_IPL)) +
      miniStat('T20I · A*', row.A_star_T20I === null ? 'not estimable' : signed(row.A_star_T20I)) +
      miniStat('T20I · pressure balls', num(row.n_pressure_T20I)) +
      '</div>';
    if (row.A_star_T20I === null) {
      html += '<p class="small muted">T20I between-player variance is estimated at zero for this role, so no T20I-only score exists. The combined score is descriptive, not evidence of transferability.</p>';
    }

    if (stab) {
      html += '<h4>Bootstrap stability</h4><div class="grid-mini">' +
        miniStat('P(kept in top 10)', pct(stab.share_top10)) +
        miniStat('Median resampled rank', stab.rank_median) +
        miniStat('5–95% rank range', stab.rank_p05 + '–' + stab.rank_p95) +
        miniStat('Resamples scored', num(stab.replicates_scored)) +
        '</div><p class="small muted">Match-block bootstrap, fixed empirical-Bayes fit. A wide rank range means the position is fragile, not that the player is worse.</p>';
    }

    if (excl) {
      html += '<h4>Why not published</h4><div class="callout ' + (excl.reason_code === 'NO_VARIANCE' ? 'amber' : 'blue') + '">' +
        '<p>' + esc(excl.reason_detail) + '</p></div>';
    }

    html += '<h4>What this means</h4><p class="small">' + plainMeaning(row, pub, isBatter) + '</p>' +
      '<p class="small muted">This card reports a point estimate and its uncertainty. It is not a prediction of future performance and it does not compare players across the two contexts.</p>';

    drawerBody.innerHTML = html;
    lastFocus = trigger || document.activeElement;
    drawer.classList.add('open');
    scrim.classList.add('open');
    document.body.style.overflow = 'hidden';
    var close = drawer.querySelector('.drawer-close');
    if (close) close.focus();
  }

  function miniStat(label, value) {
    return '<div><dt>' + label + '</dt><dd>' + value + '</dd></div>';
  }

  function buildExplanation(row) {
    var a = row.A_star, b = row.B_star, s = row.S_star;
    if (a === null || b === null) return '';
    var penalty = -0.30 * b;
    return 'A* ' + signed(a) + ' (pressure residual, positive = better), B* ' + signed(b) +
      ' (baseline), S* = ' + signed(a) + ' − 0.30 × ' + signed(b) + ' = ' + signed(s) +
      '; shrinkage B_A ' + num(row.shrinkage_A, 3) + ' (' + row.evidence_tier + ' evidence).';
  }

  function plainMeaning(row, pub, isBatter) {
    if (!row.eligible && !pub) {
      return 'This player does not have enough reliable pressure evidence to publish a score. That is a statement about the sample, not about ability.';
    }
    var who = isBatter ? 'batter' : 'bowler';
    var base = 'As a ' + who + ', this player was ' + (row.S_star >= 0 ? 'better' : 'worse') +
      ' than the league expectation on pressure deliveries (' + signed(row.A_star) + '), after a ' +
      (row.B_star >= 0 ? 'positive' : 'negative') + ' general-form adjustment.';
    var reliability = ' The evidence is ' + row.evidence_tier.toLowerCase() + ' (B_A ' + num(row.shrinkage_A, 3) + '), and the 90% interval ' +
      ciText(row) + (row.S_ci90_low <= 0 && row.S_ci90_high >= 0 ? ' includes zero, so average performance cannot be ruled out.' : ' excludes zero.');
    var order = pub ? ' The published position is an ordering of point estimates inside the eligible set; it is not a claim of superiority over the next name.' : ' The player is eligible but outside the fixed publication length of ten.';
    return base + reliability + order;
  }

  function closeDrawer() {
    if (!drawer.classList.contains('open')) return;
    drawer.classList.remove('open');
    scrim.classList.remove('open');
    document.body.style.overflow = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  /* ---------------------------------------------------------------- tooltip */
  document.addEventListener('mouseover', function (event) {
    var el = event.target.closest('[data-tip]');
    if (!el) return;
    tooltip.textContent = el.getAttribute('data-tip');
    tooltip.classList.add('on');
    var rect = el.getBoundingClientRect();
    tooltip.style.left = Math.min(window.innerWidth - 300, Math.max(8, rect.left)) + 'px';
    tooltip.style.top = (rect.bottom + 8) + 'px';
  });
  document.addEventListener('mouseout', function (event) {
    if (event.target.closest('[data-tip]')) tooltip.classList.remove('on');
  });

  /* ------------------------------------------------------------------ start */
  render();
})();
