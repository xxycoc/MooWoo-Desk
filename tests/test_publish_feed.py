"""Feed transport and runner failure isolation, using only local Git repositories."""
import base64
import json
from pathlib import Path
import re
import subprocess
import sys
from argparse import Namespace

import pytest

import publish_feed
import run_session
from moowoo.persistence import LedgerStore
from test_export_dashboard import event, git


@pytest.fixture(autouse=True)
def feed_env(monkeypatch):
    monkeypatch.delenv('FEED_BRANCH', raising=False)
    monkeypatch.setenv('FEED_REPO_URL', 'https://github.com/example/public-feed')
    monkeypatch.setenv('GITHUB_FEED_TOKEN', 'ghp_TestSecretNeverPrinted')


def test_missing_configuration_is_successful_noop(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_FEED_TOKEN')
    monkeypatch.setattr(publish_feed.subprocess, 'run', lambda *a, **k: pytest.fail('git on absent config'))
    assert publish_feed.publish(tmp_path)['published'] is False


def test_push_tree_scrubbed_and_replaces_stale_data(tmp_path, monkeypatch, capsys):
    remote = tmp_path / 'remote.git'
    remote.mkdir()
    git(remote, 'init', '--bare', '--initial-branch=main')
    runtime = tmp_path / 'runtime'
    logs = runtime / 'logs'
    logs.mkdir(parents=True)
    name = '2026-11-18-morning-abcdef.jsonl'
    row = event(acc_id='123456789', token='opaque-secret')
    row['text'] = 'acc_id=123456789 ghp_supersecret github_pat_othersecret Bearer secret opaque-secret'
    (logs / name).write_text(json.dumps(row) + '\n')
    (runtime / 'state.json').write_text('{"acc_id":123456789}')
    original = {p.relative_to(runtime): p.read_bytes() for p in runtime.rglob('*') if p.is_file()}
    real_run = subprocess.run
    calls = []

    def capture(command, **kwargs):
        calls.append((command, kwargs['env']))
        return real_run(command, **kwargs)

    monkeypatch.setattr(publish_feed.subprocess, 'run', capture)
    assert publish_feed.publish(runtime, local_remote=remote)['published']
    (logs / name).unlink()
    (logs / '2026-11-18-watch-abcdef.jsonl').write_text(json.dumps(event()) + '\n')
    assert publish_feed.publish(runtime, local_remote=remote)['published']
    monkeypatch.setattr(publish_feed.subprocess, 'run', real_run)
    names = git(remote, 'ls-tree', '-r', '--name-only', 'dashboard-feed').splitlines()
    assert set(names) == {'data/index.json', 'data/meta.json', 'data/2026-11-18-watch-abcdef.jsonl'}
    for revision in ('dashboard-feed', 'dashboard-feed^'):
        for name in git(remote, 'ls-tree', '-r', '--name-only', revision).splitlines():
            contents = git(remote, 'show', f'{revision}:{name}')
            assert not re.search(r'\d{7,}|acc_id|ghp_|github_pat_|Bearer |opaque-secret', contents, re.I)
    assert git(remote, 'log', '-1', '--format=%s', 'dashboard-feed').strip() == 'Feed update 2026-11-18T16:00:00Z'
    assert git(remote, 'rev-list', '--count', 'dashboard-feed').strip() == '2'
    assert (runtime / 'state.json').read_bytes() == original[Path('state.json')]
    token = 'ghp_TestSecretNeverPrinted'
    auth = base64.b64encode(('x-access-token:' + token).encode()).decode()
    assert calls and all(token not in str(cmd) and auth not in str(cmd) for cmd, _ in calls)
    assert all('GITHUB_FEED_TOKEN' not in env and 'GITHUB_LEDGER_TOKEN' not in env for _, env in calls)
    assert any('Authorization: Basic ' + auth in env.values() for _, env in calls)
    assert token not in capsys.readouterr().out


@pytest.mark.parametrize('url', ['https://user:secret@github.com/a/b', 'https://github.com/a/b?token=secret',
                                 'https://elsewhere.invalid/a/b', 'file:///private'])
def test_feed_url_guard(url):
    with pytest.raises(ValueError):
        publish_feed.validate_repo_url(url)


@pytest.mark.parametrize('mode', ['exception', 'timeout', 'bad-json', 'failed', 'success'])
@pytest.mark.parametrize('phase', ['finish', 'abort', 'skip'])
def test_publication_cannot_change_saved_result(tmp_path, monkeypatch, phase, mode):
    # Real ledger save/restore + real run phase, only the optional publisher is stubbed.
    remote = tmp_path / 'ledger.git'
    remote.mkdir()
    git(remote, 'init', '--bare')
    args = Namespace(kind='watch', phase='start', dir=tmp_path / 'runtime', remote=str(remote))
    now = '2026-11-18T16:00:00Z'
    if phase != 'skip':
        run_session.run(args, now)
        control = args.dir / '.session.json'
        context = json.loads(control.read_text())
        context['phase'] = 'reconcile'
        control.write_text(json.dumps(context))
        args.phase = phase
    else:
        now = '2026-11-26T16:00:00Z'
    real_run = subprocess.run
    calls = []
    persisted = {}

    def fake(command, **kwargs):
        if 'publish_feed.py' not in str(command):
            return real_run(command, **kwargs)
        assert not (args.dir / '.session.json').exists()
        assert not (args.dir / 'locks/run.lock').exists()
        assert kwargs['timeout'] == 30
        calls.append(command)
        persisted.update({p.relative_to(args.dir): p.read_bytes() for p in args.dir.rglob('*')
                          if p.is_file() and '.git' not in p.relative_to(args.dir).parts})
        if mode == 'exception':
            raise RuntimeError('private-token')
        if mode == 'timeout':
            raise subprocess.TimeoutExpired(command, 30)
        return subprocess.CompletedProcess(command, 1 if mode == 'failed' else 0,
                                           'invalid' if mode == 'bad-json' else '{"published":true}')

    monkeypatch.setattr(run_session.subprocess, 'run', fake)
    result = run_session.run(args, now)
    assert result['saved'] and result['unlocked']
    assert result['feedPublished'] is (mode == 'success')
    assert len(calls) == 1
    assert persisted == {p.relative_to(args.dir): p.read_bytes() for p in args.dir.rglob('*')
                         if p.is_file() and '.git' not in p.relative_to(args.dir).parts}
    restored = LedgerStore(tmp_path / 'restored', str(remote))
    restored.restore()
    assert not (restored.directory / 'locks/run.lock').exists()
    assert 'feedPublished' not in git(remote, 'log', 'ledger', '-1', '--format=%B')
    assert 'private-token' not in json.dumps(result)


def test_publish_cli_absent_env(tmp_path, monkeypatch):
    monkeypatch.delenv('FEED_REPO_URL')
    result = subprocess.run([sys.executable, 'scripts/publish_feed.py', '--runtime', str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)['published'] is False


@pytest.mark.parametrize('failure', [RuntimeError('secret'), subprocess.TimeoutExpired('publisher', 30)])
def test_finish_cli_exit_code_unchanged_on_publish_error(monkeypatch, capsys, tmp_path, failure):
    monkeypatch.setattr(sys, 'argv', ['run_session.py', '--kind', 'watch', '--phase', 'finish'])
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(run_session.subprocess, 'run', fail)
    monkeypatch.setattr(run_session, 'run', lambda args: dict(
        saved=True, unlocked=True, feedPublished=run_session.publish_feed(tmp_path)))
    assert run_session.main() == 0
    assert json.loads(capsys.readouterr().out) == dict(saved=True, unlocked=True, feedPublished=False)


def test_failed_save_never_publishes(tmp_path, monkeypatch):
    from moowoo.persistence import LedgerError
    root = tmp_path / 'runtime'
    root.mkdir()
    class Store:
        directory = root
        def restore(self):
            return dict(restored=True)
        def save(self, *args):
            raise LedgerError('save refused')
    monkeypatch.setattr(run_session, 'LedgerStore', lambda *args: Store())
    monkeypatch.setattr(run_session, 'acquire', lambda *args: dict(holder='test', expiresAt='later'))
    monkeypatch.setattr(run_session, 'publish_feed', lambda *args: pytest.fail('publication before save'))
    args = Namespace(kind='watch', phase='start', dir=root, remote='unused')
    with pytest.raises(LedgerError, match='save refused'):
        run_session.run(args, '2026-11-26T16:00:00Z')
    assert (root / '.session.json').exists()


def test_publish_cli_never_echoes_exception_secrets(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['publish_feed.py'])
    def fail(*args, **kwargs):
        raise RuntimeError('ghp_SensitiveTokenFromTransport')
    monkeypatch.setattr(publish_feed, 'publish', fail)
    assert publish_feed.main() == 0
    output = capsys.readouterr()
    assert 'Sensitive' not in output.out + output.err
    assert json.loads(output.out) == dict(published=False, reason='feed publication failed')


@pytest.mark.parametrize("branch", ["main", "master", "MAIN", "HEAD", "-x", "", "a..b",
                                    "a//b", "a/", "a.", "a.lock", "a.lock/b", "a/.b",
                                    "a b", "a@{b", "a:b", "a\\b", "a\nb"])
def test_feed_refuses_code_branches(monkeypatch, branch):
    monkeypatch.setenv("FEED_BRANCH", branch)
    monkeypatch.setattr(publish_feed.subprocess, 'run', lambda *a, **k: pytest.fail('git on invalid branch'))
    with pytest.raises(ValueError):
        publish_feed.publish(Path('unused'))


@pytest.mark.parametrize('branch', ['dashboard-feed', 'feeds/dashboard-v2'])
def test_publish_keeps_main_and_creates_unrelated_feed(tmp_path, monkeypatch, branch):
    remote = tmp_path / 'remote.git'
    remote.mkdir()
    git(remote, 'init', '--bare', '--initial-branch=main')
    code = tmp_path / 'code'
    code.mkdir()
    git(code, 'init', '--initial-branch=main')
    git(code, 'config', 'user.name', 'Test')
    git(code, 'config', 'user.email', 'test@example.invalid')
    (code / 'app.py').write_text('print("code, not feed")\n')
    git(code, 'add', '.')
    git(code, 'commit', '-m', 'Code root')
    git(code, 'push', str(remote), 'main')
    original_main = git(remote, 'rev-parse', 'main')
    original_tree = git(remote, 'ls-tree', '-r', 'main')
    runtime = tmp_path / 'runtime'
    logs = runtime / 'logs'
    logs.mkdir(parents=True)
    (logs / '2026-11-18-watch-abcdef.jsonl').write_text(json.dumps(event()) + '\n')
    monkeypatch.setenv('FEED_BRANCH', branch)
    for count in (1, 2):
        result = publish_feed.publish(runtime, local_remote=remote)
        assert result['published'] and result['branch'] == branch
        assert git(remote, 'rev-parse', 'main') == original_main
        assert git(remote, 'ls-tree', '-r', 'main') == original_tree
        assert git(remote, 'symbolic-ref', 'HEAD').strip() == 'refs/heads/main'
        assert git(remote, 'rev-list', '--count', branch).strip() == str(count)
        assert original_main.strip() not in git(remote, 'rev-list', branch).splitlines()
        assert set(git(remote, 'ls-tree', '-r', '--name-only', branch).splitlines()) == {
            'data/index.json', 'data/meta.json', 'data/2026-11-18-watch-abcdef.jsonl'}
    assert set(git(remote, 'for-each-ref', '--format=%(refname)', 'refs/heads').splitlines()) == {
        'refs/heads/main', f'refs/heads/{branch}'}
