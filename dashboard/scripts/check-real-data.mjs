// Offline check of the same loader, reducer, verification and views used by Vite.
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { resolve, basename } from 'node:path';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const dataDir = resolve(process.argv[2] ?? 'public/data');
const originalFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  const name = decodeURIComponent(String(url).split('/').at(-1));
  assert.equal(basename(name), name);
  try { return new Response(await readFile(resolve(dataDir, name), 'utf8')); }
  catch { return new Response('', { status: 404 }); }
};
const server = await createServer({ server: { middlewareMode: true, hmr: false },
  optimizeDeps: { noDiscovery: true, include: [] } });
try {
  const { loadCorpus } = await server.ssrLoadModule('/src/data/load.ts');
  const { stateAt } = await server.ssrLoadModule('/src/data/state.ts');
  const { verifyLog } = await server.ssrLoadModule('/src/data/verify.ts');
  const { creditPlan } = await server.ssrLoadModule('/src/data/metrics.ts');
  const { debateRecords, truthView } = await server.ssrLoadModule('/src/data/stage2.ts');
  const corpus = await loadCorpus();
  assert.deepEqual(corpus.errors, []);
  assert(corpus.events.length > 0);
  assert(corpus.events.every((e) => e.dataset === 'paper-ledger'));
  for (let i = 0; i < corpus.events.length; i++) {
    assert.equal(corpus.events[i].gseq, i + 1);
    if (i) assert(Date.parse(corpus.events[i - 1].ts) <= Date.parse(corpus.events[i].ts));
  }
  const state = stateAt(corpus.events, corpus.events.length);
  assert.deepEqual(Object.fromEntries(state.positions.map((p) => [p.ticker, p.qty])),
    { IEF: 218, XLP: 40, ACM: 130 });
  assert(Math.abs(state.cash - 65780.70) < 0.01, `cash: ${state.cash}`);
  assert.equal(state.positions.find((p) => p.ticker === 'IEF').sleeve, 'core');
  assert.equal(state.positions.find((p) => p.ticker === 'XLP').sleeve, 'core');
  const firstFill = corpus.events.find((e) => e.type === 'fill');
  assert.deepEqual(stateAt(corpus.events, firstFill.gseq - 1).positions, [], 'proposals are not holdings');
  assert(state.ratings.some((r) => r.tier === 'single' && r.credits === null));
  assert.equal(creditPlan(state).unavailable, true);
  assert.equal(state.creditTotal, null);
  assert(state.reflectionNotes.some((n) => n.executionAction === 'skip'));
  assert.equal(state.skips.filter((s) => s.ev.executionAction === 'skip').length, 5);
  assert(state.vetoes.some((v) => v.firedRule === 'core_target'));
  assert(state.resizes.some((v) => v.firedRule === 'core_target'));
  assert(state.halts.some((h) => h.ev.diff != null));
  assert(debateRecords(state).some((r) => r.tier === 'single' && r.manager?.tier === 'single'));
  assert.equal(truthView(state).bins.reduce((sum, bin) => sum + bin.single, 0), 10);
  for (const log of corpus.logs) {
    const result = await verifyLog(log.file, log.rawText);
    assert.equal(result.scrubbed, true);
    assert.equal(result.count, 0, 'must not claim original hash verification');
  }
  // Original fixtures remain verifiable; their corruption must still fail.
  const original = await readFile('../fixtures/2026-11-17-us.jsonl', 'utf8');
  assert.equal((await verifyLog('original', original)).ok, true);
  assert.equal((await verifyLog('corrupt', original.replace('100000', '100001'))).ok, false);
  const listed = JSON.parse(await readFile(resolve(dataDir, 'index.json'), 'utf8')).files;
  assert.deepEqual((await readdir(dataDir)).filter((n) => n.endsWith('.jsonl')).sort(), [...listed].sort());
  for (const name of await readdir(dataDir)) {
    const text = await readFile(resolve(dataDir, name), 'utf8');
    assert(!/\d{7,}/.test(text), `${name}: long number`);
    assert(!/"[^"\n]*(?:acc_id|account.?id|token|secret|password|authorization|raw.?payload|broker.?payload)[^"\n]*"\s*:/i.test(text), `${name}: private key`);
    assert(!/\/data\//.test(text), `${name}: private path`);
  }
  for (const name of ['MissionControl', 'RiskDesk', 'MoverRadar', 'TruthTable', 'DebateRoom']) {
    const module = await server.ssrLoadModule(`/src/views/${name}.tsx`);
    const html = renderToStaticMarkup(React.createElement(module[name], { state, onOpenDecision() {} }));
    assert(html.length > 100);
    assert(!html.includes('NaN'), `${name}: NaN output`);
    if (name === 'RiskDesk') assert(html.includes('CURRENT LATCH UNKNOWN'));
    if (name === 'MissionControl') assert(html.includes('Credit usage unavailable'));
    if (name === 'DebateRoom') assert(html.includes('Researcher-rater verdict'));
  }
  console.log(JSON.stringify({ logs: corpus.logs.length, events: corpus.events.length,
    asOf: state.asOf.ts, positions: state.positions.map(({ ticker, qty }) => ({ ticker, qty })),
    cash: state.cash, ratings: state.ratings.length, orders: state.orders.length,
    checks: 'loader, reducer, scrub scan, original-chain verification, five SSR views passed' }, null, 2));
} finally {
  globalThis.fetch = originalFetch;
  await server.close();
}
