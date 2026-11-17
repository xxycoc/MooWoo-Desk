"""Write dashboard-readable preregistered H1-H3 results from verified JSONL."""

import argparse
from pathlib import Path

from _common import expand_logs
from _execution import atomic_json
from moowoo.hypotheses import score
from moowoo.outcomes import read_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=Path(".cache/desk/hypotheses.json"))
    args = parser.parse_args()
    paths = expand_logs(args.logs)
    if args.out.resolve() in {Path(path).resolve() for path in paths}:
        raise ValueError("score output must not overwrite a source log")
    result = score(read_events(paths))
    atomic_json(args.out, result)
    print(f"graded primary calls: {result['H1']['count']}; missing: {len(result['missing'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
