from decimal import Decimal

from models import Account, Order, OrderSide, Position, OrderType


class MockExecutor:
    def execute(
        self,
        orders: list[Order],
        account: Account,
        positions: list[Position],
        prices: dict[str, Decimal],
    ):

        for order in orders:
            price = prices[order.ticker]

            if order.order_type == OrderType.LIMIT:
                raise NotImplementedError("Limit orders are not implemented")

            if order.side == OrderSide.BUY:
                self._buy(order, price, account, positions)

            elif order.side == OrderSide.SELL:
                self._sell(order, price, account, positions)

    def _buy(
        self, order: Order, price: Decimal, account: Account, positions: list[Position]
    ):
        cost = order.quantity * price

        if account.balances["USD"] < cost:
            raise ValueError(f"Not enough balance to buy {order.quantity} {order.ticker}")

        account.balances["USD"] -= cost

        positions.append(
            Position(ticker=order.ticker, quantity=order.quantity, average_price=price)
        )

    def _sell(
        self, order: Order, price: Decimal, account: Account, positions: list[Position]
    ):
        for position in positions:
            if position.ticker != order.ticker:
                continue

            if position.quantity < order.quantity:
                raise ValueError(f"Not enough quantity to sell {order.quantity} {order.ticker}")

            position.quantity -= order.quantity

            account.balances["USD"] += order.quantity * price

            break

        
