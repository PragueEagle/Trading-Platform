from decimal import Decimal

from backtest.types import EquityPoint


def _max_drawdown(equities: list[Decimal]) -> Decimal:
    peak = equities[0]
    worst = Decimal("0")
    for e in equities:
        peak = max(peak, e)
        if peak > 0:
            dd = (e - peak) / peak
            worst = min(worst, dd)
    return worst


def compute_metrics(
    curve: list[EquityPoint],
    *,
    periods_per_year: int,
    trade_pnls: list[Decimal] | None = None,
) -> dict[str, Decimal]:
    if not curve:
        raise ValueError("compute_metrics requires a non-empty equity curve")
    equities = [p.equity for p in curve]
    start, end = equities[0], equities[-1]
    total_return = Decimal("0") if start == 0 else (end - start) / start

    rets: list[Decimal] = []
    for i in range(1, len(equities)):
        prev = equities[i - 1]
        if prev != 0:
            rets.append((equities[i] - prev) / prev)

    def _mean(xs: list[Decimal]) -> Decimal:
        return sum(xs, Decimal("0")) / Decimal(len(xs)) if xs else Decimal("0")

    def _stdev(xs: list[Decimal]) -> Decimal:
        if len(xs) < 2:
            return Decimal("0")
        mu = _mean(xs)
        var = sum(((x - mu) ** 2 for x in xs), Decimal("0")) / Decimal(len(xs))
        return var.sqrt()

    def _downside_dev(xs: list[Decimal]) -> Decimal:
        # Standard Sortino semideviation about a 0 target, normalized by the full
        # period count (not just the negative-return count).
        if len(xs) < 2:
            return Decimal("0")
        downside = sum((x**2 for x in xs if x < 0), Decimal("0")) / Decimal(len(xs))
        return downside.sqrt()

    ann = Decimal(periods_per_year).sqrt()
    mean_r = _mean(rets)
    stdev = _stdev(rets)
    dd_dev = _downside_dev(rets)
    sharpe = Decimal("0") if stdev == 0 else (mean_r / stdev) * ann
    sortino = Decimal("0") if dd_dev == 0 else (mean_r / dd_dev) * ann

    # Compound annual growth rate: annualize the total return over the elapsed
    # periods. Requires at least one return step and a positive starting equity.
    if len(rets) == 0 or start <= 0 or end <= 0:
        cagr = Decimal("0")
    else:
        years = Decimal(len(rets)) / Decimal(periods_per_year)
        cagr = (end / start) ** (Decimal("1") / years) - Decimal("1")

    metrics: dict[str, Decimal] = {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": _max_drawdown(equities),
        "sharpe": sharpe,
        "sortino": sortino,
    }

    if trade_pnls:
        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]
        gross_win = sum(wins, Decimal("0"))
        gross_loss = -sum(losses, Decimal("0"))
        metrics["win_rate"] = Decimal(len(wins)) / Decimal(len(trade_pnls))
        metrics["profit_factor"] = (
            gross_win / gross_loss if gross_loss > 0 else Decimal("0")
        )
    return metrics
