import csv
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from models import Candle


def load_candles(data_file: Path | str) -> list[Candle]:
    candles = []

    with open(data_file) as f:
        reader = csv.DictReader(f)

        for row in reader:
            candles.append(
                Candle(
                    time=datetime.fromisoformat(row["time"]),
                    ticker=row["ticker"],
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                    volume=Decimal(row["volume"]),
                )
            )

    return candles


def load_candles_many(data_files: list[Path | str]) -> list[Candle]:
    candles: list[Candle] = []
    for data_file in data_files:
        candles.extend(load_candles(data_file))
    return candles


def parse_date(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def filter_candles_by_date(
    candles: list[Candle],
    start_date: str | datetime | None = None,
    end_date: str | datetime | None = None,
) -> list[Candle]:
    start = parse_date(start_date)
    end = parse_date(end_date)

    filtered = []
    for candle in candles:
        candle_day = candle.time.date()
        if start is not None and candle_day < start.date():
            continue
        if end is not None and candle_day > end.date():
            continue
        filtered.append(candle)
    return filtered


def group_candles_by_time(candles: list[Candle]) -> dict[datetime, list[Candle]]:
    by_time: dict[datetime, list[Candle]] = defaultdict(list)
    for candle in candles:
        by_time[candle.time].append(candle)
    return dict(sorted(by_time.items()))
