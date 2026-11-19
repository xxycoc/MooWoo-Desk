"""Input transport errors abort a run, never disable the next scheduled run."""
import json
from pathlib import Path


class InputFileError(ValueError):
    pass


def read_input(path):
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InputFileError(f"{path.name}: missing input file") from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise InputFileError(f"{path.name}: invalid JSON input") from exc


def broker_input(path, parser, *args):
    try:
        return parser(read_input(path), *args)
    except InputFileError as exc:
        raise InputFileError(f"{Path(path).name}: {exc}") from exc
    except (KeyError, TypeError, AttributeError) as exc:
        raise InputFileError(f"{Path(path).name}: invalid broker input shape") from exc
