"""Experimental v3 smart-chart analysis.

The implementation borrows *design ideas* from established open-source projects
without adding their heavy runtime dependencies or copying their source:

* TA-Lib Python (12k+ stars): candlestick recognition, BBANDS and ATR concepts.
* Freqtrade (50k+ stars): explicit no-lookahead signal checks and diagnostics.
* vectorbt (9k+ stars): vectorised event generation and forward-return validation.
* ruptures (2k+ stars): change-point/regime segmentation concepts.

This is an explainable research aid, not an order-execution or prediction engine.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.indicators.smart_analysis_v2 import (
    _prepare_ohlcv,
    analyze_chart_patterns_v2,
    analyze_support_resistance_v2,
    analyze_vcp_v2,
    calculate_atr,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def _grade(score: float) -> str:
    return "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"


def analyze_candlestick_patterns(df: pd.DataFrame, lookback: int = 12) -> Dict[str, Any]:
    """Recognise a compact, context-aware subset of TA-Lib-style candle patterns."""
    clean = _prepare_ohlcv(df)
    if len(clean) < 8:
        return {
            "is_valid": False,
            "signals": [],
            "strongest": None,
            "bullish_count": 0,
            "bearish_count": 0,
            "summary": "캔들 패턴을 계산할 데이터가 부족합니다.",
        }

    if "open" not in clean.columns:
        clean["open"] = clean["close"].shift(1).fillna(clean["close"])
    clean["open"] = pd.to_numeric(clean["open"], errors="coerce").fillna(clean["close"])

    o = clean["open"].to_numpy(dtype=float)
    h = clean["high"].to_numpy(dtype=float)
    low = clean["low"].to_numpy(dtype=float)
    c = clean["close"].to_numpy(dtype=float)
    volume = clean["volume"].to_numpy(dtype=float)
    body = np.abs(c - o)
    candle_range = np.maximum(h - low, 1e-9)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - low
    avg_volume = clean["volume"].rolling(20, min_periods=5).mean().shift(1).to_numpy(dtype=float)

    signals: List[Dict[str, Any]] = []
    start = max(2, len(clean) - lookback)

    def add(idx: int, name: str, direction: str, base_score: int, description: str) -> None:
        prior_start = max(0, idx - 6)
        prior_return = c[idx - 1] / max(c[prior_start], 1e-9) - 1.0 if idx > prior_start else 0.0
        context_ok = (direction == "bullish" and prior_return <= 0.01) or (direction == "bearish" and prior_return >= -0.01)
        volume_ratio = volume[idx] / max(avg_volume[idx], 1e-9) if np.isfinite(avg_volume[idx]) else 1.0
        score = base_score + (8 if context_ok else -8) + (7 if volume_ratio >= 1.25 else 0)
        signals.append(
            {
                "idx": idx,
                "date": str(clean["date"].iloc[idx]),
                "name": name,
                "direction": direction,
                "score": int(np.clip(score, 0, 100)),
                "context_confirmed": bool(context_ok),
                "volume_ratio": round(_safe_float(volume_ratio, 1.0), 2),
                "description": description,
            }
        )

    for i in range(start, len(clean)):
        bullish = c[i] > o[i]
        bearish = c[i] < o[i]
        prev_bullish = c[i - 1] > o[i - 1]
        prev_bearish = c[i - 1] < o[i - 1]

        if bullish and prev_bearish and o[i] <= c[i - 1] and c[i] >= o[i - 1] and body[i] >= body[i - 1] * 0.9:
            add(i, "상승 장악형", "bullish", 78, "이전 음봉 몸통을 감싼 상승 반전 후보")
        if bearish and prev_bullish and o[i] >= c[i - 1] and c[i] <= o[i - 1] and body[i] >= body[i - 1] * 0.9:
            add(i, "하락 장악형", "bearish", 78, "이전 양봉 몸통을 감싼 하락 반전 후보")

        small_body = body[i] / candle_range[i] <= 0.38
        if bullish and small_body and lower[i] >= body[i] * 2.0 and upper[i] <= max(body[i] * 0.7, candle_range[i] * 0.12):
            add(i, "해머", "bullish", 68, "긴 아래꼬리가 확인된 상승 반전 후보")
        if bearish and small_body and upper[i] >= body[i] * 2.0 and lower[i] <= max(body[i] * 0.7, candle_range[i] * 0.12):
            add(i, "슈팅스타", "bearish", 68, "긴 위꼬리가 확인된 하락 반전 후보")

        prev2_bearish = c[i - 2] < o[i - 2]
        prev2_bullish = c[i - 2] > o[i - 2]
        middle_small = body[i - 1] <= body[i - 2] * 0.55
        midpoint = (o[i - 2] + c[i - 2]) / 2.0
        if prev2_bearish and middle_small and bullish and c[i] > midpoint:
            add(i, "모닝스타", "bullish", 82, "3봉 구조의 상승 반전 후보")
        if prev2_bullish and middle_small and bearish and c[i] < midpoint:
            add(i, "이브닝스타", "bearish", 82, "3봉 구조의 하락 반전 후보")

        three_up = np.all(c[i - 2 : i + 1] > o[i - 2 : i + 1]) and np.all(np.diff(c[i - 2 : i + 1]) > 0)
        three_down = np.all(c[i - 2 : i + 1] < o[i - 2 : i + 1]) and np.all(np.diff(c[i - 2 : i + 1]) < 0)
        if three_up and np.all(body[i - 2 : i + 1] / candle_range[i - 2 : i + 1] >= 0.45):
            add(i, "적삼병", "bullish", 74, "3개 강한 양봉이 연속 상승")
        if three_down and np.all(body[i - 2 : i + 1] / candle_range[i - 2 : i + 1] >= 0.45):
            add(i, "흑삼병", "bearish", 74, "3개 강한 음봉이 연속 하락")

    signals.sort(key=lambda item: (item["score"], item["idx"]), reverse=True)
    strongest = signals[0] if signals else None
    bullish_count = sum(signal["direction"] == "bullish" for signal in signals)
    bearish_count = sum(signal["direction"] == "bearish" for signal in signals)
    if strongest:
        direction_text = "상승" if strongest["direction"] == "bullish" else "하락"
        summary = f"{strongest['name']} · {direction_text} 후보 · 신뢰 점수 {strongest['score']}"
    else:
        summary = "최근 구간에서 뚜렷한 캔들 반전 패턴이 없습니다."
    return {
        "is_valid": True,
        "signals": signals,
        "strongest": strongest,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "summary": summary,
    }


def analyze_volatility_squeeze(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
    """Detect Bollinger-inside-Keltner compression and its release."""
    clean = _prepare_ohlcv(df)
    if len(clean) < period + 5:
        return {"is_valid": False, "squeeze_on": False, "release": False, "squeeze_count": 0, "score": 0}

    close = clean["close"]
    basis = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    atr = calculate_atr(clean, period)
    ema = close.ewm(span=period, adjust=False).mean()
    bb_upper, bb_lower = basis + 2.0 * std, basis - 2.0 * std
    kc_upper, kc_lower = ema + 1.5 * atr, ema - 1.5 * atr
    squeeze = (bb_upper < kc_upper) & (bb_lower > kc_lower)

    squeeze_count = 0
    for value in reversed(squeeze.fillna(False).tolist()):
        if value:
            squeeze_count += 1
        else:
            break
    release = bool(not squeeze.iloc[-1] and squeeze.iloc[-2])
    recent_squeeze = bool(squeeze.tail(10).any())
    bandwidth_pct = _safe_float((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / max(basis.iloc[-1], 1e-9) * 100)
    previous_width = (bb_upper - bb_lower) / basis.replace(0, np.nan) * 100
    width_percentile = _safe_float((previous_width.tail(120) <= previous_width.iloc[-1]).mean() * 100, 50.0)

    momentum_window = min(20, len(clean))
    y = close.tail(momentum_window).to_numpy(dtype=float)
    slope = np.polyfit(np.arange(momentum_window, dtype=float), y, 1)[0]
    momentum_pct_per_bar = slope / max(float(np.mean(y)), 1e-9) * 100
    direction = "상승" if momentum_pct_per_bar > 0.03 else "하락" if momentum_pct_per_bar < -0.03 else "중립"
    score = int(np.clip(100 - width_percentile, 0, 100))
    if squeeze.iloc[-1]:
        score = max(score, min(95, 55 + squeeze_count * 4))
    if release:
        score = max(score, 82)

    return {
        "is_valid": True,
        "squeeze_on": bool(squeeze.iloc[-1]),
        "recent_squeeze": recent_squeeze,
        "release": release,
        "squeeze_count": squeeze_count,
        "bandwidth_pct": round(bandwidth_pct, 2),
        "width_percentile": round(width_percentile, 1),
        "momentum_pct_per_bar": round(_safe_float(momentum_pct_per_bar), 3),
        "momentum_direction": direction,
        "score": score,
        "summary": (
            f"스퀴즈 {squeeze_count}봉 지속 · {direction} 모멘텀"
            if squeeze.iloc[-1]
            else f"스퀴즈 해제 · {direction} 모멘텀"
            if release
            else f"압축 대기 · 밴드 폭 백분위 {width_percentile:.0f}%"
        ),
    }


def analyze_market_regime(df: pd.DataFrame, max_window: int = 180, min_segment: int = 15) -> Dict[str, Any]:
    """Find a recent structural break and classify trend/volatility regime."""
    clean = _prepare_ohlcv(df)
    if len(clean) < 45:
        return {"is_valid": False, "regime": "데이터 부족", "change_points": [], "score": 0}

    sample = clean.tail(max_window).reset_index(drop=True)
    returns = np.log(sample["close"]).diff().fillna(0.0).to_numpy(dtype=float)
    atr_pct = (calculate_atr(sample) / sample["close"].replace(0, np.nan)).bfill().fillna(0.0).to_numpy(dtype=float)
    features = np.column_stack([returns, atr_pct])
    scale = np.nanstd(features, axis=0)
    scale[scale < 1e-9] = 1.0
    features = (features - np.nanmean(features, axis=0)) / scale

    candidates: List[Dict[str, Any]] = []
    n = len(sample)
    for split in range(min_segment, n - min_segment + 1):
        left = features[max(0, split - 45) : split]
        right = features[split : min(n, split + 45)]
        if len(left) < min_segment or len(right) < min_segment:
            continue
        mean_gap = float(np.linalg.norm(np.mean(left, axis=0) - np.mean(right, axis=0)))
        balance = np.sqrt(len(left) * len(right) / max(len(left) + len(right), 1))
        strength = mean_gap * balance
        if strength >= 2.2:
            candidates.append({"idx": split, "strength": strength})

    selected: List[Dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: item["strength"], reverse=True):
        if all(abs(candidate["idx"] - item["idx"]) >= min_segment for item in selected):
            selected.append(candidate)
        if len(selected) == 3:
            break
    selected.sort(key=lambda item: item["idx"])
    change_points = [
        {
            "idx": int(len(clean) - len(sample) + item["idx"]),
            "date": str(sample["date"].iloc[min(item["idx"], len(sample) - 1)]),
            "strength": round(item["strength"], 2),
            "bars_ago": int(n - item["idx"]),
        }
        for item in selected
    ]

    trend_window = min(40, len(sample))
    prices = sample["close"].tail(trend_window).to_numpy(dtype=float)
    log_slope = np.polyfit(np.arange(trend_window, dtype=float), np.log(prices), 1)[0] * 100
    path = np.abs(np.diff(prices)).sum()
    efficiency = abs(prices[-1] - prices[0]) / max(path, 1e-9)
    recent_vol = float(np.std(returns[-20:], ddof=0))
    baseline_vol = float(np.std(returns[-60:], ddof=0))
    volatility_ratio = recent_vol / max(baseline_vol, 1e-9)

    if efficiency >= 0.28 and log_slope >= 0.08:
        trend = "상승 추세"
        trend_score = min(100, 55 + efficiency * 45)
    elif efficiency >= 0.28 and log_slope <= -0.08:
        trend = "하락 추세"
        trend_score = max(0, 45 - efficiency * 45)
    else:
        trend = "박스권"
        trend_score = 50
    vol_label = "고변동" if volatility_ratio >= 1.25 else "저변동" if volatility_ratio <= 0.75 else "보통변동"
    return {
        "is_valid": True,
        "regime": f"{trend} · {vol_label}",
        "trend": trend,
        "volatility": vol_label,
        "slope_pct_per_bar": round(_safe_float(log_slope), 3),
        "efficiency_ratio": round(_safe_float(efficiency), 3),
        "volatility_ratio": round(_safe_float(volatility_ratio, 1.0), 2),
        "change_points": change_points,
        "last_change": change_points[-1] if change_points else None,
        "score": int(np.clip(trend_score, 0, 100)),
    }


def walk_forward_breakout_validation(df: pd.DataFrame, horizon: int = 10) -> Dict[str, Any]:
    """Validate prior-high breakouts using only information available at signal time."""
    clean = _prepare_ohlcv(df)
    minimum = max(70, horizon + 30)
    if len(clean) < minimum:
        return {
            "is_valid": False,
            "sample_count": 0,
            "hit_rate_pct": 0.0,
            "avg_return_pct": 0.0,
            "avg_mfe_pct": 0.0,
            "avg_mae_pct": 0.0,
            "signals": [],
            "warning": "워크포워드 검증을 위한 데이터가 부족합니다.",
        }

    prior_high = clean["high"].rolling(20, min_periods=20).max().shift(1)
    prior_volume = clean["volume"].rolling(20, min_periods=20).mean().shift(1)
    basis = clean["close"].rolling(20).mean()
    width = clean["close"].rolling(20).std(ddof=0) * 4.0 / basis.replace(0, np.nan)
    low_width_threshold = width.rolling(60, min_periods=30).quantile(0.35).shift(1)
    was_compressed = (width.shift(1) <= low_width_threshold).rolling(10, min_periods=1).max().fillna(0).astype(bool)
    raw_signal = (
        (clean["close"] > prior_high)
        & (clean["volume"] >= prior_volume * 1.20)
        & was_compressed
    ).fillna(False)

    signal_indices: List[int] = []
    next_allowed = 0
    for idx in np.flatnonzero(raw_signal.to_numpy()):
        if idx >= next_allowed and idx + horizon < len(clean):
            signal_indices.append(int(idx))
            next_allowed = int(idx) + horizon + 1

    events: List[Dict[str, Any]] = []
    for idx in signal_indices:
        entry = float(clean["close"].iloc[idx])
        exit_price = float(clean["close"].iloc[idx + horizon])
        future = clean.iloc[idx + 1 : idx + horizon + 1]
        forward_return = (exit_price / entry - 1.0) * 100
        mfe = (float(future["high"].max()) / entry - 1.0) * 100
        mae = (float(future["low"].min()) / entry - 1.0) * 100
        events.append(
            {
                "idx": idx,
                "date": str(clean["date"].iloc[idx]),
                "entry": round(entry, 4),
                "forward_return_pct": round(forward_return, 2),
                "mfe_pct": round(mfe, 2),
                "mae_pct": round(mae, 2),
            }
        )

    returns = np.asarray([event["forward_return_pct"] for event in events], dtype=float)
    mfes = np.asarray([event["mfe_pct"] for event in events], dtype=float)
    maes = np.asarray([event["mae_pct"] for event in events], dtype=float)
    count = len(events)
    hit_rate = float(np.mean(returns > 0) * 100) if count else 0.0
    avg_return = float(np.mean(returns)) if count else 0.0
    score = int(np.clip(50 + avg_return * 5 + (hit_rate - 50) * 0.5, 0, 100)) if count else 50
    warning = "표본 5건 미만: 승률·수익률 해석을 보류하세요." if count < 5 else "과거 이벤트 결과이며 미래 성과를 보장하지 않습니다."
    return {
        "is_valid": count >= 3,
        "sample_count": count,
        "horizon_days": horizon,
        "hit_rate_pct": round(hit_rate, 1),
        "avg_return_pct": round(avg_return, 2),
        "median_return_pct": round(float(np.median(returns)), 2) if count else 0.0,
        "avg_mfe_pct": round(float(np.mean(mfes)), 2) if count else 0.0,
        "avg_mae_pct": round(float(np.mean(maes)), 2) if count else 0.0,
        "score": score,
        "signals": events,
        "warning": warning,
        "no_lookahead": True,
    }


def analyze_smart_chart_v3(df: pd.DataFrame) -> Dict[str, Any]:
    """Run A/B/C plus candle, squeeze, regime and walk-forward diagnostics."""
    sr = analyze_support_resistance_v2(df)
    patterns = analyze_chart_patterns_v2(df)
    vcp = analyze_vcp_v2(df)
    candles = analyze_candlestick_patterns(df)
    squeeze = analyze_volatility_squeeze(df)
    regime = analyze_market_regime(df)
    validation = walk_forward_breakout_validation(df)

    pattern_score = 0.0
    if patterns.get("primary_pattern"):
        pattern_score = _safe_float(patterns["primary_pattern"].get("confidence"))
    if candles.get("strongest"):
        pattern_score = max(pattern_score, _safe_float(candles["strongest"].get("score")))
    validation_score = validation.get("score", 50) if validation.get("sample_count", 0) >= 3 else 50
    components = {
        "support_resistance": _safe_float(sr.get("quality_score")) * 0.20,
        "patterns_and_candles": pattern_score * 0.15,
        "vcp": _safe_float(vcp.get("quality_score")) * 0.20,
        "market_regime": _safe_float(regime.get("score", 50)) * 0.15,
        "squeeze": _safe_float(squeeze.get("score", 50)) * 0.10,
        "walk_forward": _safe_float(validation_score, 50) * 0.20,
    }
    composite_score = int(np.clip(round(sum(components.values())), 0, 100))
    vcp["squeeze"] = squeeze
    return {
        "algorithm_version": "experimental-v3",
        "support_resistance": sr,
        "patterns": patterns,
        "vcp": vcp,
        "candlesticks": candles,
        "squeeze": squeeze,
        "regime": regime,
        "validation": validation,
        "composite_score": composite_score,
        "grade": _grade(composite_score),
        "score_components": {key: round(value, 1) for key, value in components.items()},
        "research_only": True,
    }
