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


def _normalize_assets(assets: str | list[str] | None) -> list[str] | None:
    if assets is None:
        return None
    if isinstance(assets, str):
        return [assets]
    return [str(asset) for asset in assets]


def find_entries(
    runs_dir: Path,
    *,
    strategy: str | None = None,
    id: str | None = None,
    folder: str | None = None,
    assets: str | list[str] | None = None,
    params: dict | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return registry entries matching any provided filters (all optional)."""
    wanted_assets = _normalize_assets(assets)
    matches = []

    for entry in load_registry(runs_dir):
        if strategy is not None and entry.get("strategy") != strategy:
            continue
        if id is not None and entry.get("id") != id:
            continue
        if folder is not None and entry.get("folder") != folder:
            continue
        if wanted_assets is not None and entry.get("assets") != wanted_assets:
            continue
        if start_date is not None and entry.get("start_date") != start_date:
            continue
        if end_date is not None and entry.get("end_date") != end_date:
            continue
        if params is not None:
            entry_params = {
                key: str(value) for key, value in entry.get("params", {}).items()
            }
            if any(entry_params.get(key) != str(value) for key, value in params.items()):
                continue
        matches.append(entry)

    return matches


def latest_entry(
    runs_dir: Path,
    *,
    strategy: str | None = None,
    id: str | None = None,
    folder: str | None = None,
    assets: str | list[str] | None = None,
    params: dict | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    matches = find_entries(
        runs_dir,
        strategy=strategy,
        id=id,
        folder=folder,
        assets=assets,
        params=params,
        start_date=start_date,
        end_date=end_date,
    )
    if not matches:
        raise FileNotFoundError(
            "No registry entries matched filters: "
            f"strategy={strategy!r}, id={id!r}, folder={folder!r}, "
            f"assets={assets!r}, params={params!r}, "
            f"start_date={start_date!r}, end_date={end_date!r}"
        )
    return matches[-1]


def steps_path(runs_dir: Path, entry: dict) -> Path:
    return Path(runs_dir) / entry["folder"] / "steps.jsonl"


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
