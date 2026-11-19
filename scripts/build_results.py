"""Build docs/results.{md,json}: auditable competition results from the private ledger."""

from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import random
import re
from statistics import mean

import _common  # noqa: F401  (makes moowoo importable for direct script runs)
from moowoo import audit, calendar, hypotheses
from moowoo.outcomes import instant, price, read_events

START_EQUITY = 100000
SPY_START_DAY = "2026-11-17"
BOOTSTRAP_SEED = 7
BOOTSTRAP_RESAMPLES = 10000
LONG_NUMBER = re.compile(r"\d{7,}")
PRIVATE_KEY = re.compile(
    r"account|acc_?id|token|secret|password|authorization|credential|api_?key|raw.*payload|broker.*payload",
    re.I,
)


def mask_number(text: str) -> str:
    return LONG_NUMBER.sub(lambda match: "***" + match.group()[-4:], text)


def scrub(value: object) -> object:
    """Mask long digit runs and drop private keys; never emit raw payload fields."""
    if isinstance(value, dict):
        return {mask_number(str(key)): scrub(child) for key, child in value.items()
                if not PRIVATE_KEY.search(str(key))}
    if isinstance(value, list):
        return [scrub(child) for child in value]
    if isinstance(value, str):
        return mask_number(value)
    if isinstance(value, float):
        return round(value, 6)
    return value


def verified_report(ledger: Path, day: date) -> float | None:
    path = ledger / "reports" / f"{day.isoformat()}.json"
    if not path.is_file():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(report, dict) or report.get("reconciliationVerified") is not True:
        return None
    equity = report.get("equity")
    if type(equity) not in (int, float) or not math.isfinite(equity) or equity <= 0:
        return None
    return float(equity)


def broker_total(ledger: Path, run_id: str) -> float | None:
    """Only the numeric total_asset is read; the raw payload never leaves this function."""
    path = ledger / "inputs" / run_id / "cash.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    raw = data.get("total_asset") if isinstance(data, dict) else None
    if not isinstance(raw, str):
        return None
    try:
        value = float(raw.replace(",", "").replace("$", "").strip())
    except ValueError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def run_starts(events: list[dict]) -> dict[str, dict]:
    latest = {}
    for event in events:
        if event["type"] != "run_started":
            continue
        prior = latest.get(event["runId"])
        if prior is None or instant(event["ts"]) > instant(prior["ts"]):
            latest[event["runId"]] = event
    return latest


def latest_data_day(ledger: Path, starts: dict[str, dict]) -> date | None:
    days = {day for day in calendar.TRADING_DAYS if verified_report(ledger, day) is not None}
    for run_id, event in starts.items():
        local = calendar.local_time(event["ts"])
        if local.date() in calendar.TRADING_DAYS and broker_total(ledger, run_id) is not None:
            days.add(local.date())
    return max(days) if days else None


def daily_rows(ledger: Path, starts: dict[str, dict], latest: date | None) -> tuple[list[dict], list[str]]:
    rows, missing = [], []
    for day in sorted(calendar.TRADING_DAYS):
        if latest is None or day > latest:
            break
        equity, source = None, "missing"
        report = verified_report(ledger, day)
        if report is not None:
            equity, source = report, "audit report"
        else:
            snapshots = []
            for run_id, event in starts.items():
                local = calendar.local_time(event["ts"])
                if local.date() != day:
                    continue
                value = broker_total(ledger, run_id)
                if value is not None:
                    snapshots.append((instant(event["ts"]), run_id, value, local))
            if snapshots:
                _, _, equity, local = max(snapshots, key=lambda row: (row[0], row[1]))
                source = f"last broker snapshot {local.strftime('%H:%M')} ET"
        rows.append(dict(day=day.isoformat(), equity=equity, source=source))
        if equity is None:
            missing.append(day.isoformat())
    return rows, missing


def daily_returns(rows: list[dict]) -> list[float] | None:
    equities = [row["equity"] for row in rows]
    if not equities or any(value is None for value in equities):
        return None
    series = [START_EQUITY, *equities]
    return [later / earlier - 1 for earlier, later in zip(series, series[1:])]


def bootstrap(returns: list[float] | None) -> dict:
    result = dict(mean=None, interval95=None, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED)
    if not returns:
        return result
    generator = random.Random(BOOTSTRAP_SEED)
    samples = sorted(mean(generator.choices(returns, k=len(returns)))
                     for _ in range(BOOTSTRAP_RESAMPLES))

    def percentile(fraction: float) -> float:
        index = (len(samples) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(samples) - 1)
        return samples[lower] + (samples[upper] - samples[lower]) * (index - lower)

    result.update(mean=mean(returns), interval95=[percentile(.025), percentile(.975)])
    return result


def spy_comparison(ledger: Path) -> dict:
    bars = []
    for folder in sorted((ledger / "inputs").glob("*")):
        path = folder / "bars.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            bars.append(data)
    result = dict(start=f"{SPY_START_DAY} regular-session open", end=None, returnPct=None,
                  reason="unavailable: no SPY bars in inputs/")
    if not bars:
        return result
    closes = {}
    for day in sorted(calendar.TRADING_DAYS):
        for data in bars:
            try:
                closes[day] = price(data, "SPY", day.isoformat(), "close")
            except ValueError:
                continue
    start = None
    for data in bars:
        try:
            start = price(data, "SPY", SPY_START_DAY, "open")
            break
        except ValueError:
            continue
    if start is None:
        return result | dict(reason="unavailable: missing SPY 17 Nov regular-session open")
    if not closes:
        return result | dict(reason="unavailable: missing SPY session close")
    end = max(closes)
    return dict(start=result["start"], end=f"{end.isoformat()} close",
                returnPct=closes[end] / start - 1, reason=None)


def hypothesis_summary(events: list[dict]) -> dict:
    scored = hypotheses.score(events)
    matched = scored["H2"]["matched"]

    def mean_or_none(values: list[float]) -> float | None:
        return mean(values) if values else None

    return dict(
        H1=dict(matched=scored["H1"]["count"], right=scored["H1"]["right"],
                hitRate=scored["H1"]["hitRate"], interval95=scored["H1"]["interval95"],
                verdict=scored["H1"]["verdict"]),
        H2=dict(matched=scored["H2"]["count"],
                followExcess=mean_or_none([row["followExcess"] for row in matched]),
                fadeExcess=mean_or_none([row["fadeExcess"] for row in matched]),
                llmExcess=mean_or_none([row["llmExcess"] for row in matched]),
                versusFollow=scored["H2"]["comparisons"]["versusFollow"]["mean"],
                versusFade=scored["H2"]["comparisons"]["versusFade"]["mean"],
                verdict=scored["H2"]["verdict"]),
        H3=dict(matched=scored["H3"]["count"], brier=scored["H3"]["brier"],
                interval95=scored["H3"]["interval95"], verdict=scored["H3"]["verdict"]),
    )


def trade_rows(events: list[dict]) -> list[dict]:
    intents = {event["decisionId"]: event.get("side") for event in events
               if event["type"] == "order_intent"}
    orders = [event for event in events if event["type"] == "order_submitted"]
    fills = [event for event in events if event["type"] == "fill"]

    def side(decision_id: str, order: dict | None = None, fill: dict | None = None) -> str:
        for value in ((order or {}).get("side"), (fill or {}).get("side"), intents.get(decision_id)):
            if isinstance(value, str) and value:
                return value
        return "unavailable"

    def et_stamp(ts: str) -> str:
        return calendar.local_time(ts).strftime("%Y-%m-%d %H:%M ET")

    def number(value: object) -> float | None:
        return float(value) if type(value) in (int, float) and math.isfinite(value) else None

    rows, filled = [], set()
    for fill in sorted(fills, key=lambda event: instant(event["ts"])):
        order = next((row for row in orders if row["decisionId"] == fill["decisionId"]
                      and row.get("orderId") == fill.get("orderId")), None)
        if order is None:
            order = next((row for row in orders if row["decisionId"] == fill["decisionId"]), None)
        if order is not None:
            filled.add(order["hash"])
        rows.append(dict(
            timeEt=et_stamp(fill["ts"]),
            ticker=fill.get("ticker") or (order or {}).get("ticker", "unavailable"),
            side=side(fill["decisionId"], order, fill),
            filledQty=number(fill.get("filledQty")),
            avgPrice=number(fill.get("avgPrice")),
            fees=number(fill.get("fees")),
            status=fill.get("status", "unavailable"),
            orderId=fill.get("orderId"),
        ))
    for order in sorted(orders, key=lambda event: instant(event["ts"])):
        if order["hash"] in filled:
            continue
        rows.append(dict(
            timeEt=et_stamp(order["ts"]),
            ticker=order.get("ticker", "unavailable"),
            side=side(order["decisionId"], order),
            filledQty=None,
            avgPrice=None,
            fees=None,
            status="submitted; no fill recorded",
            orderId=order.get("orderId"),
        ))
    return sorted(rows, key=lambda row: (row["timeEt"], str(row["ticker"])))


def action_counts(events: list[dict]) -> dict:
    buckets = dict(vetoes={}, skips={}, halts={})

    def bump(bucket: dict, reason: object) -> None:
        label = reason.strip() if isinstance(reason, str) and reason.strip() else "unspecified"
        bucket[label] = bucket.get(label, 0) + 1

    for event in events:
        if event["type"] == "risk_verdict" and event.get("verdict") == "veto":
            bump(buckets["vetoes"], event.get("firedRule"))
        if event.get("skipped") is True or event.get("executionAction") == "skip":
            bump(buckets["skips"], event.get("reason") or event.get("text"))
        if event["type"] == "halt":
            bump(buckets["halts"], event.get("reason"))
    return {name: dict(sorted(bucket.items())) for name, bucket in buckets.items()}


def money(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:,.2f}"


def percent(value: float | None) -> str:
    return "unavailable" if value is None else f"{value * 100:.2f}%"


def number_text(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.3f}"


def ratio(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.2f}"


def quantity(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:g}"


def price_text(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.4f}"


def markdown(results: dict) -> str:
    lines = [
        "# MooWoo Desk results",
        "",
        "Paper trading only, US stocks and ETFs, long only. Returns are fractions unless a "
        "value is shown with a percent sign.",
        "",
        "## Daily equity",
        "",
        "| Day | Equity (USD) | Source |",
        "| --- | ---: | --- |",
    ]
    for row in results["days"]:
        lines.append(f"| {row['day']} | {money(row['equity'])} | {row['source']} |")
    if not results["days"]:
        lines.append("| — | unavailable | no equity data |")
    lines += ["", f"Latest data day: {results['latestDataDay'] or 'unavailable'}."]
    if results["missingDays"]:
        lines.append("Missing days: " + ", ".join(results["missingDays"]) +
                     ". No value is interpolated across a gap.")
    else:
        lines.append("No missing days: every session has a reconciled audit report or a broker snapshot.")

    metrics = results["metrics"]
    lines += ["", "## Account metrics", ""]
    if results["metricsUnavailableReason"]:
        lines.append("Metrics unavailable: " + results["metricsUnavailableReason"] + ".")
    lines += [
        f"- Total return: {percent(metrics['totalReturn'])}",
        f"- Sharpe (annualised): {ratio(metrics['sharpe'])}",
        f"- Sortino (annualised): {ratio(metrics['sortino'])}",
        f"- Calmar (annualised): {ratio(metrics['calmar'])}",
        f"- Max drawdown: {percent(metrics['maxDrawdown'])}",
        "",
        "Annualised ratios over about eight sessions are unstable and descriptive only.",
    ]

    boot = results["dailyMean"]
    lines += ["", "## Mean daily return", ""]
    if boot["mean"] is None:
        lines.append("- Mean daily return: unavailable (requires a complete daily equity series).")
        lines.append("- 95% bootstrap interval: unavailable.")
    else:
        lines.append(f"- Mean daily return: {percent(boot['mean'])}")
        lines.append(f"- 95% bootstrap interval: {percent(boot['interval95'][0])} to "
                     f"{percent(boot['interval95'][1])} "
                     f"({boot['resamples']:,} resamples, seed {boot['seed']}).")

    spy = results["spy"]
    lines += ["", "## SPY comparison", ""]
    if spy["returnPct"] is None:
        lines.append(f"- SPY return: {spy['reason']}.")
    else:
        lines.append(f"- SPY return from the {spy['start']} to the {spy['end']}: "
                     f"{percent(spy['returnPct'])}.")

    h = results["hypotheses"]
    lines += ["", "## Preregistered hypotheses", ""]
    h1_interval = ("unavailable" if not h["H1"]["interval95"] else
                   f"{percent(h['H1']['interval95'][0])} to {percent(h['H1']['interval95'][1])}")
    lines.append(f"- H1: matched {h['H1']['matched']}; hit rate {percent(h['H1']['hitRate'])}; "
                 f"95% interval {h1_interval}; verdict {h['H1']['verdict']}.")
    lines.append(f"- H2: matched {h['H2']['matched']}; mean excess follow "
                 f"{percent(h['H2']['followExcess'])}, fade {percent(h['H2']['fadeExcess'])}, "
                 f"LLM {percent(h['H2']['llmExcess'])}; verdict {h['H2']['verdict']}.")
    h3_interval = ("unavailable" if not h["H3"]["interval95"] else
                   f"{number_text(h['H3']['interval95'][0])} to {number_text(h['H3']['interval95'][1])}")
    lines.append(f"- H3: matched {h['H3']['matched']}; Brier score {number_text(h['H3']['brier'])}; "
                 f"95% interval {h3_interval}; verdict {h['H3']['verdict']}.")

    lines += ["", "## Trades", ""]
    if results["trades"]:
        lines += ["| Time (ET) | Ticker | Side | Filled qty | Average price | Fees (USD) | Status |",
                  "| --- | --- | --- | ---: | ---: | ---: | --- |"]
        for row in results["trades"]:
            lines.append(f"| {row['timeEt']} | {row['ticker']} | {row['side']} | "
                         f"{quantity(row['filledQty'])} | {price_text(row['avgPrice'])} | "
                         f"{money(row['fees'])} | {row['status']} |")
    else:
        lines.append("No orders recorded.")

    lines += ["", "## Risk actions and halts", ""]
    for key, title in (("vetoes", "Vetoes"), ("skips", "Skips"), ("halts", "Halts")):
        lines.append(f"### {title} by reason")
        lines.append("")
        if results["counts"][key]:
            lines += [f"- {reason}: {count}" for reason, count in results["counts"][key].items()]
        else:
            lines.append("- None recorded.")
        lines.append("")

    lines += [
        "## Privacy",
        "",
        "Account IDs, tokens and raw broker payloads are never included. Any number of seven "
        "or more digits, including order IDs, is masked as *** plus its last four digits.",
        "",
    ]
    return "\n".join(lines)


def build(ledger: Path, out: Path) -> dict:
    ledger, out = Path(ledger), Path(out)
    if not (ledger / "logs").is_dir():
        raise ValueError(f"missing logs directory: {ledger / 'logs'}")
    events = [event for event in read_events(sorted((ledger / "logs").glob("*.jsonl")))
              if not event["drill"]]
    starts = run_starts(events)
    latest = latest_data_day(ledger, starts)
    rows, missing = daily_rows(ledger, starts, latest)
    returns = daily_returns(rows)
    metrics_values = dict(totalReturn=None, sharpe=None, sortino=None, calmar=None, maxDrawdown=None)
    reason = None
    if not rows:
        reason = "no equity data"
    elif missing:
        reason = "missing daily equity for " + ", ".join(missing)
    else:
        calculated = audit.metrics([START_EQUITY, *[row["equity"] for row in rows]])
        metrics_values = {key: calculated[key] for key in metrics_values}
        if any(value is None for value in metrics_values.values()):
            reason = "insufficient observations or zero denominator"
    results = dict(
        schemaVersion=1,
        returnUnit="fraction unless a field ends in Pct",
        startEquity=START_EQUITY,
        latestDataDay=latest.isoformat() if latest else None,
        days=rows,
        missingDays=missing,
        metrics=metrics_values,
        metricsUnavailableReason=reason,
        dailyMean=bootstrap(returns),
        spy=spy_comparison(ledger),
        hypotheses=hypothesis_summary(events),
        trades=trade_rows(events),
        counts=action_counts(events),
    )
    results = scrub(results)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n",
                                      encoding="utf-8", newline="\n")
    (out / "results.md").write_text(markdown(results), encoding="utf-8", newline="\n")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    results = build(args.ledger, args.out)
    print(f"Wrote {args.out / 'results.md'} and {args.out / 'results.json'} "
          f"({len(results['days'])} days, {len(results['trades'])} trades)")


if __name__ == "__main__":
    main()
