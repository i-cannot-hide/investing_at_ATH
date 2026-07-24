from decimal import Decimal

from engine.journal import (
    EntryType,
    deposit_entry,
    interest_entry,
    order_cancelled_entry,
    order_filled_entry,
    withdrawal_entry,
)
from models import Order, OrderSide, OrderType


def test_deposit_and_withdrawal_entries():
    assert deposit_entry(currency="USD", amount=Decimal("1000")) == {
        "type": EntryType.DEPOSIT.value,
        "currency": "USD",
        "amount": "1000",
    }
    assert withdrawal_entry(currency="USD", amount=Decimal("250")) == {
        "type": EntryType.WITHDRAWAL.value,
        "currency": "USD",
        "amount": "250",
    }


def test_interest_entry():
    assert interest_entry(
        ticker="USD",
        amount=Decimal("40"),
        principal=Decimal("400"),
        rate=Decimal("0.1"),
    ) == {
        "type": EntryType.INTEREST.value,
        "ticker": "USD",
        "amount": "40",
        "principal": "400",
        "rate": "0.1",
    }


def test_order_filled_entry():
    order = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        price=Decimal("90"),
        id="o9",
    )
    assert order_filled_entry(
        order=order,
        quantity=Decimal("1"),
        price=Decimal("90"),
    ) == {
        "type": "order_filled",
        "order_id": "o9",
        "ticker": "BTC",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": "1",
        "price": "90",
    }


def test_order_cancelled_entry():
    order = Order(
        ticker="ETH",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        total_value=Decimal("500"),
        price=Decimal("2000"),
        id="o3",
    )
    assert order_cancelled_entry(order=order) == {
        "type": "order_cancelled",
        "order_id": "o3",
        "ticker": "ETH",
        "side": "SELL",
        "order_type": "LIMIT",
        "quantity": None,
        "total_value": "500",
        "price": "2000",
    }
