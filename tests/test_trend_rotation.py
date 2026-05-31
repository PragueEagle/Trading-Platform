from decimal import Decimal

from feature_engine.features import FeatureRow
from strategy_engine.trend_rotation import (
    RotationConfig,
    SignalAction,
    decide,
    market_filter_passes,
    score_asset,
)


def _row(close, ema50, ema200, **kw) -> FeatureRow:
    base = dict(
        ts=0, close=Decimal(close), ema20=None,
        ema50=Decimal(ema50), ema200=Decimal(ema200), atr14=Decimal("1"),
        ret_7d=Decimal("0.05"), ret_30d=Decimal("0.1"), realized_vol=Decimal("0.02"),
        volume_ratio=Decimal("1.5"), drawdown=Decimal("0"),
        dist_from_ema50=Decimal("0.01"),
    )
    base.update(kw)
    return FeatureRow(**base)


def test_market_filter_on_when_btc_above_emas_and_calm() -> None:
    btc_1d = _row("100", ema50="80", ema200="70")
    btc_4h = _row("100", ema50="95", ema200="90")
    assert market_filter_passes(
        btc_1d=btc_1d, btc_4h=btc_4h, max_realized_vol=Decimal("0.1"),
        data_quality_ok=True,
    ) is True


def test_market_filter_off_when_btc_below_ema200_1d() -> None:
    btc_1d = _row("60", ema50="80", ema200="70")
    btc_4h = _row("60", ema50="95", ema200="90")
    assert market_filter_passes(
        btc_1d=btc_1d, btc_4h=btc_4h, max_realized_vol=Decimal("0.1"),
        data_quality_ok=True,
    ) is False


def test_market_filter_off_when_data_quality_bad() -> None:
    btc_1d = _row("100", ema50="80", ema200="70")
    btc_4h = _row("100", ema50="95", ema200="90")
    assert market_filter_passes(
        btc_1d=btc_1d, btc_4h=btc_4h, max_realized_vol=Decimal("0.1"),
        data_quality_ok=False,
    ) is False


def test_score_rewards_momentum_and_penalizes_drawdown() -> None:
    strong = _row("100", ema50="90", ema200="80",
                  ret_7d=Decimal("0.1"), ret_30d=Decimal("0.3"),
                  drawdown=Decimal("0"), realized_vol=Decimal("0.02"))
    weak = _row("100", ema50="90", ema200="80",
                ret_7d=Decimal("-0.1"), ret_30d=Decimal("-0.2"),
                drawdown=Decimal("-0.3"), realized_vol=Decimal("0.08"))
    assert score_asset(strong) > score_asset(weak)


def test_score_returns_zero_when_features_missing() -> None:
    incomplete = _row("100", ema50="90", ema200="80", ret_7d=None)
    assert score_asset(incomplete) == Decimal("0")


def test_decide_returns_cash_for_all_when_market_filter_off() -> None:
    btc_1d = _row("60", ema50="80", ema200="70")
    btc_4h = _row("60", ema50="95", ema200="90")
    features = {"ETH/USDT": _row("100", ema50="90", ema200="80")}
    signals = decide(
        ts=0, btc_1d=btc_1d, btc_4h=btc_4h, features_4h=features,
        holdings=set(), data_quality_ok=True, config=RotationConfig(),
    )
    assert all(s.action == SignalAction.CASH for s in signals)
    assert len(signals) == 1


def test_decide_enters_top_scoring_asset_when_filter_on() -> None:
    btc_1d = _row("100", ema50="80", ema200="70")
    btc_4h = _row("100", ema50="95", ema200="90")
    features = {
        "ETH/USDT": _row("100", ema50="90", ema200="80", ret_7d=Decimal("0.2")),
        "ADA/USDT": _row("100", ema50="90", ema200="80", ret_7d=Decimal("-0.2")),
    }
    signals = decide(
        ts=0, btc_1d=btc_1d, btc_4h=btc_4h, features_4h=features,
        holdings=set(), data_quality_ok=True, config=RotationConfig(max_positions=1),
    )
    enters = [s for s in signals if s.action == SignalAction.ENTER]
    assert [s.symbol for s in enters] == ["ETH/USDT"]


def test_decide_exits_holding_that_falls_below_ema50() -> None:
    btc_1d = _row("100", ema50="80", ema200="70")
    btc_4h = _row("100", ema50="95", ema200="90")
    features = {"ETH/USDT": _row("80", ema50="90", ema200="80")}
    signals = decide(
        ts=0, btc_1d=btc_1d, btc_4h=btc_4h, features_4h=features,
        holdings={"ETH/USDT"}, data_quality_ok=True, config=RotationConfig(),
    )
    assert any(s.symbol == "ETH/USDT" and s.action == SignalAction.EXIT for s in signals)


def test_decide_holds_silently_when_holding_stays_above_ema50() -> None:
    btc_1d = _row("100", ema50="80", ema200="70")
    btc_4h = _row("100", ema50="95", ema200="90")
    # holding remains above its EMA50 -> no exit, no re-entry signal for it
    features = {"ETH/USDT": _row("100", ema50="90", ema200="80")}
    signals = decide(
        ts=0, btc_1d=btc_1d, btc_4h=btc_4h, features_4h=features,
        holdings={"ETH/USDT"}, data_quality_ok=True, config=RotationConfig(),
    )
    assert all(s.symbol != "ETH/USDT" for s in signals)
