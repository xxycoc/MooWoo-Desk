"""Export aggregate Forward session credits without exposing session contents."""

import argparse
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo


API = 'https://api.qoder.com/api/v1/forward/sessions'
CREDIT_FIELDS = ('model_credits', 'sandbox_runtime_credits', 'total_credits')
TIMEZONES = ('America/New_York', 'Asia/Singapore', 'UTC')
MAX_PUBLIC_NUMBER = Decimal('999999')


class UsageError(ValueError):
    """A fixed, public-safe error, never an API response or exception body."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid arguments. Use --help for supported options.\n')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UsageError('API redirects are not allowed.')


class Client:
    def __init__(self):
        token = os.environ.get('QODER_PAT', '').strip()
        if not token:
            raise UsageError('Set QODER_PAT in the process environment.')
        self._token = token
        self._opener = build_opener(NoRedirect())

    def get(self, session_id, params):
        url = API
        if session_id is not None:
            url += '/' + quote(session_id, safe='') + '/events'
        try:
            request = Request(url + '?' + urlencode(params), headers={
                'Authorization': 'Bearer ' + self._token, 'Accept': 'application/json'})
            with self._opener.open(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            raise UsageError('Qoder request failed; no report was generated.') from None


def pages(get, session_id=None, **params):
    params = dict(limit=100, order='asc', **params)
    cursors = set()
    while True:
        page = get(session_id, dict(params))
        if (not isinstance(page, dict) or not isinstance(page.get('data'), list)
                or not isinstance(page.get('has_more'), bool)):
            raise UsageError('Invalid pagination response.')
        for item in page['data']:
            if not isinstance(item, dict):
                raise UsageError('Invalid page item.')
            yield item
        if not page['has_more']:
            return
        cursor = page.get('last_id')
        if not isinstance(cursor, str) or not cursor or cursor in cursors:
            raise UsageError('Missing or repeated pagination cursor.')
        cursors.add(cursor)
        params['after_id'] = cursor


def identifier(item):
    value = item.get('id')
    if not isinstance(value, str) or not value:
        raise UsageError('Missing record identifier.')
    return value


def category(session):
    metadata = session.get('metadata')
    schedule = session.get('schedule')
    labels = [session.get('schedule_name'),
              schedule.get('name') if isinstance(schedule, dict) else None,
              metadata.get('schedule_name') if isinstance(metadata, dict) else None,
              session.get('title')]
    for label in labels:
        if not isinstance(label, str):
            continue
        words = set(re.findall(r'[a-z]+', label.lower()))
        for name, aliases in (('audit', {'audit', 'auditor'}),
                              ('watcher', {'watch', 'watcher'}),
                              ('morning', {'morning'}), ('manual', {'manual'})):
            if words & aliases:
                return name
    return 'manual'


def session_day(session, timezone):
    try:
        created = datetime.fromisoformat(session['created_at'].replace('Z', '+00:00'))
        if created.tzinfo is None:
            raise ValueError
        return created.astimezone(timezone).date().isoformat()
    except (KeyError, AttributeError, TypeError, ValueError, OverflowError):
        raise UsageError('Missing or invalid session creation timestamp.') from None


def credit(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UsageError('Invalid credit measurement.')
    amount = Decimal(str(value))
    if not amount.is_finite() or not 0 <= amount <= MAX_PUBLIC_NUMBER:
        raise UsageError('Invalid credit measurement.')
    return amount


def latest_usage(get, session_id):
    latest = None
    seen = set()
    for event in pages(get, session_id, type='session.usage',
                       include_tool_calls='false', include_thinking='false'):
        if event.get('type') != 'session.usage':
            continue
        event_id = identifier(event)
        if event_id in seen:
            continue
        seen.add(event_id)
        if event.get('session_id', session_id) != session_id:
            raise UsageError('Usage belongs to another session.')
        latest = {field: credit(event.get(field)) for field in CREDIT_FIELDS}
    return latest or dict.fromkeys(CREDIT_FIELDS)


def empty_bucket():
    return dict(sessions=0, sessions_missing_usage=0,
                known_credits={field: Decimal(0) for field in CREDIT_FIELDS},
                missing_measurements=dict.fromkeys(CREDIT_FIELDS, 0))


def add_usage(bucket, usage):
    bucket['sessions'] += 1
    bucket['sessions_missing_usage'] += any(value is None for value in usage.values())
    for field, value in usage.items():
        if value is None:
            bucket['missing_measurements'][field] += 1
        else:
            bucket['known_credits'][field] += value


def public_bucket(bucket):
    if bucket['sessions'] > MAX_PUBLIC_NUMBER:
        raise UsageError('Aggregate exceeds the public numeric limit.')
    known = {}
    for field, value in bucket['known_credits'].items():
        if value > MAX_PUBLIC_NUMBER:
            raise UsageError('Aggregate exceeds the public numeric limit.')
        known[field] = float(value.quantize(Decimal('0.000001')))
    return dict(sessions=bucket['sessions'],
                sessions_missing_usage=bucket['sessions_missing_usage'],
                credits={field: known[field] if not bucket['missing_measurements'][field]
                         else None for field in CREDIT_FIELDS},
                known_credits=known, missing_measurements=bucket['missing_measurements'])


def summarize(get, timezone='America/New_York', search=None):
    if timezone not in TIMEZONES:
        raise UsageError('Unsupported reporting timezone.')
    zone = ZoneInfo(timezone)
    groups = {}
    total = empty_bucket()
    seen = set()
    params = dict(include_archived='true')
    if search:
        params['search'] = search
    for session in pages(get, **params):
        session_id = identifier(session)
        if session_id in seen:
            continue
        seen.add(session_id)
        key = (session_day(session, zone), category(session))
        usage = latest_usage(get, session_id)
        add_usage(groups.setdefault(key, empty_bucket()), usage)
        add_usage(total, usage)
    return dict(schema_version=1, timezone=timezone,
                scope='title_filter' if search else 'all_accessible_sessions',
                includes_archived=True, attribution='session_creation_day',
                usage_basis='latest_cumulative_event',
                rows=[dict(day=day, group=group, **public_bucket(bucket))
                      for (day, group), bucket in sorted(groups.items())],
                totals=public_bucket(total))


def markdown(report):
    lines = ['# Qoder Cloud Agent usage', '',
             'Timezone: ' + report['timezone'] + '. Scope: ' + report['scope'] + '.',
             'Credits use the latest cumulative event per session, attributed to its creation day.',
             'Unmatched titles are manual; labels are inferred, not verified schedule identities.',
             'Missing values are unavailable, not zero. Known subtotals exclude missing measurements.',
             'Active sessions can accrue more credits; this is not a final invoice.', '',
             '| Day | Group | Sessions | Missing usage | Model | Sandbox | Total | Known total |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in [*report['rows'], dict(day='All', group='All', **report['totals'])]:
        values = [row['day'], row['group'], row['sessions'], row['sessions_missing_usage'],
                  *(row['credits'][field] for field in CREDIT_FIELDS),
                  row['known_credits']['total_credits']]
        lines.append('| ' + ' | '.join('unavailable' if value is None else str(value)
                                     for value in values) + ' |')
    return '\n'.join(lines) + '\n'


def write_report(report, out_dir):
    artifacts = {'qoder-usage.json': json.dumps(report, indent=2, allow_nan=False) + '\n',
                 'qoder-usage.md': markdown(report)}
    if any(re.search(r'\d{7,}', text) for text in artifacts.values()):
        raise UsageError('Public output numeric scan failed.')
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in artifacts.items():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                             dir=out_dir, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
            temporary.replace(out_dir / name)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = SafeArgumentParser(prog='qoder_usage.py', description=__doc__)
    parser.add_argument('--search', help='Optional server-side session title filter; omitted means all sessions.')
    parser.add_argument('--timezone', choices=TIMEZONES, default=TIMEZONES[0])
    parser.add_argument('--out-dir', type=Path, default=Path('.cache'))
    args = parser.parse_args(argv)
    try:
        report = summarize(Client().get, args.timezone, args.search)
        write_report(report, args.out_dir)
    except Exception:
        print('Usage export failed. Check environment, connectivity, API schema and output permissions; '
              'existing reports may be stale.', file=sys.stderr)
        return 1
    print('Wrote aggregate JSON and Markdown usage reports.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
