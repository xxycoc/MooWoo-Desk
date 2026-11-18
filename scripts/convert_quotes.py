"""Convert raw analyst Moomoo quote responses, refusing missing or stale evidence."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import _common  # noqa: F401
from moowoo import calendar, config as C
from moowoo.broker import decimal_number, ticker
from gather_inputs import context
from plan_session import atomic_json, read_json


def quote_rows(payload):
    """Accept one broker envelope, MCP text envelope, or list of batch replies."""
    if isinstance(payload, list):
        return [row for batch in payload for row in quote_rows(batch)]
    if not isinstance(payload, dict):
        raise ValueError("quote response must be an envelope")
    if "content" in payload:
        if payload.get("isError") or not isinstance(payload["content"], list):
            raise ValueError("failed MCP quote response")
        blocks = payload["content"]
        if not blocks or any(block.get("type") != "text" for block in blocks):
            raise ValueError("expected MCP JSON text blocks")
        return [row for block in blocks for row in quote_rows(json.loads(block["text"]))]
    if type(payload.get("ret_code")) is not int or payload["ret_code"] != 0:
        raise ValueError("unsuccessful quote response")
    if not isinstance(payload.get("ret_msg"), str):
        raise ValueError("missing quote response status")
    values = payload.get("data")
    if isinstance(values, dict):
        # The live quote_market_snapshot tool returns data.snapshot_list (17 Nov rerun 10).
        keys = [key for key in ("quotes", "snapshots", "snapshot_list") if key in values]
        values = values[keys[0]] if len(keys) == 1 else None
    if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
        raise ValueError("expected data list, data.quotes, data.snapshots or data.snapshot_list")
    return values


def quote_time(row):
    stamp = row.get("update_time")
    if type(stamp) in (int, float) and not isinstance(stamp, bool):
        # Live snapshots give update_time as Unix epoch milliseconds.
        seconds = stamp / 1000 if stamp > 1e11 else stamp
        return calendar.local_time(datetime.fromtimestamp(seconds, timezone.utc))
    if row.get("data_date") and row.get("data_time"):
        # Moomoo/Futu US quote data_date/data_time are exchange-local wall time.
        value = datetime.fromisoformat(row["data_date"] + "T" + row["data_time"])
        if value.tzinfo is not None:
            raise ValueError("data_date/data_time must be exchange-local wall time")
        return calendar.local_time(value.replace(tzinfo=calendar.NEW_YORK))
    value = datetime.fromisoformat(row["update_time"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        # Documented US market snapshot format; this is source time, not receipt time.
        value = datetime.strptime(row["update_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=calendar.NEW_YORK)
    return calendar.local_time(value)


def parse_quote(row):
    """Shared source timestamp and price parsing for planning and dispatch."""
    if not isinstance(row.get("code"), str) or not row["code"].startswith("US."):
        raise ValueError("quote must identify a US security")
    stamp = quote_time(row)
    quote = {target: decimal_number(row[source], target)
             for target, source in (("last", "last_price"), ("bid", "bid_price"), ("ask", "ask_price"))}
    if quote["bid"] > quote["ask"]:
        raise ValueError("crossed quote")
    quote["ts"] = calendar.utc_stamp(stamp)
    return ticker(row["code"]), quote


def convert(inputs, now=None):
    inputs = Path(inputs).resolve()
    # A failed refresh must not leave the previous valid snapshot usable.
    request = read_json(inputs / "quote-request.json")
    now = calendar.local_time(now or datetime.now(timezone.utc))
    inputs, _, control = context(inputs, request["kind"], now)
    (inputs / "quotes.json").unlink(missing_ok=True)
    session = read_json(inputs / "session.json")
    if (request["runId"] != control["runId"] or session["runId"] != control["runId"]
            or request["sessionDate"] != now.date().isoformat()
            or session["sessionDate"] != request["sessionDate"]):
        raise ValueError("quote request does not match current session")
    expected = {ticker(code) for code in request["codes"]}
    raw = read_json(inputs / "quotes-raw.json") if expected else []
    quotes = {}
    for row in quote_rows(raw):
        symbol, quote = parse_quote(row)
        if symbol not in expected or symbol in quotes:
            raise ValueError("unexpected or duplicate quote symbol")
        if not 0 <= (now - calendar.local_time(quote["ts"])).total_seconds() <= C.STALE_PRICE_SECONDS:
            raise ValueError("stale or future quote timestamp")
        quotes[symbol] = quote
    if set(quotes) != expected:
        raise ValueError("missing requested quotes")
    atomic_json(inputs / "quotes.json", dict(runId=control["runId"], now=calendar.utc_stamp(now),
        sessionDate=request["sessionDate"], quotes=quotes))
    return dict(converted=True, quotes=len(quotes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--now", help="Aware clock override for offline rehearsal only")
    args = parser.parse_args()
    try:
        print(json.dumps(convert(args.inputs, args.now)))
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, "quote conversion refused; check raw envelope, requested symbols, prices and source timestamps; retain evidence and abort\n")


if __name__ == "__main__":
    main()
