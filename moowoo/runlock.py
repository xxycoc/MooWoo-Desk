"""Account-wide 45-minute lease acquired by a non-force ledger-branch push."""

from datetime import datetime, timedelta, timezone
import json
import uuid

from .calendar import local_time, utc_stamp
from .ledger import EventLog
from .persistence import LedgerError

LEASE_MINUTES = 45
MAX_LEASE_MINUTES = 120


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
                expiresAt=(now + timedelta(minutes=LEASE_MINUTES)).isoformat())
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


def renew(store, holder, now=None):
    lock = require_owned(store, holder, now)
    current = local_time(now or datetime.now(timezone.utc))
    if current < local_time(lock["startedAt"]):
        raise LedgerError("run lease acquisition is in the future")
    deadline = local_time(lock["startedAt"]) + timedelta(minutes=MAX_LEASE_MINUTES)
    if current >= deadline:
        raise LedgerError("run lease reached its total duration cap")
    if local_time(lock["expiresAt"]) >= deadline:
        return lock | dict(capped=True)
    renewed = lock | dict(expiresAt=min(current + timedelta(minutes=LEASE_MINUTES), deadline).isoformat())
    path = store.directory / "locks/run.lock"
    pending = json.dumps(renewed) + "\n"
    path.write_text(pending, encoding="utf-8")

    def check_renewal():
        current = local_time(now or datetime.now(timezone.utc))
        remote = store.remote_lock()
        if not remote or remote.get("holder") != holder or local_time(remote["expiresAt"]) <= current:
            raise LedgerError("run lease expired or ownership lost before renewal save")
        if remote.get("startedAt") != lock["startedAt"] or current >= deadline:
            raise LedgerError("run lease acquisition changed or total duration cap reached")
    try:
        store.save("Renew account run lock", holder, release=False, before_push=check_renewal)
    except (LedgerError, ValueError, OSError):
        if path.read_text(encoding="utf-8") == pending:
            path.write_text(json.dumps(lock) + "\n", encoding="utf-8")
        raise
    return renewed | dict(capped=local_time(renewed["expiresAt"]) >= deadline)


def require_owned(store, holder, now=None):
    if not store.fetch():
        raise LedgerError("ledger branch missing")
    # Fetch can outlast the lease; read the live clock only after it returns.
    now = local_time(now or datetime.now(timezone.utc))
    lock = store.remote_lock()
    if not lock or lock.get("holder") != holder or local_time(lock["expiresAt"]) <= now:
        raise LedgerError("run lease expired or ownership lost; no further agent/order work")
    return lock
