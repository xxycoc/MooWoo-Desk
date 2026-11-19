"""Save minimal broker replies from stdin and validate before any phase runs."""
import argparse
import json
from pathlib import Path
import sys

import _common
from moowoo import broker, broker_fields as fields
from moowoo.input_files import InputFileError, broker_input, read_input
from plan_session import atomic_json
from persist_ledger import redact_error

TABLES = dict(accounts=fields.ACCOUNT_LIST, cash=fields.CASH_INFO,
              positions=fields.POSITION_LIST, history=fields.ORDER_HISTORY)
PARSERS = dict(accounts=broker.parse_accounts, cash=broker.parse_cash,
               positions=broker.parse_positions, history=broker.parse_history)


def trim(payload, kind):
    data = broker.successful_data(payload)
    table = TABLES[kind]
    key = dict(accounts="accounts", positions="positions", history="orders").get(kind)
    rows = data.get(key) if key else [data]
    if not isinstance(rows, list):
        raise InputFileError(f"missing required broker rows: {key}")
    keep = set(table["required"].values()) | set(table["optional"].values())
    if kind == "cash":
        keep |= {"realized_profit", "unrealized_profit"}
    result = []
    for row in rows:
        broker.mapped(row, table)
        result.append({k: v for k, v in row.items() if k in keep})
    trimmed = dict(ret_code=payload["ret_code"], ret_msg=payload["ret_msg"],
                   data={key: result} if key else result[0])
    if kind == "history":
        for location, source in ((trimmed, payload), (trimmed["data"], data)):
            if "pagination" in source:
                location["pagination"] = source["pagination"]
    return trimmed


def validate(payload, kind):
    if kind == "history":
        # Validate each saved page now; the real full-chain parser still runs at reconciliation.
        data = broker.successful_data(payload)
        pagination = data.get("pagination", payload.get("pagination"))
        if (not isinstance(pagination, dict) or type(pagination.get("has_more")) is not bool
                or not isinstance(pagination.get("next_key"), str)):
            raise InputFileError("missing required broker pagination fields")
        if "pagination" in data and "pagination" in payload and data["pagination"] != payload["pagination"]:
            raise ValueError("conflicting broker pagination")
        if pagination["has_more"] and not pagination["next_key"]:
            raise ValueError("invalid history cursor")
        terminal = dict(has_more=False, next_key="")
        payload = payload | dict(pagination=terminal, data=data | dict(pagination=terminal))
    PARSERS[kind](payload)


def save(path, kind, raw):
    path = Path(path)
    attempts = path.with_suffix(".validation.json")
    failed = read_input(attempts).get("failures", 0) if attempts.exists() else 0
    if failed >= 3:
        raise InputFileError(f"{path.name}: two retries exhausted; abort run")
    # Never allow an earlier snapshot to survive a failed replacement.
    path.unlink(missing_ok=True)
    try:
        payload = trim(json.loads(raw), kind)
        validate(payload, kind)
        atomic_json(path, payload)
        broker_input(path, lambda value: validate(value, kind))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        atomic_json(attempts, dict(failures=failed + 1))
        raise InputFileError(f"{path.name}: {redact_error(exc)}; retries left {max(0, 2-failed)}") from exc
    attempts.unlink(missing_ok=True)
    return dict(valid=True, file=path.name)


def assemble(inputs):
    inputs = Path(inputs)
    payload = read_input(inputs / "history.json")
    pages, index = {}, 1
    while True:
        data = broker.successful_data(payload)
        pagination = data.get("pagination", payload.get("pagination"))
        validate(payload, "history")
        if not pagination["has_more"]:
            break
        cursor = pagination["next_key"]
        if cursor in pages:
            raise ValueError("repeated history cursor")
        payload = read_input(inputs / f"history-page-{index}.json")
        pages[cursor] = payload
        index += 1
    broker.parse_history(read_input(inputs / "history.json"), pages.__getitem__)
    atomic_json(inputs / "history-pages.json", pages)
    return dict(valid=True, pages=index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=TABLES)
    parser.add_argument("--file")
    parser.add_argument("--assemble", metavar="INPUTS")
    parser.add_argument("--stdin", action="store_true")
    args = parser.parse_args()
    try:
        if args.assemble:
            print(json.dumps(assemble(args.assemble)))
            return 0
        if not args.kind or not args.file:
            parser.error("--kind and --file required for a save/check")
        result = (save(args.file, args.kind, sys.stdin.read()) if args.stdin else
                  broker_input(args.file, lambda value: validate(value, args.kind)))
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        print(json.dumps(dict(valid=False, file=Path(args.file).name if args.file else "history-pages.json", reason=redact_error(exc))))
        return 2
    print(json.dumps(result or dict(valid=True, file=Path(args.file).name)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
