from datetime import datetime
from decimal import Decimal

from data.loader import filter_candles_by_date
from models import Candle


def make_candle(day: str, ticker: str = "BTC") -> Candle:
    return Candle(
        time=datetime.fromisoformat(day),
        ticker=ticker,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
    )


def test_filter_keeps_inclusive_range():
    candles = [
        make_candle("2021-01-01"),
        make_candle("2021-01-02"),
        make_candle("2021-01-03"),
        make_candle("2021-01-04"),
    ]

    filtered = filter_candles_by_date(
        candles,
        start_date="2021-01-02",
        end_date="2021-01-03",
    )

    assert [c.time.date().isoformat() for c in filtered] == [
        "2021-01-02",
        "2021-01-03",
    ]


def test_filter_start_only():
    candles = [
        make_candle("2021-01-01"),
        make_candle("2021-01-02"),
        make_candle("2021-01-03"),
    ]

    filtered = filter_candles_by_date(candles, start_date="2021-01-02")

    assert [c.time.date().isoformat() for c in filtered] == [
        "2021-01-02",
        "2021-01-03",
    ]


def test_filter_end_only():
    candles = [
        make_candle("2021-01-01"),
        make_candle("2021-01-02"),
        make_candle("2021-01-03"),
    ]

    filtered = filter_candles_by_date(candles, end_date="2021-01-02")

    assert [c.time.date().isoformat() for c in filtered] == [
        "2021-01-01",
        "2021-01-02",
    ]


def test_filter_none_returns_all():
    candles = [make_candle("2021-01-01"), make_candle("2021-01-02")]

    assert filter_candles_by_date(candles) == candles
