from datetime import datetime
from decimal import Decimal

import pytest

from executors.mock_executor import MockExecutor
from models import Account, Candle, Order, OrderSide, OrderType, Position


def make_order(
    side: OrderSide,
    *,
    quantity: str | None = None,
    total_value: str | None = None,
    ticker: str = "BTC",
) -> Order:
    return Order(
        ticker=ticker,
        side=side,
        order_type=OrderType.MARKET,
        quantity=Decimal(quantity) if quantity is not None else None,
        total_value=Decimal(total_value) if total_value is not None else None,
    )


def make_candle(close: str, ticker: str = "BTC") -> Candle:
    price = Decimal(close)
    return Candle(
        time=datetime(2021, 1, 1),
        ticker=ticker,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1"),
    )


def test_buy_creates_position():
    account = Account(balances={"USD": Decimal("10000")})
    positions: list[Position] = []
    executor = MockExecutor()

    executor.execute(
        [make_order(OrderSide.BUY, quantity="2")],
        account,
        positions,
        {"BTC": make_candle("100")},
    )

    assert account.balances["USD"] == Decimal("9800")
    assert len(positions) == 1
    assert positions[0].ticker == "BTC"
    assert positions[0].quantity == Decimal("2")
    assert positions[0].average_price == Decimal("100")


def test_buy_by_total_value():
    account = Account(balances={"USD": Decimal("10000")})
    positions: list[Position] = []
    executor = MockExecutor()

    executor.execute(
        [make_order(OrderSide.BUY, total_value="1000")],
        account,
        positions,
        {"BTC": make_candle("100")},
    )

    assert account.balances["USD"] == Decimal("9000")
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("10")
    assert positions[0].average_price == Decimal("100")


def test_second_buy_merges_and_updates_average():
    account = Account(balances={"USD": Decimal("10000")})
    positions: list[Position] = []
    executor = MockExecutor()

    executor.execute(
        [make_order(OrderSide.BUY, quantity="1")],
        account,
        positions,
        {"BTC": make_candle("100")},
    )
    executor.execute(
        [make_order(OrderSide.BUY, quantity="1")],
        account,
        positions,
        {"BTC": make_candle("200")},
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
        [make_order(OrderSide.SELL, quantity="1")],
        account,
        positions,
        {"BTC": make_candle("150")},
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
        [make_order(OrderSide.SELL, quantity="2")],
        account,
        positions,
        {"BTC": make_candle("150")},
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
            [make_order(OrderSide.SELL, quantity="2")],
            account,
            positions,
            {"BTC": make_candle("150")},
        )


def test_sell_unknown_ticker_raises():
    account = Account(balances={"USD": Decimal("0")})
    positions: list[Position] = []
    executor = MockExecutor()

    with pytest.raises(ValueError, match="Not enough quantity"):
        executor.execute(
            [make_order(OrderSide.SELL, quantity="1")],
            account,
            positions,
            {"BTC": make_candle("150")},
        )


def test_buy_insufficient_balance_raises():
    account = Account(balances={"USD": Decimal("50")})
    positions: list[Position] = []
    executor = MockExecutor()

    with pytest.raises(ValueError, match="Not enough balance"):
        executor.execute(
            [make_order(OrderSide.BUY, quantity="1")],
            account,
            positions,
            {"BTC": make_candle("100")},
        )


def test_positions_for_different_tickers_stay_separate():
    account = Account(balances={"USD": Decimal("10000")})
    positions: list[Position] = []
    executor = MockExecutor()

    executor.execute(
        [
            make_order(OrderSide.BUY, quantity="1", ticker="BTC"),
            make_order(OrderSide.BUY, quantity="2", ticker="ETH"),
        ],
        account,
        positions,
        {
            "BTC": make_candle("100", ticker="BTC"),
            "ETH": make_candle("50", ticker="ETH"),
        },
    )

    assert len(positions) == 2
    by_ticker = {position.ticker: position for position in positions}
    assert by_ticker["BTC"].quantity == Decimal("1")
    assert by_ticker["BTC"].average_price == Decimal("100")
    assert by_ticker["ETH"].quantity == Decimal("2")
    assert by_ticker["ETH"].average_price == Decimal("50")


def test_market_fill_uses_candle_close():
    account = Account(balances={"USD": Decimal("1000")})
    positions: list[Position] = []
    executor = MockExecutor()
    candle = Candle(
        time=datetime(2021, 1, 1),
        ticker="BTC",
        open=Decimal("90"),
        high=Decimal("110"),
        low=Decimal("80"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )

    executor.execute(
        [make_order(OrderSide.BUY, quantity="1")],
        account,
        positions,
        {"BTC": candle},
    )

    assert positions[0].average_price == Decimal("100")
    assert account.balances["USD"] == Decimal("900")


def test_market_total_value_sized_at_close_not_open():
    account = Account(balances={"USD": Decimal("1000")})
    positions: list[Position] = []
    executor = MockExecutor()
    candle = Candle(
        time=datetime(2021, 1, 1),
        ticker="BTC",
        open=Decimal("50"),
        high=Decimal("120"),
        low=Decimal("40"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )

    executor.execute(
        [make_order(OrderSide.BUY, total_value="1000")],
        account,
        positions,
        {"BTC": candle},
    )

    assert positions[0].quantity == Decimal("10")
    assert positions[0].average_price == Decimal("100")
    assert account.balances["USD"] == Decimal("0")


def make_ohlc_candle(
    *,
    open_: str,
    high: str,
    low: str,
    close: str,
    ticker: str = "BTC",
) -> Candle:
    return Candle(
        time=datetime(2021, 1, 1),
        ticker=ticker,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1"),
    )


def test_limit_buy_fills_at_limit_price_when_low_touches():
    account = Account(balances={"USD": Decimal("1000")})
    positions: list[Position] = []
    executor = MockExecutor()
    order = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        price=Decimal("90"),
    )

    executor.execute(
        [order],
        account,
        positions,
        {"BTC": make_ohlc_candle(open_="100", high="110", low="85", close="105")},
    )

    assert positions[0].average_price == Decimal("90")
    assert account.balances["USD"] == Decimal("910")


def test_limit_buy_does_not_fill_when_low_stays_above():
    account = Account(balances={"USD": Decimal("1000")})
    positions: list[Position] = []
    executor = MockExecutor()
    order = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        price=Decimal("90"),
    )

    executor.execute(
        [order],
        account,
        positions,
        {"BTC": make_ohlc_candle(open_="100", high="110", low="95", close="105")},
    )

    assert positions == []
    assert account.balances["USD"] == Decimal("1000")


def test_limit_sell_fills_when_high_touches():
    account = Account(balances={"USD": Decimal("0")})
    positions = [
        Position(ticker="BTC", quantity=Decimal("1"), average_price=Decimal("80"))
    ]
    executor = MockExecutor()
    order = Order(
        ticker="BTC",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        price=Decimal("120"),
    )

    executor.execute(
        [order],
        account,
        positions,
        {"BTC": make_ohlc_candle(open_="100", high="125", low="95", close="110")},
    )

    assert positions == []
    assert account.balances["USD"] == Decimal("120")
