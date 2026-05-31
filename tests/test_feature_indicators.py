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


def test_candle_holds_decimal_ohlcv() -> None:
    c = Candle(
        ts=0, open=Decimal("1"), high=Decimal("2"),
        low=Decimal("0.5"), close=Decimal("1.5"), volume=Decimal("10"),
    )
    assert c.close == Decimal("1.5")
    assert c.high >= c.low


def _series(values: list[str]) -> list[Decimal]:
    return [Decimal(v) for v in values]


def test_ema_matches_known_recurrence() -> None:
    closes = _series(["1", "2", "3"])
    result = ema(closes, period=2)
    assert result[0] is None
    assert result[1] == Decimal("1.5")
    assert result[2] == Decimal("2.5")


def test_returns_simple_pct() -> None:
    closes = _series(["100", "110", "99"])
    r = returns(closes, lookback=1)
    assert r[0] is None
    assert r[1] == Decimal("0.1")
    assert r[2] == Decimal("-0.1")


def test_atr_is_average_true_range() -> None:
    highs = _series(["10", "11", "12"])
    lows = _series(["9", "9", "11"])
    closes = _series(["9.5", "10", "11.5"])
    result = atr(highs, lows, closes, period=2)
    assert result[0] is None
    assert result[2] == Decimal("2")


def test_drawdown_from_high_is_non_positive() -> None:
    closes = _series(["10", "12", "9"])
    dd = drawdown_from_high(closes)
    assert dd[0] == Decimal("0")
    assert dd[1] == Decimal("0")
    assert dd[2] == Decimal("-0.25")


def test_volume_ratio_vs_average() -> None:
    vols = _series(["10", "10", "20"])
    vr = volume_ratio(vols, period=2)
    assert vr[0] is None
    assert vr[2] == Decimal("2")


def test_realized_volatility_zero_for_flat_series() -> None:
    closes = _series(["100", "100", "100", "100"])
    rv = realized_volatility(closes, period=3)
    assert rv[-1] == Decimal("0")
