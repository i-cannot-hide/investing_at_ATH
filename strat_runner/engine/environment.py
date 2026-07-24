from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from data.loader import filter_candles_by_date, group_candles_by_time, load_candles_many
from models import (
    Account,
    Candle,
    Context,
    Decision,
    Order,
    OrderType,
    Position,
)
from engine.experiment import Experiment
from engine.journal import (
    deposit_entry,
    order_cancelled_entry,
    order_filled_entry,
)
from engine.recorder import Recorder
from engine.outcome_registry import (
    allocate_outcome_dir,
    register_outcome,
    strategy_assets,
    strategy_params,
)
from executors.mock_executor import Fill


class Environment:
    def __init__(
        self,
        experiment: Experiment,
        mock_executor,
        data_files: str | list[str],
        full_debug_outcomes: bool = False,
        interval: str = "1d",
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
        outcomes_dir: Path | str | None = None,
        research_name: str | None = None,
        research_id: str | None = None,
        initial_usd: Decimal | int | str | float = 10_000,
    ):
        self.experiment = experiment
        self.strategy = experiment.strategy
        self.money_spawner = experiment.money_spawner
        self.mock_executor = mock_executor
        self.full_debug_outcomes = full_debug_outcomes
        self.interval = interval
        self.start_date = start_date
        self.end_date = end_date
        self.research_name = research_name
        self.research_id = research_id
        self.initial_usd = Decimal(str(initial_usd))

        project_dir = Path(__file__).resolve().parent.parent
        if isinstance(data_files, str):
            data_files = [data_files]
        self.data_files = [
            path if Path(path).is_absolute() else project_dir / path
            for path in data_files
        ]
        self.account = Account(balances={"USD": self.initial_usd})
        self.positions = []
        self.open_orders: list[Order] = []

        self.outcomes_dir = Path(outcomes_dir) if outcomes_dir is not None else project_dir / "outcomes"
        self.outcome_id, self.date_time, outcome_folder = allocate_outcome_dir(self.outcomes_dir)
        self.recorder = Recorder(outcome_folder, full_debug_outcomes=full_debug_outcomes)

    def run(self):
        candles = load_candles_many(self.data_files)
        candles = filter_candles_by_date(
            candles,
            start_date=self.start_date,
            end_date=self.end_date,
        )
        if not candles:
            raise ValueError(
                "No candles loaded from data files for the given date range"
            )

        bars_by_time = group_candles_by_time(candles)
        history: dict[str, list[Candle]] = defaultdict(list)
        last_candles: dict[str, Candle] = {}

        for step, (time, bar_candles) in enumerate(bars_by_time.items()):
            current_open_prices = {
                candle.ticker: candle.open for candle in bar_candles
            }
            current_candles = {candle.ticker: candle for candle in bar_candles}
            journal: list[dict] = []

            if self.money_spawner is not None:
                deposit = self.money_spawner.spawn(time, self.account)
                if deposit is not None:
                    journal.append(
                        deposit_entry(
                            currency=self.money_spawner.currency,
                            amount=deposit,
                        )
                    )

            context = self._build_context(time, history, current_open_prices)
            snapshot_path = self.recorder.save_snapshot(step, context)
            decision = self.strategy.decide(context) or Decision()

            cancelled_orders = self._cancel_open_orders(decision.cancel_order_ids)
            for order in cancelled_orders:
                journal.append(order_cancelled_entry(order=order))

            markets: list[Order] = []
            limits: list[Order] = []
            for order in decision.orders:
                if order.order_type == OrderType.MARKET:
                    markets.append(order)
                elif order.order_type == OrderType.LIMIT:
                    limits.append(order)
                else:
                    raise ValueError(f"Unsupported order type: {order.order_type}")

            self.open_orders.extend(markets)

            for candle in bar_candles:
                history[candle.ticker].append(candle)
                last_candles[candle.ticker] = candle

            for fill in self._fill_open_orders(current_candles):
                journal.append(
                    order_filled_entry(
                        order=fill.order,
                        quantity=fill.quantity,
                        price=fill.price,
                    )
                )

            self.open_orders.extend(limits)

            last_prices = {
                ticker: candle.close for ticker, candle in last_candles.items()
            }
            equity = self._mark_to_market(last_prices)
            self.recorder.record_step(
                self._step_record(
                    step,
                    time,
                    last_prices,
                    decision,
                    journal,
                    equity,
                    snapshot_path,
                )
            )

        times = list(bars_by_time)
        register_outcome(
            self.outcomes_dir,
            {
                "id": self.outcome_id,
                "folder": self.recorder.folder.name,
                "date_time": self.date_time,
                "research": self.research_name,
                "research_id": self.research_id,
                "name": self.experiment.name,
                "strategy": type(self.strategy).__name__.removesuffix("Strategy").lower(),
                "assets": strategy_assets(self.strategy),
                "params": strategy_params(self.strategy),
                "money_spawner": (
                    None
                    if self.money_spawner is None
                    else {
                        "currency": self.money_spawner.currency,
                        "amount": str(self.money_spawner.amount),
                        "interval": self.money_spawner.interval.value,
                    }
                ),
                "start_date": times[0].strftime("%Y-%m-%d"),
                "end_date": times[-1].strftime("%Y-%m-%d"),
                "interval": self.interval,
                "initial_usd": str(self.initial_usd),
            },
        )

    def _cancel_open_orders(self, cancel_ids: list[str]) -> list[Order]:
        if not cancel_ids:
            return []
        cancel_set = set(cancel_ids)
        cancelled = [order for order in self.open_orders if order.id in cancel_set]
        self.open_orders = [
            order for order in self.open_orders if order.id not in cancel_set
        ]
        return cancelled

    def _fill_open_orders(self, candles: dict[str, Candle]) -> list[Fill]:
        still_open: list[Order] = []
        fills: list[Fill] = []

        for order in self.open_orders:
            candle = candles.get(order.ticker)
            if candle is None:
                still_open.append(order)
                continue

            if order.order_type == OrderType.MARKET:
                should_fill = True
            elif order.order_type == OrderType.LIMIT:
                should_fill = self.mock_executor.limit_is_triggered(order, candle)
            else:
                raise ValueError(f"Unsupported order type: {order.order_type}")

            if should_fill:
                fills.extend(
                    self.mock_executor.execute(
                        [order],
                        self.account,
                        self.positions,
                        candles,
                    )
                )
            else:
                still_open.append(order)

        self.open_orders = still_open
        return fills

    def _build_context(
        self,
        time: datetime,
        history: dict[str, list[Candle]],
        current_open_prices: dict[str, Decimal],
    ) -> Context:
        """Snapshot for `decide` — copies mutable state so strategies cannot corrupt the sim."""
        return Context(
            time=time,
            history={
                ticker: list(candles) for ticker, candles in history.items()
            },
            current_open_prices=dict(current_open_prices),
            account=Account(balances=dict(self.account.balances)),
            positions=[
                Position(
                    ticker=position.ticker,
                    quantity=position.quantity,
                    average_price=position.average_price,
                )
                for position in self.positions
            ],
            open_orders=list(self.open_orders),
        )

    def _mark_to_market(self, prices: dict[str, Decimal]) -> Decimal:
        equity = self.account.balances["USD"]

        for position in self.positions:
            equity += position.quantity * prices[position.ticker]

        return equity

    def _step_record(
        self,
        step: int,
        time: datetime,
        prices: dict[str, Decimal],
        decision: Decision,
        journal: list[dict],
        equity: Decimal,
        snapshot_path: Path | None,
    ) -> dict:
        record = {
            "step": step,
            "time": str(time),
            "prices": {ticker: str(price) for ticker, price in prices.items()},
            "decision": [
                {
                    "id": order.id,
                    "ticker": order.ticker,
                    "side": order.side.value,
                    "quantity": str(order.quantity) if order.quantity is not None else None,
                    "total_value": (
                        str(order.total_value) if order.total_value is not None else None
                    ),
                    "price": str(order.price) if order.price is not None else None,
                    "order_type": order.order_type.value,
                }
                for order in decision.orders
            ],
            "journal": journal,
            "open_orders": [
                {
                    "id": order.id,
                    "ticker": order.ticker,
                    "side": order.side.value,
                    "order_type": order.order_type.value,
                    "quantity": (
                        str(order.quantity) if order.quantity is not None else None
                    ),
                    "total_value": (
                        str(order.total_value) if order.total_value is not None else None
                    ),
                    "price": str(order.price) if order.price is not None else None,
                }
                for order in self.open_orders
            ],
            "balances": {
                currency: str(amount)
                for currency, amount in self.account.balances.items()
            },
            "positions": [
                {
                    "ticker": position.ticker,
                    "quantity": str(position.quantity),
                    "average_price": str(position.average_price),
                }
                for position in self.positions
            ],
            "equity": str(equity),
        }
        if snapshot_path is not None:
            record["source_snapshot"] = str(snapshot_path)
        return record
