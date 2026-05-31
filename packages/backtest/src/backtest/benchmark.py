from decimal import Decimal

from backtest.engine import Bar
from backtest.types import EquityPoint


def buy_and_hold_curve(bars: list[Bar], *, starting_cash: Decimal) -> list[EquityPoint]:
    if not bars:
        return []
    first = bars[0].open
    qty = starting_cash / first if first > 0 else Decimal("0")
    return [EquityPoint(ts=b.ts, equity=qty * b.close) for b in bars]
