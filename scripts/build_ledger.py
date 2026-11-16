"""Rebuild the SQLite projection from verified JSONL logs."""

import argparse
import sqlite3

from _common import expand_logs
from moowoo.ledger import build_sqlite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("logs", nargs="+")
    args = parser.parse_args()
    try:
        paths = expand_logs(args.logs)
        build_sqlite(paths, args.out)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"OK {args.out}: rebuilt from {len(paths)} logs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
