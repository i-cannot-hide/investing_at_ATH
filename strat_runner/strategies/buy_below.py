from decimal import Decimal

from models import Context, Decision, Order, OrderSide, OrderType


MIN_USD = Decimal("10.00")


class BuyBelowStrategy:
    def __init__(
        self,
        target_price: Decimal | float | str | int = 20000,
        ticker: str = "BTC",
    ):
        self.target_price = Decimal(str(target_price))
        self.ticker = ticker

    def decide(self, context: Context) -> Decision | None:
        usd = context.account.balances.get("USD", Decimal("0"))
        if usd < MIN_USD:
            return None

        if self.target_price <= 0:
            return None

        if self.ticker not in context.current_open_prices:
            return None

        if any(order.ticker == self.ticker for order in context.open_orders):
            return None

        return Decision(
            orders=[
                Order(
                    ticker=self.ticker,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=usd / self.target_price,
                    price=self.target_price,
                )
            ]
        )
