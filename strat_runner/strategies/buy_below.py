from decimal import Decimal

from models import Context, Order, OrderSide, OrderType


MIN_USD = Decimal("10.00")


class BuyBelowStrategy:
    def __init__(
        self,
        target_price: Decimal | float | str | int = 20000,
        ticker: str = "BTC",
    ):
        self.target_price = Decimal(str(target_price))
        self.ticker = ticker

    def decide(self, context: Context) -> list[Order]:
        usd = context.account.balances.get("USD", Decimal("0"))
        if usd < MIN_USD:
            return []

        candles = context.candles.get(self.ticker, [])
        if not candles:
            return []

        current_candle = candles[-1]
        price = current_candle.close
        if price <= 0 or price >= self.target_price:
            return []

        quantity = usd / price

        return [
            Order(
                ticker=self.ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type=OrderType.MARKET,
            )
        ]
