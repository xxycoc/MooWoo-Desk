"""Publish only the scrubbed runtime projection; never modify the private ledger."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from export_dashboard import ROOT, export


def validate_repo_url(value):
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?', value):
        raise ValueError('FEED_REPO_URL must be a GitHub HTTPS repository URL without credentials')
    return value.rstrip('/')


def validate_feed_branch(branch):
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', branch)
            or branch.lower() in ('main', 'master', 'head')
            or '..' in branch or branch.endswith('.')
            or any(not part or part.startswith('.') or part.endswith('.lock')
                   for part in branch.split('/'))):
        raise ValueError('FEED_BRANCH must be a data-only branch, never main or master')
    return branch


def feed_branch():
    return validate_feed_branch(os.environ.get('FEED_BRANCH', 'dashboard-feed'))


def publish(runtime, *, local_remote=None):
    remote = os.environ.get('FEED_REPO_URL', '')
    token = os.environ.get('GITHUB_FEED_TOKEN', '')
    if not remote or not token:
        return dict(published=False, reason='FEED_REPO_URL or GITHUB_FEED_TOKEN absent')
    remote = validate_repo_url(remote)
    branch = feed_branch()
    # Explicit local bare repositories support offline transport tests, never env URL overrides.
    if local_remote is not None:
        remote = str(Path(local_remote).resolve(strict=True))
    deadline = time.monotonic() + 25  # Leave time for cleanup within the runner's 30-second cap.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GIT_', 'GCM_')) and k not in ('GITHUB_FEED_TOKEN', 'GITHUB_LEDGER_TOKEN')}
    auth = base64.b64encode(('x-access-token:' + token).encode()).decode()
    configs = [('credential.helper', ''), ('core.hooksPath', os.devnull),
               ('commit.gpgSign', 'false'), ('core.autocrlf', 'false'),
               ('user.name', 'MooWoo feed'), ('user.email', 'feed@moowoo.invalid'),
               ('http.https://github.com/.extraHeader', 'Authorization: Basic ' + auth)]
    env.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_CONFIG_COUNT=str(len(configs)))
    for index, (key, value) in enumerate(configs):
        env[f'GIT_CONFIG_KEY_{index}'] = key
        env[f'GIT_CONFIG_VALUE_{index}'] = value
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='feed-', dir=cache) as folder:
        work = Path(folder)
        data = work / 'export'
        export(None, None, data, runtime=Path(runtime).resolve())
        meta = json.loads((data / 'meta.json').read_text(encoding='utf-8'))
        repo = work / 'repo'
        repo.mkdir()

        def git(*args, allowed=(0,)):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('feed publication timed out')
            try:
                result = subprocess.run(['git', '-C', str(repo), *args], env=env,
                                        stdin=subprocess.DEVNULL, capture_output=True,
                                        timeout=remaining)
            except (OSError, subprocess.TimeoutExpired):
                raise RuntimeError('feed git failed or timed out') from None
            if result.returncode not in allowed:
                # Never expose remote output, command headers, or credentials.
                raise RuntimeError('feed git failed')
            return result

        git('init', f'--initial-branch={branch}')
        exists = git('ls-remote', '--exit-code', remote, f'refs/heads/{branch}', allowed=(0, 2))
        if exists.returncode == 0:
            git('fetch', '--no-tags', '--depth=1', remote, f'refs/heads/{branch}')
            git('checkout', '-B', branch, 'FETCH_HEAD')
        destination = repo / 'data'
        if destination.is_symlink() or destination.is_file():
            destination.unlink()
        elif destination.exists():
            # This resolved target is the data child of our newly created temporary checkout.
            if destination.resolve() != repo.resolve() / 'data':
                raise ValueError('feed data path escaped temporary checkout')
            shutil.rmtree(destination)
        shutil.copytree(data, destination)
        git('add', '--all', '--', 'data')
        git('commit', '--allow-empty', '-m', f"Feed update {meta['latestEventTs']}")
        git('push', remote, f'HEAD:refs/heads/{branch}')
    return dict(published=True, branch=branch, latestEventTs=meta['latestEventTs'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT / 'runtime')
    args = parser.parse_args()
    try:
        result = publish(args.runtime)
    except Exception:
        # Publication is optional; arbitrary exception text may contain credentials.
        result = dict(published=False, reason='feed publication failed')
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
