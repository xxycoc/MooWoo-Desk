"""Reconcile supplied broker snapshots at close; never cancel orders itself."""

import argparse

from _execution import atomic_json, command, frozen_config, read_json
from moowoo.broker import parse_cash, parse_history, parse_positions
from moowoo.execution import load_tickets, reconcile
from moowoo.portfolio import PortfolioState


def run(args, log):
    tickets = load_tickets(read_json(args.tickets), log, frozen_config()["configHash"])
    history = read_json(args.history)
    pages = read_json(args.history_pages) if getattr(args, "history_pages", None) else {}
    def fetch_page(cursor):
        if cursor not in pages:
            raise ValueError("history incomplete: missing page for next_key")
        return pages[cursor]
    state, result = reconcile(tickets, parse_history(history, fetch_page),
        parse_positions(read_json(args.positions)), parse_cash(read_json(args.cash)),
        PortfolioState.from_dict(read_json(args.state)), log)
    atomic_json(args.state, state.to_dict())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-pages", help="JSON object mapping requested next_key to its response")
    for name in ("history", "positions", "cash", "tickets", "state", "log"):
        parser.add_argument("--" + name, required=True)
    return command(parser.parse_args(), run, persist_halt=True)


if __name__ == "__main__":
    raise SystemExit(main())
