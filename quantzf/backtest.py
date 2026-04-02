from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from math import copysign
from typing import Dict, Iterable, List, Optional, Protocol, Tuple

from .data import DataSourceAdapter
from .models import Bar, Fill, Order, OrderType, Position, Side, Symbol, Frequency
from .strategy import Strategy, StrategyContext


class SlippageModel(Protocol):
    def apply(self, order: Order, ref_price: float, bar: Bar) -> float: ...


class FeeModel(Protocol):
    def cost(self, fill_price: float, filled_qty: float, bar: Bar) -> float: ...


@dataclass(slots=True)
class NoSlippage:
    def apply(self, order: Order, ref_price: float, bar: Bar) -> float:
        return ref_price


@dataclass(slots=True)
class LinearSlippage:
    bps: float = 2.0

    def apply(self, order: Order, ref_price: float, bar: Bar) -> float:
        signed = copysign(1.0, order.signed_qty())
        return ref_price * (1.0 + signed * self.bps / 10000.0)


@dataclass(slots=True)
class FixedBpsFee:
    bps: float = 3.0
    min_fee: float = 0.0

    def cost(self, fill_price: float, filled_qty: float, bar: Bar) -> float:
        notional = abs(fill_price * filled_qty)
        fee = notional * self.bps / 10000.0
        return fee if fee >= self.min_fee else self.min_fee


@dataclass(slots=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    freq: Frequency = "1d"
    periods_per_year: int = 252
    slippage_model: SlippageModel = field(default_factory=NoSlippage)
    fee_model: FeeModel = field(default_factory=FixedBpsFee)


@dataclass(slots=True)
class RunResult:
    run_id: str
    equity_curve: List[Tuple[datetime, float]]
    orders: List[Order]
    fills: List[Fill]
    positions: Dict[str, Position]
    cash: float


@dataclass(slots=True)
class Broker:
    initial_cash: float
    slippage_model: SlippageModel
    fee_model: FeeModel
    cash: float = field(init=False)
    positions: Dict[str, Position] = field(default_factory=dict, init=False)
    _pending_orders: List[Order] = field(default_factory=list, init=False)
    orders: List[Order] = field(default_factory=list, init=False)
    fills: List[Fill] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    def position(self, symbol: Symbol) -> Position:
        key = symbol.canonical()
        pos = self.positions.get(key)
        if pos is None:
            pos = Position(symbol=symbol)
            self.positions[key] = pos
        return pos

    def submit_order(
        self,
        symbol: Symbol,
        ts: datetime,
        qty: float,
        side: Side,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
        client_order_id: str = "",
    ) -> Order:
        order = Order(
            symbol=symbol,
            ts=ts,
            qty=float(qty),
            side=side,
            type=order_type,
            price=price,
            client_order_id=client_order_id,
        )
        self._pending_orders.append(order)
        self.orders.append(order)
        return order

    def target_position(self, symbol: Symbol, target_qty: float, ts: datetime) -> Optional[Order]:
        pos = self.position(symbol)
        delta = float(target_qty) - float(pos.qty)
        if delta == 0.0:
            return None
        side = Side.BUY if delta > 0 else Side.SELL
        return self.submit_order(symbol=symbol, ts=ts, qty=abs(delta), side=side, order_type=OrderType.MARKET)

    def process_bar(self, bar: Bar) -> List[Fill]:
        if not self._pending_orders:
            return []
        to_exec = self._pending_orders
        self._pending_orders = []
        fills: List[Fill] = []
        for order in to_exec:
            if order.symbol != bar.symbol:
                self._pending_orders.append(order)
                continue
            fill_price = self.slippage_model.apply(order=order, ref_price=bar.open, bar=bar)
            filled_qty = order.qty
            fee = self.fee_model.cost(fill_price=fill_price, filled_qty=filled_qty, bar=bar)
            signed = order.signed_qty()
            cash_change = -(signed * fill_price) - fee
            if self.cash + cash_change < 0:
                continue
            self.cash += cash_change
            fill = Fill(order=order, fill_ts=bar.ts, fill_price=fill_price, filled_qty=filled_qty, fee=fee)
            self.fills.append(fill)
            fills.append(fill)
            pos = self.position(order.symbol)
            pos.apply_fill(fill)
        return fills

    def mark_to_market(self, prices: Dict[str, float]) -> float:
        value = self.cash
        for key, pos in self.positions.items():
            px = prices.get(key)
            if px is None:
                continue
            value += pos.qty * px
        return value


class BacktestEngine:
    def __init__(self, data_source: DataSourceAdapter, config: BacktestConfig) -> None:
        self._data_source = data_source
        self._config = config

    def run(
        self,
        strategy: Strategy,
        universe: list[Symbol],
        start_ts: datetime,
        end_ts: datetime,
    ) -> RunResult:
        run_id = uuid.uuid4().hex
        broker = Broker(
            initial_cash=self._config.initial_cash,
            slippage_model=self._config.slippage_model,
            fee_model=self._config.fee_model,
        )
        ctx = StrategyContext(broker=broker, universe=universe)
        strategy.initialize(ctx)

        bars_by_symbol: Dict[str, List[Bar]] = {}
        for sym in universe:
            bars = list(self._data_source.fetch_bars(sym, start_ts=start_ts, end_ts=end_ts, freq=self._config.freq))
            bars_by_symbol[sym.canonical()] = bars

        merged: List[Bar] = []
        for bars in bars_by_symbol.values():
            merged.extend(bars)
        merged.sort(key=lambda b: (b.ts, b.symbol.canonical()))

        last_trading_day: Optional[date] = None
        equity_curve: List[Tuple[datetime, float]] = []
        last_price: Dict[str, float] = {}

        for bar in merged:
            broker.process_bar(bar)
            ctx.now = bar.ts
            d = bar.ts.date()
            if last_trading_day != d:
                strategy.before_trading(ctx, bar.ts)
                last_trading_day = d
            strategy.handle_bar(ctx, bar)
            last_price[bar.symbol.canonical()] = bar.close
            equity = broker.mark_to_market(last_price)
            equity_curve.append((bar.ts, equity))
        if merged:
            strategy.after_trading(ctx, merged[-1].ts)

        return RunResult(
            run_id=run_id,
            equity_curve=equity_curve,
            orders=list(broker.orders),
            fills=list(broker.fills),
            positions=dict(broker.positions),
            cash=broker.cash,
        )

