"""Runnable end-to-end backtest: `python -m backtest.example`.

Wires the real pipeline together — feature engine -> trend-rotation strategy ->
event-driven backtest -> risk engine -> metrics — and runs it twice (with the
risk engine off, then on) so you can see the risk layer's effect on drawdown.

The candles here are **synthetic and deterministic** (seeded), generated in-process
so the example runs with zero external data or network. The printed numbers are a
demonstration that the engine composes correctly, NOT a performance claim — for
real figures you would feed real OHLCV (e.g. via ccxt) into the same `Bar` series.
"""

import random
from decimal import Decimal

from feature_engine.candle import Candle
from feature_engine.features import FeatureRow, compute_features
from risk_engine.policy import RiskPolicy
from strategy_engine.trend_rotation import RotationConfig, StrategySignal, decide

from backtest.benchmark import buy_and_hold_curve
from backtest.engine import Bar, run_backtest
from backtest.metrics import compute_metrics
from backtest.types import BacktestConfig, EquityPoint

BAR_MS = 14_400_000  # 4 hours
DAY_MS = 86_400_000
BARS_PER_DAY = 6
PERIODS_PER_YEAR = 365 * BARS_PER_DAY


def _gen_4h(*, seed: int, n: int, start: str, drift: float, vol: float) -> list[Candle]:
    """Deterministic synthetic 4h candles: a geometric random walk with drift."""
    rng = random.Random(seed)
    price = Decimal(start)
    out: list[Candle] = []
    for i in range(n):
        ret = drift + rng.gauss(0.0, vol)
        open_p = price
        close_p = open_p * (Decimal(1) + Decimal(str(round(ret, 6))))
        wick_hi = Decimal(str(round(abs(rng.gauss(0.0, vol / 2)), 6)))
        wick_lo = Decimal(str(round(abs(rng.gauss(0.0, vol / 2)), 6)))
        high = max(open_p, close_p) * (Decimal(1) + wick_hi)
        low = min(open_p, close_p) * (Decimal(1) - wick_lo)
        out.append(Candle(
            ts=i * BAR_MS, open=open_p, high=high, low=low,
            close=close_p, volume=Decimal(rng.randint(800, 1200)),
        ))
        price = close_p
    return out


def _resample_daily(candles: list[Candle], *, group: int = BARS_PER_DAY) -> list[Candle]:
    out: list[Candle] = []
    for i in range(0, len(candles) - group + 1, group):
        chunk = candles[i : i + group]
        out.append(Candle(
            ts=chunk[0].ts, open=chunk[0].open,
            high=max(c.high for c in chunk), low=min(c.low for c in chunk),
            close=chunk[-1].close, volume=sum((c.volume for c in chunk), Decimal(0)),
        ))
    return out


def _index(candles: list[Candle], *, bars_per_day: int) -> dict[int, FeatureRow]:
    return {r.ts: r for r in compute_features(candles, bars_per_day=bars_per_day)}


def _bars(candles: list[Candle], symbol: str) -> list[Bar]:
    return [
        Bar(ts=c.ts, symbol=symbol, open=c.open, close=c.close, high=c.high, low=c.low)
        for c in candles
    ]


class TrendRotationStrategy:
    """Adapts `trend_rotation.decide` to the backtest's strategy callable.

    Crucially, the daily BTC filter uses only the **last fully-closed day** before
    the current bar — never the in-progress day — so the market filter cannot peek
    at a daily close that has not happened yet.
    """

    def __init__(
        self,
        *,
        btc_4h: dict[int, FeatureRow],
        btc_1d: list[FeatureRow],
        assets: dict[str, dict[int, FeatureRow]],
        config: RotationConfig,
    ) -> None:
        self._btc_4h = btc_4h
        self._btc_1d = sorted(btc_1d, key=lambda r: r.ts)
        self._assets = assets
        self._config = config

    def _btc_1d_for(self, ts: int) -> FeatureRow | None:
        day_start = (ts // DAY_MS) * DAY_MS
        chosen: FeatureRow | None = None
        for row in self._btc_1d:
            if row.ts < day_start:
                chosen = row
            else:
                break
        return chosen

    def __call__(
        self, ts: int, holdings: set[str], bars_now: dict[str, Bar]
    ) -> list[StrategySignal]:
        btc_4h = self._btc_4h.get(ts)
        btc_1d = self._btc_1d_for(ts)
        if btc_4h is None or btc_1d is None:
            return []
        features_4h = {
            sym: idx[ts] for sym, idx in self._assets.items() if ts in idx
        }
        if not features_4h:
            return []
        return decide(
            ts=ts, btc_1d=btc_1d, btc_4h=btc_4h, features_4h=features_4h,
            holdings=holdings, data_quality_ok=True, config=self._config,
        )


def _pct(value: Decimal) -> str:
    return f"{value * 100:+.1f}%"


def main() -> None:
    n = 320 * BARS_PER_DAY  # ~320 days of 4h candles

    btc = _gen_4h(seed=1, n=n, start="30000", drift=0.0009, vol=0.012)
    assets_raw = {
        "ETH/USDT": _gen_4h(seed=2, n=n, start="2000", drift=0.0011, vol=0.018),
        "SOL/USDT": _gen_4h(seed=3, n=n, start="100", drift=0.0014, vol=0.028),
        "ADA/USDT": _gen_4h(seed=4, n=n, start="0.5", drift=0.0004, vol=0.022),
    }

    btc_4h_idx = _index(btc, bars_per_day=BARS_PER_DAY)
    btc_1d_rows = compute_features(_resample_daily(btc), bars_per_day=1)
    asset_idx = {sym: _index(c, bars_per_day=BARS_PER_DAY) for sym, c in assets_raw.items()}

    series = {sym: _bars(c, sym) for sym, c in assets_raw.items()}
    atr_by_symbol = {
        sym: {ts: row.atr14 for ts, row in idx.items() if row.atr14 is not None}
        for sym, idx in asset_idx.items()
    }

    config = BacktestConfig(fee_bps=Decimal("10"), slippage_bps=Decimal("5"))
    rot = RotationConfig(max_positions=3)

    def strategy() -> TrendRotationStrategy:
        return TrendRotationStrategy(
            btc_4h=btc_4h_idx, btc_1d=btc_1d_rows, assets=asset_idx, config=rot
        )

    no_risk = run_backtest(series, strategy(), config=config, max_positions=3)
    risk = run_backtest(
        series, strategy(), config=config, max_positions=3,
        risk_policy=RiskPolicy(), atr_by_symbol=atr_by_symbol, bar_ms=BAR_MS,
    )

    bh = buy_and_hold_curve(_bars(btc, "BTC/USDT"), starting_cash=config.starting_cash)

    def report(name: str, curve: list[EquityPoint], pnls: list[Decimal] | None) -> None:
        m = compute_metrics(curve, periods_per_year=PERIODS_PER_YEAR, trade_pnls=pnls)
        line = (
            f"  {name:<22} return {_pct(m['total_return']):>8}   "
            f"CAGR {_pct(m['cagr']):>8}   maxDD {_pct(m['max_drawdown']):>7}   "
            f"Sharpe {m['sharpe']:>5.2f}"
        )
        if pnls:
            line += f"   PF {m.get('profit_factor', Decimal(0)):>4.2f}"
        print(line)

    approved = sum(1 for d in risk.risk_decisions if d.approved)
    rejected = sum(1 for d in risk.risk_decisions if not d.approved)

    print("Synthetic 3-asset universe, ~320 days of 4h candles (seeded, deterministic)\n")
    report("strategy (no risk)", no_risk.equity_curve, [t.pnl for t in no_risk.trades])
    report("strategy (risk on)", risk.equity_curve, [t.pnl for t in risk.trades])
    report("buy & hold BTC", bh, None)
    print()
    print(f"  trades:        no-risk {len(no_risk.trades):>3}   risk-on {len(risk.trades):>3}")
    print(f"  risk decisions: approved {approved}   rejected {rejected}")
    print(f"  kill-switch trips (risk-on): {risk.kill_switch_trips}")
    print("\n  (synthetic data — demonstrates the pipeline runs, not a performance claim)")


if __name__ == "__main__":
    main()
