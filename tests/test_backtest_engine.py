from decimal import Decimal

from backtest.engine import Bar, run_backtest
from backtest.types import BacktestConfig


def _bars(symbol: str, closes: list[str]) -> list[Bar]:
    return [
        Bar(ts=i * 3_600_000, symbol=symbol, open=Decimal(c), close=Decimal(c),
            high=Decimal(c), low=Decimal(c))
        for i, c in enumerate(closes)
    ]


def _always_enter(ts, holdings, bars_by_symbol):
    from strategy_engine.trend_rotation import SignalAction, StrategySignal
    if "ETH/USDT" in holdings:
        return [StrategySignal("ETH/USDT", ts, SignalAction.HOLD, Decimal("1"))]
    return [StrategySignal("ETH/USDT", ts, SignalAction.ENTER, Decimal("1"))]


def test_signal_fills_at_next_bar_open_not_same_close() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    series = {"ETH/USDT": _bars("ETH/USDT", ["100", "110", "121"])}
    result = run_backtest(series, _always_enter, config=cfg, max_positions=1)
    assert result.fills[0].price == Decimal("110")


def test_mutating_future_bar_does_not_change_past_fill() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    base = {"ETH/USDT": _bars("ETH/USDT", ["100", "110", "121"])}
    r1 = run_backtest(base, _always_enter, config=cfg, max_positions=1)
    mutated = {"ETH/USDT": _bars("ETH/USDT", ["100", "110", "999"])}
    r2 = run_backtest(mutated, _always_enter, config=cfg, max_positions=1)
    assert r1.fills[0].price == r2.fills[0].price == Decimal("110")


def _enter_then_exit(ts, holdings, bars_by_symbol):
    from strategy_engine.trend_rotation import SignalAction, StrategySignal
    # enter ETH on bar 0, exit on bar 1, then stay flat
    if ts == 0 and "ETH/USDT" not in holdings:
        return [StrategySignal("ETH/USDT", ts, SignalAction.ENTER, Decimal("1"))]
    if "ETH/USDT" in holdings:
        return [StrategySignal("ETH/USDT", ts, SignalAction.EXIT, Decimal("0"))]
    return []


def test_engine_records_a_trade_on_exit_with_net_pnl() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    # enter fills at bar1 open (110), exit fills at bar2 open (121)
    series = {"ETH/USDT": _bars("ETH/USDT", ["100", "110", "121"])}
    result = run_backtest(series, _enter_then_exit, config=cfg, max_positions=1)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == Decimal("110")
    assert trade.exit_price == Decimal("121")
    assert trade.pnl > 0  # bought 110, sold 121, no costs


def test_fill_price_reflects_slippage() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("100"))  # 1%
    series = {"ETH/USDT": _bars("ETH/USDT", ["100", "100", "100"])}
    result = run_backtest(series, _always_enter, config=cfg, max_positions=1)
    # buy fill at next-bar open 100 * (1 + 1%) = 101
    assert result.fills[0].side == "buy"
    assert result.fills[0].price == Decimal("101")
