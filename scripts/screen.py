"""Screen a frozen universe and append one hash-chained screen event."""

import argparse
import json
from pathlib import Path
import _common  # noqa: F401
from moowoo.ledger import EventLog
from moowoo.screener import format_table, screen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--log", required=True)
    args = parser.parse_args()
    universe = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    result = screen(universe, args.asof)
    EventLog(args.log, runId=f"{args.asof}-us").append("screen", result)
    print(format_table(result))
    print(f"Skipped: {len(result['skipped'])}; earnings lookup errors: {len(result['earningsErrors'])}")


if __name__ == "__main__":
    main()
