"""Verify one or more JSONL logs."""

import argparse

from _common import expand_logs
from moowoo.ledger import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+")
    args = parser.parse_args()
    try:
        paths = expand_logs(args.logs)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    for path in paths:
        result = verify(path)
        if not result.ok:
            print(f"FAIL {path}: seq {result.bad_seq}: {result.reason}")
            return 1
        print(f"OK {path}: {result.count} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
