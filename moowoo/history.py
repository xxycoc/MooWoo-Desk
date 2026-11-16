"""Price-only history check. All trade returns are independent, not a portfolio."""
from datetime import datetime, timezone
import itertools
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from .data import get_daily_bars, _provider, session_index
from .indicators import atr, ema
from .screener import screen
from .setup_score import setup_score, support_levels

START, END = '2023-11-01', '2026-11-13'
PERIODS = {'FIT': ('2023-12-01', '2025-10-31'), 'HOLDOUT': ('2025-11-01', END)}
SEED = 20261116
COST = 0.0005
LIMITATIONS = [
    "Survivorship bias: today's frozen constituents, not historical membership.",
    "Earnings dates proxy for explained news; non-earnings dates proxy for unexplained moves. This tests prices, not the LLM/news rule. Missing earnings can mislabel explained moves.",
    "Daily bars cannot reveal intraday paths; stop wins when stop and target share a bar.",
    "Yahoo bars and earnings can be incomplete or wrong; split-adjusted, not dividend-adjusted prices are used.",
    "Independent overlapping trades, equal weight per trade; no $100,000 portfolio, capacity, or cash constraint is simulated.",
]


def collect(universe, root, batch_size=20, pause=2):
    """Serial requests in paced batches; persist earnings and reuse price cache."""
    tickers = list(dict.fromkeys(universe['passing'] + ['SPY']))
    cache = Path(root) / '.cache' / 'history'
    cache.mkdir(parents=True, exist_ok=True)
    bars, earnings, provenance = {}, {}, {}
    for offset in range(0, len(tickers), batch_size):
        batch = tickers[offset:offset+batch_size]
        bars.update(get_daily_bars(batch, START, END))
        for ticker in batch:
            if ticker == 'SPY':
                continue
            path = cache / f'{ticker}-earnings-80.json'
            if path.exists():
                payload = json.loads(path.read_text(encoding='utf-8'))
            else:
                payload = dict(dates=[], error=None, retrievedAt=datetime.now(timezone.utc).isoformat())
                try:
                    frame = _provider(ticker).get_earnings_dates(limit=80)
                    if frame is None:
                        raise ValueError('no earnings dates returned')
                    payload['dates'] = sorted(set(session_index(frame.index).strftime('%Y-%m-%d')))
                except Exception as exc:
                    payload['error'] = f'{type(exc).__name__}: {exc}'
                path.write_text(json.dumps(payload), encoding='utf-8')
            earnings[ticker] = [d for d in payload['dates'] if START <= d <= END]
            provenance[ticker] = payload
        print(f'Data {min(offset+batch_size, len(tickers))}/{len(tickers)}', flush=True)
        if offset + batch_size < len(tickers):
            time.sleep(pause)
    return bars, earnings, provenance


def signal_context(df):
    volatility = float(atr(df).iloc[-1])
    close = float(df.close.iloc[-1])
    levels = [v['price'] for v in support_levels(df) if v['price'] <= close]
    support = max(levels) if levels else None
    return dict(atr=volatility, support=support, target=float(df.close.iloc[-2]),
                bounceEligible=bool(close > ema(df.close).iloc[-1]
                                    or (support is not None and close-support <= volatility)),
                score=setup_score(df)['total'])


def simulate_trade(df, spy, signal_date, context, strategy, k=2):
    """Trade next open, current-bar stop before target, next-bar trailing updates.

    Signal ATR stays fixed. Gap-through stops fill at open; gap-through targets
    also fill at open. Stops at/above entry close immediately at entry. Require a
    full maximum holding window, so end-of-period censoring cannot select winners.
    """
    horizon = 5 if strategy in ('drift', 'follow-all') else 3
    future = df.loc[df.index > pd.Timestamp(signal_date)].iloc[:horizon]
    expected = spy.index[spy.index > pd.Timestamp(signal_date)][:horizon]
    if len(future) < horizon or not future.index.equals(expected):
        return None
    entry = float(future.open.iloc[0])
    if entry <= 0:
        return None
    active = strategy in ('drift', 'bounce')
    volatility = context['atr']
    if active and (not np.isfinite(volatility) or volatility <= 0):
        return None
    stop = max(entry-k*volatility, context['support']-volatility
               if context['support'] is not None else -np.inf) if active else -np.inf
    target = context['target'] if strategy == 'bounce' else np.inf
    high_close, armed = entry, False
    stops = []
    for day, row in future.iterrows():
        stops.append(float(stop) if active else None)
        reason, price = 'time', float(row.close)
        if row.open <= stop:
            reason, price = 'stop', float(row.open)
        elif row.low <= stop:
            reason, price = 'stop', float(stop)
        elif row.open >= target:
            reason, price = 'target', float(row.open)
        elif row.high >= target:
            reason, price = 'target', float(target)
        if reason != 'time':
            break
        if strategy == 'drift':
            high_close = max(high_close, float(row.close))
            armed = armed or row.close >= entry + volatility
            if armed:
                stop = max(stop, high_close - 1.5*volatility)
    if future.index[0] not in spy.index or day not in spy.index:
        return None
    spy_entry, spy_exit = float(spy.loc[future.index[0], 'open']), float(spy.loc[day, 'close'])
    # Daily SPY closes are the only reproducible comparator for an intraday stop.
    net = price*(1-COST)/(entry*(1+COST))-1
    benchmark = spy_exit*(1-COST)/(spy_entry*(1+COST))-1
    return dict(signal=str(pd.Timestamp(signal_date).date()), entryDate=str(future.index[0].date()),
                exitDate=str(day.date()), entry=entry, exit=price, reason=reason,
                returnNet=net, spyReturn=benchmark, excess=net-benchmark,
                score=context['score'], stops=stops, strategy=strategy)


def bootstrap(values, seed=SEED):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return None
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(20):
        means.extend(values[rng.integers(0, len(values), size=(100, len(values)))].mean(axis=1))
    return [float(v) for v in np.quantile(means, [0.025, 0.975])]


def metrics(trades):
    if not trades:
        return dict(trades=0, hitRate=None, meanReturn=None, medianReturn=None,
                    meanExcess=None, payoffRatio=None, worstTrade=None, excessCI95=None,
                    meanSpyReturn=None, spyMatched=None)
    returns = np.array([t['returnNet'] for t in trades])
    wins, losses = returns[returns > 0], returns[returns < 0]
    spy = np.array([t['spyReturn'] for t in trades])
    spy_wins, spy_losses = spy[spy > 0], spy[spy < 0]
    return dict(trades=len(trades), hitRate=float((returns > 0).mean()),
                meanReturn=float(returns.mean()), medianReturn=float(np.median(returns)),
                meanExcess=float(np.mean([t['excess'] for t in trades])),
                payoffRatio=float(wins.mean()/-losses.mean()) if len(wins) and len(losses) else None,
                worstTrade=float(returns.min()), excessCI95=bootstrap([t['excess'] for t in trades]),
                meanSpyReturn=float(spy.mean()),
                spyMatched=dict(trades=len(spy), hitRate=float((spy > 0).mean()),
                                meanReturn=float(spy.mean()), medianReturn=float(np.median(spy)),
                                meanExcess=0.0, excessCI95=[0.0, 0.0],
                                payoffRatio=float(spy_wins.mean()/-spy_losses.mean())
                                if len(spy_wins) and len(spy_losses) else None,
                                worstTrade=float(spy.min())))


def buckets(trades):
    return {label: metrics([t for t in trades if low <= t['score'] <= high])
            for label, low, high in [('0-2', 0, 2), ('3', 3, 3), ('4-5', 4, 5)]}


def replay(universe, bars, earnings):
    spy = bars['SPY']
    sessions = spy.index[(spy.index >= PERIODS['FIT'][0]) & (spy.index <= END)]
    contexts, pools, counts = {}, {}, {}
    for mode in ('raw', 'abnormal'):
        pools[mode] = {period: {name: [] for name in
                       ['follow-all', 'fade-all', 'drift-2', 'drift-2.5', 'drift-3', 'bounce-2', 'bounce-2.5']}
                       for period in PERIODS}
        counts[mode] = []
        for number, date in enumerate(sessions):
            period = 'FIT' if date <= pd.Timestamp(PERIODS['FIT'][1]) else 'HOLDOUT'
            result = screen(universe, date, bars=bars, earnings=earnings, mode=mode)
            counts[mode].append(dict(date=str(date.date()), period=period,
                                     candidates=len(result['candidates']), picked=len(result['picked'])))
            for row in result['candidates'][:len(result['picked'])]:
                ticker = row['ticker']
                df = bars[ticker]
                key = (ticker, date)
                if key not in contexts:
                    contexts[key] = signal_context(df.loc[:date])
                ctx = contexts[key]
                # No FIT outcome crosses into HOLDOUT; no truncated late HOLDOUT trades.
                available = df.loc[:PERIODS[period][1]]
                names = [('follow-all' if row['z'] > 0 else 'fade-all', 2)]
                if row['earnings'] and row['z'] > 0 and row['rvol'] >= 1.5:
                    names += [('drift', k) for k in (2, 2.5, 3)]
                if not row['earnings'] and row['z'] < 0 and row['rvol'] < 3 and ctx['bounceEligible']:
                    names += [('bounce', k) for k in (2, 2.5)]
                for strategy, k in names:
                    trade = simulate_trade(available, spy, date, ctx, strategy, k)
                    if trade is not None:
                        trade.update(ticker=ticker, rvol=row['rvol'])
                        name = f'{strategy}-{k}' if strategy in ('drift', 'bounce') else strategy
                        pools[mode][period][name].append(trade)
            if number % 50 == 0:
                print(f'Replay {mode} {number+1}/{len(sessions)} {date.date()}', flush=True)
    return pools, counts


def evaluate(pools):
    grid, trades_by_variant = [], {}
    for mode, kd, rd, kb in itertools.product(('raw', 'abnormal'), (2, 2.5, 3), (1.5, 2), (2, 2.5)):
        identifier = f'{mode}-D{kd}-R{rd}-B{kb}'
        variant = dict(id=identifier, parameters=dict(MOVE_MODE=mode, K_drift=kd, R_drift=rd, K_bounce=kb), periods={})
        trades_by_variant[identifier] = {}
        for period in PERIODS:
            pool = pools[mode][period]
            drift = [t for t in pool[f'drift-{kd}'] if t['rvol'] >= rd]
            bounce = pool[f'bounce-{kb}']
            combined = drift + bounce
            trades_by_variant[identifier][period] = combined
            variant['periods'][period] = dict(drift=metrics(drift), bounce=metrics(bounce),
                                              combined=metrics(combined), setupScoreBuckets=buckets(combined))
        grid.append(variant)
    eligible = [v for v in grid if v['periods']['FIT']['drift']['trades'] >= 100
                and v['periods']['FIT']['bounce']['trades'] >= 100]
    chosen = max(eligible, key=lambda v: v['periods']['FIT']['combined']['meanExcess']) if eligible else None
    baselines = {mode: {p: {s: metrics(pools[mode][p][s]) for s in ('follow-all', 'fade-all')}
                       for p in PERIODS} for mode in pools}
    finding = dict(recommendSizing=False, monotonic={})
    if chosen:
        for p in PERIODS:
            b = chosen['periods'][p]['setupScoreBuckets']
            vals = [b[s]['meanExcess'] for s in ('0-2', '3', '4-5')]
            finding['monotonic'][p] = bool(all(x is not None for x in vals) and vals[0] <= vals[1] <= vals[2])
        finding['recommendSizing'] = all(
            chosen['periods'][p]['setupScoreBuckets']['4-5']['meanExcess'] is not None
            and chosen['periods'][p]['setupScoreBuckets']['0-2']['meanExcess'] is not None
            and chosen['periods'][p]['setupScoreBuckets']['4-5']['meanExcess'] > chosen['periods'][p]['setupScoreBuckets']['0-2']['meanExcess']
            for p in PERIODS)
    return dict(grid=grid, chosen=chosen, eligibleVariants=len(eligible), baselines=baselines,
                setupScoreFinding=finding), trades_by_variant.get(chosen['id'], {}) if chosen else {}


def coverage(bars, earnings, provenance, universe):
    details = {}
    for ticker in universe['passing']:
        df, dates = bars[ticker], earnings[ticker]
        quarters = sorted({str(pd.Timestamp(d).to_period('Q')) for d in dates})
        details[ticker] = dict(bars=len(df), first=str(df.index.min().date()) if len(df) else None,
                               last=str(df.index.max().date()) if len(df) else None,
                               earningsDates=len(dates), quarters=quarters,
                               earningsError=provenance[ticker]['error'],
                               barsError=df.attrs.get('unavailable'))
    return dict(requestedNames=len(details), namesWithBars=sum(v['bars'] > 0 for v in details.values()),
                namesWithEarnings=sum(v['earningsDates'] > 0 for v in details.values()),
                nameQuarters=sum(len(v['quarters']) for v in details.values()),
                distinctQuarters=sorted({q for v in details.values() for q in v['quarters']}),
                earningsByPeriod={p: dict(
                    names=sum(any(lo <= d <= hi for d in dates) for dates in earnings.values()),
                    dates=sum(sum(lo <= d <= hi for d in dates) for dates in earnings.values()),
                    nameQuarters=sum(len({str(pd.Timestamp(d).to_period('Q')) for d in dates
                                          if lo <= d <= hi}) for dates in earnings.values()))
                    for p, (lo, hi) in PERIODS.items()},
                namesReachingEnd=sum(v['last'] == END for v in details.values()), byTicker=details)


def write_report(result, path):
    def pct(x):
        return 'n/a' if x is None else f'{x*100:.2f}%'
    def cell(m):
        ci = m['excessCI95']
        interval = 'n/a' if ci is None else f'[{pct(ci[0])}, {pct(ci[1])}]'
        return f"{m['trades']} / {pct(m['meanReturn'])} / {pct(m['meanExcess'])} {interval}"
    c, chosen = result['coverage'], result['chosen']
    lines = ['# Price-half history check', '',
             'Earnings is a proxy for explained news, and non-earnings is a proxy for unexplained moves. This does not backtest news classification.', '',
             'FIT: 1 Dec 2023–31 Oct 2025. HOLDOUT: 1 Nov 2025–13 Nov 2026. Replay uses the live as-of screener, its earnings-first rank, and top 15 each day. The 24 variants combine raw/abnormal moves, drift stops 2/2.5/3 ATR, drift RVOL 1.5/2, and bounce stops 2/2.5 ATR. FIT alone selects highest trade-weighted mean excess, requiring 100 trades in each strategy. Ties use grid order.', '',
             'Enter next open; pay 5 bps each side. Drift holds at most five sessions; bounce targets the pre-drop close and holds at most three. Stop wins if target and stop share a bar. Gap-through fills use open. Signal ATR is fixed; trailing updates apply next session and never fall. Support is the highest setup-score level at/below signal close; absent support uses the ATR stop. Trades needing a full holding window beyond a period end are omitted. SPY buys at the same entry open and sells at the exit-day close, including costs; exact intraday SPY matching is unavailable.', '',
             f"Coverage: {c['namesWithBars']}/{c['requestedNames']} names with bars; {c['namesReachingEnd']} reach 13 Nov 2026. Earnings: {c['namesWithEarnings']} names, {c['nameQuarters']} name-quarters ({len(c['distinctQuarters'])} distinct calendar quarters). No earnings record is treated as unexplained, so incomplete coverage biases both ranking and labels.", '',
             'Each cell: trades / mean net return / mean excess over SPY [95% interval]. Intervals use 2,000 trade resamples, seed 20261116; overlapping and same-day trades are dependent, so these intervals can be too narrow.', '',
             '| Strategy | FIT | HOLDOUT |', '|---|---|---|']
    if chosen:
        for s in ('drift', 'bounce', 'combined'):
            lines.append(f"| {s} | {cell(chosen['periods']['FIT'][s])} | {cell(chosen['periods']['HOLDOUT'][s])} |")
        if chosen['periods']['FIT']['combined'].get('spyMatched') and chosen['periods']['HOLDOUT']['combined'].get('spyMatched'):
            lines.append(f"| SPY (combined windows) | {cell(chosen['periods']['FIT']['combined']['spyMatched'])} | {cell(chosen['periods']['HOLDOUT']['combined']['spyMatched'])} |")
        mode = chosen['parameters']['MOVE_MODE']
        for s in ('follow-all', 'fade-all'):
            lines.append(f"| {s} | {cell(result['baselines'][mode]['FIT'][s])} | {cell(result['baselines'][mode]['HOLDOUT'][s])} |")
        lines += ['', f"FIT-selected parameters: `{json.dumps(chosen['parameters'])}`. Live defaults were not changed."]
        hold = chosen['periods']['HOLDOUT']['combined']
        if hold['meanExcess'] is None or hold['meanExcess'] <= 0 or hold['excessCI95'][0] <= 0:
            lines += ['The holdout edge is weak or absent: positive excess is not established by its interval. These parameters are a FIT selection, not evidence of reliable profit.']
        lines += ['', '| Setup score | FIT | HOLDOUT |', '|---|---|---|']
        for b in ('0-2', '3', '4-5'):
            lines.append(f"| {b} | {cell(chosen['periods']['FIT']['setupScoreBuckets'][b])} | {cell(chosen['periods']['HOLDOUT']['setupScoreBuckets'][b])} |")
        finding = result['setupScoreFinding']
        patterns = '; '.join(f"{p}: {'monotonic' if finding['monotonic'][p] else 'not monotonic'}"
                             for p in PERIODS)
        sizing = ('The 4–5 bucket beats 0–2 on both periods, meeting the specified rule for sizing.'
                  if finding['recommendSizing'] else
                  'Do not use the score for sizing: the 4–5 bucket does not beat 0–2 on both periods.')
        lines += ['', f'Score pattern: {patterns}. {sizing} This is a secondary descriptive check.']
    else:
        lines += ['| No eligible variant | n/a | n/a |', '',
                  'No variant meets 100 FIT drift and 100 FIT bounce trades. No parameters are selected or recommended; retain the current raw default pending adequate evidence. Full grid and baselines remain in JSON.']
    lines += ['', 'Raw versus abnormal (daily candidate counts: mean / 95th percentile / maximum):']
    for mode, rows in result['candidateCounts'].items():
        for p in PERIODS:
            values = [r['candidates'] for r in rows if r['period'] == p]
            lines += [f"- {mode}, {p}: {np.mean(values):.2f} / {np.quantile(values, .95):.0f} / {max(values)}"
                      if values else f'- {mode}, {p}: unavailable']
    lines += ['', '| Best eligible FIT variant within mode | FIT | HOLDOUT unchanged |',
              '|---|---|---|']
    for mode in ('raw', 'abnormal'):
        eligible = [v for v in result['grid'] if v['parameters']['MOVE_MODE'] == mode
                    and v['periods']['FIT']['drift']['trades'] >= 100
                    and v['periods']['FIT']['bounce']['trades'] >= 100]
        if eligible:
            best = max(eligible, key=lambda v: v['periods']['FIT']['combined']['meanExcess'])
            lines += [f"| {best['id']} | {cell(best['periods']['FIT']['combined'])} | {cell(best['periods']['HOLDOUT']['combined'])} |"]
        else:
            lines += [f'| {mode}: none eligible | n/a | n/a |']
    lines += ['', 'Abnormal mode estimates OLS beta with intercept and residual standard error (n−2) on prior 60 close returns; subtracts beta × SPY move from close and gap, without subtracting intercept. Raw uses prior 20 returns. Their first warm-up dates differ; the requested November data start cannot supply 60 returns for early FIT.', '',
              'Limitations: ' + ' '.join(LIMITATIONS), '',
              f"Run: {result['runTimestamp']}; {result['runtimeSeconds']:.1f} seconds. Coverage, hashes, all metrics and grid results are in `config/history-check-2026-11-16.json`; every simulated trade and signal score is in `config/history-trades-2026-11-16.jsonl.gz`."]
    Path(path).write_text('\n'.join(lines)+'\n', encoding='utf-8')
