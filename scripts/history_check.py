"""Run the fixed FIT/HOLDOUT price-half experiment, without changing live defaults."""
import argparse
from datetime import datetime, timezone
import hashlib
import gzip
import json
from pathlib import Path
import time
import _common
from moowoo.history import (collect, replay, evaluate, coverage, write_report, LIMITATIONS, PERIODS, SEED)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=20)
    parser.add_argument('--pause', type=float, default=2)
    args = parser.parse_args()
    if args.batch_size < 1 or args.pause < 0:
        parser.error('batch-size must be positive and pause must be nonnegative')
    root = Path(__file__).resolve().parents[1]
    started = time.monotonic()
    universe_path = root / 'config/universe-2026-11-16.json'
    universe = json.loads(universe_path.read_text(encoding='utf-8'))
    bars, earnings, provenance = collect(universe, root, args.batch_size, args.pause)
    pools, counts = replay(universe, bars, earnings)
    result, chosen_trades = evaluate(pools)
    records_path = root / 'config/history-trades-2026-11-16.jsonl.gz'
    record_count = 0
    with records_path.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as archive:
            for mode, periods in pools.items():
                for period, strategies in periods.items():
                    for strategy, trades in strategies.items():
                        for trade in trades:
                            record = dict(trade, mode=mode, period=period, pool=strategy)
                            archive.write((json.dumps(record, allow_nan=False)+'\n').encode())
                            record_count += 1
    result['tradeRecords'] = dict(path=str(records_path.relative_to(root)).replace('\\', '/'),
                                  count=record_count, sha256=hashlib.sha256(records_path.read_bytes()).hexdigest())
    hashes = {ticker: hashlib.sha256(df.to_json(orient='table', double_precision=15).encode()).hexdigest()
              for ticker, df in bars.items()}
    result.update(runTimestamp=datetime.now(timezone.utc).isoformat(), periods=PERIODS,
                  selectionRule='FIT only; >=100 drift and >=100 bounce trades; maximize trade-weighted mean excess; ties use grid order',
                  recommendedConfig=result['chosen']['parameters'] if result['chosen'] else None,
                  bootstrap=dict(seed=SEED, resamples=2000), limitations=LIMITATIONS,
                  coverage=coverage(bars, earnings, provenance, universe),
                  dataHashes=dict(bars=hashes, earnings=hashlib.sha256(json.dumps(earnings, sort_keys=True).encode()).hexdigest(),
                                  universe=hashlib.sha256(universe_path.read_bytes()).hexdigest()),
                  earningsProvenance=provenance, candidateCounts=counts, chosenTrades=chosen_trades,
                  runtimeSeconds=time.monotonic()-started)
    output = root / 'config/history-check-2026-11-16.json'
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    write_report(result, root / 'docs/history-check.md')
    print(json.dumps(dict(chosen=result['chosen']['parameters'] if result['chosen'] else None,
                          runtimeSeconds=result['runtimeSeconds'], output=str(output))), flush=True)


if __name__ == '__main__':
    main()
