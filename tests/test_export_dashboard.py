"""Public export is offline and must fail closed on unsupported source events."""
import json
import os
from pathlib import Path
import re
import subprocess

import pytest

from export_dashboard import export, project, public_id, scrub, timestamp


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True, encoding='utf8')


def event(seq=1, ts='2026-11-18T16:00:00Z', **payload):
    return dict(v=0, seq=seq, ts=ts, runId='2026-11-18-morning-abcdef',
                decisionId='2026-11-18-morning-abcdef:ACM', type='reflection_note',
                drill=False, hash='0' * 64, prevHash='0' * 64, prompt='test', text='note', **payload)


@pytest.fixture
def ledger(tmp_path):
    repo = tmp_path / 'ledger'
    repo.mkdir()
    git(repo, 'init')
    (repo / 'logs').mkdir()
    # Deliberately reverse filename/start ordering, plus a non-run artifact and a lock.
    for name, rows in {
        '2026-11-18-morning-abcdef.jsonl': [event(), event(2, '2026-11-18T18:00:00Z')],
        '2026-11-17-watch-abcdef.jsonl': [event(ts='2026-11-17T16:00:00Z')],
        '2026-11-18-morning-abcdef-screen.jsonl': [event()],
        'lock-2026-11-18.jsonl': [event()],
        'notes.jsonl': [event()],
    }.items():
        (repo / 'logs' / name).write_text(''.join(json.dumps(e) + '\n' for e in rows))
    (repo / 'state.json').write_text('{"acc_id":123456789}')
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Offline Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'test')
    return repo


def assert_public(folder):
    for path in folder.iterdir():
        text = path.read_text(encoding='utf8')
        assert not re.search(r'\d{7,}', text)
        assert not re.search(r'"[^"\n]*(?:account|acc_id|token|secret|password|authorization|raw.?payload|broker.?payload)[^"\n]*"\s*:', text, re.I)
        assert '/data/' not in text


def test_default_cutoff_cleanup_and_determinism(ledger, tmp_path):
    out = tmp_path / 'export'
    out.mkdir()
    (out / 'fictional.jsonl').write_text('old fixture')
    index = export(ledger, 'HEAD', out, '2026-11-18T16:00:00Z')
    assert index['files'] == ['2026-11-17-watch-abcdef.jsonl', '2026-11-18-morning-abcdef.jsonl']
    assert not (out / 'fictional.jsonl').exists()
    assert sum(len((out / f).read_text().splitlines()) for f in index['files']) == 2
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.name != 'meta.json'}
    export(ledger, 'HEAD', out, '2026-11-18T16:00:00Z')
    assert before == {p.name: p.read_bytes() for p in out.iterdir() if p.name != 'meta.json'}
    assert_public(out)
    assert git(ledger, 'status', '--porcelain') == ''


def test_fixtures_are_opt_in_and_removed_again(ledger, tmp_path):
    out = tmp_path / 'export'
    index = export(ledger, 'HEAD', out, include_fixtures=True)
    fixtures = [f for f in index['files'] if f.startswith('fixture-')]
    assert len(fixtures) == 3
    assert all(json.loads((out / f).read_text().splitlines()[0])['dataset'] == 'fixture' for f in fixtures)
    assert_public(out)
    export(ledger, 'HEAD', out)
    assert not any(p.name.startswith('fixture-') for p in out.iterdir())


def test_nested_scrub_and_order_linkage():
    order = dict(event(), type='fill', orderId='987654321', ticker='ACM',
                 filledQty=130, avgPrice=83.049, acc_id=123456789, token='opaque',
                 rawBrokerPayload={'password': 'private'}, source='order_status')
    result = project(order)
    assert result['orderId'] == public_id('987654321')
    assert result['orderId'] == project(dict(order, type='order_submitted'))['orderId']
    assert result['orderId'] != public_id('987654322')
    assert result['decisionId'] == order['decisionId']
    assert result['avgPrice'] == 83.049 and result['filledQty'] == 130
    assert 'hash' not in result and 'prevHash' not in result
    nested = scrub({'evidence': [{'headline': 'A headline', 'access_token': 'private'}],
                    'diff': {'snapshot': {'acc_id': 123456789, 'broker_payload': {'secret': 'private'}}},
                    'reason': 'MOOMOO_ACCOUNT_ID=123456789 at /data/receipts/foo.json Bearer opaque',
                    'cash': 65780.70000000001, 'huge': 123456789, 'small': 0.123456789})
    assert nested['evidence'] == [{'headline': 'A headline'}]
    assert 'private' not in json.dumps(nested).replace('[private path]', '')
    assert not re.search(r'\d{7,}', json.dumps(nested))
    assert 'MOOMOO_ACCOUNT_ID' not in nested['reason']
    assert nested['cash'] == 65780.7
    assert nested['huge'] is None


def test_numeric_run_alias_preserves_links():
    run = '2026-11-18-morning-12345678'
    assert scrub(run, 'runId') + ':ACM' == scrub(run + ':ACM', 'decisionId')
    assert scrub(run, 'runId') != scrub(run + '9', 'runId')


def test_credentials_and_order_ids_echoed_in_prose():
    row = event(token='opaque-token-value', orderId='broker-order-abc')
    row['text'] = 'opaque-token-value submitted broker-order-abc'
    result = project(row)
    assert result['text'] == '[redacted] submitted ' + public_id('broker-order-abc')


def test_output_and_time_guards(ledger, tmp_path):
    with pytest.raises(ValueError, match='read-only'):
        export(ledger, 'HEAD', ledger / 'public')
    with pytest.raises(ValueError, match='UTC'):
        timestamp('2026-11-18T16:00:00')
    out = tmp_path / 'export'
    out.mkdir()
    (out / 'keep.txt').write_text('leave alone')
    with pytest.raises(ValueError, match='dedicated'):
        export(ledger, 'HEAD', out)
    assert (out / 'keep.txt').read_text() == 'leave alone'
    with pytest.raises(ValueError, match='unsupported'):
        project(dict(event(), type='new_unknown_type'))


def test_committed_public_data_has_no_secret_patterns():
    assert_public(Path(__file__).resolve().parents[1] / 'dashboard/public/data')


def test_runtime_export_matches_ledger_and_writes_meta(ledger, tmp_path):
    left, right = tmp_path / 'committed', tmp_path / 'runtime'
    export(ledger, 'HEAD', left)
    export(None, None, right, runtime=ledger)
    assert {p.name: p.read_bytes() for p in left.iterdir() if p.name != 'meta.json'} == {
        p.name: p.read_bytes() for p in right.iterdir() if p.name != 'meta.json'}
    meta = json.loads((right / 'meta.json').read_text())
    assert meta['latestEventTs'] == '2026-11-18T18:00:00Z'
    assert meta['logs'] == json.loads((right / 'index.json').read_text())['files']
    assert timestamp(meta['generatedAt'])
    result = subprocess.run([str(Path(__import__('sys').executable)), 'scripts/export_dashboard.py',
                             '--runtime', str(ledger), '--out', str(right)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert_public(right)


@pytest.mark.parametrize('halted', [True, False])
def test_runtime_desk_projects_only_public_state(ledger, tmp_path, halted):
    state_path = ledger / 'state.json'
    private_account = '7' * 9
    private_credential = 'fixture-opaque-value'
    reason = f'cash mismatch {private_account} {private_credential} at /data/private.json ' + 'detail ' * 80
    state_path.write_text(json.dumps(dict(halted=halted, haltReason=reason, tier='reduced',
                                         acc_id=private_account, token=private_credential,
                                         positions={'private': True}, restartReasons=['private'])))
    modified = timestamp('2026-11-19T02:00:00Z').timestamp()
    os.utime(state_path, (modified, modified))
    original = state_path.read_bytes()
    out = tmp_path / 'export'
    export(None, None, out, runtime=ledger)
    desk = json.loads((out / 'meta.json').read_text())['desk']
    assert desk == dict(halted=halted, haltReason=scrub(reason, replacements={
        private_account: '[redacted]', private_credential: '[redacted]'})[:240],
        tier='reduced', updatedAt='2026-11-19T02:00:00Z')
    assert len(desk['haltReason']) == 240
    assert private_credential not in json.dumps(desk)
    assert state_path.read_bytes() == original
    assert_public(out)


def test_state_credentials_are_redacted_from_logs_and_log_credentials_from_state(ledger, tmp_path):
    state_secret, log_secret = 'fixture-state-value', 'fixture-log-value'
    (ledger / 'state.json').write_text(json.dumps(dict(halted=True, tier='kill',
        token=state_secret, haltReason=log_secret)))
    row = event(token=log_secret)
    row['text'] = state_secret
    name = '2026-11-18-morning-abcdef.jsonl'
    (ledger / 'logs' / name).write_text(json.dumps(row) + '\n')
    out = tmp_path / 'export'
    export(None, None, out, runtime=ledger)
    assert json.loads((out / 'meta.json').read_text())['desk']['haltReason'] == '[redacted]'
    assert json.loads((out / name).read_text())['text'] == '[redacted]'
    assert_public(out)


def test_ledger_desk_uses_pinned_ref_and_last_state_commit(ledger, tmp_path, monkeypatch):
    state_path = ledger / 'state.json'
    state_path.write_text(json.dumps(dict(halted=True, haltReason='cash mismatch', tier='kill')))
    monkeypatch.setenv('GIT_AUTHOR_DATE', '2026-11-18T20:32:00Z')
    monkeypatch.setenv('GIT_COMMITTER_DATE', '2026-11-18T20:32:00Z')
    git(ledger, 'add', 'state.json')
    git(ledger, '-c', 'user.name=Offline Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'halt')
    halted_ref = git(ledger, 'rev-parse', 'HEAD').strip()
    state_path.write_text(json.dumps(dict(halted=False, haltReason='', tier='normal')))
    monkeypatch.setenv('GIT_AUTHOR_DATE', '2026-11-19T01:00:00Z')
    monkeypatch.setenv('GIT_COMMITTER_DATE', '2026-11-19T01:00:00Z')
    git(ledger, 'add', 'state.json')
    git(ledger, '-c', 'user.name=Offline Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'restart')
    monkeypatch.setenv('GIT_COMMITTER_DATE', '2026-11-19T02:00:00Z')
    git(ledger, '-c', 'user.name=Offline Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-m', 'later run')
    state_path.write_text(json.dumps(dict(halted=True, haltReason='uncommitted', tier='kill')))
    for ref, halted, reason, tier, updated_at in [
        (halted_ref, True, 'cash mismatch', 'kill', '2026-11-18T20:32:00Z'),
        ('HEAD', False, '', 'normal', '2026-11-19T01:00:00Z'),
    ]:
        out = tmp_path / 'export'
        export(ledger, ref, out)
        assert json.loads((out / 'meta.json').read_text())['desk'] == dict(
            halted=halted, haltReason=reason, tier=tier, updatedAt=updated_at)
        assert_public(out)


def test_missing_or_legacy_state_omits_desk(ledger, tmp_path):
    out = tmp_path / 'export'
    export(None, None, out, runtime=ledger)
    assert 'desk' not in json.loads((out / 'meta.json').read_text())
    (ledger / 'state.json').unlink()
    export(None, None, out, runtime=ledger)
    assert 'desk' not in json.loads((out / 'meta.json').read_text())
    git(ledger, 'add', 'state.json')
    git(ledger, '-c', 'user.name=Offline Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'old ledger')
    export(ledger, 'HEAD', out)
    assert 'desk' not in json.loads((out / 'meta.json').read_text())


@pytest.mark.parametrize('state', [
    '{invalid', '[]', '{"halted": "false"}', '{"halted": 0}',
    '{"halted": false, "haltReason": []}', '{"halted": false, "tier": "unexpected"}',
])
def test_invalid_state_never_replaces_previous_export(ledger, tmp_path, state):
    out = tmp_path / 'export'
    export(None, None, out, runtime=ledger)
    previous = {path.name: path.read_bytes() for path in out.iterdir()}
    (ledger / 'state.json').write_text(state)
    with pytest.raises(ValueError):
        export(None, None, out, runtime=ledger)
    assert previous == {path.name: path.read_bytes() for path in out.iterdir()}
