from decimal import Decimal

import pytest

from executors.mock_executor import MockExecutor
from models import Account, Order, OrderSide, OrderType, Position


def make_order(side: OrderSide, quantity: str, ticker: str = "BTC") -> Order:
    return Order(
        ticker=ticker,
        side=side,
        quantity=Decimal(quantity),
        order_type=OrderType.MARKET,
    )


def test_buy_creates_position():
    account = Account(balances={"USD": Decimal("10000")})
    positions: list[Position] = []
    executor = MockExecutor()

    executor.execute(
        [make_order(OrderSide.BUY, "2")],
        account,
        positions,
        {"BTC": Decimal("100")},
    )

    assert account.balances["USD"] == Decimal("9800")
    assert len(positions) == 1
    assert positions[0].ticker == "BTC"
    assert positions[0].quantity == Decimal("2")
    assert positions[0].average_price == Decimal("100")


def test_second_buy_merges_and_updates_average():
    account = Account(balances={"USD": Decimal("10000")})
    positions: list[Position] = []
    executor = MockExecutor()

    executor.execute(
        [make_order(OrderSide.BUY, "1")],
        account,
        positions,
        {"BTC": Decimal("100")},
    )
    executor.execute(
        [make_order(OrderSide.BUY, "1")],
        account,
        positions,
        {"BTC": Decimal("200")},
    )

    assert len(positions) == 1
    assert positions[0].quantity == Decimal("2")
    assert positions[0].average_price == Decimal("150")
    assert account.balances["USD"] == Decimal("9700")


def test_partial_sell_keeps_average_price():
    account = Account(balances={"USD": Decimal("0")})
    positions = [
        Position(ticker="BTC", quantity=Decimal("2"), average_price=Decimal("100"))
    ]
    executor = MockExecutor()

    executor.execute(
        [make_order(OrderSide.SELL, "1")],
        account,
        positions,
        {"BTC": Decimal("150")},
    )

    assert account.balances["USD"] == Decimal("150")
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("1")
    assert positions[0].average_price == Decimal("100")


def test_full_sell_removes_position():
    account = Account(balances={"USD": Decimal("0")})
    positions = [
        Position(ticker="BTC", quantity=Decimal("2"), average_price=Decimal("100"))
    ]
    executor = MockExecutor()

    executor.execute(
        [make_order(OrderSide.SELL, "2")],
        account,
        positions,
        {"BTC": Decimal("150")},
    )

    assert account.balances["USD"] == Decimal("300")
    assert positions == []


def test_sell_too_much_raises():
    account = Account(balances={"USD": Decimal("0")})
    positions = [
        Position(ticker="BTC", quantity=Decimal("1"), average_price=Decimal("100"))
    ]
    executor = MockExecutor()

    with pytest.raises(ValueError, match="Not enough quantity"):
        executor.execute(
            [make_order(OrderSide.SELL, "2")],
            account,
            positions,
            {"BTC": Decimal("150")},
        )


def test_sell_unknown_ticker_raises():
    account = Account(balances={"USD": Decimal("0")})
    positions: list[Position] = []
    executor = MockExecutor()

    with pytest.raises(ValueError, match="Not enough quantity"):
        executor.execute(
            [make_order(OrderSide.SELL, "1")],
            account,
            positions,
            {"BTC": Decimal("150")},
        )


def test_buy_insufficient_balance_raises():
    account = Account(balances={"USD": Decimal("50")})
    positions: list[Position] = []
    executor = MockExecutor()

    with pytest.raises(ValueError, match="Not enough balance"):
        executor.execute(
            [make_order(OrderSide.BUY, "1")],
            account,
            positions,
            {"BTC": Decimal("100")},
        )


def test_positions_for_different_tickers_stay_separate():
    account = Account(balances={"USD": Decimal("10000")})
    positions: list[Position] = []
    executor = MockExecutor()

    executor.execute(
        [
            make_order(OrderSide.BUY, "1", ticker="BTC"),
            make_order(OrderSide.BUY, "2", ticker="ETH"),
        ],
        account,
        positions,
        {"BTC": Decimal("100"), "ETH": Decimal("50")},
    )

    assert len(positions) == 2
    by_ticker = {position.ticker: position for position in positions}
    assert by_ticker["BTC"].quantity == Decimal("1")
    assert by_ticker["BTC"].average_price == Decimal("100")
    assert by_ticker["ETH"].quantity == Decimal("2")
    assert by_ticker["ETH"].average_price == Decimal("50")
