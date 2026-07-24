import json
from decimal import Decimal
from pathlib import Path

import pytest

from engine import (
    Environment,
    Experiment,
    MoneySpawner,
    SpawnInterval,
    Staker,
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
    assert steps[0]["candles"]["BTC"] == {
        "open": "100",
        "high": "120",
        "low": "90",
        "close": "110",
    }
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
    assert recorder.contexts[1].open_orders[0].reserved_cash == Decimal("90")
    # Free cash excludes the reservation while the limit rests.
    assert recorder.contexts[1].account.balances["USD"] == Decimal("9910")

    assert environment.open_orders == []
    assert environment.frozen_usd == Decimal("0")
    assert len(environment.positions) == 1
    assert environment.positions[0].quantity == Decimal("1")
    assert environment.positions[0].average_price == Decimal("90")
    assert environment.account.balances["USD"] == Decimal("9910")

    entries = load_registry(tmp_path / "outcomes")
    steps_file = tmp_path / "outcomes" / entries[0]["folder"] / "steps.jsonl"
    steps = [json.loads(line) for line in steps_file.read_text().splitlines()]
    assert steps[0]["balances"]["USD"] == "9910"
    assert steps[0]["frozen_usd"] == "90"
    assert steps[0]["equity"] == "10000"
    assert steps[0]["open_orders"][0]["reserved_cash"] == "90"
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
    assert steps[1]["frozen_usd"] == "0"


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


def test_staker_pays_interest_on_period_minimum(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [
            ("2023-01-01", "100", "110", "90", "105"),
            ("2023-01-15", "105", "110", "100", "108"),
            ("2023-02-01", "108", "120", "105", "115"),
        ],
    )
    # Spend half on day 1 via hold-like market buy of $5000 worth... use NoOp and
    # mutate via a strategy that spends once.
    class SpendOnce:
        def __init__(self):
            self.spent = False

        def decide(self, context: Context) -> Decision | None:
            if self.spent:
                return None
            self.spent = True
            return Decision(
                orders=[
                    Order(
                        ticker="BTC",
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        total_value=Decimal("6000"),
                    )
                ]
            )

    environment = Environment(
        Experiment(
            SpendOnce(),
            stakers=[
                Staker(ticker="USD", rate="0.10", interval=SpawnInterval.MONTH),
            ],
        ),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
        initial_usd=10_000,
    )
    environment.run()

    entries = load_registry(tmp_path / "outcomes")
    steps_file = tmp_path / "outcomes" / entries[0]["folder"] / "steps.jsonl"
    steps = [json.loads(line) for line in steps_file.read_text().splitlines()]

    # Jan: start 10000, after buy free USD=4000 → min=4000. Feb 1 pays 10%.
    jan_interest = steps[2]["journal"][0]
    assert jan_interest["type"] == "interest"
    assert jan_interest["ticker"] == "USD"
    assert Decimal(jan_interest["principal"]) == Decimal("4000")
    assert Decimal(jan_interest["amount"]) == Decimal("400")
    assert Decimal(jan_interest["rate"]) == Decimal("0.10")

    # Last bar also settles Feb (one day after Jan interest credited).
    feb_interest = [e for e in steps[2]["journal"] if e["type"] == "interest"][1]
    assert Decimal(feb_interest["principal"]) == Decimal("4400")
    assert Decimal(feb_interest["amount"]) == Decimal("440")
    assert entries[0]["stakers"] == [
        {"ticker": "USD", "rate": "0.10", "interval": "1M"}
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


def test_limit_buy_reserves_cash_and_cancel_releases_it(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "110", "95", "105"),
            ("2021-01-02", "105", "110", "95", "100"),
        ],
    )
    environment = Environment(
        Experiment(LimitThenCancelStrategy()),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    entries = load_registry(tmp_path / "outcomes")
    steps = [
        json.loads(line)
        for line in (tmp_path / "outcomes" / entries[0]["folder"] / "steps.jsonl")
        .read_text()
        .splitlines()
    ]
    # Day 1: qty 1 @ 50 reserved.
    assert steps[0]["balances"]["USD"] == "9950"
    assert steps[0]["frozen_usd"] == "50"
    assert steps[0]["equity"] == "10000"
    assert steps[0]["open_orders"][0]["reserved_cash"] == "50"
    # Day 2: cancel restores free cash.
    assert steps[1]["balances"]["USD"] == "10000"
    assert steps[1]["frozen_usd"] == "0"
    assert steps[1]["equity"] == "10000"
    assert environment.account.balances["USD"] == Decimal("10000")
    assert environment.frozen_usd == Decimal("0")


def test_limit_buy_gap_fill_returns_unused_reservation(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    # Day 1 rests. Day 2 opens at 80 (through limit 90) → fill at 80.
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "110", "95", "105"),
            ("2021-01-02", "80", "90", "75", "85"),
        ],
    )
    environment = Environment(
        Experiment(LimitBuyStrategy(price="90")),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    assert environment.positions[0].average_price == Decimal("80")
    # Reserved 90, filled at 80 → 10 returned to free → 9920.
    assert environment.account.balances["USD"] == Decimal("9920")
    assert environment.frozen_usd == Decimal("0")


def test_limit_buy_rejects_when_insufficient_free_cash(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [("2021-01-01", "100", "110", "95", "105")],
    )

    class ExpensiveLimitStrategy:
        def decide(self, context: Context) -> Decision:
            return Decision(
                orders=[
                    Order(
                        ticker="BTC",
                        side=OrderSide.BUY,
                        order_type=OrderType.LIMIT,
                        quantity=Decimal("1000"),
                        price=Decimal("100"),
                    )
                ]
            )

    environment = Environment(
        Experiment(ExpensiveLimitStrategy()),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
        initial_usd=1000,
    )
    with pytest.raises(ValueError, match="Not enough free USD to reserve"):
        environment.run()


class SeedPositionThenLimitSellStrategy:
    """Day 1: market-buy 1 BTC. Day 2: rest a limit sell for that 1 BTC."""

    def __init__(self):
        self._bought = False

    def decide(self, context: Context) -> Decision | None:
        if not self._bought:
            self._bought = True
            return Decision(
                orders=[
                    Order(
                        ticker="BTC",
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=Decimal("1"),
                    )
                ]
            )
        if any(order.side == OrderSide.SELL for order in context.open_orders):
            return None
        if not context.positions:
            return None
        return Decision(
            orders=[
                Order(
                    ticker="BTC",
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    quantity=Decimal("1"),
                    price=Decimal("200"),
                )
            ]
        )


class LimitSellThenCancelStrategy(SeedPositionThenLimitSellStrategy):
    def decide(self, context: Context) -> Decision | None:
        if any(order.side == OrderSide.SELL for order in context.open_orders):
            return Decision(
                cancel_order_ids=[
                    order.id for order in context.open_orders if order.side == OrderSide.SELL
                ]
            )
        return super().decide(context)


def test_limit_sell_reserves_coins(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    # Day 1 buy at close 110. Day 2 high stays below 200 so sell rests.
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "120", "90", "110"),
            ("2021-01-02", "110", "150", "100", "140"),
        ],
    )
    recorder = RecordingStrategy(SeedPositionThenLimitSellStrategy())
    environment = Environment(
        Experiment(recorder),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    # Day-2 decide still sees the free position; sell is accepted after decide.
    assert len(recorder.contexts[1].positions) == 1
    assert recorder.contexts[1].positions[0].quantity == Decimal("1")

    entries = load_registry(tmp_path / "outcomes")
    steps = [
        json.loads(line)
        for line in (tmp_path / "outcomes" / entries[0]["folder"] / "steps.jsonl")
        .read_text()
        .splitlines()
    ]
    # End of day 2: sell rests, free position empty, 1 coin reserved.
    assert steps[1]["positions"] == []
    assert steps[1]["open_orders"][0]["reserved_quantity"] == "1"
    assert steps[1]["open_orders"][0]["side"] == "SELL"
    # Equity still includes reserved coin at close 140: 9890 + 140 = 10030.
    assert Decimal(steps[1]["equity"]) == Decimal("10030")
    assert environment.frozen_quantity("BTC") == Decimal("1")
    assert environment.positions[0].quantity == Decimal("0")


def test_limit_sell_cancel_releases_coins(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "120", "90", "110"),
            ("2021-01-02", "110", "150", "100", "140"),
            ("2021-01-03", "140", "160", "130", "150"),
        ],
    )
    environment = Environment(
        Experiment(LimitSellThenCancelStrategy()),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    assert environment.open_orders == []
    assert environment.frozen_quantity("BTC") == Decimal("0")
    assert len(environment.positions) == 1
    assert environment.positions[0].quantity == Decimal("1")


def test_limit_sell_rejects_when_insufficient_free_coins(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "120", "90", "110"),
            ("2021-01-02", "110", "150", "100", "140"),
        ],
    )

    class OversellStrategy(SeedPositionThenLimitSellStrategy):
        def decide(self, context: Context) -> Decision | None:
            if not self._bought:
                return super().decide(context)
            return Decision(
                orders=[
                    Order(
                        ticker="BTC",
                        side=OrderSide.SELL,
                        order_type=OrderType.LIMIT,
                        quantity=Decimal("2"),
                        price=Decimal("200"),
                    )
                ]
            )

    environment = Environment(
        Experiment(OversellStrategy()),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    with pytest.raises(ValueError, match="Not enough free BTC to reserve"):
        environment.run()


def test_limit_sell_fill_uses_reserved_coins(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    # Day 2 high reaches 200 → limit sell fills.
    write_btc_csv(
        csv_path,
        [
            ("2021-01-01", "100", "120", "90", "110"),
            ("2021-01-02", "110", "150", "100", "140"),
            ("2021-01-03", "140", "210", "130", "200"),
        ],
    )
    environment = Environment(
        Experiment(SeedPositionThenLimitSellStrategy()),
        MockExecutor(),
        [str(csv_path)],
        outcomes_dir=tmp_path / "outcomes",
    )
    environment.run()

    assert environment.open_orders == []
    assert environment.frozen_quantity("BTC") == Decimal("0")
    assert environment.positions == []
    # Bought at 110, sold at 200 → USD 10000 - 110 + 200 = 10090.
    assert environment.account.balances["USD"] == Decimal("10090")
