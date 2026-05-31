from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    risk_per_trade_pct: Decimal = Decimal("0.005")
    max_position_size_pct: Decimal = Decimal("0.10")
    max_total_exposure_pct: Decimal = Decimal("0.30")
    max_daily_loss_pct: Decimal = Decimal("0.01")
    max_weekly_loss_pct: Decimal = Decimal("0.03")
    max_consecutive_losses: int = 3
    cooldown_bars: int = 6
    max_trades_per_day: int = 5
    atr_stop_mult: Decimal = Decimal("2")
    block_if_data_stale: bool = True
    block_if_spread_too_wide: bool = True
    block_if_exchange_degraded: bool = True


@dataclass(frozen=True, slots=True)
class MarketConditions:
    data_stale: bool = False
    spread_too_wide: bool = False
    exchange_degraded: bool = False
