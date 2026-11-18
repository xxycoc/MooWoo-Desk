import json
from copy import deepcopy
from pathlib import Path

import pytest

from qca_deploy import ROOT, apply_payloads, build_payloads, load_receipts


@pytest.mark.parametrize('feed_branch', [None, 'feeds/dashboard-v2'])
def test_update_existing_resources_and_pin_new_children(tmp_path, capsys, monkeypatch, feed_branch):
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
                    IDENTITY_ID="identity-test", FEED_REPO_URL="https://github.com/example/feed", moomoo_tool_names=[entry["name"] for entry in
                    policy["agents"]["executor"]["configs"]])
    if feed_branch is not None:
        settings['FEED_BRANCH'] = feed_branch
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
                            receipt_path=destination, update=True, ledger_token="fake-ledger-token", feed_token="fake-feed-token")
    templates = [body for key, body in calls if key.startswith("template.")]
    assert len(templates) == 2
    assert all(body["environment_variables"]["GITHUB_FEED_TOKEN"] == "fake-feed-token" for body in templates)
    assert all(body["environment_variables"]["FEED_REPO_URL"] == "https://github.com/example/feed" for body in templates)
    assert all(body["environment_variables"]["FEED_BRANCH"] == (feed_branch or 'dashboard-feed') for body in templates)
    assert "fake-feed-token" not in json.dumps(manifest)
    assert len(calls) == len(result) == 7
    assert len(replacements) >= 8
    assert load_receipts(destination)["receipts"] == result
    assert {row["id"] for row in result} == {row["id"] for row in receipts}
    output = capsys.readouterr().out
    assert "existing-" not in output and "fake-feed-token" not in output
    with pytest.raises(ValueError, match="every existing"):
        apply_payloads(manifest, settings, "not-a-token", request=request, update=True)
    with pytest.raises(ValueError, match="never schedules"):
        apply_payloads(manifest, settings, "not-a-token", request=request, stage="schedules", update=True)


def test_feed_settings_and_optional_dotenv(tmp_path):
    from qca_deploy import check_settings, load_secret
    path = tmp_path / '.env'
    path.write_text('GITHUB_FEED_TOKEN="synthetic-feed-token"\nFEED_REPO_URL=https://github.com/example/feed\nFEED_BRANCH=feeds/dashboard-v2\n')
    assert load_secret(path, 'GITHUB_FEED_TOKEN') == 'synthetic-feed-token'
    assert load_secret(path, 'FEED_REPO_URL') == 'https://github.com/example/feed'
    assert load_secret(path, 'FEED_BRANCH') == 'feeds/dashboard-v2'
    assert load_secret(path, 'ABSENT', required=False) == ''
    with pytest.raises(ValueError):
        check_settings({'GITHUB_FEED_TOKEN': 'never-in-settings'})
    with pytest.raises(ValueError):
        check_settings({'FEED_REPO_URL': 'https://user:secret@github.com/example/feed'})


@pytest.mark.parametrize('branch', ['main', 'master', '', 'bad..branch', 'feed.lock', 'feed//data'])
def test_deployment_rejects_unsafe_feed_branch(branch):
    with pytest.raises(ValueError):
        build_payloads({'FEED_BRANCH': branch})


@pytest.mark.parametrize('dotenv_branch,settings_branch,expected', [
    (None, None, 'dashboard-feed'),
    ('feeds/from-env', None, 'feeds/from-env'),
    ('feeds/from-env', 'feeds/from-settings', 'feeds/from-settings'),
])
def test_apply_cli_loads_feed_branch(tmp_path, monkeypatch, dotenv_branch, settings_branch, expected):
    import sys
    import qca_deploy
    policy = json.loads((ROOT / 'agents/permissions.json').read_text())
    settings = dict(MOOMOO_MCP_URL='https://example.invalid/mcp', MOOMOO_ACCOUNT_ID='simulation-test',
                    MOOMOO_MARKET='100', MOOMOO_CHALLENGE_TITLE='Qoder', REPO_REVISION='a' * 40,
                    IDENTITY_ID='identity-test', moomoo_tool_names=[entry['name'] for entry in
                    policy['agents']['executor']['configs']])
    if settings_branch is not None:
        settings['FEED_BRANCH'] = settings_branch
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps(settings))
    dotenv = ['GITHUB_LEDGER_TOKEN=synthetic-token', 'GITHUB_FEED_TOKEN=synthetic-token',
              'FEED_REPO_URL=https://github.com/example/feed']
    if dotenv_branch is not None:
        dotenv.append(f'FEED_BRANCH={dotenv_branch}')
    (tmp_path / '.env').write_text(chr(10).join(dotenv) + chr(10))
    monkeypatch.setattr(qca_deploy, 'ROOT', tmp_path)
    monkeypatch.setattr(qca_deploy, 'load_pat', lambda path: 'synthetic-pat')
    calls = []
    def apply(manifest, settings, token, **kwargs):
        calls.append(manifest)
        assert kwargs['feed_token'] == kwargs['ledger_token'] == 'synthetic-token'
        templates = [op['body'] for op in manifest['operations'] if op['key'].startswith('template.')]
        assert len(templates) == 2
        assert all(body['environment_variables']['FEED_BRANCH'] == expected for body in templates)
        assert all(body['environment_variables']['FEED_REPO_URL'] == 'https://github.com/example/feed'
                   for body in templates)
    monkeypatch.setattr(qca_deploy, 'apply_payloads', apply)
    monkeypatch.setattr(sys, 'argv', ['qca_deploy.py', '--apply', '--settings', str(path)])
    qca_deploy.main()
    assert len(calls) == 1
