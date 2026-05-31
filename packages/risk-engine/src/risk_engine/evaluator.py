from decimal import Decimal

from risk_engine.policy import MarketConditions, RiskPolicy
from risk_engine.sizing import size_position
from risk_engine.state import RiskDecision, RiskState

# Effectively-unbounded caps used to compute the uncapped risk-target quantity, so we can
# tell whether the real (capped) size was reduced.
_UNBOUNDED = Decimal("1E30")


def evaluate_entry(
    *,
    policy: RiskPolicy,
    state: RiskState,
    entry_price: Decimal,
    atr: Decimal,
    market: MarketConditions,
    ts: int,
) -> RiskDecision:
    reasons: list[str] = []

    if state.kill_switch_active:
        reasons.append("kill_switch_active")
    if state.realized_pnl_today <= -(policy.max_daily_loss_pct * state.day_start_equity):
        reasons.append("daily_loss_limit")
    if state.realized_pnl_week <= -(policy.max_weekly_loss_pct * state.week_start_equity):
        reasons.append("weekly_loss_limit")
    if ts < state.cooldown_until_ts:
        reasons.append("cooldown_active")
    if state.trades_today >= policy.max_trades_per_day:
        reasons.append("max_trades_per_day")
    if policy.block_if_data_stale and market.data_stale:
        reasons.append("data_stale")
    if policy.block_if_spread_too_wide and market.spread_too_wide:
        reasons.append("spread_too_wide")
    if policy.block_if_exchange_degraded and market.exchange_degraded:
        reasons.append("exchange_degraded")
    if atr <= 0:
        reasons.append("no_atr")

    if reasons:
        return RiskDecision(approved=False, quantity=Decimal("0"), reasons=tuple(reasons))

    stop_price = entry_price - policy.atr_stop_mult * atr
    exposure_cap = policy.max_total_exposure_pct * state.equity
    available_exposure = max(Decimal("0"), exposure_cap - state.open_exposure)
    target_qty = size_position(
        equity=state.equity, risk_per_trade_pct=policy.risk_per_trade_pct,
        entry_price=entry_price, stop_price=stop_price,
        max_position_size_pct=Decimal("1"), available_exposure=_UNBOUNDED,
    )
    sized_qty = size_position(
        equity=state.equity, risk_per_trade_pct=policy.risk_per_trade_pct,
        entry_price=entry_price, stop_price=stop_price,
        max_position_size_pct=policy.max_position_size_pct,
        available_exposure=available_exposure,
    )
    if sized_qty <= 0:
        return RiskDecision(approved=False, quantity=Decimal("0"),
                            reasons=("no_exposure_headroom",))
    out_reasons = ("reduced_size",) if sized_qty < target_qty else ()
    return RiskDecision(approved=True, quantity=sized_qty, reasons=out_reasons)
