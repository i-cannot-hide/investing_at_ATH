from decimal import Decimal

from models import Context, Order, OrderSide, OrderType


MIN_USD = Decimal("10.00")
TICKER = "BTC"


class BuyBelowStrategy:
    def __init__(self, target_price: Decimal | float | str | int = 20000):
        self.target_price = Decimal(str(target_price))

    def decide(self, context: Context) -> list[Order]:
        usd = context.account.balances.get("USD", Decimal("0"))
        if usd < MIN_USD:
            return []

        btc_candles = context.candles.get(TICKER, [])
        if not btc_candles:
            return []

        price = btc_candles[-1].close
        if price <= 0 or price >= self.target_price:
            return []

        quantity = usd / price

        return [
            Order(
                ticker=TICKER,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type=OrderType.MARKET,
            )
        ]
