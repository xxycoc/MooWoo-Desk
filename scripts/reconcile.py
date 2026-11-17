"""Reconcile supplied broker snapshots at close; never cancel orders itself."""

import argparse

from _execution import atomic_json, command, frozen_config, read_json
from moowoo.broker import parse_cash, parse_history, parse_positions
from moowoo.execution import load_tickets, reconcile
from moowoo.portfolio import PortfolioState


def run(args, log):
    tickets = load_tickets(read_json(args.tickets), log, frozen_config()["configHash"])
    state, result = reconcile(tickets, parse_history(read_json(args.history)),
        parse_positions(read_json(args.positions)), parse_cash(read_json(args.cash)),
        PortfolioState.from_dict(read_json(args.state)), log)
    atomic_json(args.state, state.to_dict())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "positions", "cash", "tickets", "state", "log"):
        parser.add_argument("--" + name, required=True)
    return command(parser.parse_args(), run, persist_halt=True)


if __name__ == "__main__":
    raise SystemExit(main())
