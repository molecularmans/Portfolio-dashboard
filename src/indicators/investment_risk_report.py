"""Price-history checks that complement an A–D chart entry assessment."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _numeric_column(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame:
        return pd.Series(float("nan"), index=frame.index)
    values = pd.to_numeric(frame[name], errors="coerce")
    return values.where(values > 0)


def build_investment_risk_report(
    df: pd.DataFrame,
    assessment: dict[str, Any],
    today: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Measure recent price, gap and trading-value risk without predicting returns."""
    frame = df.copy()
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.sort_values("date", kind="stable")
    frame = frame.reset_index(drop=True)
    close = _numeric_column(frame, "close")
    high = _numeric_column(frame, "high")
    low = _numeric_column(frame, "low")
    opening = _numeric_column(frame, "open")
    volume = _numeric_column(frame, "volume")

    latest = _number(close.iloc[-1]) if len(close) else None
    if latest is None:
        return {"is_valid": False, "warnings": ["최근 종가가 없어 위험 지표를 계산할 수 없습니다."]}

    date = None
    days_since = None
    if "date" in frame and pd.notna(frame["date"].iloc[-1]):
        date = frame["date"].iloc[-1].date()
        current_day = (today if today is not None else pd.Timestamp.now(tz="Asia/Seoul")).date()
        days_since = max(0, (current_day - date).days)

    returns = close.pct_change(fill_method=None)
    daily_vol_pct = None
    if len(close) >= 21 and returns.tail(20).notna().all():
        daily_vol_pct = float(returns.tail(20).std(ddof=1) * 100)
    change_20_pct = float((latest / close.iloc[-21] - 1) * 100) if len(close) >= 21 and pd.notna(close.iloc[-21]) else None
    change_60_pct = float((latest / close.iloc[-61] - 1) * 100) if len(close) >= 61 and pd.notna(close.iloc[-61]) else None

    atr_pct = None
    if len(close) >= 15:
        previous = close.shift(1)
        true_range = pd.concat([high - low, (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1, skipna=False)
        last_14 = true_range.tail(14)
        if last_14.notna().all():
            atr_pct = float(last_14.mean() / latest * 100)

    max_down_gap_pct = None
    if len(close) >= 61:
        gap = opening / close.shift(1) - 1
        last_60 = gap.tail(60)
        if last_60.notna().all():
            max_down_gap_pct = max(0.0, -float(last_60.min()) * 100)

    median_value_20 = None
    if len(close) >= 20:
        traded_value = (close * volume).tail(20)
        if traded_value.notna().all():
            median_value_20 = float(traded_value.median())

    drawdown_52w_pct = None
    if len(high) >= 250 and high.tail(250).notna().all():
        drawdown_52w_pct = float((latest / high.tail(250).max() - 1) * 100)

    stop_risk_pct = _number(assessment.get("risk_pct"))
    stop_atr_multiple = stop_risk_pct / atr_pct if stop_risk_pct and atr_pct and atr_pct > 0 else None
    warnings = []
    if days_since is not None and days_since > 5:
        warnings.append(f"마지막 일봉이 {days_since}일 전입니다. 새 시세를 확인하세요.")
    if assessment.get("verdict") == "신규 진입 보류":
        warnings.append("종합판정이 신규 진입 보류입니다. 차트의 무효화 조건을 먼저 확인하세요.")
    if stop_risk_pct is None:
        warnings.append("진입가 아래의 유효 손절선이 없어 손실 폭을 비교할 수 없습니다.")
    if stop_atr_multiple is not None and stop_atr_multiple < 1:
        warnings.append("가정 손절 폭이 최근 14일 평균 하루 변동폭(ATR)보다 좁습니다.")
    if max_down_gap_pct is not None and stop_risk_pct and max_down_gap_pct >= stop_risk_pct:
        warnings.append("최근 60거래일 최대 하락 개장 갭이 가정 손절 폭 이상이었습니다. 손절 가격 체결을 보장할 수 없습니다.")

    return {
        "is_valid": True,
        "date": date,
        "days_since": days_since,
        "daily_vol_pct": daily_vol_pct,
        "atr_pct": atr_pct,
        "max_down_gap_pct": max_down_gap_pct,
        "median_value_20": median_value_20,
        "change_20_pct": change_20_pct,
        "change_60_pct": change_60_pct,
        "drawdown_52w_pct": drawdown_52w_pct,
        "stop_risk_pct": stop_risk_pct,
        "stop_atr_multiple": stop_atr_multiple,
        "warnings": warnings,
    }
