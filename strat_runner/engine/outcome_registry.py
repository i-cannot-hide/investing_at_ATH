import json
import random
import string
from pathlib import Path


REGISTRY_NAME = "registry.jsonl"
ID_ALPHABET = string.ascii_lowercase + string.digits


def allocate_outcome_dir(outcomes_dir: Path, when=None) -> tuple[str, str, Path]:
    """Return (outcome_id, date_time, folder_path) with name `{date_time}_{id}`."""
    from datetime import datetime

    outcomes_dir = Path(outcomes_dir)
    outcomes_dir.mkdir(parents=True, exist_ok=True)

    date_time = (when or datetime.now()).strftime("%y-%m-%d_%H-%M")
    existing = {path.name for path in outcomes_dir.iterdir() if path.is_dir()}
    existing |= {
        entry["folder"]
        for entry in load_registry(outcomes_dir)
        if "folder" in entry
    }

    for _ in range(1000):
        outcome_id = "".join(random.choices(ID_ALPHABET, k=2))
        folder_name = f"{date_time}_{outcome_id}"
        if folder_name not in existing:
            return outcome_id, date_time, outcomes_dir / folder_name

    raise RuntimeError("Could not allocate a unique 2-character outcome id")


def allocate_research_id(when=None) -> str:
    """Return a unique id for one research batch (`{date_time}_{4chars}`)."""
    from datetime import datetime

    date_time = (when or datetime.now()).strftime("%y-%m-%d_%H-%M")
    suffix = "".join(random.choices(ID_ALPHABET, k=4))
    return f"{date_time}_{suffix}"


def load_registry(outcomes_dir: Path) -> list[dict]:
    path = Path(outcomes_dir) / REGISTRY_NAME
    if not path.exists():
        return []

    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def register_outcome(outcomes_dir: Path, entry: dict) -> None:
    path = Path(outcomes_dir) / REGISTRY_NAME
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
    outcomes_dir: Path,
    *,
    strategy: str | None = None,
    id: str | None = None,
    folder: str | None = None,
    assets: str | list[str] | None = None,
    params: dict | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    research: str | None = None,
    research_id: str | None = None,
    name: str | None = None,
) -> list[dict]:
    """Return registry entries matching any provided filters (all optional)."""
    wanted_assets = _normalize_assets(assets)
    matches = []

    for entry in load_registry(outcomes_dir):
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
        if research is not None and entry.get("research") != research:
            continue
        if research_id is not None and entry.get("research_id") != research_id:
            continue
        if name is not None and entry.get("name") != name:
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
    outcomes_dir: Path,
    *,
    strategy: str | None = None,
    id: str | None = None,
    folder: str | None = None,
    assets: str | list[str] | None = None,
    params: dict | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    research: str | None = None,
    research_id: str | None = None,
    name: str | None = None,
) -> dict:
    matches = find_entries(
        outcomes_dir,
        strategy=strategy,
        id=id,
        folder=folder,
        assets=assets,
        params=params,
        start_date=start_date,
        end_date=end_date,
        research=research,
        research_id=research_id,
        name=name,
    )
    if not matches:
        raise FileNotFoundError(
            "No registry entries matched filters: "
            f"strategy={strategy!r}, id={id!r}, folder={folder!r}, "
            f"assets={assets!r}, params={params!r}, "
            f"start_date={start_date!r}, end_date={end_date!r}, "
            f"research={research!r}, research_id={research_id!r}, name={name!r}"
        )
    return matches[-1]


def latest_research_id(outcomes_dir: Path, research: str) -> str:
    """Return the research_id of the most recently registered batch for `research`."""
    matches = find_entries(outcomes_dir, research=research)
    if not matches:
        raise FileNotFoundError(f"No registry entries for research={research!r}")
    research_id = matches[-1].get("research_id")
    if not research_id:
        raise FileNotFoundError(
            f"Latest entry for research={research!r} has no research_id"
        )
    return research_id


def latest_research_entries(outcomes_dir: Path, research: str) -> list[dict]:
    """Return all outcome entries from the latest batch of `research`."""
    research_id = latest_research_id(outcomes_dir, research)
    return find_entries(outcomes_dir, research=research, research_id=research_id)


def steps_path(outcomes_dir: Path, entry: dict) -> Path:
    return Path(outcomes_dir) / entry["folder"] / "steps.jsonl"


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
