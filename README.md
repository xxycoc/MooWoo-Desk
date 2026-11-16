# WooMoo

## Run it

Python 3.11+ is required. The core package uses only the standard library.
From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
python scripts/fixture_log.py --out fixtures/ --seed 7
python scripts/verify_ledger.py fixtures/*.jsonl
python scripts/build_ledger.py --out ledger/ledger.sqlite fixtures/*.jsonl
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of
`python`, and `.\.venv\Scripts\python.exe -m pytest` for the tests. On POSIX,
activate with `source .venv/bin/activate`. Installation may need package-index
access; all runtime commands are offline. An offline setup with cached packages is:

```powershell
uv pip install --offline --python .venv/Scripts/python.exe pytest setuptools
.\.venv\Scripts\python.exe -m pip install --no-index --no-build-isolation -e ".[dev]"
```

Both ledger CLI tools expand literal wildcards on Windows. Fixture generation
replaces the three named fixture files and copies November 19 to
`game/fixture/events.jsonl`; it never accesses a broker or live market data.
The fixtures are fictional contract examples, not a portfolio backtest.
SQLite is a disposable projection; JSONL is the source of truth.

See [the event contract](docs/event-contract.md) for schemas, examples, integrity
limits, and the single-writer requirement. Only `SIMULATE` is accepted.
