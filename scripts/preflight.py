"""Validate a locally supplied account list and preregistration before a run."""

import argparse
import hashlib

from _execution import command, frozen_config, read_json
from hash_prompts import prompt_version
from plan_session import ROOT
from moowoo.events import canonical_bytes
from moowoo.execution import preflight
from moowoo.portfolio import PortfolioState


def run(args, log):
    frozen = frozen_config()
    universe = read_json(ROOT / frozen["universe"]["file"])["passing"]
    if hashlib.sha256(canonical_bytes(sorted(universe))).hexdigest() != frozen["universe"]["passingSha256"]:
        raise ValueError("frozen universe hash mismatch")
    preflight(read_json(args.accounts), PortfolioState.from_dict(read_json(args.state)),
              frozen, (ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8"),
              prompt_version(), universe, log)
    return dict(started=True, runId=log.runId)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("accounts", "state", "log"):
        parser.add_argument("--" + name, required=True)
    return command(parser.parse_args(), run)


if __name__ == "__main__":
    raise SystemExit(main())
