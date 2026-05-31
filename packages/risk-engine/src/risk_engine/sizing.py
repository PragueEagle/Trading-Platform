from decimal import Decimal


def size_position(
    *,
    equity: Decimal,
    risk_per_trade_pct: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    max_position_size_pct: Decimal,
    available_exposure: Decimal,
) -> Decimal:
    """Risk-based long position size, clamped by position and exposure caps.

    Returns 0 when the stop is not below entry or there is no headroom.
    """
    stop_distance = entry_price - stop_price
    if stop_distance <= 0 or entry_price <= 0 or available_exposure <= 0:
        return Decimal("0")
    risk_capital = equity * risk_per_trade_pct
    qty = risk_capital / stop_distance
    pos_cap_notional = equity * max_position_size_pct
    max_qty_by_pos = pos_cap_notional / entry_price
    max_qty_by_exposure = available_exposure / entry_price
    return min(qty, max_qty_by_pos, max_qty_by_exposure)
