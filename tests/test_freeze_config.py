"""Exercise the real freeze CLI offline and verify its complete hash payload."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moowoo import config
from moowoo.events import canonical_bytes


ROOT = Path(__file__).resolve().parents[1]


def test_freeze_cli_is_complete_and_repeatable(tmp_path):
    output = tmp_path / "frozen-2026-11-17.json"
    command = [sys.executable, str(ROOT / "scripts/freeze_config.py"),
               "--date", "2026-11-17", "--out", str(output)]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    first = output.read_bytes()
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    assert output.read_bytes() == first
    frozen = json.loads(first)
    digest = frozen.pop("configHash")
    assert digest == hashlib.sha256(canonical_bytes(frozen)).hexdigest()
    expected = {name: value for name, value in vars(config).items() if not name.startswith("_")}
    assert frozen["config"] == json.loads(canonical_bytes(expected))
    universe = json.loads((ROOT / frozen["universe"]["file"]).read_bytes())
    assert frozen["universe"]["passingSha256"] == hashlib.sha256(canonical_bytes(universe["passing"])).hexdigest()
    history_bytes = (ROOT / frozen["historyCheck"]["file"]).read_bytes()
    history = json.loads(history_bytes)
    assert frozen["historyCheck"]["sha256"] == hashlib.sha256(history_bytes).hexdigest()
    assert frozen["historyCheck"]["chosenVariantId"] == history["chosen"]["id"]
    assert {name: frozen["config"][name] for name in history["recommendedConfig"]} == history["recommendedConfig"]
    assert frozen["gitCommit"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    assert frozen["promptVersion"] == "pending"
    assert frozen["date"] == "2026-11-17"


def test_live_defaults_match_preregistered_rules():
    assert (config.MOVE_MODE, config.K_drift, config.R_drift, config.K_bounce) == ("abnormal", 3, 2, 2)
    assert config.CORE_WEIGHT + config.SATELLITE_CAP_STEP_UP + config.CASH_FLOOR == pytest.approx(1)
    assert config.CORE_ETFS == ("USMV", "XLP", "XLV", "IEF", "GLD")
    assert config.SETUP_SCORE_USE == "log_only"


@pytest.mark.parametrize("source,argument", [
    ("universe", "--universe"), ("history-check", "--history-check"),
])
def test_freeze_rejects_changed_inputs(tmp_path, source, argument):
    payload = json.loads((ROOT / f"config/{source}-2026-11-16.json").read_bytes())
    if source == "universe":
        payload["passing"].append("TAMPERED")
        error = "passing-list hash mismatch"
    else:
        payload["recommendedConfig"]["K_drift"] = 99
        error = "differs from FIT selection"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "frozen.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/freeze_config.py"), "--date", "2026-11-17",
         argument, str(changed), "--out", str(output)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert error in result.stderr
    assert not output.exists()


@pytest.mark.skipif(not (ROOT / "config/frozen-2026-11-17.json").exists(),
                    reason="preregistration artifacts have not been generated yet")
def test_preregistration_matches_frozen_artifact():
    frozen = json.loads((ROOT / "config/frozen-2026-11-17.json").read_bytes())
    digest = frozen.pop("configHash")
    assert digest == hashlib.sha256(canonical_bytes(frozen)).hexdigest()
    assert digest in (ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8")
    committed_config = subprocess.check_output(
        ["git", "show", f"{frozen['gitCommit']}:moowoo/config.py"], cwd=ROOT
    )
    namespace = {}
    exec(committed_config, namespace)
    from moowoo.rules import PICKS_CHANGE, SIZING_CHANGE, REGIME_SIZING_CHANGE
    for key, value in namespace.items():
        if not key.startswith("_"):
            assert getattr(config, key) == (PICKS_CHANGE["after"] | SIZING_CHANGE["after"] | REGIME_SIZING_CHANGE["after"]).get(key, value)
    additions = next(json.loads(line)["after"] for line in (ROOT / "config/rule-ledger.jsonl").read_text().splitlines()
                     if json.loads(line)["ruleId"] == "FEES-01")
    from moowoo.rules import CORE_REBALANCE_CHANGE, CORE_CASH_CHANGE, BETA_CHANGE
    from moowoo.rules import FINAL_CLOSE_CHANGE, TICKER_CAP_CHANGE
    assert {k: v for k, v in vars(config).items() if not k.startswith("_") and k not in namespace} == (
        additions | CORE_REBALANCE_CHANGE["after"] | CORE_CASH_CHANGE["after"] | BETA_CHANGE["after"]
        | FINAL_CLOSE_CHANGE["after"] | TICKER_CAP_CHANGE["after"])


@pytest.mark.parametrize("damage", [None, "missing", "changed", "extra"])
def test_topology_addendum_is_exact_and_preserves_frozen_config(tmp_path, monkeypatch, damage):
    sys.path.insert(0, str(ROOT / "scripts"))
    import plan_session
    from moowoo.rules import TOPOLOGY_CHANGE
    directory = tmp_path / "config"
    directory.mkdir()
    (directory / "frozen-2026-11-17.json").write_bytes((ROOT / "config/frozen-2026-11-17.json").read_bytes())
    lines = (ROOT / "config/rule-ledger.jsonl").read_bytes().splitlines()
    assert canonical_bytes(TOPOLOGY_CHANGE) in lines
    assert TOPOLOGY_CHANGE["ruleId"] == "TOPOLOGY-01"
    assert TOPOLOGY_CHANGE["date"] == "2026-11-18"
    assert TOPOLOGY_CHANGE["effectiveFrom"] == "first session after 18 Nov 05:00 SGT"
    if damage == "missing":
        lines.pop()
    elif damage == "changed":
        lines[-1] = canonical_bytes(TOPOLOGY_CHANGE | {"after": "raised risk limits"})
    elif damage == "extra":
        lines.append(canonical_bytes(TOPOLOGY_CHANGE))
    (directory / "rule-ledger.jsonl").write_bytes(b"\n".join(lines) + b"\n")
    monkeypatch.setattr(plan_session, "ROOT", tmp_path)
    if damage:
        with pytest.raises(ValueError, match="unrecognized rule addendum"):
            plan_session.frozen_config()
    else:
        assert plan_session.frozen_config()["configHash"] == json.loads(
            (directory / "frozen-2026-11-17.json").read_bytes())["configHash"]


def test_core_rebalance_addendum_is_canonical_and_recognized():
    from moowoo.rules import CORE_REBALANCE_CHANGE, CORE_CASH_CHANGE, BETA_CHANGE
    from plan_session import frozen_config
    assert canonical_bytes(CORE_REBALANCE_CHANGE) in (ROOT / "config/rule-ledger.jsonl").read_bytes().splitlines()
    assert CORE_REBALANCE_CHANGE["after"] == dict(CORE_REBALANCE_AFTER_FILLS=True)
    assert frozen_config()["configHash"]


@pytest.mark.parametrize("rule_id", ["SIZING-02", "CORE-REBALANCE-02", "SLEEVE-01", "FINAL-CLOSE-01", "TICKER-CAP-01"])
@pytest.mark.parametrize("damage", [None, "missing", "changed"])
def test_more_risk_addenda_are_exact(tmp_path, monkeypatch, rule_id, damage):
    import plan_session
    from moowoo.rules import REGIME_SIZING_CHANGE, CORE_CASH_CHANGE, BETA_CHANGE
    from moowoo.rules import FINAL_CLOSE_CHANGE, TICKER_CAP_CHANGE
    rule = next(r for r in (REGIME_SIZING_CHANGE, CORE_CASH_CHANGE, BETA_CHANGE,
                           FINAL_CLOSE_CHANGE, TICKER_CAP_CHANGE) if r["ruleId"] == rule_id)
    directory = tmp_path / "config"
    directory.mkdir()
    frozen = (ROOT / "config/frozen-2026-11-17.json").read_bytes()
    (directory / "frozen-2026-11-17.json").write_bytes(frozen)
    lines = (ROOT / "config/rule-ledger.jsonl").read_bytes().splitlines()
    index = lines.index(canonical_bytes(rule))
    assert rule["date"] == ("2026-11-20" if rule_id in ("FINAL-CLOSE-01", "TICKER-CAP-01") else "2026-11-19")
    assert rule["effectiveFrom"] == "first session after 20 Nov 00:00 SGT"
    if damage == "missing":
        lines.pop(index)
    elif damage == "changed":
        lines[index] = canonical_bytes(rule | {"after": {"CASH_FLOOR": 0}})
    (directory / "rule-ledger.jsonl").write_bytes(b"\n".join(lines) + b"\n")
    monkeypatch.setattr(plan_session, "ROOT", tmp_path)
    if damage:
        with pytest.raises(ValueError, match="unrecognized rule addendum"):
            plan_session.frozen_config()
    else:
        assert plan_session.frozen_config()["configHash"] == json.loads(frozen)["configHash"]
