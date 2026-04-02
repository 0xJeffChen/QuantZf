from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime

from ..models import Bar, Frequency, Symbol


class DataSourceAdapter(ABC):
    @abstractmethod
    def list_symbols(self) -> Iterable[Symbol]:
        raise NotImplementedError

    @abstractmethod
    def fetch_bars(
        self,
        symbol: Symbol,
        start_ts: datetime,
        end_ts: datetime,
        freq: Frequency,
    ) -> Iterable[Bar]:
        raise NotImplementedError

