"""Concurrent pytest runs must not erase another run's local ledger repository."""
import os
from pathlib import Path
import subprocess
import sys


def test_overlapping_pytest_runs_keep_their_files(tmp_path):
    root = Path(__file__).resolve().parents[1]
    case = tmp_path / "isolated_case.py"
    case.write_text('''import time

def test_local_ledger_survives(tmp_path):
    ledger = tmp_path / "ledger-ref"
    ledger.write_text("accepted-order")
    time.sleep(2)
    assert ledger.read_text() == "accepted-order"
''')
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "tests") + os.pathsep + str(root)
    command = [sys.executable, "-m", "pytest", "-p", "conftest", "-q", str(case)]
    processes = [subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for _ in range(2)]
    try:
        for process in processes:
            output, _ = process.communicate(timeout=30)
            assert process.returncode == 0, output
    finally:
        for process in processes:
            if process.poll() is None: process.kill()
