from decimal import Decimal

import pytest

from models import Order, OrderSide, OrderType


def test_market_order_with_quantity():
    order = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )
    assert order.price is None
    assert order.total_value is None


def test_market_order_with_total_value():
    order = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        total_value=Decimal("1000"),
    )
    assert order.quantity is None


def test_market_order_rejects_price():
    with pytest.raises(ValueError, match="must not include price"):
        Order(
            ticker="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
            price=Decimal("100"),
        )


def test_limit_order_requires_price_and_quantity_or_value():
    order = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        price=Decimal("100"),
    )
    assert order.price == Decimal("100")

    order = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        total_value=Decimal("1000"),
        price=Decimal("100"),
    )
    assert order.total_value == Decimal("1000")


def test_limit_order_rejects_missing_price():
    with pytest.raises(ValueError, match="must include price"):
        Order(
            ticker="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
        )


def test_order_gets_id_on_creation():
    first = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )
    second = Order(
        ticker="ETH",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )

    assert first.id.startswith("o")
    assert second.id.startswith("o")
    assert first.id != second.id


def test_order_rejects_both_quantity_and_value():
    with pytest.raises(ValueError, match="exactly one"):
        Order(
            ticker="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
            total_value=Decimal("1000"),
        )


def test_order_rejects_neither_quantity_nor_value():
    with pytest.raises(ValueError, match="exactly one"):
        Order(
            ticker="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
        )


def test_order_rejects_negative_reserved_cash():
    with pytest.raises(ValueError, match="non-negative"):
        Order(
            ticker="BTC",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            price=Decimal("100"),
            reserved_cash=Decimal("-1"),
        )


def test_order_rejects_negative_reserved_quantity():
    with pytest.raises(ValueError, match="non-negative"):
        Order(
            ticker="BTC",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            price=Decimal("100"),
            reserved_quantity=Decimal("-1"),
        )
