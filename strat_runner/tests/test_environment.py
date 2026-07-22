import json
from decimal import Decimal
from pathlib import Path

import pytest

from environment import Environment
from executors.mock_executor import MockExecutor
from models import Context, Order
from run_registry import load_registry
from strategies.hold import HoldStrategy


def write_btc_csv(path: Path, rows: list[tuple[str, str, str, str, str]]) -> None:
    """rows: (time, open, high, low, close)"""
    lines = ["time,ticker,open,high,low,close,volume"]
    for time, open_, high, low, close in rows:
        lines.append(f"{time},BTC,{open_},{high},{low},{close},1")
    path.write_text("\n".join(lines) + "\n")


class RecordingStrategy:
    """Wraps a strategy and records each Context passed to decide()."""

    def __init__(self, strategy):
        self.strategy = strategy
        self.contexts: list[Context] = []

    def decide(self, context: Context) -> list[Order]:
        self.contexts.append(
            Context(
                time=context.time,
                history={
                    ticker: list(candles)
                    for ticker, candles in context.history.items()
                },
                current_open_prices=dict(context.current_open_prices),
                account=context.account,
                positions=list(context.positions),
            )
        )
        return self.strategy.decide(context)


@pytest.fixture
def btc_csv(tmp_path: Path) -> Path:
    path = tmp_path / "btc.csv"
    write_btc_csv(
        path,
        [
            ("2021-01-01", "100", "120", "90", "110"),
            ("2021-01-02", "110", "130", "100", "125"),
            ("2021-01-03", "125", "140", "115", "130"),
        ],
    )
    return path


def test_history_excludes_current_candle_and_exposes_open(
    tmp_path: Path, btc_csv: Path
):
    recorder = RecordingStrategy(HoldStrategy(ticker="BTC"))
    environment = Environment(
        recorder,
        MockExecutor(),
        [str(btc_csv)],
        runs_dir=tmp_path / "runs",
    )
    environment.run()

    assert len(recorder.contexts) == 3

    day1 = recorder.contexts[0]
    assert day1.current_open_prices["BTC"] == Decimal("100")
    assert day1.history.get("BTC", []) == []

    day2 = recorder.contexts[1]
    assert day2.current_open_prices["BTC"] == Decimal("110")
    assert len(day2.history["BTC"]) == 1
    prior = day2.history["BTC"][0]
    assert prior.open == Decimal("100")
    assert prior.high == Decimal("120")
    assert prior.low == Decimal("90")
    assert prior.close == Decimal("110")

    day3 = recorder.contexts[2]
    assert day3.current_open_prices["BTC"] == Decimal("125")
    assert len(day3.history["BTC"]) == 2
    assert [c.close for c in day3.history["BTC"]] == [
        Decimal("110"),
        Decimal("125"),
    ]


def test_market_order_fills_at_close_not_open(tmp_path: Path, btc_csv: Path):
    environment = Environment(
        HoldStrategy(ticker="BTC"),
        MockExecutor(),
        [str(btc_csv)],
        runs_dir=tmp_path / "runs",
    )
    environment.run()

    assert len(environment.positions) == 1
    position = environment.positions[0]
    assert position.ticker == "BTC"
    # Bought all USD on day 1 at close 110, not open 100.
    assert position.average_price == Decimal("110")
    assert position.quantity == Decimal("10000") / Decimal("110")
    assert environment.account.balances["USD"] == Decimal("0")


def test_date_range_filters_bars(tmp_path: Path, btc_csv: Path):
    recorder = RecordingStrategy(HoldStrategy(ticker="BTC"))
    environment = Environment(
        recorder,
        MockExecutor(),
        [str(btc_csv)],
        runs_dir=tmp_path / "runs",
        start_date="2021-01-02",
        end_date="2021-01-02",
    )
    environment.run()

    assert len(recorder.contexts) == 1
    assert recorder.contexts[0].current_open_prices["BTC"] == Decimal("110")
    assert recorder.contexts[0].history.get("BTC", []) == []

    entries = load_registry(tmp_path / "runs")
    assert len(entries) == 1
    assert entries[0]["start_date"] == "2021-01-02"
    assert entries[0]["end_date"] == "2021-01-02"


def test_run_writes_steps_and_registry(tmp_path: Path, btc_csv: Path):
    environment = Environment(
        HoldStrategy(ticker="BTC"),
        MockExecutor(),
        [str(btc_csv)],
        runs_dir=tmp_path / "runs",
    )
    environment.run()

    entries = load_registry(tmp_path / "runs")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["strategy"] == "hold"
    assert entry["assets"] == ["BTC"]
    assert entry["start_date"] == "2021-01-01"
    assert entry["end_date"] == "2021-01-03"

    steps_file = tmp_path / "runs" / entry["folder"] / "steps.jsonl"
    steps = [json.loads(line) for line in steps_file.read_text().splitlines()]
    assert len(steps) == 3
    assert steps[0]["decision"][0]["total_value"] == "10000"
    assert steps[0]["positions"][0]["average_price"] == "110"
    assert steps[1]["decision"] == []


def test_empty_date_range_raises(tmp_path: Path, btc_csv: Path):
    environment = Environment(
        HoldStrategy(ticker="BTC"),
        MockExecutor(),
        [str(btc_csv)],
        runs_dir=tmp_path / "runs",
        start_date="2030-01-01",
        end_date="2030-01-02",
    )

    with pytest.raises(ValueError, match="No candles"):
        environment.run()
