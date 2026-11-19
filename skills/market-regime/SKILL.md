---
name: market-regime
description: Use when checking whether completed SPY bars require the desk's defensive satellite entry limits.
---

# Market regime

## Inputs

Completed SPY daily bars with enough history for SMA100 and both volatility
windows, plus `moowoo/config.py`. Implementation:
`moowoo/desk_data.py::regime_filter`, consumed by `moowoo/risk.py::check`.

## Procedure

1. Supply bars through the valid as-of session, not an intraday partial candle.
2. Compute SPY close versus EMA20 and SMA100, plus sample standard deviation over five and twenty daily returns.
3. Mark the defensive regime if close is below either moving average or short volatility is at least twice long volatility.
4. Let the risk desk veto new bounce entries and cap satellite exposure at 20% in that regime. Preserve the input bars as evidence; the function returns a boolean, not a measurement breakdown.
5. If required bars are missing or invalid, report unavailable input; do not silently declare a normal regime.

## Outputs

A boolean defensive-regime decision consumed by risk checks. Existing positions
continue under `moowoo/exits.py` exit rules.

## Limits

This is a fixed entry filter, not a macroeconomic forecast. It does not change
core target weights or introduce a discretionary immediate liquidation. A normal
regime does not override drawdown, liquidity, correlation or other risk gates.
