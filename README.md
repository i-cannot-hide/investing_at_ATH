# Investment Lab

**Simulate. Analyze. Invest.**

A Python lab for simulating investment strategies on historical market data, inspecting runs, and comparing results.

## What it does

- Run strategies bar-by-bar against OHLC candles (market and limit orders)
- Track cash, positions, open orders, and mark-to-market equity
- Save each run under `strat_runner/runs/` with a searchable registry
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

Runs are written to `strat_runner/runs/` and indexed in `runs/registry.jsonl`.

## Explore results

```bash
cd strat_runner/analysis
jupyter lab explore.ipynb
```

Use `load_run(...)` filters (`strategy`, `assets`, `params`, `start_date`, `end_date`, `id`, `folder`) to load the latest matching run, then plot with `plot_series`.

## Tests

From the repo root:

```bash
pytest -q
```

## Project layout

```
strat_runner/
  main.py              # sample simulation entrypoint
  environment.py       # bar loop: decide → cancel → fill → record
  models.py            # Candle, Order, Decision, Context, …
  strategies/          # Hold, BuyBelow, …
  executors/           # MockExecutor fill logic
  data/                # loaders, downloaders, preprocessed CSVs
  analysis/            # explore.ipynb + plotter
  runs/                # simulation outputs + registry
  tests/
```

## Strategies

Strategies implement `decide(context) -> Decision | None`:

- **`HoldStrategy`** — market-buy available USD when the ticker is present
- **`BuyBelowStrategy`** — rest a limit buy at a target price

`Context` exposes history (past bars only), current open prices, account, positions, and open orders. Return `Decision(orders=..., cancel_order_ids=...)` or `None` for a no-op.
