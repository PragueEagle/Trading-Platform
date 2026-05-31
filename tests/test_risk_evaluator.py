from decimal import Decimal

from risk_engine.evaluator import evaluate_entry
from risk_engine.policy import MarketConditions, RiskPolicy
from risk_engine.state import RiskState


def _state(**kw) -> RiskState:
    base = dict(
        equity=Decimal("10000"), cash=Decimal("10000"), open_exposure=Decimal("0"),
        open_positions=0, day_start_equity=Decimal("10000"),
        week_start_equity=Decimal("10000"), realized_pnl_today=Decimal("0"),
        realized_pnl_week=Decimal("0"), consecutive_losses=0,
        cooldown_until_ts=0, trades_today=0, kill_switch_active=False,
        day_index=0, week_index=0,
    )
    base.update(kw)
    return RiskState(**base)


def test_approves_and_sizes_a_clean_entry() -> None:
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(), entry_price=Decimal("100"),
        atr=Decimal("5"), market=MarketConditions(), ts=0,
    )
    assert d.approved and d.quantity > 0


def test_kill_switch_blocks() -> None:
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(kill_switch_active=True),
        entry_price=Decimal("100"), atr=Decimal("5"), market=MarketConditions(), ts=0,
    )
    assert not d.approved and "kill_switch_active" in d.reasons


def test_daily_loss_halt_blocks() -> None:
    # realized loss today = -150 ; limit 1% of 10000 = -100 -> halt
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(realized_pnl_today=Decimal("-150")),
        entry_price=Decimal("100"), atr=Decimal("5"), market=MarketConditions(), ts=0,
    )
    assert not d.approved and "daily_loss_limit" in d.reasons


def test_cooldown_active_blocks() -> None:
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(cooldown_until_ts=1000),
        entry_price=Decimal("100"), atr=Decimal("5"), market=MarketConditions(), ts=500,
    )
    assert not d.approved and "cooldown_active" in d.reasons


def test_trades_per_day_cap_blocks() -> None:
    d = evaluate_entry(
        policy=RiskPolicy(max_trades_per_day=2), state=_state(trades_today=2),
        entry_price=Decimal("100"), atr=Decimal("5"), market=MarketConditions(), ts=0,
    )
    assert not d.approved and "max_trades_per_day" in d.reasons


def test_data_stale_gate_blocks() -> None:
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(), entry_price=Decimal("100"),
        atr=Decimal("5"), market=MarketConditions(data_stale=True), ts=0,
    )
    assert not d.approved and "data_stale" in d.reasons


def test_zero_atr_rejects_no_atr() -> None:
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(), entry_price=Decimal("100"),
        atr=Decimal("0"), market=MarketConditions(), ts=0,
    )
    assert not d.approved and "no_atr" in d.reasons


def test_weekly_loss_halt_blocks() -> None:
    # realized loss this week = -350 ; limit 3% of 10000 = -300 -> halt
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(realized_pnl_week=Decimal("-350")),
        entry_price=Decimal("100"), atr=Decimal("5"), market=MarketConditions(), ts=0,
    )
    assert not d.approved and "weekly_loss_limit" in d.reasons


def test_spread_too_wide_gate_blocks() -> None:
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(), entry_price=Decimal("100"),
        atr=Decimal("5"), market=MarketConditions(spread_too_wide=True), ts=0,
    )
    assert not d.approved and "spread_too_wide" in d.reasons


def test_exchange_degraded_gate_blocks() -> None:
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(), entry_price=Decimal("100"),
        atr=Decimal("5"), market=MarketConditions(exchange_degraded=True), ts=0,
    )
    assert not d.approved and "exchange_degraded" in d.reasons


def test_no_exposure_headroom_rejects() -> None:
    # already fully exposed: open_exposure == 30% cap -> no headroom
    d = evaluate_entry(
        policy=RiskPolicy(), state=_state(open_exposure=Decimal("3000")),
        entry_price=Decimal("100"), atr=Decimal("5"), market=MarketConditions(), ts=0,
    )
    assert not d.approved and "no_exposure_headroom" in d.reasons
