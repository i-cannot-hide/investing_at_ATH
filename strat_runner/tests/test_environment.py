import json
from decimal import Decimal
from pathlib import Path

import pytest

from engine import (
    Environment,
    Experiment,
    MoneySpawner,
    SpawnInterval,
    load_registry,
)
from executors.mock_executor import MockExecutor
from models import Account, Context, Decision, Order, OrderSide, OrderType
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

    def decide(self, context: Context) -> Decision | None:
        self.contexts.append(
            Context(
                time=context.time,
                history={
                    ticker: list(candles)
                    for ticker, candles in context.history.items()
                },
                current_open_prices=dict(context.current_open_prices),
                account=Account(balances=dict(context.account.balances)),
                positions=list(context.positions),
                open_orders=list(context.open_orders),
            )
        )
        return self.strategy.decide(context)


class LimitThenCancelStrategy:
    """Day 1: place limit buy. Day 2: cancel it if still open."""

    def decide(self, context: Context) -> Decision | None:
        if not context.history.get("BTC") and not context.open_orders:
            return Decision(
                orders=[
                    Order(
                        ticker="BTC",
                        side=OrderSide.BUY,
                        order_type=OrderType.LIMIT,
                        quantity=Decimal("1"),
                        price=Decimal("50"),
                    )
                ]
            )
        if context.open_orders:
            return Decision(
                cancel_order_ids=[order.id for order in context.open_orders]
            )
        return None


class LimitBuyStrategy:
    def __init__(self, price: str, quantity: str = "1"):
        self.price = Decimal(price)
        self.quantity = Decimal(quantity)
        self._placed = False

    def decide(self, context: Context) -> Decision | None:
        if self._placed or context.open_orders:
            return None
        self._placed = True
        return Decision(
            orders=[
                Order(
                    ticker="BTC",
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=self.quantity,
                    price=self.price,
                )
            ]
        )


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
        Experiment(recorder),
        MockExecutor(),
        [str(btc_csv)],
        outcomes_dir=tmp_path / "outcomes",
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
        Experiment(HoldStrategy(ticker="BTC")),
        MockExecutor(),
        [str(btc_csv)],
        outcomes_dir=tmp_path / "outcomes",
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
        Experiment(recorder),
        MockExecutor(),
        [str(btc_csv)],
        outcomes_dir=tmp_path / "outcomes",
        start_date="2021-01-02",
        end_date="2021-01-02",
    )
    environment.run()

    assert len(recorder.contexts) == 1
    assert recorder.contexts[0].current_open_prices["BTC"] == Decimal("110")
    assert recorder.contexts[0].history.get("BTC", []) == []

    entries = load_registry(tmp_path / "outcomes")
    assert len(entries) == 1
    assert entries[0]["start_date"] == "2021-01-02"
    assert entries[0]["end_date"] == "2021-01-02"


def test_run_writes_steps_and_registry(tmp_path: Path, btc_csv: Path):
    environment = Environment(
        Experiment(HoldStrategy(ticker="BTC")),
        MockExecutor(),
        [str(btc_csv)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    entries = load_registry(tmp_path / "outcomes")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["strategy"] == "hold"
    assert entry["assets"] == ["BTC"]
    assert entry["start_date"] == "2021-01-01"
    assert entry["end_date"] == "2021-01-03"

    steps_file = tmp_path / "outcomes" / entry["folder"] / "steps.jsonl"
    steps = [json.loads(line) for line in steps_file.read_text().splitlines()]
    assert len(steps) == 3
    assert steps[0]["decision"][0]["total_value"] == "10000"
    assert steps[0]["positions"][0]["average_price"] == "110"
    assert steps[0]["journal"] == [
        {
            "type": "order_filled",
            "order_id": steps[0]["decision"][0]["id"],
            "ticker": "BTC",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": steps[0]["positions"][0]["quantity"],
            "price": "110",
        }
    ]
    assert steps[1]["decision"] == []
    assert steps[1]["journal"] == []


def test_empty_date_range_raises(tmp_path: Path, btc_csv: Path):
    environment = Environment(
        Experiment(HoldStrategy(ticker="BTC")),
        MockExecutor(),
        [str(btc_csv)],
        outcomes_dir=tmp_path / "outcomes",
        start_date="2030-01-01",
        end_date="2030-01-02",
    )

    with pytest.raises(ValueError, match="No candles"):
        environment.run()


def test_limit_order_rests_then_fills_when_touched(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    # Day 1 low=95 never hits buy@90. Day 2 low=85 fills at 90.
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "110", "95", "105"),
            ("2021-01-02", "105", "110", "85", "100"),
        ],
    )
    recorder = RecordingStrategy(LimitBuyStrategy(price="90"))
    environment = Environment(
        Experiment(recorder),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    assert len(recorder.contexts[0].open_orders) == 0
    assert len(recorder.contexts[1].open_orders) == 1
    assert recorder.contexts[1].open_orders[0].id is not None
    assert recorder.contexts[1].open_orders[0].price == Decimal("90")

    assert environment.open_orders == []
    assert len(environment.positions) == 1
    assert environment.positions[0].quantity == Decimal("1")
    assert environment.positions[0].average_price == Decimal("90")
    assert environment.account.balances["USD"] == Decimal("9910")

    entries = load_registry(tmp_path / "outcomes")
    steps_file = tmp_path / "outcomes" / entries[0]["folder"] / "steps.jsonl"
    steps = [json.loads(line) for line in steps_file.read_text().splitlines()]
    assert steps[0]["journal"] == []
    assert steps[1]["journal"] == [
        {
            "type": "order_filled",
            "order_id": recorder.contexts[1].open_orders[0].id,
            "ticker": "BTC",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": "1",
            "price": "90",
        }
    ]


def test_strategy_can_cancel_open_orders(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "110", "95", "105"),
            ("2021-01-02", "105", "110", "95", "100"),
            ("2021-01-03", "100", "110", "40", "50"),
        ],
    )
    recorder = RecordingStrategy(LimitThenCancelStrategy())
    environment = Environment(
        Experiment(recorder),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    assert len(recorder.contexts[1].open_orders) == 1
    assert recorder.contexts[2].open_orders == []
    assert environment.open_orders == []
    assert environment.positions == []
    assert environment.account.balances["USD"] == Decimal("10000")

    entries = load_registry(tmp_path / "outcomes")
    steps_file = tmp_path / "outcomes" / entries[0]["folder"] / "steps.jsonl"
    steps = [json.loads(line) for line in steps_file.read_text().splitlines()]
    assert steps[0]["open_orders"][0]["price"] == "50"
    order_id = steps[0]["open_orders"][0]["id"]
    assert steps[1]["journal"] == [
        {
            "type": "order_cancelled",
            "order_id": order_id,
            "ticker": "BTC",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": "1",
            "total_value": None,
            "price": "50",
        }
    ]
    assert steps[1]["open_orders"] == []


def test_new_limit_waits_until_next_bar_to_fill(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    # Placement bar already touches 90, but new limits fill starting next bar.
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "110", "80", "105"),
            ("2021-01-02", "105", "110", "85", "100"),
            ("2021-01-03", "100", "110", "40", "50"),
        ],
    )
    recorder = RecordingStrategy(LimitBuyStrategy(price="90"))
    environment = Environment(
        Experiment(recorder),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    assert len(recorder.contexts[1].open_orders) == 1
    assert environment.open_orders == []
    assert environment.positions[0].average_price == Decimal("90")
    assert environment.account.balances["USD"] == Decimal("9910")


class NoOpStrategy:
    def decide(self, context: Context) -> None:
        return None


def test_money_spawner_credits_before_decide(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [
            ("2023-01-01", "100", "110", "90", "105"),
            ("2023-01-15", "105", "110", "100", "108"),
            ("2023-02-01", "108", "120", "105", "115"),
        ],
    )
    recorder = RecordingStrategy(NoOpStrategy())
    environment = Environment(
        Experiment(
            recorder,
            money_spawner=MoneySpawner(
                currency="USD",
                amount=1000,
                interval=SpawnInterval.MONTH,
            ),
        ),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    # Starting 10000 + Jan deposit visible on first decide.
    assert recorder.contexts[0].account.balances["USD"] == Decimal("11000")
    assert recorder.contexts[1].account.balances["USD"] == Decimal("11000")
    assert recorder.contexts[2].account.balances["USD"] == Decimal("12000")

    entries = load_registry(tmp_path / "outcomes")
    steps_file = tmp_path / "outcomes" / entries[0]["folder"] / "steps.jsonl"
    steps = [json.loads(line) for line in steps_file.read_text().splitlines()]
    assert steps[0]["journal"] == [
        {"type": "deposit", "currency": "USD", "amount": "1000"}
    ]
    assert steps[1]["journal"] == []
    assert steps[2]["journal"] == [
        {"type": "deposit", "currency": "USD", "amount": "1000"}
    ]


class MutatingStrategy:
    """Tries to corrupt engine state through the Context handed to decide()."""

    def decide(self, context: Context) -> None:
        context.account.balances["USD"] = Decimal("0")
        context.positions.clear()
        context.history.setdefault("BTC", []).clear()
        context.current_open_prices.clear()
        context.open_orders.clear()
        return None


def test_context_mutations_do_not_affect_environment(tmp_path: Path, btc_csv: Path):
    environment = Environment(
        Experiment(MutatingStrategy()),
        MockExecutor(),
        [str(btc_csv)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    assert environment.account.balances["USD"] == Decimal("10000")
    assert environment.positions == []
    assert environment.open_orders == []
    # History still advanced for every bar despite strategy clearing its copy.
    assert len(environment.recorder.folder.joinpath("steps.jsonl").read_text().splitlines()) == 3
