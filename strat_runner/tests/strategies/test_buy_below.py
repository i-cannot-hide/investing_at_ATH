from datetime import datetime
from decimal import Decimal

from models import Account, Candle, Context, OrderSide, OrderType
from strategies.buy_below import BuyBelowStrategy, MIN_USD


def make_context(*, usd="10000", close="19000", candles=True):
    candle = Candle(
        time=datetime(2021, 1, 1),
        ticker="BTC",
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("1"),
    )
    return Context(
        time=candle.time,
        candles=[candle] if candles else [],
        account=Account(balances={"USD": Decimal(usd)}),
        positions=[],
    )


def test_default_target_is_20000():
    strategy = BuyBelowStrategy()

    assert strategy.target_price == Decimal("20000")


def test_buys_when_price_under_target():
    strategy = BuyBelowStrategy(target_price=20000)
    orders = strategy.decide(make_context(usd="10000", close="19000"))

    assert len(orders) == 1
    order = orders[0]
    assert order.ticker == "BTC"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.quantity == Decimal("10000") / Decimal("19000")


def test_skips_when_price_equals_target():
    strategy = BuyBelowStrategy(target_price=20000)

    assert strategy.decide(make_context(close="20000")) == []


def test_skips_when_price_above_target():
    strategy = BuyBelowStrategy(target_price=20000)

    assert strategy.decide(make_context(close="21000")) == []


def test_respects_custom_target():
    strategy = BuyBelowStrategy(target_price=30000)

    assert strategy.decide(make_context(close="29000")) != []
    assert strategy.decide(make_context(close="30000")) == []


def test_skips_when_usd_below_minimum():
    strategy = BuyBelowStrategy()
    just_below = MIN_USD - Decimal("0.01")

    assert strategy.decide(make_context(usd=str(just_below), close="19000")) == []


def test_buys_when_usd_equals_minimum():
    strategy = BuyBelowStrategy(target_price=20000)
    orders = strategy.decide(make_context(usd=str(MIN_USD), close="100"))

    assert len(orders) == 1
    assert orders[0].quantity == MIN_USD / Decimal("100")


def test_skips_when_no_candles():
    strategy = BuyBelowStrategy()

    assert strategy.decide(make_context(candles=False)) == []


def test_skips_when_price_is_zero():
    strategy = BuyBelowStrategy()

    assert strategy.decide(make_context(close="0")) == []


def test_skips_when_price_is_negative():
    strategy = BuyBelowStrategy()

    assert strategy.decide(make_context(close="-1")) == []


def test_uses_latest_candle_close():
    strategy = BuyBelowStrategy(target_price=20000)
    older = Candle(
        time=datetime(2021, 1, 1),
        ticker="BTC",
        open=Decimal("25000"),
        high=Decimal("25000"),
        low=Decimal("25000"),
        close=Decimal("25000"),
        volume=Decimal("1"),
    )
    newer = Candle(
        time=datetime(2021, 1, 2),
        ticker="BTC",
        open=Decimal("18000"),
        high=Decimal("18000"),
        low=Decimal("18000"),
        close=Decimal("18000"),
        volume=Decimal("1"),
    )
    context = Context(
        time=newer.time,
        candles=[older, newer],
        account=Account(balances={"USD": Decimal("1000")}),
        positions=[],
    )

    orders = strategy.decide(context)

    assert len(orders) == 1
    assert orders[0].quantity == Decimal("1000") / Decimal("18000")
