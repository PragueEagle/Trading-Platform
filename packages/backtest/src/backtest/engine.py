from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal

from risk_engine import (
    MarketConditions,
    RiskDecisionRecord,
    RiskPolicy,
    RiskState,
    evaluate_entry,
    on_entry,
    on_exit,
    on_new_bar,
)
from strategy_engine.trend_rotation import SignalAction, StrategySignal

from backtest.portfolio import Portfolio
from backtest.types import (
    BacktestConfig,
    EquityPoint,
    Trade,
    buy_fill_price,
    sell_fill_price,
)


@dataclass(frozen=True, slots=True)
class Bar:
    ts: int
    symbol: str
    open: Decimal
    close: Decimal
    high: Decimal
    low: Decimal


@dataclass(frozen=True, slots=True)
class Fill:
    ts: int
    symbol: str
    side: str
    price: Decimal


@dataclass(slots=True)
class BacktestResult:
    equity_curve: list[EquityPoint] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    risk_decisions: list[RiskDecisionRecord] = field(default_factory=list)
    kill_switch_trips: int = 0


StrategyFn = Callable[[int, set[str], dict[str, "Bar"]], list[StrategySignal]]


@dataclass(frozen=True, slots=True)
class StepOutput:
    fills: list[Fill]
    trades: list[Trade]
    risk_decisions: list[RiskDecisionRecord]
    state: RiskState | None
    kill_switch_trips: int


def step_bar(
    *,
    ts: int,
    bars_now: dict[str, "Bar"],
    pending: list[StrategySignal],
    pf: Portfolio,
    stops: dict[str, Decimal],
    state: RiskState | None,
    config: BacktestConfig,
    max_positions: int,
    risk_policy: RiskPolicy | None,
    atr_for_ts: dict[str, Decimal],
    bar_ms: int,
) -> StepOutput:
    """Process one bar: roll risk window, take stop-loss exits, execute pending fills.

    Mutates `pf` and `stops`. Returns the new RiskState, the fills/trades/risk-decisions
    produced this bar, and how many times the kill switch newly tripped. The caller is
    responsible for recording the equity snapshot and computing the next `pending` via the
    strategy.
    """
    fills: list[Fill] = []
    trades: list[Trade] = []
    decisions: list[RiskDecisionRecord] = []
    kill_trips = 0
    open_prices = {s: b.open for s, b in bars_now.items()}

    if risk_policy is not None and state is not None:
        state = on_new_bar(state, ts=ts, equity=pf.equity(open_prices))

    # 1) stop-loss exits (risk mode only)
    if risk_policy is not None:
        for sym in list(pf.positions.keys()):
            bar = bars_now.get(sym)
            if bar is None or sym not in stops:
                continue
            if bar.low <= stops[sym]:
                pos = pf.positions[sym]
                entry_ts = pf.entry_ts(sym)
                stop_fill = sell_fill_price(stops[sym], config.slippage_bps)
                pnl = pf.exit(sym, ref_price=stops[sym])
                fills.append(Fill(ts, sym, "stop", stop_fill))
                trades.append(Trade(
                    symbol=sym, entry_ts=entry_ts, exit_ts=ts,
                    entry_price=pos.entry_price, exit_price=stop_fill,
                    quantity=pos.quantity, pnl=pnl,
                ))
                stops.pop(sym, None)
                if state is not None:
                    kill_before = state.kill_switch_active
                    state = on_exit(state, pnl=pnl, ts=ts, bar_ms=bar_ms,
                                    policy=risk_policy)
                    if state.kill_switch_active and not kill_before:
                        kill_trips += 1

    # 2) execute decisions from the previous close at this bar's open
    for sig in pending:
        bar = bars_now.get(sig.symbol)
        if bar is None:
            continue
        if sig.action == SignalAction.EXIT and sig.symbol in pf.positions:
            pos = pf.positions[sig.symbol]
            entry_ts = pf.entry_ts(sig.symbol)
            exit_price = sell_fill_price(bar.open, config.slippage_bps)
            pnl = pf.exit(sig.symbol, ref_price=bar.open)
            fills.append(Fill(ts, sig.symbol, "sell", exit_price))
            trades.append(Trade(
                symbol=sig.symbol, entry_ts=entry_ts, exit_ts=ts,
                entry_price=pos.entry_price, exit_price=exit_price,
                quantity=pos.quantity, pnl=pnl,
            ))
            stops.pop(sig.symbol, None)
            if risk_policy is not None and state is not None:
                kill_before = state.kill_switch_active
                state = on_exit(state, pnl=pnl, ts=ts, bar_ms=bar_ms, policy=risk_policy)
                if state.kill_switch_active and not kill_before:
                    kill_trips += 1
        elif sig.action == SignalAction.ENTER and sig.symbol not in pf.positions:
            if risk_policy is not None and state is not None:
                atr = atr_for_ts.get(sig.symbol, Decimal("0"))
                exposure: Decimal = sum(
                    (p.quantity * open_prices.get(s, p.entry_price)
                     for s, p in pf.positions.items()),
                    Decimal("0"),
                )
                state = replace(
                    state, equity=pf.equity(open_prices), cash=pf.cash,
                    open_exposure=exposure, open_positions=len(pf.positions),
                )
                decision = evaluate_entry(
                    policy=risk_policy, state=state, entry_price=bar.open,
                    atr=atr, market=MarketConditions(), ts=ts,
                )
                decisions.append(RiskDecisionRecord(
                    ts=ts, symbol=sig.symbol, approved=decision.approved,
                    quantity=decision.quantity, reasons=decision.reasons,
                ))
                if decision.approved:
                    pf.enter_quantity(sig.symbol, ref_price=bar.open,
                                      quantity=decision.quantity, ts=ts)
                    stops[sig.symbol] = bar.open - risk_policy.atr_stop_mult * atr
                    state = on_entry(state, notional=decision.quantity * bar.open)
                    fills.append(Fill(ts, sig.symbol, "buy",
                                      buy_fill_price(bar.open, config.slippage_bps)))
            else:
                fraction = Decimal("1") / Decimal(max_positions)
                pf.enter(sig.symbol, ref_price=bar.open, fraction=fraction,
                         ts=ts, prices=open_prices)
                fills.append(Fill(ts, sig.symbol, "buy",
                                  buy_fill_price(bar.open, config.slippage_bps)))

    return StepOutput(fills=fills, trades=trades, risk_decisions=decisions,
                      state=state, kill_switch_trips=kill_trips)


def run_backtest(
    series: dict[str, list[Bar]],
    strategy: StrategyFn,
    *,
    config: BacktestConfig,
    max_positions: int = 3,
    risk_policy: RiskPolicy | None = None,
    atr_by_symbol: dict[str, dict[int, Decimal]] | None = None,
    bar_ms: int = 14_400_000,
) -> BacktestResult:
    timestamps = sorted({b.ts for bars in series.values() for b in bars})
    by_ts: dict[int, dict[str, Bar]] = {}
    for sym, bars in series.items():
        for b in bars:
            by_ts.setdefault(b.ts, {})[sym] = b

    pf = Portfolio(cash=config.starting_cash, config=config)
    result = BacktestResult()
    pending: list[StrategySignal] = []
    atr_lookup = atr_by_symbol or {}
    stops: dict[str, Decimal] = {}

    state: RiskState | None = None
    if risk_policy is not None:
        sc = config.starting_cash
        state = RiskState(
            equity=sc, cash=sc, open_exposure=Decimal("0"), open_positions=0,
            day_start_equity=sc, week_start_equity=sc, realized_pnl_today=Decimal("0"),
            realized_pnl_week=Decimal("0"), consecutive_losses=0, cooldown_until_ts=0,
            trades_today=0, kill_switch_active=False, day_index=-1, week_index=-1,
        )

    for ts in timestamps:
        bars_now = by_ts[ts]
        close_prices = {s: b.close for s, b in bars_now.items()}
        atr_for_ts = {s: atr_lookup.get(s, {}).get(ts, Decimal("0")) for s in bars_now}
        out = step_bar(
            ts=ts, bars_now=bars_now, pending=pending, pf=pf, stops=stops,
            state=state, config=config, max_positions=max_positions,
            risk_policy=risk_policy, atr_for_ts=atr_for_ts, bar_ms=bar_ms,
        )
        result.fills.extend(out.fills)
        result.trades.extend(out.trades)
        result.risk_decisions.extend(out.risk_decisions)
        result.kill_switch_trips += out.kill_switch_trips
        state = out.state
        result.equity_curve.append(EquityPoint(ts=ts, equity=pf.equity(close_prices)))
        pending = strategy(ts, set(pf.positions.keys()), bars_now)

    return result
