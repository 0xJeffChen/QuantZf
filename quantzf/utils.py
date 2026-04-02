from __future__ import annotations

from datetime import datetime
from hashlib import blake2b

from .models import Frequency, Symbol


def _hash_u64(text: str) -> int:
    return int.from_bytes(blake2b(text.encode("utf-8"), digest_size=8).digest(), "big", signed=False)


def symbol_id_from_symbol(symbol: Symbol) -> int:
    return _hash_u64(symbol.canonical())


def bar_id_from_key(symbol_id: int, freq: Frequency, ts: datetime) -> int:
    return _hash_u64(f"{symbol_id}|{freq}|{ts.isoformat()}")

