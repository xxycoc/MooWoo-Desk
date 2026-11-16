"""CLI utilities, including literal wildcard expansion for Windows shells."""

import glob
from pathlib import Path
import sys

# Permit the documented direct script entry points before an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def expand_logs(patterns):
    paths = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern)) if glob.has_magic(pattern) else [pattern]
        if not matches:
            raise ValueError(f"no logs match: {pattern}")
        paths.extend(matches)
    return paths
