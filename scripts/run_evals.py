"""Evaluate stored Qoder JSON outputs; never call a model or broker."""

import argparse
import difflib
import json
from pathlib import Path
import _common  # noqa: F401
from moowoo.rating_schema import validate_rating
from moowoo.events import ValidationError

ROOT = Path(__file__).resolve().parents[1]


def _invalid_constant(value):
    raise ValueError(f"non-JSON numeric constant: {value}")


def evaluate(outputs, cases=ROOT / "evals"):
    results = {}
    for path in sorted(Path(cases).glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        cid, brief, expected = case["id"], case["brief"], case["expected"]
        output_path = Path(outputs) / f"{cid}.json"
        if not output_path.is_file():
            results[cid] = {"pass": False, "error": "missing Qoder output"}
            continue
        try:
            raw = json.loads(output_path.read_text(encoding="utf-8"), parse_constant=_invalid_constant)
        except (ValueError, UnicodeError):
            results[cid] = {"pass": False, "error": "malformed output JSON"}
            continue
        try:
            rating = validate_rating(raw, brief["newsCutoff"])
        except ValidationError as exc:
            accepted = (expected["allowLookaheadRejection"] and "lookahead:" in str(exc)
                        and all(raw.get(k) == brief[k] for k in ("decisionId", "ticker")))
            results[cid] = {"pass": accepted, "rejected": str(exc), "output": raw}
            continue
        identity_ok = all(rating[k] == brief[k] for k in ("decisionId", "ticker"))
        evidence_ok = all(item in brief["items"] for item in rating["evidence"])
        results[cid] = {"pass": identity_ok and evidence_ok and rating["class"] == expected["class"],
                        "expectedClass": expected["class"], "output": rating}
    if len(results) != 4:
        raise ValueError("expected exactly four fixed evaluation cases")
    return {"cases": results, "passed": sum(r["pass"] for r in results.values()), "total": len(results)}


def compare(current, previous):
    before = json.dumps(previous.get("cases", {}), indent=2, sort_keys=True).splitlines()
    after = json.dumps(current["cases"], indent=2, sort_keys=True).splitlines()
    return "\n".join(difflib.unified_diff(before, after, fromfile="previous", tofile="current", lineterm=""))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outputs", type=Path, required=True)
    p.add_argument("--previous", type=Path)
    p.add_argument("--report", type=Path, default=ROOT / ".cache/evals/latest.json")
    a = p.parse_args()
    previous = a.previous or a.report
    old = json.loads(previous.read_text(encoding="utf-8")) if previous.exists() else {}
    result = evaluate(a.outputs)
    result["diff"] = compare(result, old)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{result['passed']}/{result['total']} cases passed")
    print(result["diff"] or "No change from previous run.")
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
