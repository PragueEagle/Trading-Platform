from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Candle:
    ts: int           # unix ms of the candle's exchange timestamp
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class _CandleOutLike(Protocol):
    exchange_timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def from_candle_out(row: _CandleOutLike) -> Candle:
    # Caller must supply a UTC-aware exchange_timestamp; naive datetimes would be
    # interpreted as local time by .timestamp(). MarketCandle stores tz-aware values.
    return Candle(
        ts=int(row.exchange_timestamp.timestamp() * 1000),
        open=row.open, high=row.high, low=row.low,
        close=row.close, volume=row.volume,
    )
