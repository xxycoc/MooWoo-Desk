"""Prepare exact MCP arguments, or record executor-supplied JSON receipts."""

import argparse

from _execution import command, frozen_config, read_json
from hash_prompts import prompt_version
from moowoo.execution import execution_ready, load_tickets, prepare, record


def run(args, log):
    frozen = frozen_config()
    tickets = load_tickets(read_json(args.tickets), log, frozen["configHash"])
    execution_ready(log.read(), frozen["configHash"], prompt_version())
    if args.action == "prepare":
        return prepare(tickets, log)
    return record(tickets, read_json(args.responses), log)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "record"):
        subparser = subparsers.add_parser(action)
        subparser.add_argument("--tickets", required=True)
        subparser.add_argument("--log", required=True)
        if action == "record":
            subparser.add_argument("--responses", required=True)
    return command(parser.parse_args(), run)


if __name__ == "__main__":
    raise SystemExit(main())
