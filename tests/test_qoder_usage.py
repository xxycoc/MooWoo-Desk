from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import re
import runpy
from urllib.parse import parse_qs, urlparse

import pytest

import qoder_usage as usage


def page(data, more=False, cursor=None):
    return dict(data=data, has_more=more, last_id=cursor)


def session(name, title='MooWoo morning', **kwargs):
    return dict(id=name, title=title, created_at='2026-11-19T02:00:00Z', **kwargs)


def event(name, model=2, sandbox=1, total=3):
    return dict(id=name, type='session.usage', model_credits=model,
                sandbox_runtime_credits=sandbox, total_credits=total)


@pytest.fixture
def responses():
    return {
        (None, None): page([session('first')], True, 'first'),
        (None, 'first'): page([session('first'), session('second', 'MooWoo watch'),
                              session('third', 'Ad hoc')]),
        ('first', None): page([event('old'), dict(id='text', type='message',
                                                content='private-content')], True, 'old'),
        ('first', 'old'): page([event('old'), event('new', 5, 2, 7)]),
        ('second', None): page([event('zero', 0, 0, 0)]),
        ('third', None): page([]),
    }


def transport(responses, calls=None):
    def get(session_id, params):
        if calls is not None:
            calls.append((session_id, params))
        return deepcopy(responses[(session_id, params.get('after_id'))])
    return get


def test_pagination_latest_cumulative_dedup_and_missing(responses):
    calls = []
    report = usage.summarize(transport(responses, calls))
    assert report['totals']['sessions'] == 3
    assert report['totals']['credits']['total_credits'] is None
    assert report['totals']['known_credits']['total_credits'] == 7
    assert report['totals']['sessions_missing_usage'] == 1
    morning = next(row for row in report['rows'] if row['group'] == 'morning')
    assert morning['day'] == '2026-11-18'
    assert morning['credits']['total_credits'] == 7
    watcher = next(row for row in report['rows'] if row['group'] == 'watcher')
    assert watcher['credits']['total_credits'] == 0
    assert all(params['limit'] == 100 and params['order'] == 'asc' for _, params in calls)
    assert calls[0][1]['include_archived'] == 'true'
    assert all(params['type'] == 'session.usage' and params['include_tool_calls'] == 'false'
               and params['include_thinking'] == 'false' for sid, params in calls if sid)
    assert sum(sid == 'first' for sid, _ in calls) == 2


@pytest.mark.parametrize('data,expected', [
    ({'title': 'MooWoo morning'}, 'morning'),
    ({'title': 'MooWoo close-watch early'}, 'watcher'),
    ({'title': 'MooWoo auditor'}, 'audit'),
    ({'title': 'watchmaker'}, 'manual'),
    ({'schedule_name': 'audit', 'title': 'morning'}, 'audit'),
    ({'schedule': {'name': 'watcher'}, 'title': 'audit'}, 'watcher'),
    ({'metadata': {'schedule_name': 'morning'}, 'title': 'manual'}, 'morning'),
    ({'metadata': 'invalid', 'title': None}, 'manual'),
])
def test_grouping(data, expected):
    assert usage.category(data) == expected


def test_timezone_search_and_partial_measurement(responses):
    responses[('first', 'old')]['data'][-1]['model_credits'] = None
    calls = []
    report = usage.summarize(transport(responses, calls), 'Asia/Singapore', 'MooWoo')
    morning = next(row for row in report['rows'] if row['group'] == 'morning')
    assert morning['day'] == '2026-11-19'
    assert morning['credits']['model_credits'] is None
    assert morning['credits']['total_credits'] == 7
    assert morning['sessions_missing_usage'] == 1
    assert report['scope'] == 'title_filter'
    assert all(params['search'] == 'MooWoo' for sid, params in calls if sid is None)


@pytest.mark.parametrize('response', [{}, {'data': [], 'has_more': 'false'},
                                      page(['bad']), page([], True), page([], True, '')])
def test_invalid_pages(response):
    with pytest.raises(usage.UsageError):
        list(usage.pages(lambda *_: response))


def test_repeated_cursor_fails():
    with pytest.raises(usage.UsageError, match='cursor'):
        list(usage.pages(lambda *_: page([], True, 'again')))


@pytest.mark.parametrize('value', [-1, True, '3', float('nan'), float('inf'), 10 ** 6, {}])
def test_invalid_credits(value):
    with pytest.raises(usage.UsageError, match='credit'):
        usage.credit(value)


@pytest.mark.parametrize('created', [None, '', 'invalid', '2026-11-19', '2026-11-19T02:00:00'])
def test_invalid_timestamps(created):
    with pytest.raises(usage.UsageError, match='timestamp'):
        usage.session_day(dict(created_at=created), usage.ZoneInfo('UTC'))


def test_wrong_session_and_missing_id():
    with pytest.raises(usage.UsageError, match='another session'):
        usage.latest_usage(lambda *_: page([dict(event('one'), session_id='other')]), 'one')
    with pytest.raises(usage.UsageError, match='identifier'):
        usage.summarize(lambda *_: page([{}]))


def test_empty_report_and_aggregate_limit():
    report = usage.summarize(lambda *_: page([]))
    assert report['rows'] == []
    assert report['totals']['sessions'] == 0
    bucket = usage.empty_bucket()
    for _ in range(2):
        usage.add_usage(bucket, dict.fromkeys(usage.CREDIT_FIELDS, usage.credit(600000)))
    with pytest.raises(usage.UsageError, match='numeric limit'):
        usage.public_bucket(bucket)


def test_environment_only(monkeypatch, tmp_path):
    monkeypatch.delenv('QODER_PAT', raising=False)
    monkeypatch.chdir(tmp_path)
    Path('.env').write_text('QODER_PAT=must-not-read', encoding='utf-8')
    with pytest.raises(usage.UsageError, match='process environment'):
        usage.Client()


def test_cli_real_entrypoint_uses_only_safe_aggregates(monkeypatch, tmp_path, responses, capsys):
    secret = 'fixture-secret'
    account = '9' * 8
    responses[(None, None)]['data'][0].update(
        title='MooWoo morning ' + secret + account,
        environment_variables={'PRIVATE': secret}, account_id=account)
    responses[('first', 'old')]['data'][-1]['message'] = secret + account
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            parsed = urlparse(request.full_url)
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            parts = parsed.path.split('/')
            session_id = parts[-2] if parts[-1] == 'events' else None
            assert timeout == 30
            assert request.get_header('Authorization') == 'Bearer ' + secret
            return BytesIO(json.dumps(responses[(session_id, params.get('after_id'))]).encode())

    monkeypatch.setenv('QODER_PAT', secret)
    monkeypatch.setattr(usage, 'build_opener', lambda *_: Opener())
    import urllib.request
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *_: Opener())
    monkeypatch.setattr('sys.argv', ['qoder_usage.py', '--out-dir', str(tmp_path)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(usage.__file__)), run_name='__main__')
    assert result.value.code == 0
    assert all(request.full_url.startswith(usage.API) for request in requests)
    output = ''.join(path.read_text(encoding='utf-8') for path in tmp_path.iterdir())
    captured = capsys.readouterr()
    for forbidden in (secret, account, 'environment_variables', 'private-content', 'first', 'new'):
        assert forbidden not in output + captured.out + captured.err
    assert not re.search(r'\d{7,}', output)
    assert 'unavailable' in output
    assert json.loads((tmp_path / 'qoder-usage.json').read_text())['totals']['sessions'] == 3


def test_http_error_does_not_leak(monkeypatch, tmp_path, capsys):
    secret = 'private-error-body'

    class BrokenOpener:
        def open(self, *_args, **_kwargs):
            raise OSError(secret)

    monkeypatch.setenv('QODER_PAT', 'fake-token')
    monkeypatch.setattr(usage, 'build_opener', lambda *_: BrokenOpener())
    assert usage.main(['--out-dir', str(tmp_path)]) == 1
    assert not list(tmp_path.iterdir())
    captured = capsys.readouterr()
    assert secret not in captured.err
    assert 'failed' in captured.err


def test_redirect_denied():
    with pytest.raises(usage.UsageError, match='redirects'):
        usage.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid')


@pytest.mark.parametrize('option', ['--timezone', '--unknown'])
def test_invalid_cli_arguments_do_not_echo_values(option, capsys):
    private_value = 'private-' + '9' * 8
    with pytest.raises(SystemExit) as result:
        usage.main([option, private_value])
    assert result.value.code == 2
    captured = capsys.readouterr()
    assert private_value not in captured.out + captured.err
    assert 'Invalid arguments' in captured.err


def test_credit_rounding_and_literal_output_scan(tmp_path):
    report = usage.summarize(lambda sid, _: page([session('one')]) if sid is None
                             else page([event('one', .123_456_789, 0, .123_456_789)]))
    usage.write_report(report, tmp_path)
    assert report['totals']['credits']['total_credits'] == .123457
    report['rows'][0]['day'] = '9' * 8
    with pytest.raises(usage.UsageError, match='scan'):
        usage.write_report(report, tmp_path)
