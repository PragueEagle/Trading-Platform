from decimal import Decimal


def ema(values: list[Decimal], *, period: int) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = Decimal(2) / Decimal(period + 1)
    seed = sum(values[:period], Decimal(0)) / Decimal(period)
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * alpha + prev * (1 - alpha)
        out[i] = prev
    return out


def returns(closes: list[Decimal], *, lookback: int) -> list[Decimal | None]:
    out: list[Decimal | None] = [None] * len(closes)
    for i in range(lookback, len(closes)):
        base = closes[i - lookback]
        if base == 0:
            out[i] = None
        else:
            out[i] = (closes[i] - base) / base
    return out


def atr(
    highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], *, period: int
) -> list[Decimal | None]:
    n = len(closes)
    trs: list[Decimal | None] = [None] * n
    for i in range(n):
        if i == 0:
            trs[i] = highs[i] - lows[i]
        else:
            trs[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
    out: list[Decimal | None] = [None] * n
    for i in range(period, n):
        window = [t for t in trs[i - period + 1 : i + 1] if t is not None]
        out[i] = sum(window, Decimal(0)) / Decimal(period)
    return out


def drawdown_from_high(closes: list[Decimal]) -> list[Decimal]:
    out: list[Decimal] = []
    peak = closes[0] if closes else Decimal(0)
    for c in closes:
        peak = max(peak, c)
        out.append(Decimal(0) if peak == 0 else (c - peak) / peak)
    return out


def volume_ratio(volumes: list[Decimal], *, period: int) -> list[Decimal | None]:
    out: list[Decimal | None] = [None] * len(volumes)
    for i in range(period, len(volumes)):
        avg = sum(volumes[i - period : i], Decimal(0)) / Decimal(period)
        out[i] = None if avg == 0 else volumes[i] / avg
    return out


def realized_volatility(closes: list[Decimal], *, period: int) -> list[Decimal | None]:
    log_like = returns(closes, lookback=1)
    out: list[Decimal | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        window = [r for r in log_like[i - period + 1 : i + 1] if r is not None]
        if len(window) < 2:
            continue
        mean = sum(window, Decimal(0)) / Decimal(len(window))
        var = sum(((r - mean) ** 2 for r in window), Decimal(0)) / Decimal(len(window))
        out[i] = var.sqrt()
    return out
