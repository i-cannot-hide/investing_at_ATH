import json
import random
import string
from pathlib import Path


REGISTRY_NAME = "registry.jsonl"
ID_ALPHABET = string.ascii_lowercase + string.digits


def allocate_run_dir(runs_dir: Path, when=None) -> tuple[str, str, Path]:
    """Return (run_id, date_time, folder_path) with name `{date_time}_{id}`."""
    from datetime import datetime

    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    date_time = (when or datetime.now()).strftime("%y-%m-%d_%H-%M")
    existing = {path.name for path in runs_dir.iterdir() if path.is_dir()}
    existing |= {
        entry["folder"]
        for entry in load_registry(runs_dir)
        if "folder" in entry
    }

    for _ in range(1000):
        run_id = "".join(random.choices(ID_ALPHABET, k=2))
        folder_name = f"{date_time}_{run_id}"
        if folder_name not in existing:
            return run_id, date_time, runs_dir / folder_name

    raise RuntimeError("Could not allocate a unique 2-character run id")


def load_registry(runs_dir: Path) -> list[dict]:
    path = Path(runs_dir) / REGISTRY_NAME
    if not path.exists():
        return []

    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def register_run(runs_dir: Path, entry: dict) -> None:
    path = Path(runs_dir) / REGISTRY_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def strategy_assets(strategy) -> list[str]:
    if hasattr(strategy, "tickers"):
        return [str(ticker) for ticker in strategy.tickers]
    if hasattr(strategy, "ticker"):
        return [str(strategy.ticker)]
    return []


def strategy_params(strategy) -> dict:
    params = {}
    for key, value in vars(strategy).items():
        if key.startswith("_"):
            continue
        if key in {"ticker", "tickers"}:
            continue
        params[key] = str(value)
    return params
