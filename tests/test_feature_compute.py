from decimal import Decimal

import pytest
from feature_engine.candle import Candle
from feature_engine.features import InsufficientHistory, compute_features


def _candles(n: int) -> list[Candle]:
    out = []
    for i in range(n):
        price = Decimal(100 + i)
        out.append(Candle(ts=i * 3_600_000, open=price, high=price + 1,
                          low=price - 1, close=price, volume=Decimal(10)))
    return out


def test_compute_features_aligns_to_candles_and_has_no_lookahead() -> None:
    candles = _candles(250)
    rows = compute_features(candles)
    assert len(rows) == len(candles)
    mid = rows[120]
    assert mid.ema50 is not None
    assert mid.ts == candles[120].ts


def test_compute_features_raises_on_insufficient_history() -> None:
    with pytest.raises(InsufficientHistory):
        compute_features(_candles(50))
