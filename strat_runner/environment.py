from datetime import datetime
from decimal import Decimal
from pathlib import Path

from data.loader import load_candles
from models import Account, Candle, Context, Order
from recorder import Recorder


class Environment:
    def __init__(
        self,
        strategy,
        mock_executor,
        data_file: str,
        full_debug_runs: bool = False,
    ):
        self.strategy = strategy
        self.mock_executor = mock_executor
        self.full_debug_runs = full_debug_runs

        project_dir = Path(__file__).parent
        self.data_file = project_dir / data_file
        self.account = Account(balances={"USD": Decimal("10000")})
        self.positions = []
        strategy_name = type(strategy).__name__.removesuffix("Strategy").lower()
        run_id = datetime.now().strftime("%y-%m-%d_%H-%M")
        self.recorder = Recorder(
            project_dir / "runs" / f"{strategy_name}_{run_id}",
            full_debug_runs=full_debug_runs,
        )

    def run(self):
        candles = load_candles(self.data_file)
        history = []

        for step, candle in enumerate(candles):
            history.append(candle)
            context = self._build_context(candle, history)

            snapshot_path = self.recorder.save_snapshot(step, context)
            orders = self.strategy.decide(context)

            self.mock_executor.execute(
                orders,
                self.account,
                self.positions,
                {candle.ticker: candle.close},
            )

            equity = self._mark_to_market(candle)
            self.recorder.record_step(
                self._step_record(step, candle, orders, equity, snapshot_path)
            )

    def _build_context(self, candle: Candle, history: list[Candle]) -> Context:
        return Context(
            time=candle.time,
            candles=history.copy(),
            account=self.account,
            positions=self.positions,
        )

    def _mark_to_market(self, candle: Candle) -> Decimal:
        equity = self.account.balances["USD"]

        for position in self.positions:
            equity += position.quantity * candle.close

        return equity

    def _step_record(
        self,
        step: int,
        candle: Candle,
        orders: list[Order],
        equity: Decimal,
        snapshot_path: Path | None,
    ) -> dict:
        record = {
            "step": step,
            "time": str(candle.time),
            "price": str(candle.close),
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
