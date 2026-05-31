from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RiskState:
    equity: Decimal
    cash: Decimal
    open_exposure: Decimal
    open_positions: int
    day_start_equity: Decimal
    week_start_equity: Decimal
    realized_pnl_today: Decimal
    realized_pnl_week: Decimal
    consecutive_losses: int
    cooldown_until_ts: int
    trades_today: int
    kill_switch_active: bool
    day_index: int
    week_index: int


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    quantity: Decimal
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RiskDecisionRecord:
    ts: int
    symbol: str
    approved: bool
    quantity: Decimal
    reasons: tuple[str, ...]
