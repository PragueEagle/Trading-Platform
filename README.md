# AI Trading System — Backtesting & Risk Engine (research-only)

![status: research-only](https://img.shields.io/badge/status-research--only-blue)
![no live trading](https://img.shields.io/badge/live%20trading-disabled-red)
![python](https://img.shields.io/badge/python-3.12-blue)
![tests](https://img.shields.io/badge/tests-67%20of%20600%2B%20(extracted%20core)-brightgreen)
![mypy](https://img.shields.io/badge/mypy-strict-brightgreen)

A deterministic, event-driven crypto backtesting engine with a separate risk engine
that gates and sizes every entry. This repository is the **pure-logic core** of a larger
private system, extracted as a public showcase: feature math, the strategy, the backtest
loop, and the risk layer — plus the tests that prove the parts behave.

> **On the test count:** the full private system has **600+ tests**. This public repo ships
> the **67** that cover the extracted modules above — the same number you'll see if you run
> `pytest` here. The larger figure refers to the complete system (execution, data layer,
> paper-trading loop), which is not published.

It does **not** trade. There is no exchange client, no API keys, no order routing in this
repository. See [Safety by design](#safety-by-design).

## What it does

Given OHLCV candles, the pipeline computes trend/volatility features, ranks a small
universe with a deterministic momentum-rotation strategy, and replays the signals through
an event-driven backtester that fills the *next* bar's open (never the bar that produced
the signal), charging fees and slippage. A standalone risk engine sizes each position from
its ATR stop distance and rejects entries that breach daily/weekly loss limits, exposure
caps, a loss-streak cooldown, or a kill switch. The same risk engine is designed to gate a
forward "paper" loop — without ever submitting a real order.

## Architecture

```
   OHLCV candles
        │
        ▼
┌──────────────────┐   EMA / ATR / returns / realized-vol / volume-ratio / drawdown
│  Feature Engine  │   (Decimal math, no look-ahead — value at bar i uses only ≤ i)
└────────┬─────────┘
         ▼
┌──────────────────┐   Crypto Trend Rotation:
│  Strategy Engine │   • BTC market filter (1d > EMA200, 4h ≥ EMA50, calm vol)
│   (signals only) │   • deterministic per-asset score, rank, rotate top-N
└────────┬─────────┘   → ENTER / EXIT / HOLD / CASH  (no sizing, no execution)
         ▼
┌──────────────────┐   • next-bar-open fills (t+1), fee_bps + slippage_bps
│  Backtest Engine │   • ATR stop-loss exits checked against the bar low
│  (event-driven)  │   • CAGR / Sharpe / Sortino / max-DD / profit-factor / win-rate
└────────┬─────────┘
         ▼
┌──────────────────┐   • ATR-distance position sizing, capped by position & exposure
│   Risk Engine    │   • gate chain: kill-switch, daily/weekly loss, cooldown,
│  (pure, gating)  │     trades/day, stale-data / wide-spread / degraded-exchange
└────────┬─────────┘   → approve + quantity, or reject + reasons
         ▼
   Paper loop (forward, human-triggered) — NEVER a live exchange
```

Each box is an independent package with no dependency on the layers below it. The strategy
emits **signals only** — it cannot size or place a trade. Sizing and the go/no-go decision
live entirely in the risk engine, so the "can I take this trade?" logic is testable in
isolation and impossible to bypass from the strategy.

## Safety by design

This is deliberately a **trading-readiness research tool**, not a bot:

- **No execution code in this repo.** No exchange client, no credentials, no order
  submission. The published packages import only the Python standard library.
- **Strategy can't trade.** It returns `ENTER/EXIT/HOLD/CASH` signals. Only the risk
  engine produces a sized decision, and only a backtest/paper loop consumes it.
- **Hard gates, fail-closed.** Unknown volatility, zero ATR, stale data, wide spread, or a
  degraded-exchange flag all *reject* the entry. A breached daily-loss limit flips a kill
  switch that blocks new entries until the next day rolls over.
- **No look-ahead in fill timing.** A signal computed on bar *i*'s close can only fill at
  bar *i+1*'s open. A regression test mutates a future bar and asserts a past fill is
  unchanged. (Scope: the engine enforces *fill* timing. Feature correctness — that an
  indicator at bar *i* uses only data ≤ *i* — is the feature engine's contract, covered by
  its own tests; the engine trusts the `Bar`/ATR series it is handed.)

## Tech stack

- **Python 3.12**, `Decimal` throughout (no float drift in money math)
- **pytest** for unit tests, **ruff** (E/F/I/UP/B) for lint, **mypy --strict** for types
- Standard library only in the published subset — zero runtime third-party dependencies

> The full private system additionally uses **ccxt** (public OHLCV ingestion), **FastAPI**
> (a read-only dashboard/API), and **SQLAlchemy + Alembic** (Postgres persistence). Those
> layers are intentionally excluded here — they carry environment-specific config and add
> nothing to the engineering this repo is meant to show.

## Backtest methodology

- **Next-bar-open fills (t+1).** Signals are generated from a bar's close; the order fills
  at the *following* bar's open. No same-bar close fills, no peeking.
- **Costs modelled.** Configurable `fee_bps` and `slippage_bps` are applied to every fill;
  realized trade PnL is net of both the entry and exit fee.
- **ATR stop-loss.** In risk mode each position carries `entry − atr_stop_mult × ATR`; the
  stop is checked against the bar **low** (intrabar), not just the close.
- **Metrics.** CAGR, Sharpe, Sortino (downside-deviation about 0), max drawdown, profit
  factor, win rate — all computed in `backtest/metrics.py` and unit-tested.
- **Benchmark.** Every run can be compared against a buy-and-hold equity curve.

### Reproducible demo (`python -m backtest.example`)

The repo ships a runnable end-to-end example on **synthetic, seeded** candles — no data
files, no network — that wires features → strategy → backtest → risk engine and prints
metrics for the strategy with the risk engine off, then on, against a buy-and-hold
benchmark. It is a demonstration that the pipeline composes correctly and that the risk
layer reduces drawdown, **not** a performance claim (the data is made up). Typical output:

```
  strategy (no risk)     return  +41.8%   CAGR  +49.0%   maxDD -18.2%   Sharpe 1.60   PF 1.41
  strategy (risk on)     return   +5.8%   CAGR   +6.6%   maxDD  -6.6%   Sharpe 1.09   PF 1.19
  buy & hold BTC         return +451.4%   CAGR +601.8%   maxDD -20.6%   Sharpe 3.75
```

The point isn't the returns (synthetic) — it's that flipping `risk_policy` on cuts max
drawdown roughly in half here, which is the risk engine's whole job.

> **On the private numbers.** The real system, run against fetched OHLCV over a multi-year
> crypto universe, showed the same *direction* — the risk engine traded upside for a
> materially smaller drawdown. I'm deliberately not quoting precise figures you can't
> reproduce from this repo; the reproducible demo above and the unit tests are the
> verifiable parts, and they're what's worth reviewing.

## How to run

The published subset is pure standard library, so the tests run with nothing but `pytest`:

```bash
# 1. clone, create a venv
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # installs pytest, ruff, mypy only

# 2. run the gates
pytest -q                       # 67 tests
ruff check packages tests       # lint
mypy packages/*/src             # strict type-check

# 3. run the end-to-end demo on synthetic data
python -m backtest.example
```

Driving a backtest in code (no exchange needed — feed it any candle series):

```python
from decimal import Decimal
from backtest.engine import Bar, run_backtest
from backtest.types import BacktestConfig
from risk_engine.policy import RiskPolicy

# series: {symbol: [Bar(ts, symbol, open, close, high, low), ...]} sorted by ts
result = run_backtest(
    series,
    my_strategy_fn,                       # (ts, holdings, bars_now) -> [StrategySignal]
    config=BacktestConfig(fee_bps=Decimal("10"), slippage_bps=Decimal("5")),
    risk_policy=RiskPolicy(),             # omit -> equal-weight mode; pass -> risk-gated
)
print(result.trades, result.risk_decisions, result.kill_switch_trips)
```

To reproduce realistic numbers, fetch public OHLCV (e.g. via `ccxt`) and map it into
`feature_engine.candle.Candle` / `backtest.engine.Bar`. The data layer is not included.

## Tests

**67 tests** (of 600+ in the full private system), all passing, covering the four published
packages:

- `test_feature_*` — indicator math (EMA/ATR/returns/vol/drawdown), no-look-ahead, the
  `MIN_BARS` history guard
- `test_backtest_*` — t+1 fills, the mutate-the-future regression, fee/slippage accounting,
  metrics, buy-and-hold benchmark, risk-mode integration, the `step_bar` core
- `test_risk_*` — every gate (kill switch, daily/weekly loss, cooldown, trades/day, stale
  data, wide spread, degraded exchange, no-ATR, no-headroom), ATR sizing, the rolling ledger
- `test_trend_rotation` — market filter, scoring, rotation, exits

```bash
pytest -q       # 67 passed
```

## Repo structure

```
packages/
  feature-engine/   indicators.py, features.py, candle.py   — Decimal indicator math
  strategy-engine/  trend_rotation.py                       — signals only (no execution)
  backtest/         engine.py, portfolio.py, metrics.py,    — event-driven replay
                    benchmark.py, report.py, types.py,
                    example.py  (python -m backtest.example)
  risk-engine/      evaluator.py, sizing.py, ledger.py,     — gating + ATR sizing
                    policy.py, state.py
tests/              67 unit tests across the four packages
pyproject.toml      ruff + mypy(strict) + pytest config
```

## Note on scope

This is a curated extract, not the whole system. Excluded on purpose: the ccxt data
sources, the FastAPI app, the SQLAlchemy/Alembic persistence layer, the paper-broker
runtime, and all execution/runbook code — those carry environment config and no extra
engineering signal. What remains is the part that's worth reading: the math, the strategy,
the backtest loop, the risk gates, and their tests.

## Limitations (deliberate, and worth stating)

A backtester that hides its assumptions is worse than useless, so here are this one's:

- **Optimistic fills.** Orders fill at the next bar's open with flat `bps` slippage and no
  liquidity model — no partial fills, no market impact, no "you couldn't actually get
  filled there." Real execution is harder than this; the engine is a *readiness* tool, not
  a fill simulator.
- **No survivorship handling.** The universe is a fixed symbol set. Listings/delistings and
  survivorship bias are not modelled — a well-known way crypto backtests flatter themselves.
- **`Decimal` over `float` is a correctness/perf trade-off.** It removes float drift in
  money math at ~10–50× the per-op cost. Fine at this scale (tens of thousands of bars);
  for tick-level or very large universes you'd profile and likely move hot paths to floats
  or vectorize.
- **The strategy's score weights are hand-chosen, not fitted.** `score_asset` uses fixed
  coefficients; treat the strategy as a plausible, testable baseline, not a tuned edge.
- **No-look-ahead is enforced on fill timing only** — see [Safety by design](#safety-by-design).

## Disclaimer

For research and educational use only. **Not financial advice.** Nothing here trades real
money, connects to an exchange, or should be used to. Past backtested performance does not
indicate future results.
