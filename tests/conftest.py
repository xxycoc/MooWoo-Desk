"""Keep all generated test artifacts inside the repository's ignored area."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fixture_log import generate_fixture


@pytest.fixture
def fixture_paths(tmp_path):
    return generate_fixture(tmp_path / "fixtures", 7, tmp_path / "game" / "events.jsonl")
