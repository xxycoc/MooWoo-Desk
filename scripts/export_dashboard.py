"""Offline, deliberately lossy public projection of the private paper ledger."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUN_FILE = re.compile(r"logs/\d{4}-\d{2}-\d{2}-(?:morning|watch|audit)-[a-f0-9]+\.jsonl\Z")
LONG_NUMBER = re.compile(r"\d{7,}")
PRIVATE_KEY = re.compile(r"account|acc_?id|token|secret|password|authorization|credential|api_?key|raw|broker.*(?:payload|response)|payload|transcript|.*(?:hash|file|path|ref)$", re.I)
SECRET_KEY = re.compile(r"account|acc_?id|token|secret|password|authorization|credential|api_?key", re.I)
PRIVATE_TEXT = re.compile(r"(?:MOOMOO_ACCOUNT_ID|acc_id|account_id|access_token|refresh_token|api_key|password|authorization)\s*[=:]\s*[^\s,;]+|Bearer\s+\S+|(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", re.I)
DATA_PATH = re.compile(r"/data(?:/[^\s\"'<>;,\)\]]*)?")
COMMON = set('v runId seq ts decisionId type drill'.split())
FIELDS = {
    'run_started': 'universe equity cash tier promptVersion trdEnv equityBasis',
    'screen': 'candidates picked asof moveMode universeDate skipped',
    'rating': 'ticker class confidence tier reason newsCutoff credits creditsMissingReason setupScore evidence expectedMove wrongIf secondOpinion model promptVersion bullSummary bearSummary quickSecondOpinion',
    'core_rebalance': 'etf side targetWeight actualWeight qty',
    'order_intent': 'ticker side sleeve qty limitPrice notional stop sizing kind reason',
    'risk_verdict': 'ticker verdict rules firedRule qtyAfter checks',
    'order_submitted': 'ticker orderId qty limitPrice trdEnv attempt',
    'fill': 'ticker orderId status filledQty avgPrice source fees brokerStatus',
    'stop_hit': 'ticker exitOrderId entry stop',
    'tier_changed': 'from to drawdownPct peakEquity',
    'halt': 'reason scope ticker diff disposition missingFields missingInputs stage secondOpinion',
    'drill': 'name expected observed pass',
    'rule_change': 'ruleId effectiveFrom before after triggerDecisionIds',
    'reflection_note': 'prompt text executionAction reason skipped ticker sourceRunId attempt quoteDeadline',
    'daily_report': 'equity pnlPct baselinePct brier maxDrawdownPct creditsUsed shadowPct orders vetoes skips',
    'shadow': 'book ticker side notional price completed sleeve entryTs exitTs qty entryPrice exitPrice spyReturn exitRule skipped reason',
    'outcome': 'ticker class confidence horizonSessions entryTs entryPrice exitTs exitPrice stockReturn spyReturn excess right graded reason sourceRunId ratingTs newsCutoff forecastDirection secondOpinion observedSessions truncated',
}


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError('timestamps must include UTC Z or +00:00')
    return parsed.astimezone(timezone.utc)


def public_id(value: object) -> str:
    # Letter-only digest cannot accidentally resemble a long account number.
    digest = hashlib.sha256(str(value).encode()).hexdigest()[:16]
    return 'order-' + digest.translate(str.maketrans('0123456789', 'ghijklmnop'))


def scrub(value: object, key: str = '', replacements: dict | None = None) -> object:
    if key.lower().replace('_', '') in ('orderid', 'exitorderid', 'brokerorderid'):
        return public_id(value)
    if isinstance(value, dict):
        return {str(scrub(k, replacements=replacements)): scrub(v, k, replacements)
                for k, v in value.items() if not PRIVATE_KEY.search(k)}
    if isinstance(value, list):
        return [scrub(v, key, replacements) for v in value]
    if isinstance(value, str):
        for private, public in (replacements or {}).items():
            value = value.replace(private, public)
        if key in ('runId', 'decisionId', 'sourceRunId'):
            # Preserve links without conflating distinct digit-only run suffixes.
            return LONG_NUMBER.sub(lambda m: public_id(m.group()).replace('order-', 'id-'), value)
        value = PRIVATE_TEXT.sub('[redacted]', value)
        value = DATA_PATH.sub('[private path]', value)
        # URLs can carry opaque credentials in queries/fragments.
        value = re.sub(r'(https?://[^\s?#]+)[?#][^\s]*', r'\1', value)
        return LONG_NUMBER.sub('[redacted]', value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if abs(value) >= 1000000:
            return None
        return round(value, 6) if isinstance(value, float) else value
    return value


def collect_replacements(value: object) -> dict[str, str]:
    """Also redact known credentials/IDs when echoed in otherwise public prose."""
    found = {}
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (str, int)) and not isinstance(child, bool) and str(child):
                if SECRET_KEY.search(key):
                    found[str(child)] = '[redacted]'
                elif key.lower().replace('_', '') in ('orderid', 'exitorderid', 'brokerorderid'):
                    found[str(child)] = public_id(child)
            found.update(collect_replacements(child))
    elif isinstance(value, list):
        for child in value:
            found.update(collect_replacements(child))
    return found


def project(event: dict, fixture: bool = False, replacements: dict | None = None) -> dict:
    kind = event['type']
    if kind not in FIELDS:
        raise ValueError(f'unsupported event type: {kind}')
    allowed = COMMON | set(FIELDS[kind].split())
    result = scrub({k: v for k, v in event.items() if k in allowed},
                   replacements=replacements or collect_replacements(event))
    result['exportKind'] = 'scrubbed'
    result['dataset'] = 'fixture' if fixture else 'paper-ledger'
    return result


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], encoding='utf-8')


def export(ledger_repo: Path, ref: str, out: Path, until: str | None = None,
           include_fixtures: bool = False) -> dict:
    cutoff = timestamp(until) if until else None
    # Resolve once so an externally moved ref cannot mix snapshots.
    revision = git(ledger_repo, 'rev-parse', '--verify', ref + '^{commit}').strip()
    paths = git(ledger_repo, 'ls-tree', '-r', '--name-only', revision, 'logs/').splitlines()
    sources = [(p, git(ledger_repo, 'show', f'{revision}:{p}'), False)
               for p in paths if RUN_FILE.fullmatch(p)]
    if include_fixtures:
        sources += [(p.name, p.read_text(encoding='utf-8'), True)
                    for p in sorted((ROOT / 'fixtures').glob('*.jsonl'))]
    parsed = [(path, [json.loads(line) for line in raw.splitlines() if line.strip()], fixture)
              for path, raw, fixture in sources]
    replacements = collect_replacements([events for _, events, _ in parsed])
    logs = []
    for path, events, fixture in parsed:
        events = [e for e in events if cutoff is None or timestamp(e['ts']) <= cutoff]
        if not events:
            continue
        events.sort(key=lambda e: (timestamp(e['ts']), e['seq']))
        name = ('fixture-' if fixture else '') + Path(path).name
        name = LONG_NUMBER.sub(lambda m: public_id(m.group()).replace('order-', 'id-'), name)
        logs.append((timestamp(events[0]['ts']), name, [project(e, fixture, replacements) for e in events]))
    logs.sort(key=lambda item: (item[0], item[1]))
    index = {'files': [name for _, name, _ in logs], 'exportKind': 'scrubbed',
             'until': cutoff.isoformat().replace('+00:00', 'Z') if cutoff else None,
             'includesFixtures': include_fixtures}
    artifacts = {name: ''.join(json.dumps(e, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n'
                              for e in events) for _, name, events in logs}
    artifacts['index.json'] = json.dumps(index, indent=2) + '\n'
    for name, content in artifacts.items():
        if LONG_NUMBER.search(content) or '/data/' in content:
            raise ValueError(f'publication scan failed: {name}')
    out = out.resolve()
    # Replacing this dedicated directory also removes unlisted fixtures from Vite's public copy.
    if out == ledger_repo.resolve() or ledger_repo.resolve() in out.parents:
        raise ValueError('output must not be inside the read-only ledger repository')
    out.mkdir(parents=True, exist_ok=True)
    existing = list(out.iterdir())
    if any(p.is_dir() or (p.name != 'index.json' and p.suffix != '.jsonl') for p in existing):
        raise ValueError('output must be a dedicated data directory (index.json and JSONL only)')
    for name, content in artifacts.items():
        (out / name).write_text(content, encoding='utf-8', newline='\n')
    for path in existing:
        if path.name not in artifacts:
            path.unlink()
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger-repo', type=Path, required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--until', help='inclusive UTC ISO cutoff')
    parser.add_argument('--include-fixtures', action='store_true')
    args = parser.parse_args()
    index = export(args.ledger_repo, args.ref, args.out, args.until, args.include_fixtures)
    print(f"Exported {len(index['files'])} scrubbed logs to {args.out}")


if __name__ == '__main__':
    main()
