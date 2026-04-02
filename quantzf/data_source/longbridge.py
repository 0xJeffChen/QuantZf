from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from ..models import Bar, Frequency, Symbol
from .base import DataSourceAdapter


class LongbridgeDataSource(DataSourceAdapter):
    def __init__(
        self,
        *,
        config: object | None = None,
        oauth: object | None = None,
        app_key: str | None = None,
        app_secret: str | None = None,
        access_token: str | None = None,
    ) -> None:
        if config is None and oauth is None and not (app_key and app_secret and access_token):
            raise ValueError("Provide one of: config, oauth, or (app_key, app_secret, access_token)")
        self._config = config
        self._oauth = oauth
        self._app_key = app_key
        self._app_secret = app_secret
        self._access_token = access_token

    def list_symbols(self) -> Iterable[Symbol]:
        return []

    def _get_config(self) -> object:
        if self._config is not None:
            return self._config

        try:
            from longbridge.openapi import Config
        except Exception as e:
            raise RuntimeError("longbridge-openapi not installed") from e

        if self._oauth is not None:
            return Config.from_oauth(self._oauth)

        return Config.from_apikey(
            app_key=self._app_key,
            app_secret=self._app_secret,
            access_token=self._access_token,
        )

    def _parse_ts(self, ts: object) -> datetime:
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            s = ts.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts)
        raise TypeError(f"Unsupported timestamp type: {type(ts)!r}")

    def _period_from_freq(self, freq: Frequency) -> object:
        try:
            from longbridge.openapi import Period
        except Exception as e:
            raise RuntimeError("longbridge-openapi not installed") from e

        mapping = {
            "1m": getattr(Period, "Min_1", None),
            "5m": getattr(Period, "Min_5", None),
            "15m": getattr(Period, "Min_15", None),
            "30m": getattr(Period, "Min_30", None),
            "60m": getattr(Period, "Min_60", None),
            "1d": getattr(Period, "Day", None),
            "1w": getattr(Period, "Week", None),
            "1mo": getattr(Period, "Month", None),
        }
        period = mapping.get(freq)
        if period is None:
            raise ValueError(f"LongbridgeDataSource does not support freq={freq!r} with this SDK")
        return period

    def fetch_bars(
        self,
        symbol: Symbol,
        start_ts: datetime,
        end_ts: datetime,
        freq: Frequency,
    ) -> Iterable[Bar]:
        try:
            from longbridge.openapi import AdjustType, QuoteContext
        except Exception as e:
            raise RuntimeError("longbridge-openapi not installed") from e

        period = self._period_from_freq(freq)
        ctx = QuoteContext(self._get_config())

        resp = ctx.history_candlesticks_by_date(
            symbol.code,
            period,
            AdjustType.NoAdjust,
            start_ts.date(),
            end_ts.date(),
        )
        for row in resp:
            ts = self._parse_ts(getattr(row, "timestamp"))
            yield Bar(
                symbol=symbol,
                ts=ts,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                turnover=float(getattr(row, "turnover", 0.0)) if hasattr(row, "turnover") else None,
                freq=freq,
            )
