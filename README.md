# WooMoo

## Run it

Python 3.11+ is required. The screener uses NumPy, pandas, and yfinance.
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
access; universe building and screening require Yahoo network access. An offline setup with cached packages is:

```powershell
uv pip install --offline --python .venv/Scripts/python.exe pytest setuptools
.\.venv\Scripts\python.exe -m pip install --no-index --no-build-isolation -e ".[dev]"
```

**Windows note:** If Application Control blocks a downloaded NumPy wheel, create
`.venv` with `python -m venv --system-site-packages .venv` to reuse trusted system
NumPy and pandas (NumPy 2.5.x and pandas 3.x). For an existing environment, enable
`include-system-site-packages = true` in `.venv/pyvenv.cfg` and uninstall its local
NumPy/pandas copies. Use `pip install --no-deps` when installing the project or
other packages so pip does not replace those trusted dependencies; ensure the
remaining dependencies are already available.

Both ledger CLI tools expand literal wildcards on Windows. Fixture generation
replaces the three named fixture files and copies November 19 to
`game/fixture/events.jsonl`; it never accesses a broker or live market data.
The fixtures are fictional contract examples, not a portfolio backtest.
SQLite is a disposable projection; JSONL is the source of truth.

See [the event contract](docs/event-contract.md) for schemas, examples, integrity
limits, and the single-writer requirement. Only `SIMULATE` is accepted.

## Preregistered configuration

All strategy defaults are data in `moowoo/config.py`. The 17 Nov setup adopts the
FIT-selected abnormal-move thresholds. See `PREREGISTRATION.md` for the planned
live experiment, allocation, risk rules and verdicts. These settings are not proof
that a portfolio executor or broker risk enforcement has been implemented.

After committing the code, freeze its defaults and source provenance with:

```powershell
.venv/Scripts/python scripts/freeze_config.py --date 2026-11-17
```

The default inputs are `config/universe-2026-11-16.json` and
`config/history-check-2026-11-16.json`. The output is `config/frozen-<date>.json`.
`--universe`, `--history-check` and `--out` override those paths. The passing-list
hash and FIT recommendations are checked before writing. No network calls occur.
`configHash` covers the canonical JSON of the full payload except itself, including
the source commit SHA. Repeating at the same commit with unchanged inputs gives
identical bytes and hash. Commit the freeze and preregistration after the code
commit; the embedded SHA identifies the code, not its later artifact commit.
Prompts remain `pending` until a dated pre-order addendum freezes their hash.
