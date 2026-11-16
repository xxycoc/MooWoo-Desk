"""Daily indicators. Warm-up and zero denominators remain unavailable (NaN)."""

import numpy as np
import pandas as pd

from . import config as C


def ema(series, n=C.EMA_PERIOD):
    return series.ewm(span=n, adjust=False, min_periods=n).mean()


def atr(df, n=C.ATR_PERIOD):
    """Wilder smoothing seeded with the first n true ranges' arithmetic mean."""
    previous = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - previous).abs(),
                    (df.low - previous).abs()], axis=1).max(axis=1)
    tr[df[['high', 'low', 'close']].isna().any(axis=1)] = np.nan
    result = pd.Series(np.nan, index=df.index, dtype=float)
    if len(tr) >= n and tr.iloc[:n].notna().all():
        result.iloc[n - 1] = tr.iloc[:n].mean()
        for i in range(n, len(tr)):
            result.iloc[i] = (result.iloc[i - 1] * (n - 1) + tr.iloc[i]) / n
    return result


def rvol(df, n=C.VOLUME_PERIOD):
    baseline = df.volume.shift(1).rolling(n).mean().iloc[-1] if len(df) else np.nan
    return float(df.volume.iloc[-1] / baseline) if baseline > 0 else np.nan


def move_z(df, n=C.MOVE_PERIOD):
    """Signed winning z; ties select close return. Volatility excludes today."""
    unavailable = dict(z=np.nan, movePct=np.nan, kind=None, sigma=np.nan)
    if len(df) < n + 2:
        return unavailable
    returns = df.close.pct_change(fill_method=None)
    prior = returns.iloc[-n - 1:-1]
    sigma = prior.std(ddof=C.STD_DDOF) if prior.notna().all() else np.nan
    if not np.isfinite(sigma) or sigma <= 0 or df.close.iloc[-2] <= 0:
        return unavailable
    moves = {"close": returns.iloc[-1], "gap": df.open.iloc[-1] / df.close.iloc[-2] - 1}
    if not all(np.isfinite(v) for v in moves.values()):
        return unavailable
    kind = max(moves, key=lambda k: abs(moves[k]))
    return dict(z=float(moves[kind] / sigma), movePct=float(moves[kind] * 100),
                kind=kind, sigma=float(sigma))
