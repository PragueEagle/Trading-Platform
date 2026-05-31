from decimal import Decimal

from backtest.engine import Bar, run_backtest, step_bar
from backtest.portfolio import Portfolio
from backtest.types import BacktestConfig, EquityPoint
from risk_engine.policy import RiskPolicy
from strategy_engine.trend_rotation import SignalAction, StrategySignal

DAY = 86_400_000


def _bar(ts, o, c, hi, lo):
    return Bar(ts=ts, symbol="ETH/USDT", open=Decimal(o), close=Decimal(c),
               high=Decimal(hi), low=Decimal(lo))


def _strategy(ts, holdings, bars_now):
    if "ETH/USDT" in holdings:
        return [StrategySignal("ETH/USDT", ts, SignalAction.HOLD, Decimal("1"))]
    return [StrategySignal("ETH/USDT", ts, SignalAction.ENTER, Decimal("1"))]


def _series():
    return {"ETH/USDT": [
        _bar(0, "100", "100", "101", "99"),
        _bar(DAY, "100", "110", "111", "99"),
        _bar(2 * DAY, "110", "121", "122", "109"),
    ]}


def test_step_bar_loop_matches_run_backtest_no_risk() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    series = _series()
    expected = run_backtest(series, _strategy, config=cfg, max_positions=1)

    # Manual replication using step_bar
    timestamps = sorted({b.ts for bars in series.values() for b in bars})
    by_ts = {}
    for sym, bars in series.items():
        for b in bars:
            by_ts.setdefault(b.ts, {})[sym] = b
    pf = Portfolio(cash=cfg.starting_cash, config=cfg)
    stops: dict[str, Decimal] = {}
    pending: list[StrategySignal] = []
    state = None
    fills, trades = [], []
    equity = []
    for ts in timestamps:
        bars_now = by_ts[ts]
        out = step_bar(
            ts=ts, bars_now=bars_now, pending=pending, pf=pf, stops=stops,
            state=state, config=cfg, max_positions=1, risk_policy=None,
            atr_for_ts={}, bar_ms=DAY,
        )
        fills += out.fills
        trades += out.trades
        state = out.state
        close_prices = {s: b.close for s, b in bars_now.items()}
        equity.append(EquityPoint(ts=ts, equity=pf.equity(close_prices)))
        pending = _strategy(ts, set(pf.positions.keys()), bars_now)

    assert [(f.ts, f.side, f.price) for f in fills] == \
           [(f.ts, f.side, f.price) for f in expected.fills]
    assert [t.pnl for t in trades] == [t.pnl for t in expected.trades]
    assert [e.equity for e in equity] == [e.equity for e in expected.equity_curve]


def test_step_bar_loop_matches_run_backtest_with_risk() -> None:
    cfg = BacktestConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    policy = RiskPolicy(atr_stop_mult=Decimal("2"))
    series = _series()
    atr = {"ETH/USDT": {0: Decimal("5"), DAY: Decimal("5"), 2 * DAY: Decimal("5")}}
    expected = run_backtest(series, _strategy, config=cfg, max_positions=1,
                            risk_policy=policy, atr_by_symbol=atr, bar_ms=DAY)

    timestamps = sorted({b.ts for bars in series.values() for b in bars})
    by_ts = {}
    for sym, bars in series.items():
        for b in bars:
            by_ts.setdefault(b.ts, {})[sym] = b
    from risk_engine.state import RiskState
    sc = cfg.starting_cash
    state = RiskState(
        equity=sc, cash=sc, open_exposure=Decimal("0"), open_positions=0,
        day_start_equity=sc, week_start_equity=sc, realized_pnl_today=Decimal("0"),
        realized_pnl_week=Decimal("0"), consecutive_losses=0, cooldown_until_ts=0,
        trades_today=0, kill_switch_active=False, day_index=-1, week_index=-1,
    )
    pf = Portfolio(cash=sc, config=cfg)
    stops: dict[str, Decimal] = {}
    pending: list[StrategySignal] = []
    fills, trades = [], []
    equity = []
    for ts in timestamps:
        bars_now = by_ts[ts]
        atr_for_ts = {s: atr.get(s, {}).get(ts, Decimal("0")) for s in bars_now}
        out = step_bar(
            ts=ts, bars_now=bars_now, pending=pending, pf=pf, stops=stops,
            state=state, config=cfg, max_positions=1, risk_policy=policy,
            atr_for_ts=atr_for_ts, bar_ms=DAY,
        )
        fills += out.fills
        trades += out.trades
        state = out.state
        close_prices = {s: b.close for s, b in bars_now.items()}
        equity.append(EquityPoint(ts=ts, equity=pf.equity(close_prices)))
        pending = _strategy(ts, set(pf.positions.keys()), bars_now)

    assert [(f.ts, f.side, f.price) for f in fills] == \
           [(f.ts, f.side, f.price) for f in expected.fills]
    assert [t.pnl for t in trades] == [t.pnl for t in expected.trades]
    assert [e.equity for e in equity] == [e.equity for e in expected.equity_curve]
