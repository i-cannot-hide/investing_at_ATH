from dataclasses import dataclass, field

from engine.money_spawner import MoneySpawner
from engine.staker import Staker


@dataclass
class Experiment:
    """A strategy plus optional account elements for one simulation outcome."""

    strategy: object
    money_spawner: MoneySpawner | None = None
    stakers: list[Staker] = field(default_factory=list)
    name: str | None = None
