from datetime import datetime

import pandas as pd

from analysis.plotter import aggregate_journal_markers, flatten_journal
from engine.journal import EntryType


def _steps(*journals_by_day: list[dict]) -> pd.DataFrame:
    rows = []
    for index, journal in enumerate(journals_by_day):
        rows.append(
            {
                "time": datetime(2023, 1, 1 + index),
                "equity": 10000 + index,
                "journal": journal,
            }
        )
    return pd.DataFrame(rows)


def test_flatten_and_aggregate_keeps_single_entry_style():
    steps = _steps(
        [
            {
                "type": EntryType.DEPOSIT.value,
                "currency": "USD",
                "amount": "1000",
            }
        ]
    )
    frame = steps.copy()
    frame["time"] = pd.to_datetime(frame["time"])
    journal = flatten_journal(frame)
    markers = aggregate_journal_markers(journal, frame, "equity")

    assert len(markers) == 1
    assert markers[0]["style"]["name"] == "deposit"
    assert markers[0]["text"] == ""
    assert markers[0]["hover"] == "DEPOSIT 1000 USD"
    assert markers[0]["count"] == 1


def test_same_day_entries_collapse_to_one_events_marker():
    steps = _steps(
        [
            {
                "type": EntryType.DEPOSIT.value,
                "currency": "USD",
                "amount": "1000",
            },
            {
                "type": EntryType.INTEREST.value,
                "ticker": "USD",
                "amount": "40",
                "principal": "4000",
                "rate": "0.01",
            },
            {
                "type": EntryType.ORDER_FILLED.value,
                "side": "BUY",
                "quantity": "0.5",
                "price": "100",
                "order_id": "o1",
                "ticker": "BTC",
                "order_type": "MARKET",
            },
        ]
    )
    frame = steps.copy()
    frame["time"] = pd.to_datetime(frame["time"])
    journal = flatten_journal(frame)
    markers = aggregate_journal_markers(journal, frame, "equity")

    assert len(markers) == 1
    marker = markers[0]
    assert marker["style"]["name"] == "events"
    assert marker["text"] == "3"
    assert marker["count"] == 3
    assert marker["y"] == 10000.0
    assert marker["hover"] == (
        "3 entries<br>DEPOSIT 1000 USD<br>INTEREST 40 USD<br>BUY BTC 0.5 @ 100"
    )


def test_different_days_stay_separate():
    steps = _steps(
        [{"type": EntryType.DEPOSIT.value, "currency": "USD", "amount": "1000"}],
        [{"type": EntryType.INTEREST.value, "ticker": "USD", "amount": "10"}],
    )
    frame = steps.copy()
    frame["time"] = pd.to_datetime(frame["time"])
    journal = flatten_journal(frame)
    markers = aggregate_journal_markers(journal, frame, "equity")

    assert len(markers) == 2
    assert markers[0]["style"]["name"] == "deposit"
    assert markers[1]["style"]["name"] == "interest"


def test_series_journal_customdata_only_on_event_days():
    from analysis.plotter import series_journal_customdata

    times = list(pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]))
    markers = [
        {
            "time": times[1],
            "y": 100.0,
            "style": {"name": "events"},
            "text": "2",
            "hover": "2 entries<br>DEPOSIT 1",
            "count": 2,
        }
    ]
    customdata = series_journal_customdata(times, markers)
    assert customdata == ["", "<br>2 entries<br>DEPOSIT 1", ""]


def test_hover_number_decimals():
    from analysis.plotter import _format_asset_amount, _format_number, _hover_line

    assert _format_asset_amount("1000.129", asset="USD") == "1000.13"
    assert _format_asset_amount("1000.10", asset="USD") == "1000.1"
    assert _format_asset_amount("0.123456", asset="BTC") == "0.1235"
    assert _format_number("25000.12345", max_decimals=4) == "25000.1235"

    fill = pd.Series(
        {
            "type": EntryType.ORDER_FILLED.value,
            "side": "BUY",
            "ticker": "BTC",
            "quantity": "0.123456789",
            "price": "25000.123456",
        }
    )
    assert _hover_line(fill) == "BUY BTC 0.1235 @ 25000.1235"

    interest = pd.Series(
        {
            "type": EntryType.INTEREST.value,
            "ticker": "USD",
            "amount": "40.129",
        }
    )
    assert _hover_line(interest) == "INTEREST 40.13 USD"
