from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from models import Account, Candle, Order, Position


@dataclass
class ModifierContext:
    """State visible to experiment modifiers at a bar hook."""

    time: datetime
    account: Account
    positions: list[Position]
    open_orders: list[Order]
    bar_candles: dict[str, Candle]
    is_last_bar: bool


class ExperimentModifier:
    """Account-side experiment hook. Override the phases you need."""

    def on_bar_start(self, ctx: ModifierContext) -> list[dict]:
        """Run before strategy decide. Return journal entries (may be empty)."""
        return []

    def on_bar_end(self, ctx: ModifierContext) -> list[dict]:
        """Run after fills / resting limits. Return journal entries (may be empty)."""
        return []

    def registry_record(self) -> dict:
        """Serializable config snippet for the outcomes registry."""
        return {"type": type(self).__name__}
