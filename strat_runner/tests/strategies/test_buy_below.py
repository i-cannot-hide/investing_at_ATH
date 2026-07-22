from datetime import datetime
from decimal import Decimal

from models import Account, Candle, Context, OrderSide, OrderType
from strategies.buy_below import BuyBelowStrategy, MIN_USD


def make_candle(ticker: str, close: str, time: datetime | None = None) -> Candle:
    price = Decimal(close)
    return Candle(
        time=time or datetime(2021, 1, 1),
        ticker=ticker,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1"),
    )


def make_context(
    *,
    usd="10000",
    open_price="19000",
    history: dict[str, list[Candle]] | bool = True,
    open_prices: dict[str, Decimal] | None = None,
):
    if open_prices is not None:
        price_map = open_prices
    elif history is False:
        price_map = {}
    else:
        price_map = {"BTC": Decimal(str(open_price))}

    if history is True:
        history_map: dict[str, list[Candle]] = {}
    elif history is False:
        history_map = {}
    else:
        history_map = history

    return Context(
        time=datetime(2021, 1, 1),
        history=history_map,
        current_open_prices=price_map,
        account=Account(balances={"USD": Decimal(usd)}),
        positions=[],
    )


def test_default_target_is_20000():
    strategy = BuyBelowStrategy()

    assert strategy.target_price == Decimal("20000")


def test_buys_when_price_under_target():
    strategy = BuyBelowStrategy(target_price=20000)
    orders = strategy.decide(make_context(usd="10000", open_price="19000"))

    assert len(orders) == 1
    order = orders[0]
    assert order.ticker == "BTC"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.quantity is None
    assert order.total_value == Decimal("10000")


def test_skips_when_price_equals_target():
    strategy = BuyBelowStrategy(target_price=20000)

    assert strategy.decide(make_context(open_price="20000")) == []


def test_skips_when_price_above_target():
    strategy = BuyBelowStrategy(target_price=20000)

    assert strategy.decide(make_context(open_price="21000")) == []


def test_respects_custom_target():
    strategy = BuyBelowStrategy(target_price=30000)

    assert strategy.decide(make_context(open_price="29000")) != []
    assert strategy.decide(make_context(open_price="30000")) == []


def test_skips_when_usd_below_minimum():
    strategy = BuyBelowStrategy()
    just_below = MIN_USD - Decimal("0.01")

    assert strategy.decide(make_context(usd=str(just_below), open_price="19000")) == []


def test_buys_when_usd_equals_minimum():
    strategy = BuyBelowStrategy(target_price=20000)
    orders = strategy.decide(make_context(usd=str(MIN_USD), open_price="100"))

    assert len(orders) == 1
    assert orders[0].quantity is None
    assert orders[0].total_value == MIN_USD


def test_skips_when_no_open_price():
    strategy = BuyBelowStrategy()

    assert strategy.decide(make_context(history=False)) == []


def test_skips_when_open_price_missing_for_ticker():
    strategy = BuyBelowStrategy()
    context = make_context(open_prices={"ETH": Decimal("1000")})

    assert strategy.decide(context) == []


def test_buys_configured_ticker():
    strategy = BuyBelowStrategy(target_price=3000, ticker="ETH")
    context = make_context(
        usd="1000",
        open_prices={"BTC": Decimal("25000"), "ETH": Decimal("2000")},
    )

    orders = strategy.decide(context)

    assert len(orders) == 1
    assert orders[0].ticker == "ETH"
    assert orders[0].quantity is None
    assert orders[0].total_value == Decimal("1000")


def test_skips_when_price_is_zero():
    strategy = BuyBelowStrategy()

    assert strategy.decide(make_context(open_price="0")) == []


def test_skips_when_price_is_negative():
    strategy = BuyBelowStrategy()

    assert strategy.decide(make_context(open_price="-1")) == []


def test_uses_open_price_not_history_close():
    strategy = BuyBelowStrategy(target_price=20000)
    context = make_context(
        usd="1000",
        open_price="18000",
        history={
            "BTC": [
                make_candle("BTC", "25000", datetime(2021, 1, 1)),
            ],
        },
    )

    orders = strategy.decide(context)

    assert len(orders) == 1
    assert orders[0].quantity is None
    assert orders[0].total_value == Decimal("1000")
