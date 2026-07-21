from decimal import Decimal

from models import Account, Candle, Order, OrderSide, Position, OrderType


class MockExecutor:
    def execute(
        self,
        orders: list[Order],
        account: Account,
        positions: list[Position],
        candles: dict[str, Candle],
    ):

        for order in orders:
            candle = candles[order.ticker]

            if order.order_type == OrderType.LIMIT:
                raise NotImplementedError("Limit orders are not implemented")

            if order.order_type == OrderType.MARKET:
                price = candle.close

            quantity = self._resolve_quantity(order, price)

            if order.side == OrderSide.BUY:
                self._buy(order.ticker, quantity, price, account, positions)

            elif order.side == OrderSide.SELL:
                self._sell(order.ticker, quantity, price, account, positions)

    def _resolve_quantity(self, order: Order, price: Decimal) -> Decimal:
        if order.total_value is not None:
            if price <= 0:
                raise ValueError(f"Cannot size order for {order.ticker}: price is {price}")
            return order.total_value / price
        return order.quantity

    def _find_position(
        self, positions: list[Position], ticker: str
    ) -> tuple[int | None, Position | None]:
        for index, position in enumerate(positions):
            if position.ticker == ticker:
                return index, position
        return None, None

    def _buy(
        self,
        ticker: str,
        quantity: Decimal,
        price: Decimal,
        account: Account,
        positions: list[Position],
    ):
        cost = quantity * price

        if account.balances["USD"] < cost:
            raise ValueError(f"Not enough balance to buy {quantity} {ticker}")

        account.balances["USD"] -= cost

        _, position = self._find_position(positions, ticker)
        if position is None:
            positions.append(
                Position(
                    ticker=ticker,
                    quantity=quantity,
                    average_price=price,
                )
            )
            return

        new_quantity = position.quantity + quantity
        position.average_price = (
            position.quantity * position.average_price + quantity * price
        ) / new_quantity
        position.quantity = new_quantity

    def _sell(
        self,
        ticker: str,
        quantity: Decimal,
        price: Decimal,
        account: Account,
        positions: list[Position],
    ):
        index, position = self._find_position(positions, ticker)
        if position is None or position.quantity < quantity:
            raise ValueError(f"Not enough quantity to sell {quantity} {ticker}")

        position.quantity -= quantity
        account.balances["USD"] += quantity * price

        if position.quantity == 0:
            positions.pop(index)
