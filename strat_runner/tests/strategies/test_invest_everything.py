from datetime import datetime
from decimal import Decimal

from models import Account, Candle, Context, OrderSide, OrderType
from strategies.invest_everything import InvestEverythingStrategy, MIN_USD


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


def test_buys_all_available_usd_as_total_value():
    strategy = InvestEverythingStrategy()
    decision = strategy.decide(make_context(usd="10000", open_price="25000"))

    assert len(decision.orders) == 1
    order = decision.orders[0]
    assert order.ticker == "BTC"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.total_value == Decimal("10000")
    assert order.quantity is None


def test_skips_when_usd_below_minimum():
    strategy = InvestEverythingStrategy()
    just_below = MIN_USD - Decimal("0.01")

    assert strategy.decide(make_context(usd=str(just_below))) is None


def test_buys_when_usd_equals_minimum():
    strategy = InvestEverythingStrategy()
    decision = strategy.decide(make_context(usd=str(MIN_USD), open_price="100"))

    assert len(decision.orders) == 1
    assert decision.orders[0].total_value == MIN_USD
    assert decision.orders[0].quantity is None


def test_skips_when_no_open_price():
    strategy = InvestEverythingStrategy()

    assert strategy.decide(make_context(history=False)) is None


def test_skips_when_open_price_missing_for_ticker():
    strategy = InvestEverythingStrategy()
    context = make_context(open_prices={"ETH": Decimal("2000")})

    assert strategy.decide(context) is None


def test_buys_configured_ticker():
    strategy = InvestEverythingStrategy(ticker="ETH")
    context = make_context(
        usd="1000",
        open_prices={"BTC": Decimal("25000"), "ETH": Decimal("2000")},
    )

    decision = strategy.decide(context)

    assert len(decision.orders) == 1
    assert decision.orders[0].ticker == "ETH"
    assert decision.orders[0].total_value == Decimal("1000")
    assert decision.orders[0].quantity is None


def test_skips_when_price_is_zero():
    strategy = InvestEverythingStrategy()

    assert strategy.decide(make_context(open_price="0")) is None


def test_skips_when_price_is_negative():
    strategy = InvestEverythingStrategy()

    assert strategy.decide(make_context(open_price="-1")) is None


def test_does_not_need_history_to_buy():
    strategy = InvestEverythingStrategy()
    context = make_context(
        usd="1000",
        open_price="200",
        history={},
    )

    decision = strategy.decide(context)

    assert len(decision.orders) == 1
    assert decision.orders[0].total_value == Decimal("1000")


def test_ignores_other_assets_when_buying_btc():
    strategy = InvestEverythingStrategy()
    context = make_context(
        usd="10000",
        open_prices={"BTC": Decimal("25000"), "ETH": Decimal("1")},
    )

    decision = strategy.decide(context)

    assert len(decision.orders) == 1
    assert decision.orders[0].ticker == "BTC"
    assert decision.orders[0].total_value == Decimal("10000")
