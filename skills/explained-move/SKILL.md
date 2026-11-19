---
name: explained-move
description: Use when selecting completed-session abnormal movers for MooWoo Desk research or explaining why a candidate was selected.
---

# Explained move

## Inputs

- Frozen eligible universe in `config/universe-2026-11-16.json`.
- Completed stock and SPY daily OHLCV bars through the calendar-selected as-of date; earnings dates when available.
- Thresholds in `moowoo/config.py` and the latest addenda in `PREREGISTRATION.md`.

## Procedure

1. Use `scripts/session_info.py` to obtain the valid prior session; do not infer it by subtracting one calendar day.
2. Use `scripts/gather_inputs.py` in the coordinator's owned run, or `scripts/screen.py --universe <file> --asof <date> --log <event-log>` for screening. The standalone screen may fetch market data.
3. `moowoo/screener.py::screen` trims bars through as-of. `moowoo/indicators.py::abnormal_move_z` measures the move against stock/SPY residual history over 60 sessions; require absolute z at least two.
4. Rank earnings-related moves first, then absolute z times relative volume capped at three; ticker breaks ties. Select at most five under PICKS-01.
5. Pass one candidate and its trusted news cutoff to the analyst. Selection is not an explanation and does not authorize a trade.

## Outputs

The screener returns selected candidates, exclusions and indicator context. The
script appends screening evidence to the event log. The runtime produces inputs
for `scripts/ingest_ratings.py` and `scripts/plan_session.py`.

## Limits

Use the frozen liquid common-stock universe, not an invented ticker list. Bars
must be completed and aligned; missing evidence is not zero. Gap candidates use
the move-session open as news cutoff, but daily selection uses full-session volume;
do not describe this as a tradable real-time gap backtest. Historical proxy tests
did not establish a holdout edge or evaluate actual LLM judgments.
