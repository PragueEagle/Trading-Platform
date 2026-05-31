# tests/test_backtest_risk.py
from decimal import Decimal

from backtest.engine import Bar, run_backtest
from backtest.types import BacktestConfig
from risk_engine.policy import RiskPolicy
from strategy_engine.trend_rotation import SignalAction, StrategySignal

DAY = 86_400_000


def _bar(ts: int, sym: str, o: str, c: str, hi: str, lo: str) -> Bar:
    return Bar(ts=ts, symbol=sym, open=Decimal(o), close=Decimal(c),
               high=Decimal(hi), low=Decimal(lo))


def _enter_once(ts, holdings, bars_now):
    if "ETH/USDT" in holdings:
        return [StrategySignal("ETH/USDT", ts, SignalAction.HOLD, Decimal("1"))]
    return [StrategySignal("ETH/USDT", ts, SignalAction.ENTER, Decimal("1"))]


def test_stop_loss_exit_recorded_when_low_breaches_stop() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    policy = RiskPolicy(atr_stop_mult=Decimal("2"))
    # bar0 decide; bar1 fill at open 100 with atr 5 -> stop = 100 - 10 = 90;
    # bar2 low 80 breaches stop -> stop_loss exit recorded
    series = {"ETH/USDT": [
        _bar(0, "ETH/USDT", "100", "100", "101", "99"),
        _bar(DAY, "ETH/USDT", "100", "100", "101", "99"),
        _bar(2 * DAY, "ETH/USDT", "100", "85", "101", "80"),
    ]}
    atr = {"ETH/USDT": {0: Decimal("5"), DAY: Decimal("5"), 2 * DAY: Decimal("5")}}
    result = run_backtest(series, _enter_once, config=cfg, max_positions=1,
                          risk_policy=policy, atr_by_symbol=atr, bar_ms=DAY)
    assert any(f.side == "stop" for f in result.fills)
    assert any(r.symbol == "ETH/USDT" and r.approved for r in result.risk_decisions)


def test_consecutive_losses_trigger_cooldown_blocking_entries() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    policy = RiskPolicy(max_consecutive_losses=1, cooldown_bars=10,
                        atr_stop_mult=Decimal("1"))

    def _always_try_enter(ts, holdings, bars_now):
        if "ETH/USDT" in holdings:
            return [StrategySignal("ETH/USDT", ts, SignalAction.HOLD, Decimal("1"))]
        return [StrategySignal("ETH/USDT", ts, SignalAction.ENTER, Decimal("1"))]

    # repeated entries that immediately stop out (low gaps below stop next bar)
    bars = []
    for i in range(6):
        bars.append(_bar(i * DAY, "ETH/USDT", "100", "100", "101",
                         "80" if i % 2 == 1 else "99"))
    series = {"ETH/USDT": bars}
    atr = {"ETH/USDT": {i * DAY: Decimal("5") for i in range(6)}}
    result = run_backtest(series, _always_try_enter, config=cfg, max_positions=1,
                          risk_policy=policy, atr_by_symbol=atr, bar_ms=DAY)
    # after the first stop-loss (a loss), cooldown blocks the next entry attempt
    blocked = [r for r in result.risk_decisions
               if not r.approved and "cooldown_active" in r.reasons]
    assert blocked, "expected at least one entry blocked by cooldown"


def test_none_policy_reproduces_spec1_behavior() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    series = {"ETH/USDT": [
        _bar(0, "ETH/USDT", "100", "100", "101", "99"),
        _bar(DAY, "ETH/USDT", "110", "110", "111", "109"),
    ]}
    result = run_backtest(series, _enter_once, config=cfg, max_positions=1)
    assert result.risk_decisions == []
    assert result.fills[0].price == Decimal("110")  # fraction-based entry unchanged


def test_strategy_exit_loss_trips_cooldown() -> None:
    # A losing strategy EXIT (not a stop) must feed the ledger so a 1-loss cooldown
    # blocks the next entry attempt.
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    policy = RiskPolicy(max_consecutive_losses=1, cooldown_bars=10,
                        atr_stop_mult=Decimal("5"))  # wide stop so it never stops out

    def _enter_then_exit_at_loss(ts, holdings, bars_now):
        if "ETH/USDT" in holdings:
            return [StrategySignal("ETH/USDT", ts, SignalAction.EXIT, Decimal("0"))]
        return [StrategySignal("ETH/USDT", ts, SignalAction.ENTER, Decimal("1"))]

    # enter at bar1 open 100; bar2 EXIT fills at open 90 -> realized loss
    bars = [
        _bar(0, "ETH/USDT", "100", "100", "101", "99"),
        _bar(DAY, "ETH/USDT", "100", "100", "101", "95"),
        _bar(2 * DAY, "ETH/USDT", "90", "90", "91", "89"),
        _bar(3 * DAY, "ETH/USDT", "90", "90", "91", "89"),
    ]
    atr = {"ETH/USDT": {i * DAY: Decimal("1") for i in range(4)}}
    result = run_backtest({"ETH/USDT": bars}, _enter_then_exit_at_loss, config=cfg,
                          max_positions=1, risk_policy=policy, atr_by_symbol=atr,
                          bar_ms=DAY)
    assert any(t.pnl < 0 for t in result.trades)  # the strategy exit was a loss
    assert any(not r.approved and "cooldown_active" in r.reasons
               for r in result.risk_decisions)
