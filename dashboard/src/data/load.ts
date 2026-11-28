import type { LoadedEvent, LoadedLog, RawEvent } from "./types";

interface DataIndex {
  files: string[];
}

export interface DeskStatus {
  halted: boolean;
  haltReason: string;
  tier: "normal" | "reduced" | "exits_only" | "kill" | null;
  updatedAt: string | null;
}

interface FeedMeta {
  latestEventTs: string | null;
  logs: string[];
  desk?: DeskStatus;
}

export interface Corpus {
  events: LoadedEvent[];
  logs: LoadedLog[];
  errors: string[];
  source: "feed" | "bundled" | "bundled-fallback";
  latestEventTs: string | null;
  desk?: DeskStatus;
}

function validDesk(value: unknown): value is DeskStatus {
  if (!value || typeof value !== "object") return false;
  const desk = value as DeskStatus;
  return typeof desk.halted === "boolean" && typeof desk.haltReason === "string"
    && Array.from(desk.haltReason).length <= 240
    && [null, "normal", "reduced", "exits_only", "kill"].includes(desk.tier)
    && (desk.updatedAt === null || typeof desk.updatedAt === "string" && Number.isFinite(Date.parse(desk.updatedAt)));
}

export function baseUrl(): string {
  return import.meta.env.BASE_URL;
}

export const feedUrl: string = (import.meta.env.VITE_FEED_URL ?? "").trim();

/** Prefer a complete feed snapshot; never mix remote and bundled logs. */
export async function loadCorpus(signal?: AbortSignal, feed = feedUrl): Promise<Corpus> {
  if (feed) {
    // A stalled host must also fall back, rather than block all future refreshes.
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    const timer = setTimeout(abort, 15000);
    try {
      return await loadSource(feed.replace(/\/+$/, "") + "/", controller.signal, true);
    } catch (err) {
      if (signal?.aborted) throw err;
      const bundled = await loadSource(`${baseUrl()}data/`, signal);
      return { ...bundled, source: "bundled-fallback" };
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
  }
  return loadSource(`${baseUrl()}data/`, signal);
}

async function loadSource(base: string, signal?: AbortSignal, remote = false): Promise<Corpus> {
  const query = remote ? `?t=${Date.now()}` : "";
  const errors: string[] = [];
  const res = await fetch(`${base}index.json${query}`, { signal });
  if (!res.ok) throw new Error(`data/index.json: HTTP ${res.status}`);
  const index = (await res.json()) as DataIndex;
  if (!Array.isArray(index.files) || index.files.some((file) =>
    typeof file !== "string" || !/^[A-Za-z0-9_.-]+\.jsonl$/.test(file))) {
    throw new Error("data/index.json must list files");
  }

  let meta: FeedMeta | undefined;
  if (remote) {
    const metaRes = await fetch(`${base}meta.json${query}`, { signal });
    if (!metaRes.ok) throw new Error(`data/meta.json: HTTP ${metaRes.status}`);
    meta = await metaRes.json() as FeedMeta;
    if (!meta || !Array.isArray(meta.logs) || JSON.stringify(meta.logs) !== JSON.stringify(index.files)
        || (meta.latestEventTs !== null && (typeof meta.latestEventTs !== "string"
          || !Number.isFinite(Date.parse(meta.latestEventTs))))) {
      throw new Error("data/meta.json does not match the feed index");
    }
    if (meta.desk !== undefined && !validDesk(meta.desk)) {
      throw new Error("data/meta.json desk status is invalid");
    }
  }

  const logs: LoadedLog[] = [];
  const events: LoadedEvent[] = [];
  let gseq = 0;

  // The feed holds one file per run (149 by the end of the window); fetching them
  // one by one overran the 15 s feed timeout, so fetch a few at a time and keep order.
  const texts: (string | null)[] = new Array(index.files.length).fill(null);
  let next = 0;
  const worker = async () => {
    while (next < index.files.length) {
      const i = next++;
      const file = index.files[i];
      const fileRes = await fetch(`${base}${encodeURIComponent(file)}${query}`, { signal });
      if (!fileRes.ok) {
        errors.push(`${file}: HTTP ${fileRes.status}`);
        continue;
      }
      texts[i] = await fileRes.text();
    }
  };
  await Promise.all(Array.from({ length: Math.min(8, index.files.length) }, worker));

  for (const [i, file] of index.files.entries()) {
    const rawText = texts[i];
    if (rawText === null) continue;
    const rawLines = rawText.split("\n");
    if (rawLines.length > 0 && rawLines[rawLines.length - 1] === "") rawLines.pop();
    const fileEvents: LoadedEvent[] = [];
    rawLines.forEach((line, i) => {
      try {
        const parsed = JSON.parse(line) as RawEvent;
        fileEvents.push({ ...parsed, gseq: ++gseq, file, line: i + 1 });
      } catch (err) {
        errors.push(`${file} line ${i + 1}: ${(err as Error).message}`);
      }
    });
    logs.push({ file, rawText, events: fileEvents });
    events.push(...fileEvents);
  }

  // Runs overlap, so assign global seq only after merging by timestamp.
  events.sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts) || a.ts.localeCompare(b.ts) || a.gseq - b.gseq);
  events.forEach((event, i) => { event.gseq = i + 1; });
  if (remote && (errors.length || events.some((e) => !Number.isFinite(Date.parse(e.ts))))) {
    throw new Error("Remote feed is incomplete or invalid");
  }
  const latestEventTs = events.at(-1)?.ts ?? null;
  if (meta && meta.latestEventTs !== latestEventTs) {
    throw new Error("data/meta.json does not match the feed events");
  }
  return { events, logs, errors, source: remote ? "feed" : "bundled", latestEventTs, desk: meta?.desk };
}
