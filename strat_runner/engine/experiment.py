from dataclasses import dataclass, field

from engine.modifier import ExperimentModifier


@dataclass
class Experiment:
    """A strategy plus optional account modifiers for one simulation outcome."""

    strategy: object
    modifiers: list[ExperimentModifier] = field(default_factory=list)
    name: str | None = None
