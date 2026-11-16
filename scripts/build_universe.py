"""Freeze a universe using current fundamentals and completed daily prices."""

import argparse
import json
from pathlib import Path
import _common  # noqa: F401
from moowoo.universe import build_universe, fetch_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    tickers, source = fetch_candidates()
    print(f"Candidates: {len(tickers)} ({source['source']})", flush=True)
    result = build_universe(args.date, tickers, source)
    path = Path("config") / f"universe-{args.date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Passing: {len(result['passing'])}; written {path}")
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
