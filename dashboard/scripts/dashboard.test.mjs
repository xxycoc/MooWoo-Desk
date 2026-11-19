import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { nextScheduledRun, regularHours, sgtTime, healthStatus, lastRuns, closedTradeScore, benchmarkSeries, streamPnl } = await server.ssrLoadModule('/src/data/dashboard.ts');
const { stateAt } = await server.ssrLoadModule('/src/data/state.ts');
const { viewFromHash } = await server.ssrLoadModule('/src/components/Nav.tsx');
const eventsOf = (rows) => rows.map((row, index) => ({ v: 1, runId: 'morning-test', seq: index + 1, gseq: index + 1, ts: '2026-11-19T15:00:00Z', decisionId: 'test-decision', file: 'test.jsonl', line: index + 1, drill: false, ...row }));
const health = (rows, now = '2026-11-19T15:00:00Z', desk) => {
  const events = eventsOf(rows);
  return healthStatus(events, lastRuns(events, stateAt(events, events.length)), new Date(now), desk);
};

test('desk snapshot alone controls red status, including silent restarts', () => {
  const desk = { halted: false, haltReason: '', tier: 'normal', updatedAt: '2026-11-19T14:59:00Z' };
  const halt = { type: 'halt', reason: 'state is halted' };
  assert.deepEqual(health([halt], undefined, desk), { tone: 'ok', message: 'Running normally' });
  assert.equal(health([halt]).tone, 'halt');
  const restarted = [halt, { type: 'run_started', ts: '2026-11-19T15:30:00Z', runId: 'next-watch' }];
  assert.equal(health(restarted, '2026-11-19T15:31:00Z', desk).tone, 'ok');
  assert.deepEqual(health(restarted, '2026-11-19T15:31:00Z', { ...desk, halted: true, haltReason: 'cash mismatch' }),
    { tone: 'halt', message: 'HALTED: cash mismatch' });
  assert.equal(health([], undefined, { ...desk, halted: true }).message, 'HALTED: reason not recorded');
  assert.equal(health([{ type: 'halt', cleared: true, reason: 'manual-restart' }], undefined, { ...desk, halted: true }).tone, 'halt');
});

test('cleared desk snapshot preserves abort and regular-hours staleness rules', () => {
  const desk = { halted: false, haltReason: '', tier: 'normal', updatedAt: null };
  assert.equal(health([{ type: 'run_aborted' }], undefined, desk).message, 'Latest run aborted');
  assert.equal(health([{ type: 'reflection_note', text: 'Session aborted: inputs missing' }], undefined, desk).tone, 'warn');
  const halt = { type: 'halt', reason: 'state is halted' };
  assert.equal(health([halt], '2026-11-19T15:45:00Z', desk).tone, 'ok');
  assert.equal(health([halt], '2026-11-19T15:45:01Z', desk).message, 'No event for more than 45 minutes during US regular hours');
  assert.equal(health([], '2026-11-21T15:45:01Z', desk).tone, 'ok');
  assert.equal(health([], '2026-11-19T21:00:00Z', desk).tone, 'ok');
});

test('mover radar reserves space beyond extreme bubbles and rings', async () => {
  const { bubbleOption } = await server.ssrLoadModule('/src/views/MoverRadar.tsx');
  const points = [-6, 6].map((value, index) => ({ ticker: 'ACM', decisionId: String(index), z: value,
    rvol: index ? 8 : 0.5, marketCap: 100, traded: true, picked: true }));
  const option = bubbleOption(points);
  assert(option.xAxis.min < -6 && option.xAxis.max > 6);
  assert(option.yAxis.min < 0.5 && option.yAxis.max > 8);
  const radius = Math.max(...option.series[0].data.map((point) => point.symbolSize / 2 + point.itemStyle.borderWidth));
  assert(option.grid.right > radius && option.grid.top > radius + 15);
});

test('schedule converts winter, summer, weekends and exact slots to SGT', () => {
  for (const [now, expected, kind] of [
    ['2026-11-19T14:30:00Z', '2026-11-19T14:35:00Z', 'Morning'],
    ['2026-07-20T13:30:00Z', '2026-07-20T13:35:00Z', 'Morning'],
    ['2026-11-19T15:00:00Z', '2026-11-19T15:30:00Z', 'Watcher'],
    ['2026-11-19T20:31:00Z', '2026-11-19T20:55:00Z', 'Close watcher'],
    ['2026-11-19T20:55:00Z', '2026-11-19T21:10:00Z', 'Audit'],
    ['2026-11-20T21:10:00Z', '2026-11-23T14:35:00Z', 'Morning'],
    ['2026-03-06T21:10:00Z', '2026-03-09T13:35:00Z', 'Morning'],
    ['2026-10-30T20:10:00Z', '2026-11-02T14:35:00Z', 'Morning'],
  ]) {
    const next = nextScheduledRun(new Date(now));
    assert.equal(next.at.toISOString(), new Date(expected).toISOString());
    assert.equal(next.kind, kind);
  }
  assert.match(sgtTime('2026-11-19T20:55:00Z'), /20 Nov.*04:55 SGT/);
});

test('November early close stops watchers and advances audit', () => {
  const next = nextScheduledRun(new Date('2026-11-27T17:30:00Z'));
  assert.equal(next.at.toISOString(), new Date('2026-11-27T17:55:00Z').toISOString());
  assert.equal(next.kind, 'Close watcher');
  assert.equal(nextScheduledRun(next.at).at.toISOString(), new Date('2026-11-27T18:10:00Z').toISOString());
  assert.equal(regularHours(new Date('2026-11-27T18:00:00Z')), false);
  assert.equal(regularHours(new Date('2026-11-27T17:59:00Z')), true);
});

test('only a cleared manual restart releases the latest halt', () => {
  const halted = [{ type: 'halt', reason: 'cash mismatch' }];
  assert.deepEqual(health(halted), { tone: 'halt', message: 'HALTED: cash mismatch' });
  assert.equal(health([...halted, { type: 'run_started', equity: 100000 }]).tone, 'halt');
  assert.equal(health([...halted, { type: 'halt', cleared: true, reason: 'automatic check' }]).tone, 'halt');
  assert.equal(health([...halted, { type: 'halt', cleared: true, reason: 'manual-restart: reconciled' }]).tone, 'ok');
  assert.equal(health([...halted, { type: 'halt', cleared: false, reason: 'manual-restart' }]).tone, 'halt');
  assert.equal(health([...halted, { type: 'halt', cleared: true, reason: 'manual-restart' }, { type: 'halt', reason: 'new halt' }]).tone, 'halt');
});

test('run-only halts never show HALTED once a later run starts or when they are input aborts', () => {
  const runHalt = { type: 'halt', reason: 'accounts.json: missing input file', ts: '2026-11-19T15:00:00Z' };
  assert.notEqual(health([runHalt, { type: 'run_started', runId: 'watch-next', ts: '2026-11-19T15:30:00Z' }], '2026-11-19T15:31:00Z').tone, 'halt');
  const inputAbort = { type: 'halt', reason: 'history.json: missing required broker field: qty', disposition: 'abort', stage: 'input_validation' };
  assert.equal(health([inputAbort, { type: 'reflection_note', text: 'Session aborted: reconcile failed' }]).tone, 'warn');
  const events = eventsOf([inputAbort]);
  const row = lastRuns(events, stateAt(events, events.length))[0];
  assert.equal(row.tone, 'warn');
  assert.match(row.result, /^aborted: /);
});

test('abort and staleness are amber, but staleness only during regular hours', () => {
  assert.equal(health([{ type: 'reflection_note', text: 'Session aborted; retained all evidence' }]).tone, 'warn');
  assert.equal(health([{ type: 'run_aborted', reason: 'offline' }, { type: 'run_started', runId: 'watch-next', ts: '2026-11-19T15:30:00Z' }], '2026-11-19T15:30:00Z').tone, 'ok');
  assert.equal(health([{ type: 'run_started' }], '2026-11-19T15:45:00Z').tone, 'ok');
  assert.equal(health([{ type: 'run_started' }], '2026-11-19T15:45:01Z').tone, 'warn');
  assert.equal(health([], '2026-11-19T15:45:01Z').tone, 'warn');
  assert.equal(health([], '2026-11-21T15:45:01Z').tone, 'ok');
  assert.equal(health([], '2026-11-19T21:00:00Z').tone, 'ok');
});

test('run rows include startless skips and aborts, not purchases from proposals', () => {
  const events = eventsOf([
    { type: 'run_started', equity: 100000 },
    { type: 'core_rebalance', orders: [{ ticker: 'SPY', qty: 10 }] },
    { type: 'reflection_note', text: 'Calendar skip', runId: 'watch-skip', ts: '2026-11-19T15:30:00Z' },
    { type: 'run_aborted', reason: 'network', runId: 'audit-failed', ts: '2026-11-19T21:10:00Z' },
  ]);
  const rows = lastRuns(events, stateAt(events, events.length));
  assert.deepEqual(rows.map((row) => row.result), ['aborted: network', 'calendar skip', 'ok']);
  assert.deepEqual(rows.map((row) => row.kind), ['Audit', 'Watcher', 'Morning']);
});

test('closed round trips include partial exits, fees and ignore duplicate cumulative fills', () => {
  const rows = [
    { type: 'order_intent', ticker: 'SPY', side: 'BUY', sleeve: 'core', qty: 10 },
    { type: 'order_submitted', ticker: 'SPY', orderId: 'buy', qty: 10, limitPrice: 100 },
    { type: 'fill', ticker: 'SPY', orderId: 'buy', filledQty: 10, avgPrice: 100 },
    { type: 'order_intent', ticker: 'SPY', side: 'SELL', sleeve: 'core', qty: 10 },
    { type: 'order_submitted', ticker: 'SPY', orderId: 'sell', qty: 10, limitPrice: 101 },
    { type: 'fill', ticker: 'SPY', orderId: 'sell', filledQty: 5, avgPrice: 101 },
    { type: 'fill', ticker: 'SPY', orderId: 'sell', filledQty: 5, avgPrice: 101 },
  ];
  assert.equal(closedTradeScore(eventsOf(rows)).count, 0);
  rows.push({ type: 'fill', ticker: 'SPY', orderId: 'sell', filledQty: 10, avgPrice: 101 });
  rows.push({ ...rows.at(-1) });
  const events = eventsOf(rows);
  const score = closedTradeScore(events);
  assert.equal(score.count, 1);
  assert.equal(score.wins, 1);
  assert(score.interval.lo < 0.5 && score.interval.hi > 0.5);
  assert.equal(lastRuns(events, stateAt(events, events.length))[0].result, 'bought SPY');
  const breakeven = eventsOf(rows.map((row) => row.type === 'fill' ? { ...row, avgPrice: 100 } : row));
  assert.equal(closedTradeScore(breakeven).wins, 0);
});

test('benchmarks are absent without audits, deduplicated by day and never fill missing values', () => {
  assert(benchmarkSeries([]).every((series) => !series.complete && !series.points.length));
  const series = benchmarkSeries(eventsOf([
    { type: 'daily_report', baselinePct: 1 },
    { type: 'daily_report', baselinePct: 2, ts: '2026-11-19T21:15:00Z' },
    { type: 'daily_report', baselinePct: -1, shadowPct: { follow: 1 }, ts: '2026-11-20T21:10:00Z' },
  ]));
  assert.equal(series[0].points.length, 2);
  assert.equal(series[0].points[0][1], 102);
  assert(Math.abs(series[0].points[1][1] - 100.98) < 0.001);
  assert.equal(series[1].points.length, 0);
  assert.equal(series[2].points.length, 0);
});

test('streams remain signed and legacy hashes redirect to the new tabs', () => {
  const rows = streamPnl({ positions: [{ sleeve: 'core', lastPrice: 9, avgCost: 10, qty: 2 }, { sleeve: 'bounce', lastPrice: 12, avgCost: 10, qty: 3 }] });
  assert.deepEqual(rows.map((row) => row.value), [-2, 0, 6, 4]);
  for (const hash of ['', '#now', '#mission', '#risk', '#floor', '#unknown']) assert.equal(viewFromHash(hash), 'now');
  for (const hash of ['#strategy', '#radar', '#truth', '#debate']) assert.equal(viewFromHash(hash), 'strategy');
});
