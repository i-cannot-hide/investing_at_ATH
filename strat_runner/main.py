from environment import Environment
from executors.mock_executor import MockExecutor
from strategies.buy_below import BuyBelowStrategy
from strategies.hold import HoldStrategy


strategies = [
    HoldStrategy(),
    BuyBelowStrategy(),
]

for strategy in strategies:
    environment = Environment(
        strategy,
        MockExecutor(),
        "data/preprocessed/btc.csv",
        full_debug_runs=True,
    )
    environment.run()
    print(f"Finished {type(strategy).__name__}")

print("Simulation finished")
