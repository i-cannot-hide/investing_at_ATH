from pathlib import Path

from environment import Environment
from executors.mock_executor import MockExecutor
from strategies.buy_below import BuyBelowStrategy
from strategies.hold import HoldStrategy


strategies = [
    HoldStrategy(),
    BuyBelowStrategy(),
]

data_dir = Path(__file__).parent / "data" / "preprocessed"
data_files = sorted(str(path.relative_to(Path(__file__).parent)) for path in data_dir.glob("*.csv"))

if not data_files:
    raise FileNotFoundError(f"No CSV files found in {data_dir}")

for strategy in strategies:
    environment = Environment(
        strategy,
        MockExecutor(),
        data_files,
        full_debug_runs=False,
    )
    environment.run()
    print(f"Finished {type(strategy).__name__}")

print("Simulation finished")
