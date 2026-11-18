"""Keep all generated test artifacts inside the repository's ignored area."""

from pathlib import Path
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fixture_log import generate_fixture


@pytest.fixture
def fixture_paths(tmp_path):
    return generate_fixture(tmp_path / "fixtures", 7, tmp_path / "game" / "events.jsonl")


def pytest_configure(config):
    # pytest deletes basetemp at startup. Parallel invocations must not delete
    # another rehearsal's local bare ledger while require_owned is fetching it.
    base = config.option.basetemp
    if base and Path(base).resolve() == ROOT / ".pytest_tmp":
        # pytest creates only the last path component; a fresh clone has no parent yet.
        (ROOT / ".pytest_tmp").mkdir(exist_ok=True)
        config.option.basetemp = str(ROOT / ".pytest_tmp" / f"run-{os.getpid()}")
