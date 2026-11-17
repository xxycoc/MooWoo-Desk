const ZERO_HASH = "0".repeat(64);

export interface FileVerifyResult {
  file: string;
  ok: boolean;
  count: number;
  total: number;
  badSeq: number | null;
  reason: string | null;
}

type JsonNode =
  | { kind: "null" }
  | { kind: "bool"; value: boolean }
  | { kind: "number"; raw: string }
  | { kind: "string"; value: string }
  | { kind: "array"; items: JsonNode[] }
  | { kind: "object"; entries: Map<string, JsonNode> };

/**
 * Parses JSON while keeping each number's original lexeme. The contract hashes
 * Python json.dumps output, where 1895.0 must stay "1895.0"; JSON.parse would
 * turn it into 1895 and change every downstream hash.
 */
function parsePreservingNumbers(raw: string): JsonNode {
  let i = 0;

  const fail = (message: string): never => {
    throw new Error(`${message} at offset ${i}`);
  };
  const skipWs = () => {
    while (i < raw.length && (raw[i] === " " || raw[i] === "\t" || raw[i] === "\n" || raw[i] === "\r")) {
      i += 1;
    }
  };
  const parseString = (): string => {
    if (raw[i] !== '"') fail("expected string");
    const start = i;
    i += 1;
    while (i < raw.length) {
      if (raw[i] === "\\") {
        i += 2;
        continue;
      }
      if (raw[i] === '"') {
        i += 1;
        return JSON.parse(raw.slice(start, i)) as string;
      }
      i += 1;
    }
    return fail("unterminated string");
  };
  const parseValue = (): JsonNode => {
    skipWs();
    const ch = raw[i];
    if (ch === "{") {
      i += 1;
      const entries = new Map<string, JsonNode>();
      skipWs();
      if (raw[i] === "}") {
        i += 1;
        return { kind: "object", entries };
      }
      for (;;) {
        skipWs();
        const key = parseString();
        skipWs();
        if (raw[i] !== ":") fail("expected colon");
        i += 1;
        entries.set(key, parseValue());
        skipWs();
        if (raw[i] === ",") {
          i += 1;
          continue;
        }
        if (raw[i] === "}") {
          i += 1;
          return { kind: "object", entries };
        }
        fail("expected comma or closing brace");
      }
    }
    if (ch === "[") {
      i += 1;
      const items: JsonNode[] = [];
      skipWs();
      if (raw[i] === "]") {
        i += 1;
        return { kind: "array", items };
      }
      for (;;) {
        items.push(parseValue());
        skipWs();
        if (raw[i] === ",") {
          i += 1;
          continue;
        }
        if (raw[i] === "]") {
          i += 1;
          return { kind: "array", items };
        }
        fail("expected comma or closing bracket");
      }
    }
    if (ch === '"') return { kind: "string", value: parseString() };
    if (raw.startsWith("true", i)) {
      i += 4;
      return { kind: "bool", value: true };
    }
    if (raw.startsWith("false", i)) {
      i += 5;
      return { kind: "bool", value: false };
    }
    if (raw.startsWith("null", i)) {
      i += 4;
      return { kind: "null" };
    }
    const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(raw.slice(i));
    if (match) {
      i += match[0].length;
      return { kind: "number", raw: match[0] };
    }
    return fail("unexpected token");
  };

  const node = parseValue();
  skipWs();
  if (i !== raw.length) fail("trailing content");
  return node;
}

/** Compact JSON with sorted keys, matching Python sort_keys + "," + ":". */
function serializeCanonical(node: JsonNode): string {
  switch (node.kind) {
    case "null":
      return "null";
    case "bool":
      return node.value ? "true" : "false";
    case "number":
      return node.raw;
    case "string":
      return JSON.stringify(node.value);
    case "array":
      return `[${node.items.map(serializeCanonical).join(",")}]`;
    case "object": {
      const parts = [...node.entries.keys()]
        .sort()
        .map((key) => `${JSON.stringify(key)}:${serializeCanonical(node.entries.get(key)!)}`);
      return `{${parts.join(",")}}`;
    }
  }
}

async function sha256Hex(text: string): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error("Web Crypto unavailable (needs a secure context)");
  const bytes = new TextEncoder().encode(text);
  const digest = await subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Recomputes each event's canonical SHA-256 and checks the prevHash chain and
 * file-local seq. Reports the first bad file-local seq, like verify() does.
 */
export async function verifyLog(file: string, rawText: string): Promise<FileVerifyResult> {
  const lines = rawText.split("\n");
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  const total = lines.length;
  let count = 0;
  let prevHash = ZERO_HASH;

  for (let i = 0; i < lines.length; i += 1) {
    const position = i + 1;
    const line = lines[i];
    if (line.trim() === "") {
      return { file, ok: false, count, total, badSeq: position, reason: "blank line" };
    }
    if (line.includes("\r")) {
      return { file, ok: false, count, total, badSeq: position, reason: "CRLF line ending" };
    }
    let body: Record<string, unknown>;
    let tree: JsonNode;
    try {
      const parsed: unknown = JSON.parse(line);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("event is not an object");
      }
      body = parsed as Record<string, unknown>;
      tree = parsePreservingNumbers(line);
    } catch (err) {
      return {
        file,
        ok: false,
        count,
        total,
        badSeq: position,
        reason: `validation error: invalid JSON (${(err as Error).message})`,
      };
    }
    if (body.seq !== position) {
      return {
        file,
        ok: false,
        count,
        total,
        badSeq: position,
        reason: `seq gap: declared ${String(body.seq)}, expected ${position}`,
      };
    }
    if (body.prevHash !== prevHash) {
      return { file, ok: false, count, total, badSeq: position, reason: "broken prevHash link" };
    }
    const storedHash = body.hash;
    if (typeof storedHash !== "string") {
      return {
        file,
        ok: false,
        count,
        total,
        badSeq: position,
        reason: "validation error: missing hash",
      };
    }
    if (tree.kind !== "object" || !tree.entries.has("hash")) {
      return {
        file,
        ok: false,
        count,
        total,
        badSeq: position,
        reason: "validation error: missing hash",
      };
    }
    const digestTree: JsonNode = { kind: "object", entries: new Map(tree.entries) };
    digestTree.entries.delete("hash");
    let computed: string;
    try {
      computed = await sha256Hex(serializeCanonical(digestTree));
    } catch (err) {
      return {
        file,
        ok: false,
        count,
        total,
        badSeq: position,
        reason: `validation error: ${(err as Error).message}`,
      };
    }
    if (computed !== storedHash.toLowerCase()) {
      return { file, ok: false, count, total, badSeq: position, reason: "bad hash" };
    }
    prevHash = storedHash.toLowerCase();
    count += 1;
  }

  return { file, ok: true, count, total, badSeq: null, reason: null };
}
