"""Restore/save the dedicated ledger branch, never the source branch."""

import argparse
import json
import os
import base64

import _common  # noqa: F401
from moowoo.persistence import LedgerError, LedgerStore, REMOTE


def redact_error(exc):
    message = str(exc)
    token = os.environ.get("GITHUB_LEDGER_TOKEN", "")
    if token:
        for secret in (token, base64.b64encode(("x-access-token:" + token).encode()).decode()):
            message = message.replace(secret, "[REDACTED]")
    return message


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("restore", "save"))
    parser.add_argument("--dir", default="runtime")
    parser.add_argument("--remote", default=REMOTE, help="local bare repository override for offline checks")
    parser.add_argument("--message", default="Save runtime ledger")
    parser.add_argument("--holder", help="holder returned by run lock acquisition")
    args = parser.parse_args()
    try:
        store = LedgerStore(args.dir, args.remote)
        result = store.restore() if args.command == "restore" else store.save(args.message, args.holder)
        print(json.dumps(result))
        return 0
    except (LedgerError, ValueError, OSError) as exc:
        print(redact_error(exc) if isinstance(exc, LedgerError) else "invalid runtime data; local copy retained")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
