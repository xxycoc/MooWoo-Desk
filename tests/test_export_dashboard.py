"""Public export is offline and must fail closed on unsupported source events."""
import json
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
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    export(ledger, 'HEAD', out, '2026-11-18T16:00:00Z')
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}
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
