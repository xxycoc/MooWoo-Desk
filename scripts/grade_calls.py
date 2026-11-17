"""Grade every completed forecast from local bars and verified logs. No network."""

import argparse
import json
from pathlib import Path

from _common import expand_logs
from moowoo.ledger import EventLog
from moowoo.outcomes import grade_calls, read_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", nargs="+", required=True)
    parser.add_argument("--bars-asof", required=True)
    parser.add_argument("--bars", type=Path, default=Path(".cache/desk/bars.json"))
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    events = read_events(expand_logs(args.logs))
    bars = ({path.stem: json.loads(path.read_text(encoding="utf-8"))
             for path in sorted(args.bars.glob("*.json"))} if args.bars.is_dir()
            else json.loads(args.bars.read_text(encoding="utf-8")))
    if not isinstance(bars, dict):
        raise ValueError("bars must map ticker to daily rows")
    log = EventLog(args.log, runId=args.log.stem)
    written = grade_calls(events, bars, args.bars_asof, log)
    print(f"outcomes appended: {len(written)}; graded: {sum(event['graded'] for event in written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
