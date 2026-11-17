"""Prepare exact agent messages and collect transcripts offline; never call Qoder."""

import argparse
from datetime import datetime
import json
from pathlib import Path

import _common  # noqa: F401
from hash_prompts import prompt_version
from moowoo.events import ValidationError
from moowoo.rating_schema import parse_rating

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("bull", "bear", "manager", "quick")


def argument(case, role, output):
    value = parse_rating(output)
    brief = case["brief"]
    if (not isinstance(value, dict) or set(value) != {"decisionId", "stance", "argument", "itemIds"}
            or value["decisionId"] != brief["decisionId"] or value["stance"] != role
            or not isinstance(value["argument"], str) or not value["argument"].strip()
            or len(value["argument"].split()) > 150 or not isinstance(value["itemIds"], list)):
        raise ValidationError(f"invalid {role} argument")
    cutoff = datetime.fromisoformat(brief["newsCutoff"].replace("Z", "+00:00"))
    eligible = {item["id"] for item in brief["items"]
                if datetime.fromisoformat(item["publishedAt"].replace("Z", "+00:00")) <= cutoff}
    if any(not isinstance(item, str) or item not in eligible for item in value["itemIds"]):
        raise ValidationError(f"invalid {role} citations")
    return value


def prepare(case, outputs=None, *, version=None):
    """Manager becomes ready only after both independently produced arguments."""
    if case.get("chains") != {"debate": ["bull", "bear", "manager"], "quick": ["quick"]}:
        raise ValueError("unsupported eval chains")
    outputs = outputs or {}
    version = version or prompt_version()
    requests = []
    for role in ROLES:
        if role == "manager" and not all(name in outputs for name in ("bull", "bear")):
            continue
        model = json.loads((ROOT / "agents" / role / "agent.json").read_text(encoding="utf-8"))["model"]
        payload = dict(brief=case["brief"], model=model, promptVersion=version)
        if role in ("quick", "manager"):
            payload["tier"] = "quick" if role == "quick" else "debate"
        if role == "manager":
            payload.update({name: argument(case, name, outputs[name]) for name in ("bull", "bear")})
        requests.append(dict(agent=role, model=model, messages=[
            dict(role="system", content=(ROOT / "agents" / role / "system.md").read_text(encoding="utf-8")),
            dict(role="user", content=json.dumps(payload, ensure_ascii=False, allow_nan=False))]))
    return requests


def collect(case, outputs, *, version=None):
    if set(outputs) != set(ROLES) or any(not isinstance(text, str) or not text.strip() for text in outputs.values()):
        raise ValueError("collect requires raw bull, bear, manager and quick transcripts")
    version = version or prompt_version()
    requests = prepare(case, outputs, version=version)
    return dict(caseId=case["id"], promptVersion=version, requests=requests, outputs=outputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect"))
    parser.add_argument("--cases", type=Path, default=ROOT / "evals")
    parser.add_argument("--outputs", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.cases.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        outputs = {}
        for role in ROLES:
            source = args.outputs / case["id"] / f"{role}.txt" if args.outputs else None
            if source and source.is_file():
                outputs[role] = source.read_text(encoding="utf-8")
        result = collect(case, outputs) if args.action == "collect" else prepare(case, outputs)
        (args.out / f"{case['id']}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
