import csv
import json
from decimal import Decimal
from pathlib import Path

from backtest.report import summarize_risk_decisions, write_report
from backtest.types import EquityPoint


def test_write_report_emits_json_and_csv(tmp_path: Path) -> None:
    curve = [EquityPoint(ts=0, equity=Decimal("1000")),
             EquityPoint(ts=86_400_000, equity=Decimal("1100"))]
    metrics = {"total_return": Decimal("0.1"), "max_drawdown": Decimal("0")}
    json_path = tmp_path / "report.json"
    csv_path = tmp_path / "equity.csv"

    write_report(metrics=metrics, equity_curve=curve,
                 json_path=json_path, csv_path=csv_path)

    loaded = json.loads(json_path.read_text())
    assert loaded["metrics"]["total_return"] == "0.1"
    rows = list(csv.DictReader(csv_path.open()))
    assert rows[-1]["equity"] == "1100"


def test_summarize_risk_decisions_counts_by_reason() -> None:
    from risk_engine.state import RiskDecisionRecord
    records = [
        RiskDecisionRecord(ts=0, symbol="ETH/USDT", approved=True,
                           quantity=Decimal("1"), reasons=()),
        RiskDecisionRecord(ts=1, symbol="ETH/USDT", approved=False,
                           quantity=Decimal("0"), reasons=("cooldown_active",)),
        RiskDecisionRecord(ts=2, symbol="ETH/USDT", approved=False,
                           quantity=Decimal("0"), reasons=("cooldown_active",)),
    ]
    summary = summarize_risk_decisions(records)
    assert summary["approved"] == 1
    assert summary["rejected"] == 2
    assert summary["rejected_by_reason"]["cooldown_active"] == 2
