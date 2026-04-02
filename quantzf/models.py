from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

AssetClass = Literal["equity", "futures", "fx"]
Frequency = Literal["1m", "5m", "15m", "30m", "60m", "1d", "1w", "1mo"]


@dataclass(frozen=True, slots=True)
class Symbol:
    exchange: str
    asset_class: AssetClass
    code: str

    def canonical(self) -> str:
        return f"{self.exchange}.{self.asset_class}.{self.code}"


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: Symbol
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: Optional[float] = None
    freq: Frequency = "1d"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(slots=True)
class Order:
    symbol: Symbol
    ts: datetime
    qty: float
    side: Side
    type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    client_order_id: str = ""

    def signed_qty(self) -> float:
        return self.qty if self.side == Side.BUY else -self.qty


@dataclass(slots=True)
class Fill:
    order: Order
    fill_ts: datetime
    fill_price: float
    filled_qty: float
    fee: float


@dataclass(slots=True)
class Position:
    symbol: Symbol
    qty: float = 0.0
    avg_price: float = 0.0
    last_update_ts: Optional[datetime] = None
    realized_pnl: float = 0.0
    _cost_basis: float = field(default=0.0, repr=False)

    def apply_fill(self, fill: Fill) -> None:
        signed = fill.order.signed_qty()
        new_qty = self.qty + signed
        self.last_update_ts = fill.fill_ts

        if self.qty == 0.0:
            self.qty = new_qty
            self.avg_price = fill.fill_price if new_qty != 0.0 else 0.0
            self._cost_basis = self.avg_price * self.qty
            return

        if self.qty * new_qty > 0:
            self._cost_basis += signed * fill.fill_price
            self.qty = new_qty
            self.avg_price = self._cost_basis / self.qty if self.qty != 0.0 else 0.0
            return

        closing_qty = -self.qty if abs(signed) >= abs(self.qty) else signed
        close_price = fill.fill_price
        if self.qty > 0:
            self.realized_pnl += (-closing_qty) * (close_price - self.avg_price)
        else:
            self.realized_pnl += (closing_qty) * (self.avg_price - close_price)

        self.qty = new_qty
        if self.qty == 0.0:
            self.avg_price = 0.0
            self._cost_basis = 0.0
        else:
            self.avg_price = fill.fill_price
            self._cost_basis = self.avg_price * self.qty
