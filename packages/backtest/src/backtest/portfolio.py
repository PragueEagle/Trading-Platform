from decimal import Decimal

from backtest.types import (
    BacktestConfig,
    Position,
    buy_fill_price,
    fee,
    sell_fill_price,
)


class Portfolio:
    def __init__(self, *, cash: Decimal, config: BacktestConfig) -> None:
        self.cash = cash
        self.config = config
        self.positions: dict[str, Position] = {}
        self._entry_ts: dict[str, int] = {}

    def equity(self, prices: dict[str, Decimal]) -> Decimal:
        total = self.cash
        for sym, pos in self.positions.items():
            mark = prices.get(sym, pos.entry_price)
            total += pos.quantity * mark
        return total

    def enter(
        self,
        symbol: str,
        *,
        ref_price: Decimal,
        fraction: Decimal,
        ts: int = 0,
        prices: dict[str, Decimal] | None = None,
    ) -> None:
        if symbol in self.positions or fraction <= 0:
            return
        budget = self.equity(prices or {}) * fraction
        budget = min(budget, self.cash)
        if budget <= 0:
            return
        price = buy_fill_price(ref_price, self.config.slippage_bps)
        qty = budget / (price * (1 + self.config.fee_bps / Decimal("10000")))
        notional = qty * price
        self.cash -= notional + fee(notional, self.config.fee_bps)
        self.positions[symbol] = Position(symbol=symbol, quantity=qty, entry_price=price)
        self._entry_ts[symbol] = ts

    def enter_quantity(
        self, symbol: str, *, ref_price: Decimal, quantity: Decimal, ts: int = 0
    ) -> None:
        """Enter an explicit, pre-sized quantity (capped by cash)."""
        if symbol in self.positions or quantity <= 0:
            return
        price = buy_fill_price(ref_price, self.config.slippage_bps)
        notional = quantity * price
        cost = notional + fee(notional, self.config.fee_bps)
        if cost > self.cash:
            # clamp to affordable quantity
            quantity = self.cash / (price * (1 + self.config.fee_bps / Decimal("10000")))
            if quantity <= 0:
                return
            notional = quantity * price
            cost = notional + fee(notional, self.config.fee_bps)
        self.cash -= cost
        self.positions[symbol] = Position(symbol=symbol, quantity=quantity, entry_price=price)
        self._entry_ts[symbol] = ts

    def entry_ts(self, symbol: str) -> int:
        """Timestamp the open position was entered; 0 if not held."""
        return self._entry_ts.get(symbol, 0)

    def exit(self, symbol: str, *, ref_price: Decimal) -> Decimal:
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return Decimal("0")
        price = sell_fill_price(ref_price, self.config.slippage_bps)
        notional = pos.quantity * price
        proceeds = notional - fee(notional, self.config.fee_bps)
        self.cash += proceeds
        self._entry_ts.pop(symbol, None)
        # Net of both sides' costs: exit fee is already in `proceeds`; subtract the
        # cost basis and the entry fee that was charged to cash at enter() time.
        entry_notional = pos.quantity * pos.entry_price
        return proceeds - entry_notional - fee(entry_notional, self.config.fee_bps)
