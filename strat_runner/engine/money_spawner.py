from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from engine.journal import deposit_entry
from engine.modifier import ExperimentModifier, ModifierContext
from models import Account


class SpawnInterval(Enum):
    DAY = "1D"
    WEEK = "1W"
    MONTH = "1M"


@dataclass
class MoneySpawner(ExperimentModifier):
    currency: str
    amount: Decimal | float | str | int
    interval: SpawnInterval
    _last_period: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.amount = Decimal(str(self.amount))
        if self.amount <= 0:
            raise ValueError("MoneySpawner amount must be positive")
        if not isinstance(self.interval, SpawnInterval):
            raise TypeError(
                f"interval must be SpawnInterval, got {type(self.interval)!r}"
            )

    def period_key(self, time: datetime) -> str:
        if self.interval == SpawnInterval.DAY:
            return time.strftime("%Y-%m-%d")
        if self.interval == SpawnInterval.WEEK:
            iso = time.isocalendar()
            return f"{iso.year}-W{iso.week:02d}"
        if self.interval == SpawnInterval.MONTH:
            return time.strftime("%Y-%m")
        raise ValueError(f"Unsupported interval: {self.interval}")

    def spawn(self, time: datetime, account: Account) -> Decimal | None:
        key = self.period_key(time)
        if key == self._last_period:
            return None

        self._last_period = key
        account.balances[self.currency] = (
            account.balances.get(self.currency, Decimal("0")) + self.amount
        )
        return self.amount

    def on_bar_start(self, ctx: ModifierContext) -> list[dict]:
        deposit = self.spawn(ctx.time, ctx.account)
        if deposit is None:
            return []
        return [deposit_entry(currency=self.currency, amount=deposit)]

    def registry_record(self) -> dict:
        return {
            "type": "MoneySpawner",
            "currency": self.currency,
            "amount": str(self.amount),
            "interval": self.interval.value,
        }
