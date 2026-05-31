from decimal import Decimal

from backtest.benchmark import buy_and_hold_curve
from backtest.engine import Bar
from backtest.metrics import compute_metrics
from backtest.types import EquityPoint


def _curve(values: list[str]) -> list[EquityPoint]:
    return [EquityPoint(ts=i * 86_400_000, equity=Decimal(v)) for i, v in enumerate(values)]


def test_metrics_flat_curve_has_zero_drawdown_and_return() -> None:
    m = compute_metrics(_curve(["1000", "1000", "1000"]), periods_per_year=365)
    assert m["max_drawdown"] == Decimal("0")
    assert m["total_return"] == Decimal("0")


def test_metrics_drawdown_is_largest_peak_to_trough() -> None:
    m = compute_metrics(_curve(["1000", "1200", "600", "900"]), periods_per_year=365)
    assert m["max_drawdown"] == Decimal("-0.5")


def test_metrics_win_rate_and_profit_factor_with_trades() -> None:
    m = compute_metrics(
        _curve(["1000", "1100"]), periods_per_year=365,
        trade_pnls=[Decimal("100"), Decimal("-50"), Decimal("25")],
    )
    assert m["win_rate"] == Decimal("2") / Decimal("3")
    assert m["profit_factor"] == Decimal("125") / Decimal("50")


def test_buy_and_hold_curve_tracks_price() -> None:
    bars = [Bar(ts=i * 86_400_000, symbol="BTC/USDT", open=Decimal(p), close=Decimal(p),
                high=Decimal(p), low=Decimal(p))
            for i, p in enumerate(["100", "200"])]
    curve = buy_and_hold_curve(bars, starting_cash=Decimal("1000"))
    assert curve[0].equity == Decimal("1000")
    assert curve[-1].equity == Decimal("2000")


def test_cagr_annualizes_total_return() -> None:
    # Exactly one year of daily periods that doubles -> CAGR ~ 100%.
    curve = [EquityPoint(ts=i * 86_400_000, equity=Decimal(1000 + i))
             for i in range(366)]
    curve[-1] = EquityPoint(ts=365 * 86_400_000, equity=Decimal("2000"))
    m = compute_metrics(curve, periods_per_year=365)
    assert "cagr" in m
    assert m["cagr"] > Decimal("0.9")


def test_cagr_zero_for_single_point_guard() -> None:
    m = compute_metrics([EquityPoint(ts=0, equity=Decimal("1000"))], periods_per_year=365)
    assert m["cagr"] == Decimal("0")
