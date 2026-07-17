from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from data.loader import group_candles_by_time, load_candles_many
from models import Account, Candle, Context, Order
from recorder import Recorder


class Environment:
    def __init__(
        self,
        strategy,
        mock_executor,
        data_files: str | list[str],
        full_debug_runs: bool = False,
    ):
        self.strategy = strategy
        self.mock_executor = mock_executor
        self.full_debug_runs = full_debug_runs

        project_dir = Path(__file__).parent
        if isinstance(data_files, str):
            data_files = [data_files]
        self.data_files = [project_dir / path for path in data_files]
        self.account = Account(balances={"USD": Decimal("10000")})
        self.positions = []
        strategy_name = type(strategy).__name__.removesuffix("Strategy").lower()
        run_id = datetime.now().strftime("%y-%m-%d_%H-%M")
        self.recorder = Recorder(
            project_dir / "runs" / f"{strategy_name}_{run_id}",
            full_debug_runs=full_debug_runs,
        )

    def run(self):
        candles = load_candles_many(self.data_files)
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

    def _build_context(
        self, time: datetime, history: dict[str, list[Candle]]
    ) -> Context:
        return Context(
            time=time,
            candles={ticker: list(candles) for ticker, candles in history.items()},
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
