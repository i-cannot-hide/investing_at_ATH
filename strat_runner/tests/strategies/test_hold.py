from datetime import datetime
from decimal import Decimal

from models import Account, Candle, Context, OrderSide, OrderType
from strategies.hold import HoldStrategy, MIN_USD


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
    close="25000",
    candles: dict[str, list[Candle]] | bool = True,
):
    if candles is True:
        candle_map = {"BTC": [make_candle("BTC", close)]}
    elif candles is False:
        candle_map = {}
    else:
        candle_map = candles

    time = next(
        (candle.time for series in candle_map.values() for candle in series),
        datetime(2021, 1, 1),
    )
    return Context(
        time=time,
        candles=candle_map,
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


def test_skips_when_no_btc_candles():
    strategy = HoldStrategy()
    context = make_context(
        candles={"ETH": [make_candle("ETH", "2000")]},
    )

    assert strategy.decide(context) == []


def test_skips_when_price_is_zero():
    strategy = HoldStrategy()

    assert strategy.decide(make_context(close="0")) == []


def test_skips_when_price_is_negative():
    strategy = HoldStrategy()

    assert strategy.decide(make_context(close="-1")) == []


def test_uses_latest_btc_close():
    strategy = HoldStrategy()
    context = make_context(
        usd="1000",
        candles={
            "BTC": [
                make_candle("BTC", "100", datetime(2021, 1, 1)),
                make_candle("BTC", "200", datetime(2021, 1, 2)),
            ],
            "ETH": [
                make_candle("ETH", "3000", datetime(2021, 1, 2)),
            ],
        },
    )

    orders = strategy.decide(context)

    assert len(orders) == 1
    assert orders[0].quantity == Decimal("1000") / Decimal("200")


def test_ignores_other_assets_when_buying_btc():
    strategy = HoldStrategy()
    context = make_context(
        usd="10000",
        candles={
            "BTC": [make_candle("BTC", "25000")],
            "ETH": [make_candle("ETH", "1")],
        },
    )

    orders = strategy.decide(context)

    assert len(orders) == 1
    assert orders[0].ticker == "BTC"
    assert orders[0].quantity == Decimal("10000") / Decimal("25000")
