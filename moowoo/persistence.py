"""Dedicated ledger-branch transport. Credentials exist only in child environment."""

import base64
import json
import os
from pathlib import Path
import subprocess

from .ledger import verify
from .runtime_logs import existing_log, index_logs

# Private repo: raw receipts and tickets carry the account ID; the source repo is public.
REMOTE = "https://github.com/xxycoc/MooWoo-Ledger"


class LedgerError(RuntimeError):
    pass


class LedgerStore:
    def __init__(self, directory, remote=REMOTE):
        self.directory = Path(directory).resolve()
        # Overrides are local bare repositories, never arbitrary credential-bearing URLs.
        if remote != REMOTE and not Path(remote).is_dir():
            raise LedgerError("ledger remote must be the configured GitHub repository or a local repository")
        self.remote = remote if remote == REMOTE else str(Path(remote).resolve())

    def git(self, *args, check=True):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GIT_", "GCM_")) and k != "GITHUB_LEDGER_TOKEN"}
        token = os.environ.get("GITHUB_LEDGER_TOKEN", "")
        if self.remote == REMOTE and not token:
            raise LedgerError("GITHUB_LEDGER_TOKEN is required")
        auth = base64.b64encode(("x-access-token:" + token).encode()).decode()
        configs = [("credential.helper", ""), ("core.hooksPath", os.devnull),
                   ("commit.gpgSign", "false"), ("core.autocrlf", "false"),
                   ("user.name", "MooWoo ledger"), ("user.email", "ledger@moowoo.invalid")]
        if token:
            configs.append(("http.https://github.com/.extraHeader", "Authorization: Basic " + auth))
        env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_CONFIG_COUNT=str(len(configs)))
        for index, (key, value) in enumerate(configs):
            env[f"GIT_CONFIG_KEY_{index}"] = key
            env[f"GIT_CONFIG_VALUE_{index}"] = value
        try:
            # stdin=DEVNULL: an inherited stdin handle can hang local fetches on Windows.
            result = subprocess.run(["git", "-C", str(self.directory), *args], env=env,
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            raise LedgerError("ledger git command failed or timed out; local copy retained") from None
        for secret in (token, auth):
            if secret:
                result.stdout = result.stdout.replace(secret, "[REDACTED]")
                result.stderr = result.stderr.replace(secret, "[REDACTED]")
        if check and result.returncode:
            # Git can echo arbitrary remote content. Do not surface it as an exception.
            raise LedgerError(f"ledger git {args[0]} failed; local copy retained")
        return result

    def verify_logs(self):
        for path in self.directory.rglob("*.jsonl"):
            if ".git" in path.relative_to(self.directory).parts:
                continue
            result = verify(path)
            if not result.ok:
                raise LedgerError(f"broken event chain in {path.relative_to(self.directory)} at seq {result.bad_seq}; save refused")
        try:
            index_logs(existing_log(path) for path in (self.directory / "logs").glob("*.jsonl"))
        except ValueError as exc:
            raise LedgerError(str(exc)) from exc
        for path in (self.directory / "handoffs").glob("*.json"):
            handoff = json.loads(path.read_text(encoding="utf-8"))
            for name, checkpoint in handoff["logs"].items():
                source = (self.directory / name).resolve()
                if not source.is_relative_to(self.directory / "logs"):
                    raise LedgerError("handoff log escapes runtime logs")
                events = existing_log(source).read()
                count = checkpoint["count"]
                if len(events) < count or (count and events[count - 1]["hash"] != checkpoint["hash"]):
                    raise LedgerError("handoff terminal checkpoint does not match preserved log prefix")

    def fetch(self):
        result = self.git("ls-remote", "--exit-code", self.remote, "refs/heads/ledger", check=False)
        if result.returncode == 2:
            return False
        if result.returncode:
            raise LedgerError("cannot inspect ledger branch; authentication/transport failure, not an empty ledger")
        self.git("fetch", "--no-tags", self.remote, "refs/heads/ledger:refs/remotes/origin/ledger")
        return True

    def assert_repository(self):
        if not (self.directory / ".git").is_dir():
            raise LedgerError("restore the dedicated runtime repository first")
        if self.git("branch", "--show-current").stdout.strip() != "ledger":
            raise LedgerError("refusing to write any branch other than ledger")
        if self.git("rev-parse", "--show-toplevel").stdout.strip().replace("\\", "/").lower() != self.directory.as_posix().lower():
            raise LedgerError("runtime must be its own repository")
        if (self.directory / ".git/rebase-merge").exists() or (self.directory / ".git/rebase-apply").exists():
            raise LedgerError("unresolved ledger rebase conflict; local copy retained")

    def restore(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if not (self.directory / ".git").exists():
            if any(self.directory.iterdir()):
                raise LedgerError("restore destination is not empty; refusing to overwrite runtime data")
            self.git("init", "--initial-branch=ledger")
            (self.directory / ".git/info/exclude").write_text(".session.json\n*.jsonl.lock\n", encoding="utf-8")
        self.assert_repository()
        if self.git("status", "--porcelain").stdout.strip():
            raise LedgerError("runtime has unsaved changes; save or inspect before restore")
        exists = self.fetch()
        if exists:
            has_head = self.git("rev-parse", "--verify", "HEAD", check=False).returncode == 0
            if has_head:
                self.git("merge", "--ff-only", "refs/remotes/origin/ledger")
            else:
                self.git("checkout", "-B", "ledger", "refs/remotes/origin/ledger")
        elif self.git("rev-parse", "--verify", "HEAD", check=False).returncode == 0:
            raise LedgerError("remote ledger disappeared; local copy retained")
        self.verify_logs()
        return dict(restored=exists, message="ledger restored" if exists else "ledger branch does not exist yet; starting empty")

    def remote_lock(self):
        result = self.git("show", "refs/remotes/origin/ledger:locks/run.lock", check=False)
        return json.loads(result.stdout) if result.returncode == 0 else None

    def commit(self, message):
        self.verify_logs()
        # Runtime is the complete durable payload; never add credentials or local control files.
        if any(p.name == ".env" or p.is_symlink() for p in self.directory.rglob("*") if ".git" not in p.relative_to(self.directory).parts):
            raise LedgerError("runtime contains a secret file or symlink; refusing save")
        self.git("add", "--all", "--", ".")
        if self.git("diff", "--cached", "--quiet", check=False).returncode:
            self.git("commit", "-m", message)
        elif self.git("rev-parse", "--verify", "HEAD", check=False).returncode:
            self.git("commit", "--allow-empty", "-m", message)

    def save(self, message, holder=None, *, release=True, before_push=None):
        self.assert_repository()
        self.verify_logs()
        exists = self.fetch()
        if not exists and self.git("rev-parse", "--verify", "refs/remotes/origin/ledger", check=False).returncode == 0:
            raise LedgerError("remote ledger disappeared; refusing to recreate it from a stale copy")
        remote_lock = self.remote_lock() if exists else None
        if remote_lock and remote_lock.get("holder") != holder:
            raise LedgerError("ledger is owned by another run; local copy retained")
        local_lock = self.directory / "locks/run.lock"
        if local_lock.exists():
            lock = json.loads(local_lock.read_text(encoding="utf-8"))
            if not holder or lock.get("holder") != holder:
                raise LedgerError("save requires the lock holder")
            if release:
                local_lock.unlink()
        self.commit(message)
        for attempt in range(4):  # initial push plus at most three pull/rebase retries
            exists = self.fetch()
            if exists:
                lock = self.remote_lock()
                if lock and lock.get("holder") != holder:
                    raise LedgerError("lock changed before save; local copy retained")
                if holder and (not lock or lock.get("holder") != holder):
                    raise LedgerError("lock ownership lost before save; local copy retained")
                result = self.git("rebase", "refs/remotes/origin/ledger", check=False)
                if result.returncode:
                    raise LedgerError("ledger rebase conflict; stopped without force push; resolve local copy manually")
            self.verify_logs()
            if before_push is not None:
                before_push()
            result = self.git("push", self.remote, "HEAD:refs/heads/ledger", check=False)
            if result.returncode == 0:
                return dict(saved=True, unlocked=bool(holder and release), commit=self.git("rev-parse", "HEAD").stdout.strip())
        raise LedgerError("ledger push failed after three retries; local copy retained, do not trade")
