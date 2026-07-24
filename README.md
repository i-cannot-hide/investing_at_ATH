# Investment Lab

**Simulate. Analyze. Invest.**

A Python lab for simulating investment strategies on historical market data, inspecting outcomes, and comparing results.

## What it does

- Run strategies bar-by-bar against OHLC candles (market and limit orders)
- Track cash, positions, open orders, and mark-to-market equity
- Save each outcome under `strat_runner/outcomes/` with a searchable registry
- Explore equity and prices in an interactive Plotly notebook

## Setup

Requires **Python 3.14+**.

```bash
source virt_env_314/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

## Run a simulation

From the repo root, with the venv active:

```bash
cd strat_runner
python main.py
```

Outcomes are written to `strat_runner/outcomes/` and indexed in `outcomes/registry.jsonl`.

## Explore results

```bash
cd strat_runner/analysis
jupyter lab explore.ipynb
```

The notebook loads the latest research batch (`load_research("hold-vs-buybelow")`) and plots every experiment side by side. You can still use `load_outcome(...)` filters (`strategy`, `assets`, `params`, `start_date`, `end_date`, `id`, `folder`, `research`, `name`) for a single outcome.

## Tests

From the repo root:

```bash
pytest -q
```

## Project layout

```
strat_runner/
  main.py              # sample simulation entrypoint
  models.py            # Candle, Order, Decision, Context, …
  engine/              # Environment, Experiment, Research, registry, recorder
  strategies/          # Hold, BuyBelow, …
  executors/           # MockExecutor fill logic
  data/                # loaders, downloaders, preprocessed CSVs
  analysis/            # explore.ipynb + plotter
  outcomes/            # simulation outputs + registry
  tests/
```

## Strategies

Strategies implement `decide(context) -> Decision | None`:

- **`DoNothingStrategy`** — keep USD idle; never places orders
- **`HoldStrategy`** — market-buy available USD when the ticker is present
- **`InvestEverythingStrategy`** — same as hold: market-buy all available USD
- **`BuyBelowStrategy`** — rest a limit buy at a target price

`Context` exposes history (past bars only), current open prices, account, positions, and open orders. Return `Decision(orders=..., cancel_order_ids=...)` or `None` for a no-op.

## Experiments

Pass an `Experiment` into `Environment` instead of a bare strategy:

```python
from engine import Experiment, MoneySpawner, SpawnInterval

Experiment(
    strategy=BuyBelowStrategy(target_price=20000, ticker="BTC"),
    money_spawner=MoneySpawner(
        currency="USD",
        amount=1000,
        interval=SpawnInterval.MONTH,
    ),
    name="buybelow+spawn",
)
```

The registry stores `name`, strategy metadata, and `money_spawner` config. Applied changes are logged on each step as a `journal` of typed `entries` (deposits, fills, cancellations, …).

## Research

Group experiments into a named research batch so they share one `research_id` and load together:

```python
from engine import Experiment, Research

Research(
    name="hold-vs-buybelow",
    experiments=[
        Experiment(strategy=HoldStrategy(ticker="BTC"), name="hold"),
        Experiment(strategy=BuyBelowStrategy(target_price=20000, ticker="BTC"), name="buybelow"),
    ],
).run(
    data_files,
    start_date="2023-01-01",
    end_date="2024-12-31",
    initial_usd=10_000,
)
```

`initial_usd` is shared across the batch (same idea as the date window). `latest_research_entries(outcomes_dir, "hold-vs-buybelow")` returns every outcome from the most recent run of that research.

## Backlog

- Money Burner
- Show more charts
- Show USD and positions separately
- Journal markers on charts (fills, deposits, …) — partially done
- Implement leverage
- Implement fees
