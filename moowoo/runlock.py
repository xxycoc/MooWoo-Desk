"""Account-wide 45-minute lease acquired by a non-force ledger-branch push."""

from datetime import datetime, timedelta, timezone
import json
import uuid

from .calendar import local_time, utc_stamp
from .ledger import EventLog
from .persistence import LedgerError


def acquire(store, kind, now=None, holder=None):
    now = local_time(now or datetime.now(timezone.utc))
    if kind not in ("morning", "watch", "audit"):
        raise ValueError("unknown run kind")
    store.restore()
    path = store.directory / "locks/run.lock"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if old and local_time(old["expiresAt"]) > now:
        raise LedgerError("account run lock is held; skip this overlapping session")
    lock = dict(holder=holder or uuid.uuid4().hex, kind=kind, startedAt=now.isoformat(),
                expiresAt=(now + timedelta(minutes=45)).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lock) + "\n", encoding="utf-8")
    if old:
        EventLog(store.directory / f"logs/lock-{lock['holder']}.jsonl", runId=f"lock-{lock['holder']}").append(
            "reflection_note", dict(prompt="Run lock", text="Expired lease taken over", previousHolder=old["holder"]), ts=utc_stamp(now))
    store.commit("Acquire account run lock")
    if store.git("push", store.remote, "HEAD:refs/heads/ledger", check=False).returncode:
        # Never rebase a lock acquisition: a second winner would violate exclusivity.
        raise LedgerError("run lock acquisition lost a race or push failed; do not run; local copy retained")
    return lock


def require_owned(store, holder, now=None):
    if not store.fetch():
        raise LedgerError("ledger branch missing")
    # Fetch can outlast the lease; read the live clock only after it returns.
    now = local_time(now or datetime.now(timezone.utc))
    lock = store.remote_lock()
    if not lock or lock.get("holder") != holder or local_time(lock["expiresAt"]) <= now:
        raise LedgerError("run lease expired or ownership lost; no further agent/order work")
    return lock
