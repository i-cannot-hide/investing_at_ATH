from pathlib import Path

from engine import Experiment, MoneySpawner, Research, SpawnInterval
from strategies.do_nothing import DoNothingStrategy
from strategies.hold import HoldStrategy
from strategies.invest_everything import InvestEverythingStrategy
from strategies.buy_below import BuyBelowStrategy


research = Research(
    name="hold-vs-buybelow",
    experiments=[
        Experiment(
            strategy=DoNothingStrategy(),
            name="do-nothing",
        ),
        Experiment(
            strategy=DoNothingStrategy(),
            name="do-nothing_with_salary",
            money_spawner=MoneySpawner(
                currency="USD",
                amount=1000,
                interval=SpawnInterval.MONTH,
            ),
        ),
        Experiment(
            strategy=HoldStrategy(ticker="BTC"),
            name="hold",
        ),
        Experiment(
            strategy=InvestEverythingStrategy(ticker="BTC"),
            name="invest_everything",
        ),

        Experiment(
            strategy=InvestEverythingStrategy(ticker="BTC"),
            name="invest_everything+spawn",
            money_spawner=MoneySpawner(
                currency="USD",
                amount=1000,
                interval=SpawnInterval.MONTH,
            ),
        ),
        Experiment(
            strategy=BuyBelowStrategy(target_price=20000, ticker="BTC"),
            name="buybelow",
        ),
        Experiment(
            strategy=BuyBelowStrategy(target_price=20000, ticker="BTC"),
            money_spawner=MoneySpawner(
                currency="USD",
                amount=1000,
                interval=SpawnInterval.MONTH,
            ),
            name="buybelow+spawn",
        ),
    ],
)

data_dir = Path(__file__).parent / "data" / "preprocessed"
data_files = sorted(str(path.relative_to(Path(__file__).parent)) for path in data_dir.glob("*.csv"))

if not data_files:
    raise FileNotFoundError(f"No CSV files found in {data_dir}")

research_id = research.run(
    data_files,
    full_debug_outcomes=False,
    start_date="2021-02-20",
    end_date="2024-12-31",
    initial_usd=10_000,
)
print(f"Research finished: {research.name} ({research_id})")
