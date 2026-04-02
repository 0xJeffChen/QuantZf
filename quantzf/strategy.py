from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Dict, Optional

from .models import Bar, Order, OrderType, Side, Symbol


@dataclass(slots=True)
class StrategyContext:
    broker: object
    universe: list[Symbol]
    now: Optional[datetime] = None
    _windows: Dict[str, Deque[Bar]] = None

    def __post_init__(self) -> None:
        if self._windows is None:
            self._windows = {}

    def window(self, symbol: Symbol, size: int) -> Deque[Bar]:
        key = symbol.canonical()
        win = self._windows.get(key)
        if win is None:
            win = deque(maxlen=size)
            self._windows[key] = win
            return win
        if win.maxlen != size:
            new_win: Deque[Bar] = deque(win, maxlen=size)
            self._windows[key] = new_win
            return new_win
        return win

    def history_closes(self, symbol: Symbol, n: int) -> list[float]:
        win = self.window(symbol, n)
        if len(win) < n:
            return []
        return [b.close for b in win][-n:]

    def place_order(
        self,
        symbol: Symbol,
        qty: float,
        side: Side,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
        client_order_id: str = "",
    ) -> Order:
        return self.broker.submit_order(
            symbol=symbol,
            ts=self.now or datetime.utcnow(),
            qty=qty,
            side=side,
            order_type=order_type,
            price=price,
            client_order_id=client_order_id,
        )

    def target_position(self, symbol: Symbol, target_qty: float) -> Optional[Order]:
        return self.broker.target_position(symbol=symbol, target_qty=target_qty, ts=self.now or datetime.utcnow())


class Strategy(ABC):
    def initialize(self, ctx: StrategyContext) -> None:
        return

    def before_trading(self, ctx: StrategyContext, dt: datetime) -> None:
        return

    @abstractmethod
    def handle_bar(self, ctx: StrategyContext, bar: Bar) -> None:
        raise NotImplementedError

    def after_trading(self, ctx: StrategyContext, dt: datetime) -> None:
        return


class BuyAndHoldStrategy(Strategy):
    def __init__(self, symbol: Symbol, target_qty: float = 1.0) -> None:
        self._symbol = symbol
        self._target_qty = target_qty
        self._submitted = False

    def handle_bar(self, ctx: StrategyContext, bar: Bar) -> None:
        win = ctx.window(bar.symbol, 1)
        win.append(bar)
        ctx.now = bar.ts
        if bar.symbol != self._symbol:
            return
        if self._submitted:
            return
        ctx.target_position(symbol=self._symbol, target_qty=self._target_qty)
        self._submitted = True


class MovingAverageCrossStrategy(Strategy):
    def __init__(
        self,
        symbol: Symbol,
        fast_window: int = 5,
        slow_window: int = 20,
        target_qty: float = 1.0,
    ) -> None:
        if fast_window <= 0 or slow_window <= 0 or fast_window >= slow_window:
            raise ValueError("require 0 < fast_window < slow_window")
        self._symbol = symbol
        self._fast = fast_window
        self._slow = slow_window
        self._target_qty = target_qty
        self._last_signal: Optional[int] = None

    def _sma(self, values: Iterable[float]) -> float:
        vals = list(values)
        return sum(vals) / len(vals)

    def handle_bar(self, ctx: StrategyContext, bar: Bar) -> None:
        ctx.now = bar.ts
        win = ctx.window(bar.symbol, self._slow)
        win.append(bar)
        if bar.symbol != self._symbol:
            return
        closes = [b.close for b in win]
        if len(closes) < self._slow:
            return
        fast = self._sma(closes[-self._fast :])
        slow = self._sma(closes[-self._slow :])
        signal = 1 if fast > slow else 0
        if self._last_signal is None:
            self._last_signal = signal
            return
        if signal == self._last_signal:
            return
        if signal == 1:
            ctx.target_position(symbol=self._symbol, target_qty=self._target_qty)
        else:
            ctx.target_position(symbol=self._symbol, target_qty=0.0)
        self._last_signal = signal
