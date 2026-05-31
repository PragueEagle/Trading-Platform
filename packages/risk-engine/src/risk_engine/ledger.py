from dataclasses import replace
from decimal import Decimal

from risk_engine.policy import RiskPolicy
from risk_engine.state import RiskState

DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS


def on_new_bar(state: RiskState, *, ts: int, equity: Decimal) -> RiskState:
    new = replace(state, equity=equity)
    day = ts // DAY_MS
    week = ts // WEEK_MS
    if day != state.day_index:
        new = replace(
            new, day_index=day, day_start_equity=equity,
            realized_pnl_today=Decimal("0"), trades_today=0, kill_switch_active=False,
        )
    if week != state.week_index:
        new = replace(new, week_index=week, week_start_equity=equity,
                      realized_pnl_week=Decimal("0"))
    if ts >= state.cooldown_until_ts:
        new = replace(new, cooldown_until_ts=0)
    return new


def on_entry(state: RiskState, *, notional: Decimal) -> RiskState:
    # Note: open_exposure/open_positions here are advisory. In the backtest the engine
    # re-derives them from the live Portfolio before each evaluate_entry, so it is the
    # source of truth. A future live path that drives the ledger standalone must also
    # decrement these on exit (see on_exit) to keep them symmetric.
    return replace(
        state, trades_today=state.trades_today + 1,
        open_positions=state.open_positions + 1,
        open_exposure=state.open_exposure + notional,
    )


def on_exit(
    state: RiskState, *, pnl: Decimal, ts: int, bar_ms: int, policy: RiskPolicy
) -> RiskState:
    realized_today = state.realized_pnl_today + pnl
    realized_week = state.realized_pnl_week + pnl
    # Only a profitable exit resets the streak; breakeven (pnl == 0) continues it,
    # so a run of scratch trades cannot indefinitely defer the cooldown.
    consecutive = 0 if pnl > 0 else state.consecutive_losses + 1
    cooldown = state.cooldown_until_ts
    if consecutive >= policy.max_consecutive_losses:
        cooldown = ts + policy.cooldown_bars * bar_ms
    kill = state.kill_switch_active
    if realized_today <= -(policy.max_daily_loss_pct * state.day_start_equity):
        kill = True
    return replace(
        state, realized_pnl_today=realized_today, realized_pnl_week=realized_week,
        consecutive_losses=consecutive, cooldown_until_ts=cooldown,
        kill_switch_active=kill,
    )
