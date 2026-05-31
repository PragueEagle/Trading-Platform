from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    fee_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("5")
    starting_cash: Decimal = Decimal("10000")


@dataclass(slots=True)
class Position:
    symbol: str
    quantity: Decimal
    entry_price: Decimal


@dataclass(frozen=True, slots=True)
class Trade:
    symbol: str
    entry_ts: int
    exit_ts: int
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    pnl: Decimal


@dataclass(frozen=True, slots=True)
class EquityPoint:
    ts: int
    equity: Decimal


_BPS = Decimal("10000")


def buy_fill_price(ref: Decimal, slippage_bps: Decimal) -> Decimal:
    return ref * (1 + slippage_bps / _BPS)


def sell_fill_price(ref: Decimal, slippage_bps: Decimal) -> Decimal:
    return ref * (1 - slippage_bps / _BPS)


def fee(notional: Decimal, fee_bps: Decimal) -> Decimal:
    return notional * fee_bps / _BPS
