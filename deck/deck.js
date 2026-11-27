(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var state = { data: null, current: 1, notesOpen: false };

  function present(value) {
    return value !== null && value !== undefined && value !== '';
  }

  function tag() {
    var span = document.createElement('span');
    span.className = 'tag';
    span.textContent = '[28 Nov]';
    return span;
  }

  function fill(node, value, formatter) {
    node.textContent = '';
    if (!present(value)) {
      node.appendChild(tag());
      return;
    }
    node.textContent = formatter ? formatter(value) : String(value);
  }

  function percent(value) {
    if (typeof value !== 'number' || !isFinite(value)) return String(value);
    var digits = value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
    return (value > 0 ? '+' : '') + digits + '%';
  }

  function money(value) {
    return '$' + Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 });
  }

  function svgNode(name, attrs) {
    var node = document.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    return node;
  }

  function svgText(x, y, content, cls, anchor) {
    var node = svgNode('text', { x: x, y: y });
    if (anchor) node.setAttribute('text-anchor', anchor);
    node.setAttribute('dominant-baseline', 'middle');
    if (cls) node.setAttribute('class', cls);
    node.textContent = content;
    return node;
  }

  function svgTitle(svg, title, desc) {
    var t = svgNode('title');
    t.textContent = title;
    svg.appendChild(t);
    var d = svgNode('desc');
    d.textContent = desc;
    svg.appendChild(d);
  }

  function equityChart() {
    var equity = state.data.equity || [];
    if (!equity.length) return null;
    var spy = Array.isArray(state.data.spy) ? state.data.spy : [];
    var end = state.data.endDate || equity[equity.length - 1].date;
    var start = equity[0].date;
    var W = 1120, H = 300, L = 84, R = 192, T = 18, B = 46;
    var plotW = W - L - R, plotH = H - T - B;
    var values = equity.map(function (p) { return p.value; })
      .concat(spy.map(function (p) { return p.value; }), [100000]);
    var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    var step = 2000;
    var dmin = Math.floor((lo - 400) / step) * step;
    var dmax = Math.ceil((hi + 400) / step) * step;
    var t0 = Date.parse(start + 'T00:00:00Z');
    var t1 = Date.parse(end + 'T00:00:00Z');

    function x(date) {
      return L + (Date.parse(date + 'T00:00:00Z') - t0) / (t1 - t0) * plotW;
    }
    function y(value) {
      return T + (dmax - value) / (dmax - dmin) * plotH;
    }

    var svg = svgNode('svg', {
      viewBox: '0 0 ' + W + ' ' + H,
      class: 'chart',
      role: 'img'
    });
    svgTitle(svg,
      'Account value, ' + (state.data.chartLabel || ''),
      'Account value: ' + equity.map(function (p) {
        return p.label + ' ' + money(p.value);
      }).join('; ') + '. S&P 500: ' + (spy.length ? 'plotted as a muted line.' : '[28 Nov].'));

    for (var tick = dmin; tick <= dmax; tick += step) {
      svg.appendChild(svgNode('line', {
        x1: L - 5, y1: y(tick), x2: L, y2: y(tick), class: 'axis'
      }));
      svg.appendChild(svgText(L - 10, y(tick), money(tick), null, 'end'));
    }
    svg.appendChild(svgNode('line', { x1: L, y1: T, x2: L, y2: H - B, class: 'axis' }));
    svg.appendChild(svgNode('line', { x1: L, y1: H - B, x2: W - R, y2: H - B, class: 'axis' }));
    svg.appendChild(svgNode('line', {
      x1: L, y1: y(100000), x2: W - R, y2: y(100000), class: 'start'
    }));
    svg.appendChild(svgText(W - R + 12, y(100000), 'Start $100,000'));

    equity.forEach(function (point) {
      svg.appendChild(svgText(x(point.date), H - B + 24, point.label, null, 'middle'));
    });

    if (spy.length) {
      svg.appendChild(svgNode('polyline', {
        class: 'spy',
        points: spy.map(function (p) { return x(p.date) + ',' + y(p.value); }).join(' ')
      }));
    }

    svg.appendChild(svgNode('polyline', {
      class: 'equity',
      points: equity.map(function (p) { return x(p.date) + ',' + y(p.value); }).join(' ')
    }));
    equity.forEach(function (point) {
      svg.appendChild(svgNode('circle', { class: 'dot', cx: x(point.date), cy: y(point.value), r: 4 }));
    });

    var last = equity[equity.length - 1];
    svg.appendChild(svgText(x(last.date) + 12, y(last.value), 'Account ' + money(last.value), 'end-label'));
    if (spy.length) {
      var lastSpy = spy[spy.length - 1];
      svg.appendChild(svgText(x(lastSpy.date) + 12, y(lastSpy.value), 'S&P 500 ' + money(lastSpy.value)));
    }
    return svg;
  }

  function verdictChart() {
    var rows = state.data.verdict || [];
    if (!rows.length) return null;
    var W = 1120, H = 280, axisY = 190, maxBar = 130;
    var xs = [200, 560, 920];
    var values = rows.map(function (row) { return row.value; })
      .filter(function (v) { return typeof v === 'number' && isFinite(v); });
    var maxAbs = values.length ? Math.max.apply(null, values.map(Math.abs)) : 0;

    var svg = svgNode('svg', { viewBox: '0 0 ' + W + ' ' + H, class: 'verdict', role: 'img' });
    svgTitle(svg, 'News calls against two simple rules',
      rows.map(function (row) {
        return row.label + ': ' + (present(row.value) ? percent(row.value) : '[28 Nov]');
      }).join('; ') + '.');

    svg.appendChild(svgNode('line', { x1: 60, y1: axisY, x2: 1060, y2: axisY, class: 'axis' }));

    rows.forEach(function (row, index) {
      var cx = xs[index] || (200 + index * 360);
      var label = svgText(cx, axisY + 46, row.label, 'label', 'middle');
      svg.appendChild(label);

      if (!present(row.value) || typeof row.value !== 'number' || !maxAbs) {
        var missing = svgText(cx, axisY - 14, '[28 Nov]', 'tag', 'middle');
        svg.appendChild(missing);
        return;
      }
      var value = row.value;
      var height = Math.max(4, Math.abs(value) / maxAbs * maxBar);
      var positive = value >= 0;
      svg.appendChild(svgNode('rect', {
        x: cx - 45,
        y: positive ? axisY - height : axisY,
        width: 90,
        height: height,
        class: positive ? 'gain' : 'loss'
      }));
      var valueY = positive ? axisY - height - 14 : axisY + height + 22;
      svg.appendChild(svgText(cx, valueY, percent(value), 'value', 'middle'));
    });
    return svg;
  }

  function render() {
    var data = state.data;
    var chartLabel = document.getElementById('chart-label');
    if (chartLabel) chartLabel.textContent = data.chartLabel || '';
    document.querySelectorAll('[data-field]').forEach(function (node) {
      var key = node.getAttribute('data-field');
      var formatter = node.hasAttribute('data-percent') ? percent : null;
      fill(node, data[key], formatter);
    });
    fill(document.getElementById('wwd-exit'), data.wwdExit);
    fill(document.getElementById('credits'), data.credits);
    fill(document.getElementById('verdict-headline'), data.verdictHeadline);

    var chart = equityChart();
    var chartBox = document.getElementById('equity-chart');
    if (chartBox) {
      chartBox.textContent = '';
      if (chart) chartBox.appendChild(chart);
    }
    var spyNote = document.getElementById('spy-note');
    if (spyNote) {
      spyNote.textContent = '';
      if (!Array.isArray(data.spy) || !data.spy.length) {
        spyNote.appendChild(document.createTextNode('S&P 500 '));
        spyNote.appendChild(tag());
      }
    }

    var verdict = verdictChart();
    var verdictBox = document.getElementById('verdict-chart');
    if (verdictBox) {
      verdictBox.textContent = '';
      if (verdict) verdictBox.appendChild(verdict);
    }

    var body = document.getElementById('trades-body');
    if (body) {
      body.textContent = '';
      (data.trades || []).forEach(function (row) {
        var tr = document.createElement('tr');
        var stock = document.createElement('td');
        stock.className = 'stock';
        stock.textContent = row.ticker;
        tr.appendChild(stock);
        ['why', 'result', 'lesson'].forEach(function (key) {
          var cell = document.createElement('td');
          if (key === 'result' && row.resultTone === 'loss' && present(row.result)) {
            cell.className = 'loss';
          }
          fill(cell, row[key]);
          tr.appendChild(cell);
        });
        body.appendChild(tr);
      });
    }

    var bar = document.getElementById('alloc-bar');
    var list = document.getElementById('alloc-list');
    if (bar && list) {
      bar.textContent = '';
      list.textContent = '';
      var total = (data.allocation || []).reduce(function (sum, item) {
        return sum + (Number(item.value) || 0);
      }, 0) || 1;
      var description = [];
      (data.allocation || []).forEach(function (item, index) {
        var seg = document.createElement('div');
        seg.className = 'seg seg-' + index;
        seg.style.flex = String((Number(item.value) || 0) / total) + ' 1 0';
        bar.appendChild(seg);

        var entry = document.createElement('div');
        entry.className = 'item seg-' + index;
        var name = document.createElement('div');
        name.className = 'name';
        name.textContent = item.label + ' ';
        var amount = document.createElement('em');
        amount.textContent = item.valueLabel;
        name.appendChild(amount);
        entry.appendChild(name);
        if (item.detail) {
          var detail = document.createElement('div');
          detail.className = 'detail';
          detail.textContent = item.detail;
          entry.appendChild(detail);
        }
        list.appendChild(entry);
        description.push(item.label + ' ' + item.valueLabel);
      });
      bar.setAttribute('role', 'img');
      bar.setAttribute('aria-label', 'Planned split: ' + description.join(', '));
    }
  }

  function updateNotes() {
    var text = (state.data.notes || [])[state.current - 1];
    document.getElementById('notes-text').textContent =
      present(text) ? text : 'No speaker note for this slide.';
  }

  function show(number, updateHash) {
    var slides = document.querySelectorAll('.slide');
    var next = Math.max(1, Math.min(slides.length, number));
    state.current = next;
    slides.forEach(function (slide, index) {
      var active = index + 1 === next;
      slide.classList.toggle('active', active);
      slide.setAttribute('aria-hidden', active ? 'false' : 'true');
    });
    updateNotes();
    if (updateHash !== false) {
      try {
        history.replaceState(null, '', '#' + next);
      } catch (error) {
        location.hash = String(next);
      }
    }
  }

  function toggleNotes(force) {
    var panel = document.getElementById('notes');
    state.notesOpen = typeof force === 'boolean' ? force : !state.notesOpen;
    panel.hidden = !state.notesOpen;
    if (state.notesOpen) updateNotes();
  }

  function scale() {
    var factor = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
    document.documentElement.style.setProperty('--scale', String(factor));
  }

  function bind() {
    document.addEventListener('keydown', function (event) {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      var key = event.key;
      if (key === 'ArrowRight' || key === 'PageDown' || key === ' ') {
        event.preventDefault();
        show(state.current + 1);
      } else if (key === 'ArrowLeft' || key === 'PageUp') {
        event.preventDefault();
        show(state.current - 1);
      } else if (key === 'Home') {
        event.preventDefault();
        show(1);
      } else if (key === 'End') {
        event.preventDefault();
        show(999);
      } else if (key === 'p' || key === 'P') {
        toggleNotes();
      } else if (key === 'Escape' && state.notesOpen) {
        toggleNotes(false);
      }
    });

    document.addEventListener('click', function (event) {
      if (event.target.closest('.notes') || event.target.closest('a')) return;
      show(event.clientX < window.innerWidth / 2 ? state.current - 1 : state.current + 1);
    });

    window.addEventListener('hashchange', function () {
      var number = parseInt(String(location.hash).replace('#', ''), 10);
      if (isFinite(number)) show(number, false);
    });

    window.addEventListener('resize', scale);
  }

  function boot() {
    scale();
    var inline = document.getElementById('deck-data');
    var fallback = null;
    if (inline) {
      try {
        fallback = JSON.parse(inline.textContent);
      } catch (error) {
        fallback = null;
      }
    }
    var loaded = fetch('data.json', { cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('data.json unavailable');
        return response.json();
      })
      .catch(function () {
        if (!fallback) throw new Error('no deck data');
        return fallback;
      });

    loaded.then(function (data) {
      state.data = data;
      render();
      bind();
      var start = parseInt(String(location.hash).replace('#', ''), 10);
      show(isFinite(start) ? start : 1, false);
    }).catch(function (error) {
      var deck = document.querySelector('.deck');
      var message = document.createElement('p');
      message.style.cssText = 'padding:64px;font:20px/1.45 Georgia,serif;color:#2a2620';
      message.textContent = 'The deck data did not load. Check deck/data.json.';
      deck.appendChild(message);
      console.error(error);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
