from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from ..models import Bar, Frequency, Symbol
from ..store import InMemoryMarketDataStore, MarketDataStore
from .base import DataSourceAdapter


@dataclass(slots=True)
class InMemoryBarDataSource(DataSourceAdapter):
    store: MarketDataStore

    def list_symbols(self) -> Iterable[Symbol]:
        if isinstance(self.store, InMemoryMarketDataStore):
            seen: dict[str, Symbol] = {}
            for (canonical, _), bars in self.store._bars.items():
                if not bars:
                    continue
                seen[canonical] = bars[0].symbol
            return seen.values()
        return []

    def fetch_bars(
        self,
        symbol: Symbol,
        start_ts: datetime,
        end_ts: datetime,
        freq: Frequency,
    ) -> Iterable[Bar]:
        return self.store.read_bars(symbol, start_ts, end_ts, freq)

