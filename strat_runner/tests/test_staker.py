from datetime import datetime
from decimal import Decimal

import pytest

from engine import SpawnInterval, Staker
from models import Account, Position


def test_rejects_empty_ticker():
    with pytest.raises(ValueError, match="ticker"):
        Staker(ticker="", rate="0.01", interval=SpawnInterval.MONTH)


def test_rejects_negative_rate():
    with pytest.raises(ValueError, match="non-negative"):
        Staker(ticker="USD", rate="-0.01", interval=SpawnInterval.MONTH)


def test_rejects_non_enum_interval():
    with pytest.raises(TypeError, match="SpawnInterval"):
        Staker(ticker="USD", rate="0.01", interval="1M")  # type: ignore[arg-type]


def test_available_uses_cash_balance_and_free_position():
    staker_usd = Staker(ticker="USD", rate="0.01", interval=SpawnInterval.MONTH)
    staker_btc = Staker(ticker="BTC", rate="0.01", interval=SpawnInterval.MONTH)
    account = Account(balances={"USD": Decimal("500")})
    positions = [
        Position(ticker="BTC", quantity=Decimal("2"), average_price=Decimal("100"))
    ]

    assert staker_usd.available(account, positions) == Decimal("500")
    assert staker_btc.available(account, positions) == Decimal("2")
    assert (
        Staker(ticker="ETH", rate="0.01", interval=SpawnInterval.MONTH).available(
            account, positions
        )
        == Decimal("0")
    )


def test_tracks_period_minimum_and_pays_on_roll():
    account = Account(balances={"USD": Decimal("1000")})
    staker = Staker(ticker="USD", rate="0.10", interval=SpawnInterval.MONTH)

    assert staker.settle_if_period_changed(datetime(2023, 1, 1), account, []) is None
    staker.observe(account, [])

    account.balances["USD"] = Decimal("400")
    staker.observe(account, [])
    account.balances["USD"] = Decimal("800")
    staker.observe(account, [])

    payment = staker.settle_if_period_changed(datetime(2023, 2, 1), account, [])
    assert payment == (Decimal("40"), Decimal("400"))
    assert account.balances["USD"] == Decimal("840")


def test_settle_final_pays_open_period():
    account = Account(balances={"USD": Decimal("1000")})
    staker = Staker(ticker="USD", rate="0.05", interval=SpawnInterval.MONTH)

    staker.settle_if_period_changed(datetime(2023, 1, 1), account, [])
    staker.observe(account, [])
    payment = staker.settle_final(account, [])

    assert payment == (Decimal("50"), Decimal("1000"))
    assert account.balances["USD"] == Decimal("1050")


def test_coin_interest_dilutes_average_price():
    account = Account(balances={"USD": Decimal("0")})
    positions = [
        Position(ticker="BTC", quantity=Decimal("1"), average_price=Decimal("100"))
    ]
    staker = Staker(ticker="BTC", rate="0.10", interval=SpawnInterval.MONTH)

    staker.settle_if_period_changed(datetime(2023, 1, 1), account, positions)
    staker.observe(account, positions)
    payment = staker.settle_final(account, positions)

    assert payment == (Decimal("0.1"), Decimal("1"))
    assert positions[0].quantity == Decimal("1.1")
    assert positions[0].average_price == Decimal("100") / Decimal("1.1")


def test_zero_rate_or_zero_principal_pays_nothing():
    account = Account(balances={"USD": Decimal("1000")})
    staker = Staker(ticker="USD", rate="0", interval=SpawnInterval.DAY)
    staker.settle_if_period_changed(datetime(2023, 1, 1), account, [])
    staker.observe(account, [])
    assert staker.settle_final(account, []) is None
    assert account.balances["USD"] == Decimal("1000")
