import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true, hmr: false },
  optimizeDeps: { noDiscovery: true, include: [] } });
const { loadCorpus } = await server.ssrLoadModule('/src/data/load.ts');
const originalFetch = globalThis.fetch;
after(async () => { globalThis.fetch = originalFetch; delete globalThis.window; await server.close(); });
const row = { type: 'reflection_note', ts: '2026-11-18T16:00:00Z', seq: 1, runId: 'test' };
const feed = 'https://feed.invalid/data';

function respond(url) {
  return String(url).split('?')[0].endsWith('index.json')
    ? Response.json({ files: ['run.jsonl'] })
    : new Response(JSON.stringify(row) + '\n');
}

test('complete remote feed uses cache busters and reports latest event', async () => {
  const urls = [];
  globalThis.fetch = async (url) => { urls.push(String(url)); return respond(url); };
  const corpus = await loadCorpus(undefined, feed);
  assert.equal(corpus.source, 'feed');
  assert.equal(corpus.latestEventTs, row.ts);
  assert.equal(corpus.events.length, 1);
  assert.equal(urls.length, 2);
  assert(urls.every((url) => url.startsWith(feed + '/') && /\?t=\d+$/.test(url)));
});

for (const failure of ['network', 'index', 'log', 'parse', 'manifest']) {
  test(`${failure} failure falls back to a complete bundled snapshot`, async () => {
    const urls = [];
    globalThis.fetch = async (url) => {
      url = String(url); urls.push(url);
      if (url.startsWith(feed)) {
        if (failure === 'network') throw new Error('offline');
        if (failure === 'index' || failure === 'log' && url.includes('run.jsonl')) return new Response('', { status: 503 });
        if (failure === 'parse' && url.includes('run.jsonl')) return new Response('{broken');
        if (failure === 'manifest') return Response.json({ files: ['../private.jsonl'] });
      }
      return respond(url);
    };
    const corpus = await loadCorpus(undefined, feed);
    assert.equal(corpus.source, 'bundled-fallback');
    assert.equal(corpus.events.length, 1);
    assert.equal(corpus.latestEventTs, row.ts);
    assert.deepEqual(corpus.errors, []);
    assert(urls.includes('/data/index.json') && urls.includes('/data/run.jsonl'));
  });
}

test('unset feed keeps bundled URLs and partial-log reporting', async () => {
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return String(url).endsWith('index.json') ? Response.json({ files: ['missing.jsonl'] }) : new Response('', { status: 404 });
  };
  const corpus = await loadCorpus(undefined, '');
  assert.equal(corpus.source, 'bundled');
  assert.deepEqual(urls, ['/data/index.json', '/data/missing.jsonl']);
  assert.equal(corpus.errors.length, 1);
});

test('cancelled load does not fall back', async () => {
  const controller = new AbortController();
  controller.abort();
  const urls = [];
  globalThis.fetch = async (url, { signal }) => {
    urls.push(String(url));
    signal.throwIfAborted();
    return respond(url);
  };
  await assert.rejects(loadCorpus(controller.signal, feed), { name: 'AbortError' });
  assert.equal(urls.length, 1);
});


test('top bar names the displayed source and latest event time', async () => {
  globalThis.window = { matchMedia: () => ({ matches: true }) };
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { TopBar } = await server.ssrLoadModule('/src/components/TopBar.tsx');
  const { stateAt } = await server.ssrLoadModule('/src/data/state.ts');
  for (const [source, label] of [['feed', 'Remote feed'], ['bundled-fallback', 'Bundled fallback (feed unavailable)'], ['bundled', 'Bundled snapshot']]) {
    const html = renderToStaticMarkup(React.createElement(TopBar, {
      state: stateAt([], 0), source, latestEventTs: row.ts,
      verifyOpen: false, verifyBusy: false, verifyTone: 'unchecked', onToggleVerify() {},
    }));
    assert(html.includes(label));
    assert(html.includes(row.ts));
  }
});
