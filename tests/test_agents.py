"""Offline contracts for rating ingestion and Qoder deployment artifacts."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moowoo.events import ValidationError, validate_event
from moowoo.ledger import EventLog, verify
from moowoo.rating_schema import CLASSES, FIELDS, log_rating, rating_to_event, validate_rating

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from hash_prompts import prompt_version
from qca_deploy import apply_payloads, build_payloads, check_settings, load_receipts
from run_evals import compare, evaluate

CUTOFF = '2026-11-16T21:00:00Z'


@pytest.fixture
def good():
    return dict(decisionId='2026-11-17-us:BEAT', ticker='BEAT',
                **{'class': 'explained_up'}, confidence=0.7, tier='debate',
                reason='Earnings beat and raised guidance justify the move.',
                evidence=[dict(id='n1', headline='Earnings beat and raised guidance',
                               source='Company IR', publishedAt=CUTOFF)],
                newsCutoff=CUTOFF, expectedMove=dict(direction='up', horizon=5),
                wrongIf='Five-session return does not outperform matched SPY.',
                model='ultimate', promptVersion='a' * 64)


def test_valid_and_detached(good):
    result = validate_rating(good, CUTOFF)
    result['evidence'].clear()
    assert good['evidence']


@pytest.mark.parametrize('field', sorted(FIELDS))
def test_every_required_field(good, field):
    del good[field]
    with pytest.raises(ValidationError):
        validate_rating(good, CUTOFF)


@pytest.mark.parametrize('field,value', [
    ('ticker', 2), ('decisionId', []), ('class', 'other'), ('class', []),
    ('confidence', True), ('confidence', '0.7'), ('confidence', -0.01),
    ('confidence', 1.01), ('confidence', 10**400), ('confidence', float('nan')), ('confidence', float('inf')),
    ('tier', 'fast'), ('reason', 'a' * 601), ('reason', ' '), ('evidence', {}),
    ('expectedMove', []), ('wrongIf', None), ('model', ''), ('promptVersion', 1),
    ('newsCutoff', '2026-11-16T21:00:00'), ('newsCutoff', '2026-11-16T22:00:00Z'),
])
def test_bad_fields(good, field, value):
    good[field] = value
    with pytest.raises(ValidationError):
        validate_rating(good, CUTOFF)


@pytest.mark.parametrize('published', ['2026-11-16T21:00:00.000001Z',
                                       '2026-11-17T00:00:00Z', 'unknown',
                                       '2026-11-16T16:00:00-05:00', '2026-02-30T00:00:00Z'])
def test_bad_evidence_times(good, published):
    good['evidence'][0]['publishedAt'] = published
    with pytest.raises(ValidationError):
        validate_rating(good, CUTOFF)


@pytest.mark.parametrize('where', ['root', 'evidence', 'expectedMove'])
def test_unknown_fields(good, where):
    target = good if where == 'root' else good['evidence'][0] if where == 'evidence' else good[where]
    target['unexpected'] = 1
    with pytest.raises(ValidationError):
        validate_rating(good, CUTOFF)


@pytest.mark.parametrize('field', ['id', 'headline', 'source', 'publishedAt'])
def test_evidence_required(good, field):
    del good['evidence'][0][field]
    with pytest.raises(ValidationError):
        validate_rating(good, CUTOFF)


def test_duplicate_evidence(good):
    good['evidence'].append(deepcopy(good['evidence'][0]))
    with pytest.raises(ValidationError, match='duplicate'):
        validate_rating(good, CUTOFF)


@pytest.mark.parametrize('cls,direction,horizon', [
    ('explained_up', 'up', 5), ('explained_down', 'down', 5),
    ('unexplained_up', 'down', 3), ('unexplained_down', 'up', 3),
])
def test_forecast_mapping(good, cls, direction, horizon):
    good.update({'class': cls, 'expectedMove': {'direction': direction, 'horizon': horizon}})
    validate_rating(good, CUTOFF)
    good['expectedMove']['direction'] = 'down' if direction == 'up' else 'up'
    with pytest.raises(ValidationError):
        validate_rating(good, CUTOFF)


@pytest.mark.parametrize('horizon', [True, 3, 5.0, '5', 6])
def test_horizon_types(good, horizon):
    good['expectedMove']['horizon'] = horizon
    with pytest.raises(ValidationError):
        validate_rating(good, CUTOFF)


def test_event_and_rejected_skip(tmp_path, good):
    log = EventLog(tmp_path / 'events.jsonl', runId='2026-11-17-us')
    kwargs = dict(transcriptRef='transcripts/BEAT.json', credits=1.5, setupScore=3)
    payload = rating_to_event(good, CUTOFF, **kwargs)
    assert 'decisionId' not in payload
    event = log.append('rating', payload, decisionId=good['decisionId'])
    validate_event(event)
    assert event['evidence'] == good['evidence']
    assert event['expectedMove'] == good['expectedMove']
    assert event['model'] == 'ultimate'
    good['evidence'][0]['publishedAt'] = '2026-11-16T21:01:00Z'
    assert log_rating(log, good, CUTOFF, decision_id=good['decisionId'], ticker='BEAT', **kwargs) is None
    events = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert events[-1]['type'] == 'halt'
    assert events[-1]['disposition'] == 'skip'
    assert not any(e['type'].startswith('order') for e in events)
    assert verify(log.path).ok


def test_second_opinion_and_identity(tmp_path, good):
    log = EventLog(tmp_path / 'events.jsonl', runId='2026-11-17-us')
    kw = dict(transcriptRef='brief.json', credits=0, setupScore=0,
              decision_id=good['decisionId'], ticker=good['ticker'])
    good['tier'] = 'quick'
    assert log_rating(log, good, CUTOFF, second_opinion=True, **kw)['secondOpinion']
    good['decisionId'] = '2026-11-18-us:BEAT'
    assert log_rating(log, good, CUTOFF, **kw) is None


@pytest.mark.parametrize('field,value', [('credits', True), ('credits', -1),
                                       ('credits', float('inf')), ('credits', 10**400), ('setupScore', 6),
                                       ('setupScore', False), ('transcriptRef', '')])
def test_event_metadata(good, field, value):
    kwargs = dict(transcriptRef='brief.json', credits=1, setupScore=2)
    kwargs[field] = value
    with pytest.raises(ValidationError):
        rating_to_event(good, CUTOFF, **kwargs)


def test_permissions():
    policy = json.loads((ROOT / 'agents/permissions.json').read_text())
    assert set(policy['real_money_deny']) == {
        'trading_order_place', 'trading_order_replace', 'trading_order_cancel',
        'trading_order_confirm', 'crypto_account_create_order',
        'crypto_account_modify_order', 'crypto_account_cancel_order'}
    assert set(policy['simulated_order_tools']) == {
        'sim_trade_input_order', 'sim_trade_cancel_order', 'sim_trade_modify_order'}
    agents = list(ROOT.glob('agents/*/agent.json'))
    assert {p.parent.name for p in agents} == {'coordinator', 'analyst', 'bull', 'bear', 'manager', 'quick', 'executor', 'auditor'}
    for path in agents:
        agent = json.loads(path.read_text())
        role = path.parent.name
        prompt_bytes = path.with_name('system.md').read_bytes()
        assert b'\r' not in prompt_bytes
        assert agent['system'] == prompt_bytes.decode('utf-8')
        configs = next(t['configs'] for t in agent['tools'] if t['type'] == 'mcp_toolset')
        if role in policy['agents']:
            assert configs == policy['agents'][role]['configs']
        by_name = {c['name']: c for c in configs}
        for name in policy['real_money_deny']:
            assert by_name[name]['permission_policy']['type'] == 'always_deny'
            assert by_name[name]['enabled'] is False
        for name in policy['simulated_order_tools']:
            expected = 'always_ask' if role == 'executor' else 'always_deny'
            assert by_name[name]['permission_policy']['type'] == expected
            assert by_name[name]['enabled'] is (role == 'executor')
        for t in agent['tools']:
            if t['type'] == 'agent_toolset_20260401':
                assert t['enabled_tools']  # Empty means ALL tools in Qoder.
        if role in {'bull', 'bear', 'manager', 'quick'}:
            assert not any(c['enabled'] for c in configs)
            assert all(t['type'] != 'agent_toolset_20260401' for t in agent['tools'])
        if role == 'analyst':
            assert {c['name'] for c in configs if c['enabled']} == {
                'news_search', 'quote_market_snapshot', 'quote_stock_quote',
                'quote_history_kline', 'quote_financials_earnings_price_move'}


def test_hash_canonical_and_sensitive(tmp_path):
    for path in list(ROOT.glob('agents/*/system.md')) + [ROOT/'agents/permissions.json', ROOT/'schemas/rating.schema.json']:
        target = tmp_path/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    first = prompt_version()
    assert len(first) == 64 and first == prompt_version() == prompt_version(tmp_path)
    policy = tmp_path/'agents/permissions.json'
    policy.write_text(json.dumps(json.loads(policy.read_text()), sort_keys=True))
    assert prompt_version(tmp_path) == first
    prompt = tmp_path/'agents/bull/system.md'
    prompt.write_text(prompt.read_text() + 'Changed thesis.\n')
    assert prompt_version(tmp_path) != first


def test_deploy_offline(monkeypatch):
    import qca_deploy
    monkeypatch.setattr(qca_deploy.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('network in dry run'))
    monkeypatch.setattr(qca_deploy, 'load_pat', lambda *a: pytest.fail('secret read in dry run'))
    result = build_payloads({'moomoo_tool_names': ['new_unknown_order_tool']})
    ops = {o['key']: o['body'] for o in result['operations']}
    assert len([k for k in ops if k.startswith('agent.')]) == 4
    roster = ops['agent.coordinator']['multiagent']['agents']
    assert len(roster) == 2
    assert all('auditor' not in r['id'] for r in roster)
    assert ops['schedule.morning']['trigger_policy'] == {'type':'cron','expression':'35 9 * * 1-5','timezone':'America/New_York'}
    assert ops['schedule.audit']['execution']['session_mode'] == 'new_session'
    assert ops['template.auditor']['vaults'] == {'${vault.moomoo-mcp.id}': {'enabled': True}}
    assert 'vault_ids' in result['session_example']
    for key, body in ops.items():
        if not key.startswith(('agent.', 'template.')):
            continue
        config = next(t['configs'] for t in body['tools'] if t['type'] == 'mcp_toolset')
        assert next(c for c in config if c['name'] == 'new_unknown_order_tool')['enabled'] is False
        assert next(c for c in config if c['name'] == 'trading_order_place')['permission_policy']['type'] == 'always_deny'
    encoded = json.dumps(result)
    assert 'Authorization' not in encoded and 'QODER_PAT' not in encoded
    assert 'https://github.com/xxycoc/MooWoo-Desk' in encoded


def test_deploy_cli_no_environment_secrets(monkeypatch):
    monkeypatch.setenv('QODER_PAT', 'SENTINEL_SECRET_NEVER_PRINT')
    process = subprocess.run([sys.executable, 'scripts/qca_deploy.py'], cwd=ROOT, capture_output=True, text=True, check=True)
    assert 'SENTINEL_SECRET_NEVER_PRINT' not in process.stdout + process.stderr
    assert json.loads(process.stdout)['promptVersion'] == prompt_version()


@pytest.mark.parametrize('settings', [{'QODER_PAT':'secret'}, {'MOOMOO_MCP_URL':'https://host/mcp?token=x'},
                                     {'MOOMOO_MCP_URL':'https://user:secret@host/mcp'},
                                     {'REPO_REVISION':'main; do-bad-thing'}, {'MOOMOO_MARKET':'HK'}])
def test_bad_deploy_settings(settings):
    with pytest.raises(ValueError):
        check_settings(settings)


def test_apply_payload_resolution_with_mock_api(tmp_path):
    policy = json.loads((ROOT/'agents/permissions.json').read_text())
    settings = dict(MOOMOO_MCP_URL='https://example.invalid/mcp', MOOMOO_ACCOUNT_ID='simulation-test',
                    MOOMOO_MARKET='100', MOOMOO_CHALLENGE_TITLE='Moomoo x Qoder AI Trading Agent Challenge',
                    REPO_REVISION='a'*40, IDENTITY_ID='idn_test', SLACK_CHANNEL_PAIRING_ID='pair_test',
                    moomoo_tool_names=[c['name'] for c in policy['agents']['executor']['configs']])
    calls = []
    def fake(method, path, token, body=None):
        assert token == 'fake-token'
        if path == '/cloud/models':
            return {'data':[{'id':'ultimate','is_enabled':True,'price_factor':2},
                            {'id':'efficient','is_enabled':True,'price_factor':0.3}]}
        if path.startswith('/cloud/vaults'):
            return {'data':[{'id':'vault_test','display_name':'moomoo-mcp'}]}
        assert '${agent.' not in json.dumps(body)
        assert '${environment.' not in json.dumps(body)
        calls.append((path, body))
        return {'id': f'resource_{len(calls)}', 'version':1}
    receipt_path = tmp_path/'receipts.jsonl'
    receipts = apply_payloads(build_payloads(settings), settings, 'fake-token', request=fake, receipt_path=receipt_path,
                              ledger_token='fake-ledger-token')
    assert len(receipts) == len(calls) == 7
    receipts = apply_payloads(build_payloads(settings), settings, 'fake-token', request=fake,
                              stage='schedules', prior=load_receipts(receipt_path), receipt_path=receipt_path,
                              ledger_token='fake-ledger-token')
    assert len(receipts) == len(calls) == 13
    assert next(b for p,b in calls if p=='/forward/templates')['vaults'] == {'vault_test':{'enabled':True}}


def test_evals_and_diff(tmp_path, good):
    assert evaluate(tmp_path, mode='single')['passed'] == 0
    for path in (ROOT/'evals').glob('*.json'):
        case = json.loads(path.read_text())
        brief = case['brief']
        rating = deepcopy(good)
        rating.update({k:brief[k] for k in ('decisionId','ticker','newsCutoff')})
        rating['class'] = case['expected']['class']
        explained = rating['class'].startswith('explained_')
        move = rating['class'].rsplit('_',1)[1]
        rating['expectedMove'] = {'direction': move if explained else ('up' if move=='down' else 'down'), 'horizon':5 if explained else 3}
        rating['evidence'] = brief['items']  # last case deliberately triggers lookahead rejection
        (tmp_path/(case['id']+'.json')).write_text(json.dumps(rating))
    result = evaluate(tmp_path, mode='single')
    assert result['passed'] == 4
    assert result['cases']['post_cutoff']['rejected'].startswith('lookahead:')
    assert compare(result, result) == ''
    old = deepcopy(result)
    result['cases']['earnings_beat']['output']['confidence'] = 0.9
    assert '0.9' in compare(result, old)
    bad = tmp_path/'no_news_drop.json'
    rating = json.loads(bad.read_text())
    rating['class'] = 'explained_down'
    rating['expectedMove'] = {'direction':'down','horizon':5}
    bad.write_text(json.dumps(rating))
    assert evaluate(tmp_path, mode='single')['passed'] == 3


@pytest.mark.parametrize("tier", ["single", "debate", "quick"])
def test_schema_accepts_valid_and_rejects_structural_errors(good, tier):
    good["tier"] = tier
    jsonschema = pytest.importorskip('jsonschema')
    schema = json.loads((ROOT/'schemas/rating.schema.json').read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    validator.validate(good)
    good['expectedMove']['horizon'] = 3
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(good)


def test_coordinator_runtime_handoffs():
    prompt = (ROOT / 'agents/coordinator/system.md').read_text(encoding='utf-8')
    steps = prompt.split('## Exact command sequence (both kinds)', 1)[1]
    commands = [
        'run_session.py --kind K --phase start',
        'run_session.py --kind K --phase preflight',
        'run_session.py --kind K --phase reconcile',
        'scripts/session_info.py',
        'gather_inputs.py --kind K --inputs <inputs>',
        'ingest_ratings.py --inputs <inputs>',
        'convert_quotes.py --inputs <inputs>',
        'run_session.py --kind K --phase plan',
        'run_session.py --kind K --phase prepare',
        'dispatch_check.py --kind K --decision-id <id>',
        'run_session.py --kind K --phase record',
        'run_session.py --kind K --phase reconcile',
        'run_session.py --kind K --phase finish',
    ]
    cursor = 0
    for command in commands:
        cursor = steps.index(command, cursor) + len(command)
    assert 'Skip only step 6' in prompt
    assert '<inputs>/replies/<decisionId>.analyst.json' in steps
    assert 'Only if it prints ok:true' in steps
    assert '--phase renew' in steps and '--phase abort' in steps
    assert 'current US session has not opened' not in prompt


@pytest.mark.parametrize("tier", ["single", "debate", "quick"])
def test_all_rating_tiers_remain_valid(good, tmp_path, tier):
    good["tier"] = tier
    validate_rating(good, CUTOFF)
    log = EventLog(tmp_path / "ratings.jsonl", runId="2026-11-17-us")
    event = log_rating(log, good, CUTOFF, decision_id=good["decisionId"], ticker=good["ticker"],
                       transcriptRef="analyst.json", credits=0, setupScore=3)
    validate_event(event)
    assert event["tier"] == tier


def test_active_roster():
    from qca_deploy import ROLES
    active = {"coordinator", "analyst", "executor", "auditor"}
    assert set(ROLES) == active
    policy = json.loads((ROOT / "agents/permissions.json").read_text())
    assert set(policy["agents"]) == active
    coordinator = json.loads((ROOT / "agents/coordinator/agent.json").read_text())
    assert {a["id"] for a in coordinator["multiagent"]["agents"]} == {
        "${agent.analyst.id}", "${agent.executor.id}"}
