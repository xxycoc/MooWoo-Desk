"""Make the public, masked copy of the private ledger (Addendum 33).

Reads an exported ledger folder (logs/*.jsonl, tickets/*.json, reports/*.json,
hypotheses/*.json), verifies every log's hash chain, masks every standalone run of
seven or more digits to *** plus its last four digits, and writes the copy with a
MANIFEST.json. Hash, run and decision identifiers are left unchanged. Masked log
events are written in canonical form with their ORIGINAL hash and prevHash, so every
unmasked event still verifies and the chain links stay intact; the manifest lists
the masked events, which verify only against the private copy.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from moowoo.ledger import canonical_bytes, verify

LONG = re.compile(r"(?<![\w.])\d{7,}(?![\w.])")
KEEP = {"hash", "prevHash", "runId", "sourceRunId", "decisionId"}


def mask_text(text):
    return LONG.sub(lambda m: "***" + m.group(0)[-4:], text)


def mask(value, key=None):
    if key in KEEP:
        return value
    if isinstance(value, dict):
        return {k: mask(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and abs(value) >= 1_000_000:
        return "***" + str(abs(value))[-4:]
    if isinstance(value, str):
        return mask_text(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    manifest = {"rule": "standalone runs of 7+ digits -> *** + last 4 digits; hash, prevHash, runId, sourceRunId, decisionId unchanged",
                "logs": {}, "files": {}}
    for log in sorted((args.source / "logs").glob("*.jsonl")):
        raw = log.read_bytes()
        result = verify(log)
        if not result.ok:
            sys.exit(f"{log.name}: private log does not verify: {result}")
        lines, masked = [], []
        for line in raw.splitlines():
            event = json.loads(line)
            clean = mask(event)
            if clean != event:
                masked.append(event["seq"])
            lines.append(canonical_bytes(clean) + b"\n")
        out = args.out / "logs" / log.name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"".join(lines))
        events = [json.loads(line) for line in raw.splitlines()]
        manifest["logs"][log.name] = {"events": len(events), "headHash": events[-1]["hash"],
                                      "privateSha256": hashlib.sha256(raw).hexdigest(),
                                      "maskedSeqs": masked}
    for folder in ("tickets", "reports", "hypotheses"):
        for item in sorted((args.source / folder).glob("*.json")):
            out = args.out / folder / item.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(mask(json.loads(item.read_text(encoding="utf-8"))),
                                      indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            manifest["files"][f"{folder}/{item.name}"] = {
                "privateSha256": hashlib.sha256(item.read_bytes()).hexdigest()}
    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    total = sum(len(v["maskedSeqs"]) for v in manifest["logs"].values())
    print(f"{len(manifest['logs'])} logs verified and copied; {total} events masked; {len(manifest['files'])} other files")


if __name__ == "__main__":
    main()
