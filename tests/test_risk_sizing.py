from decimal import Decimal

from risk_engine.sizing import size_position


def test_size_from_risk_per_trade_and_stop_distance() -> None:
    # risk_capital = 10000 * 0.005 = 50 ; stop distance = 100 - 90 = 10 -> qty 5
    qty = size_position(
        equity=Decimal("10000"), risk_per_trade_pct=Decimal("0.005"),
        entry_price=Decimal("100"), stop_price=Decimal("90"),
        max_position_size_pct=Decimal("1"), available_exposure=Decimal("100000"),
    )
    assert qty == Decimal("5")


def test_position_size_cap_clamps_quantity() -> None:
    # uncapped qty would be 5 (notional 500); cap 1% of 10000 = 100 notional -> qty 1
    qty = size_position(
        equity=Decimal("10000"), risk_per_trade_pct=Decimal("0.005"),
        entry_price=Decimal("100"), stop_price=Decimal("90"),
        max_position_size_pct=Decimal("0.01"), available_exposure=Decimal("100000"),
    )
    assert qty == Decimal("1")


def test_exposure_headroom_clamps_quantity() -> None:
    qty = size_position(
        equity=Decimal("10000"), risk_per_trade_pct=Decimal("0.005"),
        entry_price=Decimal("100"), stop_price=Decimal("90"),
        max_position_size_pct=Decimal("1"), available_exposure=Decimal("200"),
    )
    assert qty == Decimal("2")  # 200 notional / 100 price


def test_zero_when_stop_not_below_entry() -> None:
    qty = size_position(
        equity=Decimal("10000"), risk_per_trade_pct=Decimal("0.005"),
        entry_price=Decimal("100"), stop_price=Decimal("100"),
        max_position_size_pct=Decimal("1"), available_exposure=Decimal("100000"),
    )
    assert qty == Decimal("0")
