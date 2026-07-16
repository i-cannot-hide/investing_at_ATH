## Backtesting scaffold (Python 3.14)

This folder is a starter scaffold for backtesting simple financial strategies.

### Quickstart

Activate your existing venv:

```bash
source virt_env_314/bin/activate
```

Install dependencies:

```bash
python -m pip install -U pip
python -m pip install -r requirements.txt
```

Run tests:

```bash
pytest -q
```

Run a sample backtest:

```bash
python -m backtest314.scripts.run_backtest
```

Open the notebook:

```bash
python -m ipykernel install --user --name virt_env_314 --display-name "Python (virt_env_314)"
jupyter lab
```

