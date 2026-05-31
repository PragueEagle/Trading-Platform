from decimal import Decimal

from risk_engine.ledger import on_exit, on_new_bar
from risk_engine.policy import RiskPolicy
from risk_engine.state import RiskState

DAY_MS = 86_400_000


def _state(**kw) -> RiskState:
    base = dict(
        equity=Decimal("10000"), cash=Decimal("10000"), open_exposure=Decimal("0"),
        open_positions=0, day_start_equity=Decimal("10000"),
        week_start_equity=Decimal("10000"), realized_pnl_today=Decimal("0"),
        realized_pnl_week=Decimal("0"), consecutive_losses=0,
        cooldown_until_ts=0, trades_today=3, kill_switch_active=True,
        day_index=0, week_index=0,
    )
    base.update(kw)
    return RiskState(**base)


def test_new_day_resets_daily_counters_and_kill_switch() -> None:
    s0 = _state(realized_pnl_today=Decimal("-50"))
    s1 = on_new_bar(s0, ts=DAY_MS, equity=Decimal("9950"))
    assert s1.trades_today == 0
    assert s1.realized_pnl_today == Decimal("0")
    assert s1.day_start_equity == Decimal("9950")
    assert s1.kill_switch_active is False


def test_same_day_does_not_reset() -> None:
    s0 = _state()
    s1 = on_new_bar(s0, ts=100, equity=Decimal("10000"))
    assert s1.trades_today == 3  # unchanged within the same day


def test_consecutive_losses_trip_cooldown() -> None:
    p = RiskPolicy(max_consecutive_losses=2, cooldown_bars=3)
    s = _state(consecutive_losses=1, kill_switch_active=False, trades_today=0)
    s = on_exit(s, pnl=Decimal("-10"), ts=1000, bar_ms=100, policy=p)
    assert s.consecutive_losses == 2
    assert s.cooldown_until_ts == 1000 + 3 * 100


def test_win_resets_consecutive_losses() -> None:
    p = RiskPolicy()
    s = _state(consecutive_losses=2, kill_switch_active=False)
    s = on_exit(s, pnl=Decimal("25"), ts=1000, bar_ms=100, policy=p)
    assert s.consecutive_losses == 0


def test_daily_loss_breach_trips_kill_switch() -> None:
    p = RiskPolicy(max_daily_loss_pct=Decimal("0.01"))  # limit -100 on 10000
    s = _state(kill_switch_active=False, realized_pnl_today=Decimal("-60"))
    s = on_exit(s, pnl=Decimal("-50"), ts=1000, bar_ms=100, policy=p)  # now -110
    assert s.kill_switch_active is True


def test_on_entry_increments_counters() -> None:
    from risk_engine.ledger import on_entry
    s = _state(trades_today=5, open_positions=0, open_exposure=Decimal("0"))
    s = on_entry(s, notional=Decimal("500"))
    assert s.trades_today == 6
    assert s.open_positions == 1
    assert s.open_exposure == Decimal("500")


def test_week_rollover_resets_weekly_counters() -> None:
    WEEK_MS = 7 * DAY_MS
    s0 = _state(realized_pnl_week=Decimal("-200"), week_index=0, day_index=0)
    s1 = on_new_bar(s0, ts=WEEK_MS, equity=Decimal("9800"))
    assert s1.realized_pnl_week == Decimal("0")
    assert s1.week_start_equity == Decimal("9800")
    assert s1.week_index == 1


def test_cooldown_lifts_on_expiry() -> None:
    s0 = _state(cooldown_until_ts=500, day_index=0, week_index=0)
    s1 = on_new_bar(s0, ts=500, equity=Decimal("10000"))  # ts >= cooldown -> lifted
    assert s1.cooldown_until_ts == 0


def test_breakeven_exit_continues_loss_streak() -> None:
    from risk_engine.ledger import on_exit
    p = RiskPolicy()
    s = _state(consecutive_losses=1, kill_switch_active=False)
    s = on_exit(s, pnl=Decimal("0"), ts=1000, bar_ms=100, policy=p)
    assert s.consecutive_losses == 2  # breakeven does not reset
