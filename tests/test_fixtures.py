from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

from moowoo.events import EVENT_TYPES
from moowoo.ledger import verify


ROOT = Path(__file__).resolve().parents[1]


def test_fixture_cli_is_deterministic_and_complete(tmp_path):
    outputs = []
    for name in ("first", "second"):
        out = tmp_path / name
        game = out / "game.jsonl"
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts" / "fixture_log.py"),
            "--out", str(out), "--seed", "7", "--game-out", str(game),
        ], cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        paths = sorted(out.glob("2026-*.jsonl"))
        assert len(paths) == 3
        assert game.read_bytes() == paths[-1].read_bytes()
        assert all(verify(path).ok for path in paths)
        outputs.append([path.read_bytes() for path in paths])
    assert outputs[0] == outputs[1]
    events = [json.loads(line) for data in outputs[0] for line in data.splitlines()]
    kinds = Counter(event["type"] for event in events)
    assert set(kinds) == EVENT_TYPES
    assert kinds["daily_report"] == 3 and kinds["reflection_note"] == 2
    assert {e["tier"] for e in events if e["type"] == "rating"} == {"quick", "debate"}
    assert {e["book"] for e in events if e["type"] == "shadow"} == {"follow", "fade", "equal_weight"}
    assert {e["etf"] for e in events if e["type"] == "core_rebalance" and e["runId"] == "2026-11-17-us"} == {"USMV", "XLP", "XLV", "IEF", "GLD"}
    assert any(e["type"] == "risk_verdict" and e["verdict"] == "veto" and e["firedRule"] == "correlation" for e in events)
    assert any(e["type"] == "risk_verdict" and e["verdict"] == "resize" for e in events)
    assert [(e["from"], e["to"]) for e in events if e["type"] == "tier_changed"] == [("normal", "reduced"), ("reduced", "normal")]
    assert any(e["type"] == "drill" and e["name"] == "stale_price" and e["pass"] is True and e["drill"] is True for e in events)
    for day, data in zip((17, 18, 19), outputs[0]):
        assert data == (ROOT / "fixtures" / f"2026-11-{day}-us.jsonl").read_bytes()
    assert outputs[0][-1] == (ROOT / "game" / "fixture" / "events.jsonl").read_bytes()
