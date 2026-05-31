import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from risk_engine.state import RiskDecisionRecord

from backtest.types import EquityPoint


def summarize_risk_decisions(
    records: list[RiskDecisionRecord],
    *,
    stop_loss_exits: int = 0,
    kill_switch_trips: int = 0,
    max_consecutive_losses: int = 0,
) -> dict[str, Any]:
    approved = sum(1 for r in records if r.approved)
    by_reason: Counter[str] = Counter()
    for r in records:
        if not r.approved:
            for reason in r.reasons:
                by_reason[reason] += 1
    return {
        "approved": approved,
        "rejected": len(records) - approved,
        "rejected_by_reason": dict(by_reason),
        "stop_loss_exits": stop_loss_exits,
        "kill_switch_trips": kill_switch_trips,
        "max_consecutive_losses": max_consecutive_losses,
    }


def write_report(
    *,
    metrics: dict[str, Decimal],
    equity_curve: list[EquityPoint],
    json_path: Path,
    csv_path: Path,
    benchmark: dict[str, dict[str, Decimal]] | None = None,
    risk: dict[str, Any] | None = None,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "metrics": {k: str(v) for k, v in metrics.items()},
        "benchmark": {
            name: {k: str(v) for k, v in m.items()}
            for name, m in (benchmark or {}).items()
        },
        "risk": risk or {},
        "points": len(equity_curve),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    with csv_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ts", "equity"])
        for p in equity_curve:
            writer.writerow([p.ts, str(p.equity)])
