from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from feature_engine.features import FeatureRow


class SignalAction(StrEnum):
    ENTER = "enter"
    HOLD = "hold"
    EXIT = "exit"
    CASH = "cash"


@dataclass(frozen=True, slots=True)
class StrategySignal:
    symbol: str
    ts: int
    action: SignalAction
    score: Decimal
    reasons: tuple[str, ...] = field(default_factory=tuple)
    invalidation: str | None = None


def market_filter_passes(
    *,
    btc_1d: FeatureRow,
    btc_4h: FeatureRow,
    max_realized_vol: Decimal,
    data_quality_ok: bool,
) -> bool:
    if not data_quality_ok:
        return False
    if btc_1d.ema200 is None or btc_4h.ema50 is None:
        return False
    if btc_1d.close <= btc_1d.ema200:
        return False
    if btc_4h.close < btc_4h.ema50:
        return False
    # Risk gate: unknown volatility is treated as a rejection (protect capital first).
    if btc_4h.realized_vol is None or btc_4h.realized_vol > max_realized_vol:
        return False
    return True


def score_asset(row: FeatureRow) -> Decimal:
    """Deterministic composite score. Missing inputs -> 0 (not investable)."""
    if row.ret_7d is None or row.ret_30d is None or row.ema50 is None:
        return Decimal("0")
    score = Decimal("0")
    score += row.ret_7d * Decimal("2")        # momentum 7d
    score += row.ret_30d                       # momentum 30d
    if row.dist_from_ema50 is not None:
        score += min(row.dist_from_ema50, Decimal("0.05"))
        if row.dist_from_ema50 > Decimal("0.15"):
            score -= (row.dist_from_ema50 - Decimal("0.15"))
    if row.volume_ratio is not None and row.volume_ratio > Decimal("1"):
        score += Decimal("0.05")
    if row.realized_vol is not None:
        score -= row.realized_vol              # volatility penalty
    score += row.drawdown                      # drawdown is <= 0, so this penalizes
    return score


@dataclass(frozen=True, slots=True)
class RotationConfig:
    max_positions: int = 3
    min_score: Decimal = Decimal("0")
    max_dist_from_ema50: Decimal = Decimal("0.15")
    max_realized_vol: Decimal = Decimal("0.1")


def _entry_allowed(row: FeatureRow, config: RotationConfig) -> bool:
    if row.ema50 is None or row.close < row.ema50:
        return False
    if row.dist_from_ema50 is not None and row.dist_from_ema50 > config.max_dist_from_ema50:
        return False
    if row.volume_ratio is not None and row.volume_ratio < Decimal("1"):
        return False
    return True


def decide(
    *,
    ts: int,
    btc_1d: FeatureRow,
    btc_4h: FeatureRow,
    features_4h: dict[str, FeatureRow],
    holdings: set[str],
    data_quality_ok: bool,
    config: RotationConfig,
) -> list[StrategySignal]:
    if not market_filter_passes(
        btc_1d=btc_1d, btc_4h=btc_4h,
        max_realized_vol=config.max_realized_vol, data_quality_ok=data_quality_ok,
    ):
        return [
            StrategySignal(symbol=sym, ts=ts, action=SignalAction.CASH,
                           score=Decimal("0"), reasons=("market_filter_off",))
            for sym in (holdings or {"_market"})
        ]

    signals: list[StrategySignal] = []
    for sym in holdings:
        row = features_4h.get(sym)
        if row is None or row.ema50 is None or row.close < row.ema50:
            signals.append(StrategySignal(
                symbol=sym, ts=ts, action=SignalAction.EXIT, score=Decimal("0"),
                reasons=("close_below_ema50",), invalidation="reclaim_ema50",
            ))

    exited = {s.symbol for s in signals if s.action == SignalAction.EXIT}
    keep = {s for s in holdings if s not in exited}

    ranked: list[tuple[Decimal, str, FeatureRow]] = sorted(
        (
            (score_asset(row), sym, row)
            for sym, row in features_4h.items()
            if _entry_allowed(row, config)
        ),
        key=lambda t: t[0], reverse=True,
    )
    slots = max(0, config.max_positions - len(keep))
    for score, sym, _row in ranked:
        if slots == 0:
            break
        if sym in holdings or score < config.min_score:
            continue
        signals.append(StrategySignal(
            symbol=sym, ts=ts, action=SignalAction.ENTER, score=score,
            reasons=("above_ema50", "momentum"), invalidation="close_below_ema50",
        ))
        slots -= 1
    return signals
