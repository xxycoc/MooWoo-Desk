import type { LoadedEvent, LoadedLog, RawEvent } from "./types";

interface DataIndex {
  files: string[];
}

export interface Corpus {
  events: LoadedEvent[];
  logs: LoadedLog[];
  errors: string[];
}

export function baseUrl(): string {
  return import.meta.env.BASE_URL;
}

/** Loads every log named by data/index.json, in the index's order. */
export async function loadCorpus(signal?: AbortSignal): Promise<Corpus> {
  const base = baseUrl();
  const errors: string[] = [];
  const res = await fetch(`${base}data/index.json`, { signal });
  if (!res.ok) throw new Error(`data/index.json: HTTP ${res.status}`);
  const index = (await res.json()) as DataIndex;
  if (!Array.isArray(index.files)) {
    throw new Error("data/index.json must list files");
  }

  const logs: LoadedLog[] = [];
  const events: LoadedEvent[] = [];
  let gseq = 0;

  for (const file of index.files) {
    const fileRes = await fetch(`${base}data/${encodeURIComponent(file)}`, { signal });
    if (!fileRes.ok) {
      errors.push(`${file}: HTTP ${fileRes.status}`);
      continue;
    }
    const rawText = await fileRes.text();
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
  return { events, logs, errors };
}
