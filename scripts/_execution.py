"""Shared offline command handling; one locked transaction per invocation."""

import json
from pathlib import Path

import _common
from moowoo.execution import halt, safe_reason
from moowoo.ledger import EventLog
from moowoo.runtime_logs import existing_log
from moowoo.portfolio import PortfolioState
from moowoo.input_files import InputFileError
from plan_session import atomic_json, frozen_config, read_json


def command(args, operation, *, persist_halt=False, preserved_identity=False):
    path = Path(args.log)
    log = existing_log(path) if preserved_identity and path.exists() else EventLog(path, runId=path.stem)
    with log.locked():
        try:
            result = operation(args, log)
        except InputFileError as exc:
            reason = safe_reason(exc)
            halt(log, reason, disposition="abort", stage="input_validation")
            print(json.dumps(dict(halted=False, aborted=True, reason=reason)))
            return 2
        except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
            reason = safe_reason(exc)
            halt(log, reason)
            if persist_halt:
                state = PortfolioState.from_dict(read_json(args.state))
                state.halted, state.haltReason = True, reason
                atomic_json(args.state, state.to_dict())
            print(json.dumps(dict(halted=True, reason=reason)))
            return 2
    print(json.dumps(result, allow_nan=False))
    return 2 if result.get("halted") else 0
