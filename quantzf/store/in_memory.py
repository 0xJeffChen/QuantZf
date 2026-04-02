from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from ..models import Bar, Frequency, Symbol
from .base import MarketDataStore


@dataclass(slots=True)
class InMemoryMarketDataStore(MarketDataStore):
    _bars: dict[tuple[str, str], list[Bar]]

    def __init__(self) -> None:
        self._bars = {}

    def write_bars(self, bars: Iterable[Bar]) -> int:
        count = 0
        for bar in bars:
            key = (bar.symbol.canonical(), bar.freq)
            self._bars.setdefault(key, []).append(bar)
            count += 1
        for _, items in self._bars.items():
            items.sort(key=lambda b: b.ts)
        return count

    def read_bars(
        self,
        symbol: Symbol,
        start_ts: datetime,
        end_ts: datetime,
        freq: Frequency,
    ) -> Iterable[Bar]:
        key = (symbol.canonical(), freq)
        items = self._bars.get(key, [])
        return (b for b in items if start_ts <= b.ts <= end_ts)

