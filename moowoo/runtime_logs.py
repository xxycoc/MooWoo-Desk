"""Open preserved logs by their recorded identities, never their filenames."""

import json

from .ledger import EventLog, verify


def existing_log(path):
    result = verify(path)
    if not result.ok:
        raise ValueError("invalid runtime event chain")
    with path.open(encoding="utf-8") as stream:
        first = stream.readline()
    if not first:
        raise ValueError("runtime log has no event identity")
    return EventLog(path, runId=json.loads(first)["runId"])


def index_logs(logs):
    indexed = {}
    for log in logs:
        if log.runId in indexed and indexed[log.runId].path.resolve() != log.path.resolve():
            raise ValueError("ambiguous duplicate runtime log identity")
        indexed[log.runId] = log
    return indexed
