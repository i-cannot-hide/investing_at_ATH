from decimal import Decimal

from models import Context, Order, OrderSide, OrderType


MIN_USD = Decimal("10.00")
TICKER = "BTC"


class HoldStrategy:
    def decide(self, context: Context) -> list[Order]:
        usd = context.account.balances.get("USD", Decimal("0"))
        if usd < MIN_USD:
            return []

        btc_candles = context.candles.get(TICKER, [])
        if not btc_candles:
            return []

        price = btc_candles[-1].close
        if price <= 0:
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
