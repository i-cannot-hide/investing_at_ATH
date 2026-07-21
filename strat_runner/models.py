from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from decimal import Decimal


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class Candle:
    time: datetime
    ticker: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass
class Order:
    ticker: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal | None = None
    total_value: Decimal | None = None
    price: Decimal | None = None

    def __post_init__(self):
        has_quantity = self.quantity is not None
        has_value = self.total_value is not None

        if has_quantity == has_value:
            raise ValueError("Order must specify exactly one of quantity or total_value")

        if (self.order_type == OrderType.MARKET) and (self.price is not None):
            raise ValueError("Market orders must not include price")
        elif (self.order_type == OrderType.LIMIT) and (self.price is None):
            raise ValueError("Limit orders must include price")


@dataclass
class Position:
    ticker: str
    quantity: Decimal
    average_price: Decimal


@dataclass
class Account:
    balances: dict[str, Decimal]


@dataclass
class Context:
    time: datetime
    candles: dict[str, list[Candle]]
    account: Account
    positions: list[Position]
