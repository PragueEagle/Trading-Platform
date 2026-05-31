from dataclasses import dataclass
from decimal import Decimal

from feature_engine.candle import Candle
from feature_engine.indicators import (
    atr,
    drawdown_from_high,
    ema,
    realized_volatility,
    returns,
    volume_ratio,
)

__all__ = ["MIN_BARS", "InsufficientHistory", "FeatureRow", "compute_features"]

MIN_BARS = 200  # ema200 seed requirement


class InsufficientHistory(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FeatureRow:
    ts: int
    close: Decimal
    ema20: Decimal | None
    ema50: Decimal | None
    ema200: Decimal | None
    atr14: Decimal | None
    ret_7d: Decimal | None
    ret_30d: Decimal | None
    realized_vol: Decimal | None
    volume_ratio: Decimal | None
    drawdown: Decimal
    dist_from_ema50: Decimal | None


def compute_features(candles: list[Candle], *, bars_per_day: int = 24) -> list[FeatureRow]:
    if len(candles) < MIN_BARS:
        raise InsufficientHistory(f"need >= {MIN_BARS} candles, got {len(candles)}")
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    vols = [c.volume for c in candles]

    ema20 = ema(closes, period=20)
    ema50 = ema(closes, period=50)
    ema200 = ema(closes, period=200)
    atr14 = atr(highs, lows, closes, period=14)
    ret7 = returns(closes, lookback=7 * bars_per_day)
    ret30 = returns(closes, lookback=30 * bars_per_day)
    rvol = realized_volatility(closes, period=30)
    vr = volume_ratio(vols, period=20)
    dd = drawdown_from_high(closes)

    rows: list[FeatureRow] = []
    for i, c in enumerate(candles):
        e50 = ema50[i]
        dist = None if e50 is None or e50 == 0 else (c.close - e50) / e50
        rows.append(FeatureRow(
            ts=c.ts, close=c.close,
            ema20=ema20[i], ema50=e50, ema200=ema200[i], atr14=atr14[i],
            ret_7d=ret7[i], ret_30d=ret30[i], realized_vol=rvol[i],
            volume_ratio=vr[i], drawdown=dd[i], dist_from_ema50=dist,
        ))
    return rows
