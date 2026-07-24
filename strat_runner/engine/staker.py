from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from engine.journal import interest_entry
from engine.modifier import ExperimentModifier, ModifierContext
from engine.money_spawner import SpawnInterval
from models import Account, Position


@dataclass
class Staker(ExperimentModifier):
    """Pay interest on the period's minimum available balance of one ticker.

    Available means free cash (`account.balances[ticker]`) or free position
    quantity (not reserved on resting sell limits). ``rate`` is applied once
    per ``interval`` period on that period's running minimum.

    ``on_bar_start`` pays when a period rolls; ``on_bar_end`` tracks the min
    and pays the open period on the last bar.
    """

    ticker: str
    rate: Decimal | float | str | int
    interval: SpawnInterval
    _period: str | None = field(default=None, init=False, repr=False)
    _period_min: Decimal | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.ticker = str(self.ticker)
        if not self.ticker:
            raise ValueError("Staker ticker must be non-empty")
        self.rate = Decimal(str(self.rate))
        if self.rate < 0:
            raise ValueError("Staker rate must be non-negative")
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

    def available(self, account: Account, positions: list[Position]) -> Decimal:
        if self.ticker in account.balances:
            return account.balances[self.ticker]
        for position in positions:
            if position.ticker == self.ticker:
                return position.quantity
        return Decimal("0")

    def settle_if_period_changed(
        self,
        time: datetime,
        account: Account,
        positions: list[Position],
    ) -> tuple[Decimal, Decimal] | None:
        """If ``time`` starts a new period, pay interest on the prior period's min.

        Returns ``(interest, principal)`` when interest is credited.
        """
        key = self.period_key(time)
        if self._period is None:
            self._period = key
            return None
        if key == self._period:
            return None

        payment = self._credit_interest(account, positions)
        self._period = key
        self._period_min = None
        return payment

    def observe(self, account: Account, positions: list[Position]) -> None:
        """Update the current period's running minimum available balance."""
        available = self.available(account, positions)
        if self._period_min is None:
            self._period_min = available
        else:
            self._period_min = min(self._period_min, available)

    def settle_final(
        self,
        account: Account,
        positions: list[Position],
    ) -> tuple[Decimal, Decimal] | None:
        """Pay interest for the open period at the end of a backtest.

        Returns ``(interest, principal)`` when interest is credited.
        """
        payment = self._credit_interest(account, positions)
        self._period_min = None
        return payment

    def on_bar_start(self, ctx: ModifierContext) -> list[dict]:
        payment = self.settle_if_period_changed(
            ctx.time, ctx.account, ctx.positions
        )
        if payment is None:
            return []
        interest, principal = payment
        return [
            interest_entry(
                ticker=self.ticker,
                amount=interest,
                principal=principal,
                rate=self.rate,
            )
        ]

    def on_bar_end(self, ctx: ModifierContext) -> list[dict]:
        self.observe(ctx.account, ctx.positions)
        if not ctx.is_last_bar:
            return []
        payment = self.settle_final(ctx.account, ctx.positions)
        if payment is None:
            return []
        interest, principal = payment
        return [
            interest_entry(
                ticker=self.ticker,
                amount=interest,
                principal=principal,
                rate=self.rate,
            )
        ]

    def _credit_interest(
        self,
        account: Account,
        positions: list[Position],
    ) -> tuple[Decimal, Decimal] | None:
        if self._period_min is None:
            return None

        principal = self._period_min
        interest = principal * self.rate
        if interest <= 0:
            return None

        if self.ticker in account.balances:
            account.balances[self.ticker] = (
                account.balances.get(self.ticker, Decimal("0")) + interest
            )
        else:
            self._credit_position(positions, interest)

        return interest, principal

    def _credit_position(self, positions: list[Position], interest: Decimal) -> None:
        for position in positions:
            if position.ticker != self.ticker:
                continue
            # Interest coins have zero cost basis → dilute average price.
            total_cost = position.quantity * position.average_price
            position.quantity += interest
            position.average_price = (
                total_cost / position.quantity if position.quantity > 0 else Decimal("0")
            )
            return

        positions.append(
            Position(
                ticker=self.ticker,
                quantity=interest,
                average_price=Decimal("0"),
            )
        )

    def registry_record(self) -> dict:
        return {
            "type": "Staker",
            "ticker": self.ticker,
            "rate": str(self.rate),
            "interval": self.interval.value,
        }
