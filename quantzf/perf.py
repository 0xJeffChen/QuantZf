from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    total_return: float
    annual_return: float
    annual_volatility: float
    max_drawdown: float
    sharpe: float
    information_ratio: Optional[float]


def _returns_from_equity(equity_curve: List[Tuple[datetime, float]]) -> List[float]:
    if len(equity_curve) < 2:
        return []
    rets: List[float] = []
    prev = equity_curve[0][1]
    for _, val in equity_curve[1:]:
        if prev == 0:
            rets.append(0.0)
        else:
            rets.append(val / prev - 1.0)
        prev = val
    return rets


def max_drawdown(equity_curve: List[Tuple[datetime, float]]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0][1]
    mdd = 0.0
    for _, v in equity_curve:
        if v > peak:
            peak = v
        dd = 0.0 if peak == 0 else (peak - v) / peak
        if dd > mdd:
            mdd = dd
    return float(mdd)


def analyze_performance(
    equity_curve: List[Tuple[datetime, float]],
    periods_per_year: int = 252,
    benchmark_equity_curve: Optional[List[Tuple[datetime, float]]] = None,
) -> PerformanceReport:
    if not equity_curve:
        return PerformanceReport(
            total_return=0.0,
            annual_return=0.0,
            annual_volatility=0.0,
            max_drawdown=0.0,
            sharpe=0.0,
            information_ratio=None,
        )

    start = equity_curve[0][1]
    end = equity_curve[-1][1]
    total_ret = 0.0 if start == 0 else (end / start - 1.0)
    rets = _returns_from_equity(equity_curve)

    if rets:
        avg = mean(rets)
        vol = pstdev(rets)
    else:
        avg = 0.0
        vol = 0.0

    annual_ret = (1.0 + avg) ** periods_per_year - 1.0 if periods_per_year > 0 else 0.0
    annual_vol = vol * sqrt(periods_per_year) if periods_per_year > 0 else 0.0
    sharpe = 0.0 if annual_vol == 0.0 else annual_ret / annual_vol

    ir: Optional[float] = None
    if benchmark_equity_curve:
        bench_rets = _returns_from_equity(benchmark_equity_curve)
        if len(bench_rets) == len(rets) and rets:
            active = [r - b for r, b in zip(rets, bench_rets)]
            active_avg = mean(active)
            active_vol = pstdev(active)
            if active_vol != 0.0 and periods_per_year > 0:
                ir = (active_avg * periods_per_year) / (active_vol * sqrt(periods_per_year))

    return PerformanceReport(
        total_return=float(total_ret),
        annual_return=float(annual_ret),
        annual_volatility=float(annual_vol),
        max_drawdown=float(max_drawdown(equity_curve)),
        sharpe=float(sharpe),
        information_ratio=ir,
    )

