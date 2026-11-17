"""Evaluate stored Qoder JSON outputs; never call a model or broker."""

import argparse
import difflib
import json
from pathlib import Path
import _common  # noqa: F401
from moowoo.rating_schema import validate_rating, parse_rating
from qca_evals import collect
from moowoo.events import ValidationError

ROOT = Path(__file__).resolve().parents[1]


def check_output(raw, brief, expected):
    try:
        rating = validate_rating(raw, brief["newsCutoff"])
    except ValidationError as exc:
        accepted = (expected["allowLookaheadRejection"] and "lookahead:" in str(exc)
                    and isinstance(raw, dict)
                    and all(raw.get(key) == brief[key] for key in ("decisionId", "ticker")))
        return {"pass": accepted, "rejected": str(exc), "output": raw}
    identity_ok = all(rating[key] == brief[key] for key in ("decisionId", "ticker"))
    evidence_ok = all(item in brief["items"] for item in rating["evidence"])
    return {"pass": identity_ok and evidence_ok and rating["class"] == expected["class"],
            "expectedClass": expected["class"], "output": rating}


def evaluate(outputs, cases=ROOT / "evals", *, mode="chain"):
    results = {}
    for path in sorted(Path(cases).glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        cid, brief, expected = case["id"], case["brief"], case["expected"]
        output_path = Path(outputs) / f"{cid}.json"
        if not output_path.is_file():
            results[cid] = {"pass": False, "error": "missing Qoder output"}
            continue
        try:
            raw = parse_rating(output_path.read_text(encoding="utf-8"))
            if mode == "chain":
                if not isinstance(raw, dict):
                    raise ValueError("expected collected chain")
                expected_bundle = collect(case, raw.get("outputs", {}), version=raw.get("promptVersion"))
                if raw != expected_bundle:
                    raise ValueError("collected messages or provenance differ")
                checks = {}
                for role, tier in (("manager", "debate"), ("quick", "quick")):
                    rating = parse_rating(raw["outputs"][role])
                    checks[role] = check_output(rating, brief, expected)
                    request = next(item for item in raw["requests"] if item["agent"] == role)
                    checks[role]["pass"] &= (isinstance(rating, dict) and rating.get("tier") == tier
                        and rating.get("promptVersion") == raw["promptVersion"]
                        and rating.get("model") == request["model"])
                results[cid] = {"pass": all(item["pass"] for item in checks.values()), "chains": checks}
                continue
        except (ValueError, UnicodeError, KeyError, TypeError) as exc:
            results[cid] = {"pass": False, "error": str(exc)}
            continue
        results[cid] = check_output(raw, brief, expected)
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
    p.add_argument("--mode", choices=("chain", "single"), default="chain")
    p.add_argument("--report", type=Path, default=ROOT / ".cache/evals/latest.json")
    a = p.parse_args()
    previous = a.previous or a.report
    old = json.loads(previous.read_text(encoding="utf-8")) if previous.exists() else {}
    result = evaluate(a.outputs, mode=a.mode)
    result["diff"] = compare(result, old)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{result['passed']}/{result['total']} cases passed")
    print(result["diff"] or "No change from previous run.")
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
