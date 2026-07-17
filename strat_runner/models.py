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
    quantity: Decimal
    order_type: OrderType


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
    candles: list[Candle]
    account: Account
    positions: list[Position]
