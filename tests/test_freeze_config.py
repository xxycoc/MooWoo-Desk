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
    assert config.CORE_WEIGHT + config.SATELLITE_CAP_STEP_UP + config.CASH_FLOOR == 1
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
    assert committed_config.replace(b"\r\n", b"\n") == (ROOT / "moowoo/config.py").read_bytes().replace(b"\r\n", b"\n")
