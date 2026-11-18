"""Reconcile supplied broker snapshots at close; never cancel orders itself."""

import argparse
from pathlib import Path

from _execution import atomic_json, command, frozen_config, read_json
from moowoo.broker import parse_cash, parse_history, parse_positions
from moowoo.execution import load_tickets, reconcile
from moowoo.portfolio import PortfolioState
from moowoo.runtime_logs import existing_log, index_logs


class RuntimeLogs:
    """Read all durable runs; route fill appends to the original decision's log."""

    def __init__(self, logs, current):
        self.logs = index_logs([*logs, current])
        self.current, self.runId = current, current.runId

    def read(self):
        return sorted((event for log in self.logs.values() for event in log.read()), key=lambda event: (event["ts"], event["runId"], event["seq"]))

    def append(self, kind, payload, decisionId=None, **kwargs):
        target = self.logs[decisionId.rsplit(":", 1)[0]] if decisionId else self.current
        return target.append(kind, payload, decisionId=decisionId, **kwargs)


def run(args, log):
    config_hash = frozen_config()["configHash"]
    handoffs = []
    if getattr(args, "runtime", None):
        root = Path(args.runtime)
        logs = [log if path.resolve() == log.path.resolve() else existing_log(path)
                for path in sorted((root / "logs").glob("*.jsonl"))]
        by_run = index_logs(logs)
        tickets = {}
        for path in sorted((root / "tickets").glob("*.json")):
            manifest = read_json(path)
            source = by_run[manifest["runId"]]
            loaded = load_tickets(manifest, source, config_hash)
            if tickets.keys() & loaded.keys():
                raise ValueError("duplicate ticket manifest")
            tickets.update(loaded)
            handoff_path = root / "inputs" / manifest["runId"] / "handoffs.json"
            if handoff_path.exists():
                saved = read_json(handoff_path)
                if not isinstance(saved, list):
                    raise ValueError("handoffs must be a list")
                handoffs.extend(row for row in saved if isinstance(row, dict)
                    and row.get("decisionId") in loaded)
        log = RuntimeLogs(logs, log)
    else:
        tickets = load_tickets(read_json(args.tickets), log, config_hash)
    history = read_json(args.history)
    pages = read_json(args.history_pages) if getattr(args, "history_pages", None) else {}
    def fetch_page(cursor):
        if cursor not in pages:
            raise ValueError("history incomplete: missing page for next_key")
        return pages[cursor]
    rows = parse_history(history, fetch_page)
    if getattr(args, "runtime", None):
        submitted = {event["orderId"] for event in log.read() if event["type"] == "order_submitted" and not event["drill"]}
        if any(row["orderId"] not in submitted for row in rows):
            raise ValueError("account history contains an unrecorded order; record its receipt first")
    state, result = reconcile(tickets, rows,
        parse_positions(read_json(args.positions)), parse_cash(read_json(args.cash)),
        PortfolioState.from_dict(read_json(args.state)), log,
        history_complete=True, handoffs=handoffs)
    atomic_json(args.state, state.to_dict())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-pages", help="JSON object mapping requested next_key to its response")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tickets")
    source.add_argument("--runtime", help="reconcile all immutable manifests and original run logs")
    for name in ("history", "positions", "cash", "state", "log"):
        parser.add_argument("--" + name, required=True)
    return command(parser.parse_args(), run, persist_halt=True, preserved_identity=True)


if __name__ == "__main__":
    raise SystemExit(main())
