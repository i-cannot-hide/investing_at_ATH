from datetime import datetime
from decimal import Decimal

from models import Account, Candle, Context, Order, OrderSide, OrderType
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
    open_price="25000",
    history: dict[str, list[Candle]] | bool = True,
    open_prices: dict[str, Decimal] | None = None,
    open_orders: list[Order] | None = None,
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
        open_orders=open_orders or [],
    )


def test_default_target_is_20000():
    strategy = BuyBelowStrategy()

    assert strategy.target_price == Decimal("20000")


def test_places_limit_buy_at_target_price():
    strategy = BuyBelowStrategy(target_price=20000)
    decision = strategy.decide(make_context(usd="10000", open_price="25000"))

    assert len(decision.orders) == 1
    order = decision.orders[0]
    assert order.ticker == "BTC"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.LIMIT
    assert order.price == Decimal("20000")
    assert order.quantity == Decimal("10000") / Decimal("20000")
    assert order.total_value is None


def test_respects_custom_target():
    strategy = BuyBelowStrategy(target_price=30000)
    decision = strategy.decide(make_context(open_price="40000"))

    assert decision.orders[0].price == Decimal("30000")
    assert decision.orders[0].quantity == Decimal("10000") / Decimal("30000")


def test_skips_when_usd_below_minimum():
    strategy = BuyBelowStrategy()
    just_below = MIN_USD - Decimal("0.01")

    assert strategy.decide(make_context(usd=str(just_below))) is None


def test_buys_when_usd_equals_minimum():
    strategy = BuyBelowStrategy(target_price=20000)
    decision = strategy.decide(make_context(usd=str(MIN_USD), open_price="25000"))

    assert len(decision.orders) == 1
    assert decision.orders[0].order_type == OrderType.LIMIT
    assert decision.orders[0].price == Decimal("20000")
    assert decision.orders[0].quantity == MIN_USD / Decimal("20000")
    assert decision.orders[0].total_value is None


def test_skips_when_no_open_price():
    strategy = BuyBelowStrategy()

    assert strategy.decide(make_context(history=False)) is None


def test_skips_when_open_price_missing_for_ticker():
    strategy = BuyBelowStrategy()
    context = make_context(open_prices={"ETH": Decimal("1000")})

    assert strategy.decide(context) is None


def test_skips_when_open_order_already_exists_for_ticker():
    strategy = BuyBelowStrategy(target_price=20000)
    existing = Order(
        ticker="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.5"),
        price=Decimal("20000"),
    )
    context = make_context(open_orders=[existing])

    assert strategy.decide(context) is None


def test_buys_configured_ticker():
    strategy = BuyBelowStrategy(target_price=3000, ticker="ETH")
    context = make_context(
        usd="1000",
        open_prices={"BTC": Decimal("25000"), "ETH": Decimal("2000")},
    )

    decision = strategy.decide(context)

    assert len(decision.orders) == 1
    assert decision.orders[0].ticker == "ETH"
    assert decision.orders[0].order_type == OrderType.LIMIT
    assert decision.orders[0].price == Decimal("3000")
    assert decision.orders[0].quantity == Decimal("1000") / Decimal("3000")
    assert decision.orders[0].total_value is None


def test_does_not_need_history_to_place():
    strategy = BuyBelowStrategy(target_price=20000)
    context = make_context(
        usd="1000",
        open_price="25000",
        history={},
    )

    decision = strategy.decide(context)

    assert len(decision.orders) == 1
    assert decision.orders[0].price == Decimal("20000")
    assert decision.orders[0].quantity == Decimal("1000") / Decimal("20000")
    assert decision.orders[0].total_value is None
