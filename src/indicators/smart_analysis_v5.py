"""V5 chart context built from confirmed structure and daily OHLCV estimates.

The ideas are informed by public indicator projects (bukosabino/ta,
joshyattridge/smart-money-concepts, bfolkens/py-market-profile).  The formulas
below are independent, small Pandas/NumPy implementations.  A close-bucket
volume profile is explicitly an estimate, not exchange volume-at-price data.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.indicators.smart_analysis_v2 import _prepare_ohlcv, calculate_atr
from src.indicators.smart_analysis_v4 import analyze_smart_chart_v4


def _grade(score: int) -> str:
    return "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"


def _pivot_date_label(value: Any) -> str:
    if isinstance(value, (int, float, np.integer, np.floating)):
        return f"{int(value) + 1}번째 봉"
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def analyze_market_structure(df: pd.DataFrame, swing_bars: int = 3) -> dict[str, Any]:
    """Confirm a swing only after its right-hand bars have actually closed."""
    clean = _prepare_ohlcv(df)
    empty = {"is_valid": False, "score": 50, "trend": "자료 부족", "swings": [], "breaks": [],
             "last_swing_high": None, "last_swing_low": None, "summary": "확정된 고점·저점 부족"}
    wing = max(2, int(swing_bars))
    if len(clean) < max(30, wing * 2 + 5):
        return empty

    highs = clean["high"].to_numpy(dtype=float)
    lows = clean["low"].to_numpy(dtype=float)
    closes = clean["close"].to_numpy(dtype=float)
    swings: list[dict[str, Any]] = []
    breaks: list[dict[str, Any]] = []
    last_high: dict[str, Any] | None = None
    last_low: dict[str, Any] | None = None
    broken_high: int | None = None
    broken_low: int | None = None
    direction = 0

    for confirmed_idx in range(wing * 2, len(clean)):
        # The break check uses levels that were confirmed before this bar.
        if last_high and broken_high != last_high["pivot_idx"]:
            level = last_high["price"]
            if closes[confirmed_idx - 1] <= level < closes[confirmed_idx]:
                kind = "BOS" if direction == 1 else "CHoCH" if direction == -1 else "상단 돌파"
                breaks.append({"kind": kind, "direction": "상승", "confirmed_idx": confirmed_idx, "price": level})
                broken_high = last_high["pivot_idx"]
                direction = 1
        if last_low and broken_low != last_low["pivot_idx"]:
            level = last_low["price"]
            if closes[confirmed_idx - 1] >= level > closes[confirmed_idx]:
                kind = "BOS" if direction == -1 else "CHoCH" if direction == 1 else "하단 이탈"
                breaks.append({"kind": kind, "direction": "하락", "confirmed_idx": confirmed_idx, "price": level})
                broken_low = last_low["pivot_idx"]
                direction = -1

        pivot_idx = confirmed_idx - wing
        is_high = highs[pivot_idx] > max(highs[pivot_idx - wing:pivot_idx]) and highs[pivot_idx] >= max(highs[pivot_idx + 1:confirmed_idx + 1])
        is_low = lows[pivot_idx] < min(lows[pivot_idx - wing:pivot_idx]) and lows[pivot_idx] <= min(lows[pivot_idx + 1:confirmed_idx + 1])
        if is_high and is_low:
            continue  # A very wide candle cannot unambiguously be both pivots.
        if is_high:
            label = "HH" if last_high and highs[pivot_idx] > last_high["price"] else "LH" if last_high else "H"
            last_high = {"kind": label, "pivot_idx": pivot_idx, "confirmed_idx": confirmed_idx,
                         "pivot_date": _pivot_date_label(clean["date"].iloc[pivot_idx]),
                         "price": float(highs[pivot_idx])}
            swings.append(last_high)
        if is_low:
            label = "HL" if last_low and lows[pivot_idx] > last_low["price"] else "LL" if last_low else "L"
            last_low = {"kind": label, "pivot_idx": pivot_idx, "confirmed_idx": confirmed_idx,
                        "pivot_date": _pivot_date_label(clean["date"].iloc[pivot_idx]),
                        "price": float(lows[pivot_idx])}
            swings.append(last_low)

    if not last_high or not last_low:
        return {**empty, "swings": swings[-12:], "breaks": breaks[-8:]}
    bullish = last_high["kind"] == "HH" and last_low["kind"] == "HL"
    bearish = last_high["kind"] == "LH" and last_low["kind"] == "LL"
    trend = "상승 구조" if bullish else "하락 구조" if bearish else "혼조 구조"
    score = 50 + (20 if bullish else -20 if bearish else 0)
    latest_break = breaks[-1] if breaks and breaks[-1]["confirmed_idx"] >= len(clean) - 15 else None
    if latest_break:
        score += 12 if latest_break["direction"] == "상승" else -12
    if closes[-1] < last_low["price"]:
        score -= 15
    score = int(np.clip(score, 0, 100))
    summary = f"{trend} · 고점 {last_high['kind']} {last_high['price']:,.2f} · 저점 {last_low['kind']} {last_low['price']:,.2f}"
    if latest_break:
        summary += f" · 최근 {latest_break['direction']} {latest_break['kind']}"
    return {"is_valid": True, "score": score, "trend": trend, "swings": swings[-12:],
            "breaks": breaks[-8:], "last_swing_high": last_high, "last_swing_low": last_low,
            "latest_break": latest_break, "summary": summary, "confirmation_bars": wing}


def analyze_anchored_vwap(df: pd.DataFrame, anchor_date: Any = None, lookback: int = 60) -> dict[str, Any]:
    """Approximate an anchored VWAP from bar typical prices and volumes."""
    clean = _prepare_ohlcv(df)
    empty = {"is_valid": False, "score": 50, "vwap": None, "distance_pct": None,
             "anchor_idx": None, "anchor_date": None, "series": pd.Series(dtype=float),
             "summary": "VWAP 계산용 가격·거래량 부족"}
    if len(clean) < 10:
        return empty
    anchor_idx = max(0, len(clean) - max(10, int(lookback)))
    if anchor_date is not None and "date" in clean:
        dates = pd.to_datetime(clean["date"], errors="coerce")
        requested = pd.to_datetime(anchor_date, errors="coerce")
        if pd.isna(requested):
            return empty
        matched = np.flatnonzero((dates >= requested).to_numpy())
        if not len(matched):
            return empty
        anchor_idx = int(matched[0])
    volume = clean["volume"].iloc[anchor_idx:]
    if len(volume) < 5 or float(volume.sum()) <= 0:
        return empty
    typical = (clean["high"] + clean["low"] + clean["close"]) / 3.0
    numerator = (typical.iloc[anchor_idx:] * volume).cumsum()
    denominator = volume.cumsum().replace(0, np.nan)
    series = pd.Series(np.nan, index=clean.index, dtype=float)
    series.iloc[anchor_idx:] = (numerator / denominator).to_numpy(dtype=float)
    value = float(series.iloc[-1])
    if not np.isfinite(value) or value <= 0:
        return empty
    close = float(clean["close"].iloc[-1])
    distance = (close / value - 1.0) * 100.0
    score = 80 if 0 <= distance <= 3 else 65 if 3 < distance <= 8 else 45 if distance > 8 else 35 if distance >= -2 else 20
    anchor_label = str(clean["date"].iloc[anchor_idx])[:10]
    return {"is_valid": True, "score": score, "vwap": round(value, 4),
            "distance_pct": round(distance, 2), "anchor_idx": anchor_idx,
            "anchor_date": anchor_label, "series": series,
            "summary": f"{anchor_label} 시작 · VWAP {value:,.2f} · 종가 대비 {distance:+.1f}%",
            "estimate": "봉의 대표가격(H+L+C)/3과 거래량으로 계산한 근사치"}


def analyze_volume_profile(df: pd.DataFrame, lookback: int = 120, bins: int = 24) -> dict[str, Any]:
    """Bucket each bar's entire volume at its close; never imply tick accuracy."""
    clean = _prepare_ohlcv(df).tail(max(30, int(lookback)))
    empty = {"is_valid": False, "score": 50, "poc": None, "vah": None, "val": None,
             "centers": [], "volumes": [], "summary": "가격대별 거래량 추정 자료 부족",
             "estimate": "봉 종가에 해당 봉의 전체 거래량을 배분한 추정치"}
    if len(clean) < 30 or float(clean["volume"].sum()) <= 0:
        return empty
    close = clean["close"].to_numpy(dtype=float)
    volume = clean["volume"].to_numpy(dtype=float)
    if close.max() <= close.min():
        return empty
    edges = np.linspace(float(close.min()), float(close.max()), max(8, int(bins)) + 1)
    histogram, _ = np.histogram(close, bins=edges, weights=volume)
    if histogram.sum() <= 0:
        return empty
    poc_idx = int(np.argmax(histogram))
    left = right = poc_idx
    covered = float(histogram[poc_idx])
    target = float(histogram.sum()) * 0.70
    while covered < target and (left > 0 or right < len(histogram) - 1):
        left_volume = histogram[left - 1] if left > 0 else -1
        right_volume = histogram[right + 1] if right < len(histogram) - 1 else -1
        if right_volume > left_volume:
            right += 1
            covered += float(histogram[right])
        else:
            left -= 1
            covered += float(histogram[left])
    poc = float((edges[poc_idx] + edges[poc_idx + 1]) / 2)
    val, vah = float(edges[left]), float(edges[right + 1])
    current = float(close[-1])
    distance_poc = (current / poc - 1.0) * 100
    score = 75 if 0 <= distance_poc <= 5 else 60 if current >= poc else 50 if current >= val else 30
    return {"is_valid": True, "score": score, "poc": round(poc, 4),
            "vah": round(vah, 4), "val": round(val, 4),
            "centers": ((edges[:-1] + edges[1:]) / 2).tolist(), "volumes": histogram.tolist(),
            "bars": len(clean), "distance_poc_pct": round(distance_poc, 2),
            "summary": f"종가 기반 추정 POC {poc:,.2f} · 70% 구간 {val:,.2f}~{vah:,.2f}",
            "estimate": empty["estimate"]}


def analyze_atr_risk(df: pd.DataFrame, structure: dict[str, Any]) -> dict[str, Any]:
    """Compare the confirmed swing-low gap with ordinary bar volatility."""
    clean = _prepare_ohlcv(df)
    empty = {"is_valid": False, "score": 50, "atr": None, "stop": None,
             "risk_atr": None, "summary": "ATR 또는 확정 저점 부족"}
    if len(clean) < 20:
        return empty
    atr = float(calculate_atr(clean).iloc[-1])
    current = float(clean["close"].iloc[-1])
    stop = (structure.get("last_swing_low") or {}).get("price")
    if not np.isfinite(atr) or atr <= 0 or not stop or stop >= current:
        return empty
    multiple = (current - stop) / atr
    score = 75 if 1 <= multiple <= 3 else 55 if 0.7 <= multiple < 1 else 35 if multiple < 0.7 else 45 if multiple <= 4 else 30
    return {"is_valid": True, "score": score, "atr": round(atr, 4),
            "stop": round(float(stop), 4), "risk_atr": round(multiple, 2),
            "summary": f"확정 저점 {stop:,.2f}까지 {multiple:.1f} ATR"}


def analyze_smart_chart_v5(df: pd.DataFrame, rp_rating: float | None = None,
                           anchor_date: Any = None) -> dict[str, Any]:
    """Extend V4's entry score with causal structure and labeled estimates."""
    v4 = analyze_smart_chart_v4(df, rp_rating=rp_rating)
    structure = analyze_market_structure(df)
    vwap = analyze_anchored_vwap(df, anchor_date=anchor_date)
    profile = analyze_volume_profile(df)
    atr_risk = analyze_atr_risk(df, structure)
    weights = {"v4_baseline": 0.65, "market_structure": 0.15,
               "anchored_vwap": 0.10, "volume_profile_estimate": 0.05, "atr_risk": 0.05}
    raw = {"v4_baseline": v4["composite_score"], "market_structure": structure["score"],
           "anchored_vwap": vwap["score"], "volume_profile_estimate": profile["score"],
           "atr_risk": atr_risk["score"]}
    components = {name: round(raw[name] * weight, 2) for name, weight in weights.items()}
    composite = int(np.clip(round(sum(components.values())), 0, 100))
    verdict = "긍정 우세" if composite >= 72 else "관찰" if composite >= 58 else "중립" if composite >= 43 else "위험 우세"
    return {**v4, "algorithm_version": "experimental-v5", "v4_baseline": v4,
            "market_structure": structure, "anchored_vwap": vwap, "volume_profile": profile,
            "atr_risk": atr_risk, "composite_score": composite, "grade": _grade(composite),
            "verdict": verdict, "score_components": components, "score_inputs": raw,
            "validation_scope": "v4-baseline-only", "research_only": True}
