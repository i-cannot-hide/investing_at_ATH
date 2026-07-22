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

        price = context.current_open_prices.get(self.ticker)
        if price is None or price <= 0 or price >= self.target_price:
            return None

        return Decision(
            orders=[
                Order(
                    ticker=self.ticker,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    total_value=usd,
                )
            ]
        )
