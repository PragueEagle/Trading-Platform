from decimal import Decimal

from backtest.portfolio import Portfolio
from backtest.types import BacktestConfig


def test_buy_applies_fee_and_slippage_and_reduces_cash() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("10"), slippage_bps=Decimal("5"))
    pf = Portfolio(cash=Decimal("1000"), config=cfg)
    pf.enter("BTC/USDT", ref_price=Decimal("100"), fraction=Decimal("0.5"))
    assert pf.positions["BTC/USDT"].quantity > 0
    assert pf.cash < Decimal("1000")


def test_round_trip_with_no_costs_is_flat() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    pf = Portfolio(cash=Decimal("1000"), config=cfg)
    pf.enter("BTC/USDT", ref_price=Decimal("100"), fraction=Decimal("1"))
    pf.exit("BTC/USDT", ref_price=Decimal("100"))
    assert pf.cash == Decimal("1000")
    assert "BTC/USDT" not in pf.positions


def test_equity_marks_to_market() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    pf = Portfolio(cash=Decimal("1000"), config=cfg)
    pf.enter("BTC/USDT", ref_price=Decimal("100"), fraction=Decimal("1"))
    assert pf.equity({"BTC/USDT": Decimal("200")}) > Decimal("1900")
