from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Callable

from ..models import Bar, Frequency, Symbol
from ..utils import bar_id_from_key, symbol_id_from_symbol
from .base import MarketDataStore


class MySQLMarketDataStore(MarketDataStore):
    def __init__(
        self,
        connect: Callable[[], object],
        *,
        symbols_table: str = "symbols",
        bars_table: str = "bars",
        batch_size: int = 1000,
    ) -> None:
        self._connect = connect
        self._symbols_table = symbols_table
        self._bars_table = bars_table
        self._batch_size = batch_size

    def _ensure_symbol(self, cur: object, symbol: Symbol) -> int:
        sid = symbol_id_from_symbol(symbol)
        sql = (
            f"INSERT INTO {self._symbols_table} (symbol_id, exchange, asset_class, code) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE exchange=VALUES(exchange), asset_class=VALUES(asset_class), code=VALUES(code)"
        )
        cur.execute(sql, (sid, symbol.exchange, symbol.asset_class, symbol.code))
        return sid

    def write_bars(self, bars: Iterable[Bar]) -> int:
        bars_list = list(bars)
        if not bars_list:
            return 0

        conn = self._connect()
        cur = conn.cursor()
        symbol_cache: dict[str, int] = {}

        insert_sql = (
            f"INSERT INTO {self._bars_table} "
            "(bar_id, symbol_id, freq, ts, open, high, low, close, volume, turnover) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "open=VALUES(open), high=VALUES(high), low=VALUES(low), close=VALUES(close), "
            "volume=VALUES(volume), turnover=VALUES(turnover)"
        )

        params: list[tuple] = []
        for bar in bars_list:
            key = bar.symbol.canonical()
            sid = symbol_cache.get(key)
            if sid is None:
                sid = self._ensure_symbol(cur, bar.symbol)
                symbol_cache[key] = sid
            bid = bar_id_from_key(sid, bar.freq, bar.ts)
            params.append(
                (
                    bid,
                    sid,
                    bar.freq,
                    bar.ts,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                    bar.turnover,
                )
            )

        count = 0
        for i in range(0, len(params), self._batch_size):
            chunk = params[i : i + self._batch_size]
            cur.executemany(insert_sql, chunk)
            count += len(chunk)

        try:
            conn.commit()
        finally:
            try:
                cur.close()
            finally:
                conn.close()

        return count

    def read_bars(
        self,
        symbol: Symbol,
        start_ts: datetime,
        end_ts: datetime,
        freq: Frequency,
    ) -> Iterable[Bar]:
        sid = symbol_id_from_symbol(symbol)
        conn = self._connect()
        cur = conn.cursor()
        sql = (
            f"SELECT ts, open, high, low, close, volume, turnover "
            f"FROM {self._bars_table} "
            "WHERE symbol_id=%s AND freq=%s AND ts >= %s AND ts <= %s "
            "ORDER BY ts ASC"
        )
        cur.execute(sql, (sid, freq, start_ts, end_ts))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        for ts, o, h, l, c, v, t in rows:
            yield Bar(
                symbol=symbol,
                ts=ts,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(v),
                turnover=float(t) if t is not None else None,
                freq=freq,
            )

