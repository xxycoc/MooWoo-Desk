import json
from copy import deepcopy
from pathlib import Path

import pytest

from qca_deploy import ROOT, apply_payloads, build_payloads, load_receipts


def test_update_existing_resources_and_pin_new_children(tmp_path, capsys, monkeypatch):
    original_replace = Path.replace
    replacements = []

    def transient_lock(source, destination):
        replacements.append(source)
        if len(replacements) == 1:
            error = PermissionError("temporary Windows file lock")
            error.winerror = 5
            raise error
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", transient_lock)
    policy = json.loads((ROOT / "agents/permissions.json").read_text())
    settings = dict(MOOMOO_MCP_URL="https://example.invalid/mcp", MOOMOO_ACCOUNT_ID="simulation-test",
                    MOOMOO_MARKET="100", MOOMOO_CHALLENGE_TITLE="Qoder", REPO_REVISION="a" * 40,
                    IDENTITY_ID="identity-test", moomoo_tool_names=[entry["name"] for entry in
                    policy["agents"]["executor"]["configs"]])
    manifest = build_payloads(settings)
    operations = [op for op in manifest["operations"] if not op["key"].startswith("schedule.")]
    receipts = [{"key": op["key"], "id": "existing-" + op["key"],
                 "version": 7 if op["key"].startswith("agent.") else None} for op in operations]
    prior = {"receipts": receipts, "bindings": {row["key"] + ".id": row["id"] for row in receipts}}
    calls = []

    def request(method, path, token, body=None):
        assert "schedule" not in path
        if path == "/cloud/models":
            return {"data": [{"id": "ultimate", "is_enabled": True, "price_factor": 2},
                             {"id": "efficient", "is_enabled": True, "price_factor": .3}]}
        if path.startswith("/cloud/vaults"):
            return {"data": [{"id": "vault-test", "display_name": "moomoo-mcp"}]}
        resource = next(row for row in receipts if path.endswith("/" + row["id"]))
        if method == "GET":
            return deepcopy(resource)
        calls.append((resource["key"], deepcopy(body)))
        if resource["key"].startswith("agent."):
            assert body["version"] == 7
        else:
            assert "version" not in body
        if body.get("multiagent"):
            assert all(child["version"] == 8 for child in body["multiagent"]["agents"])
        return {"id": resource["id"], "version": 8 if resource["version"] else None}

    destination = tmp_path / "receipts.jsonl"
    result = apply_payloads(manifest, settings, "not-a-token", request=request, prior=prior,
                            receipt_path=destination, update=True, ledger_token="fake-ledger-token")
    assert len(calls) == len(result) == 11
    assert len(replacements) >= 12
    assert load_receipts(destination)["receipts"] == result
    assert {row["id"] for row in result} == {row["id"] for row in receipts}
    assert "existing-" not in capsys.readouterr().out
    with pytest.raises(ValueError, match="every existing"):
        apply_payloads(manifest, settings, "not-a-token", request=request, update=True)
    with pytest.raises(ValueError, match="never schedules"):
        apply_payloads(manifest, settings, "not-a-token", request=request, stage="schedules", update=True)
