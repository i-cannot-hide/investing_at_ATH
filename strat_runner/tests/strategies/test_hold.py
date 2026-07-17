from datetime import datetime
from decimal import Decimal

from models import Account, Candle, Context, OrderSide, OrderType
from strategies.hold import HoldStrategy, MIN_USD


def make_context(*, usd="10000", close="25000", candles=True):
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


def test_buys_all_available_usd():
    strategy = HoldStrategy()
    orders = strategy.decide(make_context(usd="10000", close="25000"))

    assert len(orders) == 1
    order = orders[0]
    assert order.ticker == "BTC"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.quantity == Decimal("10000") / Decimal("25000")


def test_skips_when_usd_below_minimum():
    strategy = HoldStrategy()
    just_below = MIN_USD - Decimal("0.01")

    assert strategy.decide(make_context(usd=str(just_below))) == []


def test_buys_when_usd_equals_minimum():
    strategy = HoldStrategy()
    orders = strategy.decide(make_context(usd=str(MIN_USD), close="100"))

    assert len(orders) == 1
    assert orders[0].quantity == MIN_USD / Decimal("100")


def test_skips_when_no_candles():
    strategy = HoldStrategy()

    assert strategy.decide(make_context(candles=False)) == []


def test_skips_when_price_is_zero():
    strategy = HoldStrategy()

    assert strategy.decide(make_context(close="0")) == []


def test_skips_when_price_is_negative():
    strategy = HoldStrategy()

    assert strategy.decide(make_context(close="-1")) == []


def test_uses_latest_candle_close():
    strategy = HoldStrategy()
    older = Candle(
        time=datetime(2021, 1, 1),
        ticker="BTC",
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )
    newer = Candle(
        time=datetime(2021, 1, 2),
        ticker="BTC",
        open=Decimal("200"),
        high=Decimal("200"),
        low=Decimal("200"),
        close=Decimal("200"),
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
    assert orders[0].quantity == Decimal("1000") / Decimal("200")
