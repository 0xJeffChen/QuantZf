from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime

from ..models import Bar, Frequency, Symbol


class MarketDataStore(ABC):
    @abstractmethod
    def write_bars(self, bars: Iterable[Bar]) -> int:
        raise NotImplementedError

    @abstractmethod
    def read_bars(
        self,
        symbol: Symbol,
        start_ts: datetime,
        end_ts: datetime,
        freq: Frequency,
    ) -> Iterable[Bar]:
        raise NotImplementedError

