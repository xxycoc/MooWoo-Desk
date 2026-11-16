"""Freeze strategy data and source provenance without timestamps or network access."""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess

import _common  # noqa: F401
from moowoo import config
from moowoo.events import canonical_bytes


ROOT = Path(__file__).resolve().parents[1]


def freeze_config(freeze_date, universe_path, history_path):
    date.fromisoformat(freeze_date)
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    passing_hash = hashlib.sha256(canonical_bytes(universe["passing"])).hexdigest()
    if passing_hash != universe["passingSha256"]:
        raise ValueError("universe passing-list hash mismatch")
    history_bytes = history_path.read_bytes()
    history = json.loads(history_bytes)
    chosen = history["chosen"]
    values = {name: value for name, value in vars(config).items() if not name.startswith("_")}
    for name, value in history["recommendedConfig"].items():
        if values[name] != value or chosen["parameters"][name] != value:
            raise ValueError(f"live configuration differs from FIT selection: {name}")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    frozen = dict(
        date=freeze_date,
        config=values,
        universe=dict(file=universe_path.relative_to(ROOT).as_posix(), passingSha256=passing_hash),
        historyCheck=dict(file=history_path.relative_to(ROOT).as_posix(),
                          sha256=hashlib.sha256(history_bytes).hexdigest(), chosenVariantId=chosen["id"]),
        gitCommit=commit,
        promptVersion="pending",
    )
    frozen["configHash"] = hashlib.sha256(canonical_bytes(frozen)).hexdigest()
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--universe", type=Path, default=Path("config/universe-2026-11-16.json"))
    parser.add_argument("--history-check", type=Path, default=Path("config/history-check-2026-11-16.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    frozen = freeze_config(args.date, (ROOT / args.universe).resolve(),
                           (ROOT / args.history_check).resolve())
    output = args.out or ROOT / "config" / f"frozen-{args.date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(frozen, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(f"{output}: {frozen['configHash']}")


if __name__ == "__main__":
    main()
