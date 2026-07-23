from pathlib import Path

import pytest

from engine import (
    Experiment,
    Research,
    latest_research_entries,
    latest_research_id,
    load_registry,
)
from models import Context


def write_btc_csv(path: Path, rows: list[tuple[str, str, str, str, str]]) -> None:
    lines = ["time,ticker,open,high,low,close,volume"]
    for time, open_, high, low, close in rows:
        lines.append(f"{time},BTC,{open_},{high},{low},{close},1")
    path.write_text("\n".join(lines) + "\n")


class NoOpStrategy:
    def decide(self, context: Context) -> None:
        return None


def test_allocate_research_id_format():
    from engine.outcome_registry import allocate_research_id

    research_id = allocate_research_id()
    assert "_" in research_id
    assert len(research_id.split("_")[-1]) == 4


def test_research_run_tags_outcomes(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [
            ("2023-01-01", "100", "110", "90", "105"),
            ("2023-01-02", "105", "110", "100", "108"),
        ],
    )
    outcomes_dir = tmp_path / "outcomes"
    research = Research(
        name="demo",
        experiments=[
            Experiment(strategy=NoOpStrategy(), name="a"),
            Experiment(strategy=NoOpStrategy(), name="b"),
        ],
    )

    research_id = research.run(
        [str(csv_path)],
        outcomes_dir=outcomes_dir,
    )

    entries = load_registry(outcomes_dir)
    assert len(entries) == 2
    assert {entry["name"] for entry in entries} == {"a", "b"}
    assert all(entry["research"] == "demo" for entry in entries)
    assert all(entry["research_id"] == research_id for entry in entries)

    batch = latest_research_entries(outcomes_dir, "demo")
    assert len(batch) == 2
    assert latest_research_id(outcomes_dir, "demo") == research_id


def test_latest_research_picks_newest_batch(tmp_path: Path):
    csv_path = tmp_path / "btc.csv"
    write_btc_csv(
        csv_path,
        [("2023-01-01", "100", "110", "90", "105")],
    )
    outcomes_dir = tmp_path / "outcomes"

    first = Research(
        name="demo",
        experiments=[Experiment(strategy=NoOpStrategy(), name="old")],
    )
    first_id = first.run([str(csv_path)], outcomes_dir=outcomes_dir)

    second = Research(
        name="demo",
        experiments=[
            Experiment(strategy=NoOpStrategy(), name="new-a"),
            Experiment(strategy=NoOpStrategy(), name="new-b"),
        ],
    )
    second_id = second.run([str(csv_path)], outcomes_dir=outcomes_dir)

    assert first_id != second_id
    batch = latest_research_entries(outcomes_dir, "demo")
    assert latest_research_id(outcomes_dir, "demo") == second_id
    assert {entry["name"] for entry in batch} == {"new-a", "new-b"}


def test_research_requires_experiments():
    research = Research(name="empty", experiments=[])
    with pytest.raises(ValueError, match="at least one"):
        research.run(["unused.csv"])
