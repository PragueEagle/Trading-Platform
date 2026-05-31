from decimal import Decimal

from risk_engine.policy import MarketConditions, RiskPolicy
from risk_engine.state import RiskDecision, RiskDecisionRecord, RiskState


def test_policy_defaults_match_roadmap() -> None:
    p = RiskPolicy()
    assert p.risk_per_trade_pct == Decimal("0.005")
    assert p.max_position_size_pct == Decimal("0.10")
    assert p.max_total_exposure_pct == Decimal("0.30")
    assert p.max_daily_loss_pct == Decimal("0.01")
    assert p.max_weekly_loss_pct == Decimal("0.03")
    assert p.max_consecutive_losses == 3
    assert p.atr_stop_mult == Decimal("2")


def test_market_conditions_default_all_clear() -> None:
    m = MarketConditions()
    assert not m.data_stale and not m.spread_too_wide and not m.exchange_degraded


def test_risk_state_holds_account_snapshot() -> None:
    s = RiskState(
        equity=Decimal("10000"), cash=Decimal("10000"), open_exposure=Decimal("0"),
        open_positions=0, day_start_equity=Decimal("10000"),
        week_start_equity=Decimal("10000"), realized_pnl_today=Decimal("0"),
        realized_pnl_week=Decimal("0"), consecutive_losses=0,
        cooldown_until_ts=0, trades_today=0, kill_switch_active=False,
        day_index=0, week_index=0,
    )
    assert s.equity == Decimal("10000")


def test_risk_decision_and_record() -> None:
    d = RiskDecision(approved=True, quantity=Decimal("0.5"), reasons=("reduced_size",))
    rec = RiskDecisionRecord(ts=1, symbol="BTC/USDT", approved=True,
                             quantity=Decimal("0.5"), reasons=("reduced_size",))
    assert d.approved and rec.symbol == "BTC/USDT"
