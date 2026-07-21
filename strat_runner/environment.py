from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from data.loader import filter_candles_by_date, group_candles_by_time, load_candles_many
from models import Account, Candle, Context, Order
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
        self.data_files = [project_dir / path for path in data_files]
        self.account = Account(balances={"USD": Decimal("10000")})
        self.positions = []

        self.runs_dir = project_dir / "runs"
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
        last_prices: dict[str, Decimal] = {}

        for step, (time, bar_candles) in enumerate(bars_by_time.items()):
            prices = {candle.ticker: candle.close for candle in bar_candles}
            last_prices.update(prices)

            for candle in bar_candles:
                history[candle.ticker].append(candle)

            context = self._build_context(time, history)
            snapshot_path = self.recorder.save_snapshot(step, context)
            orders = self.strategy.decide(context)

            self.mock_executor.execute(
                orders,
                self.account,
                self.positions,
                last_prices,
            )

            equity = self._mark_to_market(last_prices)
            self.recorder.record_step(
                self._step_record(step, time, last_prices, orders, equity, snapshot_path)
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

    def _build_context(
        self, time: datetime, history: dict[str, list[Candle]]
    ) -> Context:
        return Context(
            time=time,
            candles=history,
            account=self.account,
            positions=self.positions,
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
        orders: list[Order],
        equity: Decimal,
        snapshot_path: Path | None,
    ) -> dict:
        record = {
            "step": step,
            "time": str(time),
            "prices": {ticker: str(price) for ticker, price in prices.items()},
            "decision": [
                {
                    "ticker": order.ticker,
                    "side": order.side.value,
                    "quantity": str(order.quantity),
                    "order_type": order.order_type.value,
                }
                for order in orders
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
