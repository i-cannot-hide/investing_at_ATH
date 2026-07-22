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
)
from recorder import Recorder
from run_registry import (
    allocate_run_dir,
    register_run,
    strategy_assets,
    strategy_params,
)


class Environment:
    def __init__(
        self,
        strategy,
        mock_executor,
        data_files: str | list[str],
        full_debug_runs: bool = False,
        interval: str = "1d",
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
        runs_dir: Path | str | None = None,
    ):
        self.strategy = strategy
        self.mock_executor = mock_executor
        self.full_debug_runs = full_debug_runs
        self.interval = interval
        self.start_date = start_date
        self.end_date = end_date

        project_dir = Path(__file__).parent
        if isinstance(data_files, str):
            data_files = [data_files]
        self.data_files = [
            path if Path(path).is_absolute() else project_dir / path
            for path in data_files
        ]
        self.account = Account(balances={"USD": Decimal("10000")})
        self.positions = []
        self.open_orders: list[Order] = []

        self.runs_dir = Path(runs_dir) if runs_dir is not None else project_dir / "runs"
        self.run_id, self.date_time, run_folder = allocate_run_dir(self.runs_dir)
        self.recorder = Recorder(run_folder, full_debug_runs=full_debug_runs)

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

            context = self._build_context(time, history, current_open_prices)
            snapshot_path = self.recorder.save_snapshot(step, context)
            decision = self.strategy.decide(context) or Decision()

            cancelled_ids = self._cancel_open_orders(decision.cancel_order_ids)
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

            filled_ids = self._fill_open_orders(current_candles)
            
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
                    cancelled_ids,
                    filled_ids,
                    equity,
                    snapshot_path,
                )
            )

        times = list(bars_by_time)
        register_run(
            self.runs_dir,
            {
                "id": self.run_id,
                "folder": self.recorder.folder.name,
                "date_time": self.date_time,
                "strategy": type(self.strategy).__name__.removesuffix("Strategy").lower(),
                "assets": strategy_assets(self.strategy),
                "params": strategy_params(self.strategy),
                "start_date": times[0].strftime("%Y-%m-%d"),
                "end_date": times[-1].strftime("%Y-%m-%d"),
                "interval": self.interval,
            },
        )

    def _cancel_open_orders(self, cancel_ids: list[str]) -> list[str]:
        if not cancel_ids:
            return []
        cancel_set = set(cancel_ids)
        cancelled = [order.id for order in self.open_orders if order.id in cancel_set]
        self.open_orders = [
            order for order in self.open_orders if order.id not in cancel_set
        ]
        return cancelled

    def _fill_open_orders(self, candles: dict[str, Candle]) -> list[str]:
        still_open: list[Order] = []
        filled_ids: list[str] = []

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
                self.mock_executor.execute(
                    [order],
                    self.account,
                    self.positions,
                    candles,
                )
                filled_ids.append(order.id)
            else:
                still_open.append(order)

        self.open_orders = still_open
        return filled_ids

    def _build_context(
        self,
        time: datetime,
        history: dict[str, list[Candle]],
        current_open_prices: dict[str, Decimal],
    ) -> Context:
        return Context(
            time=time,
            history=history,
            current_open_prices=current_open_prices,
            account=self.account,
            positions=self.positions,
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
        cancelled_ids: list[str],
        filled_ids: list[str],
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
            "cancel_order_ids": cancelled_ids,
            "filled_order_ids": filled_ids,
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
