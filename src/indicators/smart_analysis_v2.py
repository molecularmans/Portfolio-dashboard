"""Experimental smart-chart analysis algorithms.

The module keeps the public result shape of the original A/B/C analyzers while
adding volatility-adaptive pivots, scored price zones, pattern confirmation,
and a transparent VCP quality score.  It intentionally depends only on
NumPy/Pandas so the Streamlit deployment stays lightweight.

Design references (ideas, not copied source):
* jbn/ZigZag: reversal-threshold peak/valley extraction
* ednunezg/pytrendline: touch/error/violation based trendline scoring
* white07S/TradingPatternScanner and zeta-zetra/chart_patterns:
  pivot-sequence pattern recognition and noise/confirmation filtering
* bukosabino/ta: ATR-normalised volatility features
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.indicators.pattern_detector import (
    detect_double_bottom,
    detect_double_top,
    detect_inverse_head_and_shoulders,
    detect_triangles,
)
from src.indicators.vcp_analyzer import detect_vcp_pattern


REQUIRED_OHLCV = ("high", "low", "close", "volume")


def _prepare_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Return a clean, positional OHLCV frame without mutating the caller."""
    if df is None or df.empty or any(col not in df.columns for col in REQUIRED_OHLCV):
        return pd.DataFrame()

    clean = df.copy().reset_index(drop=True)
    for col in REQUIRED_OHLCV:
        clean[col] = pd.to_numeric(clean[col], errors="coerce")
    clean = clean.dropna(subset=["high", "low", "close"])
    clean = clean[(clean["high"] > 0) & (clean["low"] > 0) & (clean["close"] > 0)]
    clean["volume"] = clean["volume"].fillna(0).clip(lower=0)
    if "date" not in clean.columns:
        clean["date"] = np.arange(len(clean))
    return clean.reset_index(drop=True)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder-style ATR with useful values even for short test samples."""
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False, min_periods=2).mean()


def _adaptive_window(df: pd.DataFrame, atr: pd.Series) -> int:
    atr_pct = (atr / df["close"].replace(0, np.nan) * 100).tail(40).median()
    atr_pct = float(atr_pct) if pd.notna(atr_pct) else 2.0
    return int(np.clip(round(2.5 + atr_pct * 0.8), 3, 8))


def find_adaptive_pivots(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, float]]:
    """Find alternating pivots using an ATR-aware local window and ZigZag filter."""
    clean = _prepare_ohlcv(df)
    if len(clean) < 9:
        return [], [], {"window": 0, "atr_pct": 0.0, "reversal_pct": 0.0}

    atr = calculate_atr(clean)
    window = _adaptive_window(clean, atr)
    atr_pct = float((atr / clean["close"] * 100).tail(40).median())
    if not np.isfinite(atr_pct):
        atr_pct = 2.0
    reversal_pct = float(np.clip(atr_pct * 1.15, 1.2, 6.0))
    dates = clean["date"].to_numpy()

    raw: List[Dict[str, Any]] = []
    highs = clean["high"].to_numpy(dtype=float)
    lows = clean["low"].to_numpy(dtype=float)
    volumes = clean["volume"].to_numpy(dtype=float)
    for idx in range(window, len(clean) - window):
        high_slice = highs[idx - window : idx + window + 1]
        low_slice = lows[idx - window : idx + window + 1]
        if highs[idx] >= np.max(high_slice):
            raw.append({"type": "peak", "idx": idx, "date": dates[idx], "price": float(highs[idx]), "volume": float(volumes[idx])})
        if lows[idx] <= np.min(low_slice):
            raw.append({"type": "valley", "idx": idx, "date": dates[idx], "price": float(lows[idx]), "volume": float(volumes[idx])})

    raw.sort(key=lambda point: (point["idx"], 0 if point["type"] == "peak" else 1))
    alternating: List[Dict[str, Any]] = []
    for point in raw:
        if alternating and point["idx"] == alternating[-1]["idx"]:
            continue
        if alternating and point["type"] == alternating[-1]["type"]:
            more_extreme = point["price"] > alternating[-1]["price"] if point["type"] == "peak" else point["price"] < alternating[-1]["price"]
            if more_extreme:
                alternating[-1] = point
            continue
        if alternating:
            move_pct = abs(point["price"] - alternating[-1]["price"]) / alternating[-1]["price"] * 100
            if move_pct < reversal_pct:
                continue
        alternating.append(point)

    peaks = [point for point in alternating if point["type"] == "peak"]
    valleys = [point for point in alternating if point["type"] == "valley"]
    return peaks, valleys, {
        "window": float(window),
        "atr_pct": round(atr_pct, 3),
        "reversal_pct": round(reversal_pct, 3),
    }


def _cluster_price_zones(
    points: List[Dict[str, Any]],
    current_idx: int,
    atr_value: float,
    tolerance_pct: float,
    min_touches: int = 2,
) -> List[Dict[str, Any]]:
    if not points:
        return []

    clusters: List[List[Dict[str, Any]]] = []
    for point in sorted(points, key=lambda item: item["price"]):
        best_cluster: Optional[List[Dict[str, Any]]] = None
        best_distance = float("inf")
        for cluster in clusters:
            center = float(np.median([item["price"] for item in cluster]))
            distance = abs(point["price"] - center) / max(center, 1e-9)
            if distance <= tolerance_pct and distance < best_distance:
                best_cluster = cluster
                best_distance = distance
        if best_cluster is None:
            clusters.append([point])
        else:
            best_cluster.append(point)

    levels: List[Dict[str, Any]] = []
    for cluster in clusters:
        if len(cluster) < min_touches:
            continue
        prices = np.asarray([point["price"] for point in cluster], dtype=float)
        ages = np.asarray([current_idx - point["idx"] for point in cluster], dtype=float)
        recency_weights = np.exp(-ages / 90.0)
        level_price = float(np.average(prices, weights=recency_weights))
        dispersion_pct = float(np.std(prices) / max(level_price, 1e-9) * 100)
        touch_score = min(1.0, len(cluster) / 5.0)
        recency_score = float(np.exp(-float(np.min(ages)) / 70.0))
        compactness = max(0.0, 1.0 - dispersion_pct / max(tolerance_pct * 100, 0.1))
        strength_score = round(100 * (0.50 * touch_score + 0.30 * recency_score + 0.20 * compactness))
        half_zone = max(atr_value * 0.30, level_price * tolerance_pct * 0.20)
        levels.append(
            {
                "price": round(level_price, 2),
                "zone_low": round(level_price - half_zone, 2),
                "zone_high": round(level_price + half_zone, 2),
                "touches": len(cluster),
                "last_idx": int(max(point["idx"] for point in cluster)),
                "age_bars": int(min(ages)),
                "indices": [int(point["idx"]) for point in cluster],
                "dispersion_pct": round(dispersion_pct, 2),
                "strength_score": int(strength_score),
            }
        )
    levels.sort(key=lambda item: (item["strength_score"], item["touches"], item["last_idx"]), reverse=True)
    return levels


def _fit_scored_trendline(
    points: List[Dict[str, Any]],
    df: pd.DataFrame,
    atr_value: float,
    is_upper: bool,
) -> Optional[Dict[str, Any]]:
    recent = [point for point in points if point["idx"] >= max(0, len(df) - 140)][-14:]
    if len(recent) < 2:
        return None

    prices = df["high"].to_numpy(dtype=float) if is_upper else df["low"].to_numpy(dtype=float)
    best: Optional[Dict[str, Any]] = None
    best_score = -float("inf")
    for first in range(len(recent) - 1):
        for second in range(first + 1, len(recent)):
            p1, p2 = recent[first], recent[second]
            span = p2["idx"] - p1["idx"]
            if span < 8:
                continue
            slope = (p2["price"] - p1["price"]) / span
            intercept = p1["price"] - slope * p1["idx"]
            end_price = slope * (len(df) - 1) + intercept
            if end_price <= 0:
                continue

            tolerance = max(atr_value * 0.45, end_price * 0.006)
            pivot_errors = [abs(point["price"] - (slope * point["idx"] + intercept)) for point in recent]
            touches = sum(error <= tolerance for error in pivot_errors)
            start_idx = p1["idx"]
            x = np.arange(start_idx, len(df), dtype=float)
            line_values = slope * x + intercept
            segment = prices[start_idx:]
            if len(segment) != len(line_values):
                continue
            if is_upper:
                violations = int(np.sum(segment > line_values + tolerance))
            else:
                violations = int(np.sum(segment < line_values - tolerance))
            mean_error_pct = float(np.mean(pivot_errors) / max(end_price, 1e-9) * 100)
            span_score = min(25.0, span / max(len(df), 1) * 50.0)
            score = touches * 17.0 + span_score - violations * 9.0 - mean_error_pct * 4.0
            if score <= best_score:
                continue
            best_score = score
            quality = int(np.clip(45 + touches * 10 + span_score - violations * 8 - mean_error_pct * 3, 0, 100))
            best = {
                "start_idx": int(p1["idx"]),
                "start_price": round(float(p1["price"]), 4),
                "end_idx": int(p2["idx"]),
                "end_price": round(float(p2["price"]), 4),
                "slope": float(slope),
                "intercept": float(intercept),
                "current_price": round(float(end_price), 4),
                "touches": int(touches),
                "violations": violations,
                "mean_error_pct": round(mean_error_pct, 3),
                "quality_score": quality,
                "type": "resistance" if is_upper else "support",
            }
    return best


def analyze_support_resistance_v2(df: pd.DataFrame) -> Dict[str, Any]:
    """[A] ATR-adaptive support/resistance zones and scored trendlines."""
    clean = _prepare_ohlcv(df)
    empty = {
        "is_valid": False,
        "algorithm_version": "experimental-v2",
        "current_price": 0.0,
        "nearest_support": None,
        "nearest_resistance": None,
        "support_levels": [],
        "resistance_levels": [],
        "upper_trendline": None,
        "lower_trendline": None,
        "breakout_type": "data_lack",
        "status_badge": "분석 불가",
        "status_color": "#94a3b8",
        "status_desc": "분석을 위한 충분한 OHLCV 데이터가 없습니다.",
        "quality_score": 0,
        "diagnostics": {},
    }
    if len(clean) < 30:
        return empty

    atr = calculate_atr(clean)
    atr_value = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else float((clean["high"] - clean["low"]).tail(14).mean())
    cur_close = float(clean["close"].iloc[-1])
    peaks, valleys, pivot_meta = find_adaptive_pivots(clean)
    tolerance_pct = float(np.clip((atr_value / cur_close) * 0.85, 0.008, 0.03))
    resistance_zones = _cluster_price_zones(peaks, len(clean) - 1, atr_value, tolerance_pct)
    support_zones = _cluster_price_zones(valleys, len(clean) - 1, atr_value, tolerance_pct)
    supports = [level for level in support_zones if level["zone_low"] <= cur_close]
    resistances = [level for level in resistance_zones if level["zone_high"] >= cur_close]
    broken_resistances = [level for level in resistance_zones if level["zone_high"] < cur_close]
    nearest_support = min(supports, key=lambda level: abs(cur_close - level["price"])) if supports else None
    nearest_resistance = min(resistances, key=lambda level: abs(level["price"] - cur_close)) if resistances else None
    breakout_resistance = max(broken_resistances, key=lambda level: level["price"]) if broken_resistances else None
    upper = _fit_scored_trendline(peaks, clean, atr_value, is_upper=True)
    lower = _fit_scored_trendline(valleys, clean, atr_value, is_upper=False)

    dist_support = ((cur_close - nearest_support["price"]) / nearest_support["price"] * 100) if nearest_support else None
    dist_resistance = ((nearest_resistance["price"] - cur_close) / cur_close * 100) if nearest_resistance else None
    prior_volume = float(clean["volume"].iloc[-21:-1].mean()) if len(clean) > 21 else float(clean["volume"].iloc[:-1].mean())
    volume_ratio = float(clean["volume"].iloc[-1] / max(prior_volume, 1e-9))
    breakout_buffer = max(atr_value * 0.35, cur_close * 0.004)

    status_badge = "📦 변동성 적응 박스권"
    status_color = "#38bdf8"
    status_desc = "ATR로 보정한 지지·저항 존 사이에서 가격이 움직이고 있습니다."
    breakout_type = "range"
    if upper and cur_close > upper["current_price"] + breakout_buffer:
        confirmed = volume_ratio >= 1.20
        status_badge = "🚀 거래량 확인 추세선 돌파" if confirmed else "👀 추세선 돌파 관찰"
        status_color = "#26a69a" if confirmed else "#f59e0b"
        status_desc = f"상단 추세선 ${upper['current_price']:,.2f}를 ATR 버퍼만큼 돌파했습니다. 거래량은 20일 평균의 {volume_ratio:.2f}배입니다."
        breakout_type = "upper_trendline_breakout_confirmed" if confirmed else "upper_trendline_breakout_unconfirmed"
    elif breakout_resistance and cur_close > breakout_resistance["zone_high"] + breakout_buffer:
        confirmed = volume_ratio >= 1.20
        status_badge = "🔥 거래량 확인 저항 돌파" if confirmed else "👀 저항 돌파 관찰"
        status_color = "#26a69a" if confirmed else "#f59e0b"
        status_desc = f"저항 존 상단 ${breakout_resistance['zone_high']:,.2f} 위로 이탈했습니다. 거래량 확인 여부를 함께 보세요."
        breakout_type = "resistance_breakout_confirmed" if confirmed else "resistance_breakout_unconfirmed"
    elif lower and cur_close < lower["current_price"] - breakout_buffer:
        status_badge = "⚠️ ATR 확인 추세선 이탈"
        status_color = "#ef5350"
        status_desc = f"하단 추세선 ${lower['current_price']:,.2f} 아래로 ATR 버퍼 이상 이탈했습니다."
        breakout_type = "lower_trendline_breakdown"
    elif nearest_support and nearest_support["zone_low"] <= cur_close <= nearest_support["zone_high"]:
        status_badge = "🛡️ 핵심 지지 존 테스트"
        status_color = "#f59e0b"
        status_desc = f"강도 {nearest_support['strength_score']}점의 지지 존(${nearest_support['zone_low']:,.2f}~${nearest_support['zone_high']:,.2f})을 테스트 중입니다."
        breakout_type = "support_zone_test"
    elif nearest_resistance and nearest_resistance["zone_low"] <= cur_close <= nearest_resistance["zone_high"]:
        status_badge = "🛑 핵심 저항 존 테스트"
        status_color = "#f59e0b"
        status_desc = f"강도 {nearest_resistance['strength_score']}점의 저항 존(${nearest_resistance['zone_low']:,.2f}~${nearest_resistance['zone_high']:,.2f})을 테스트 중입니다."
        breakout_type = "resistance_zone_test"

    quality_inputs = [
        nearest_support["strength_score"] if nearest_support else 0,
        nearest_resistance["strength_score"] if nearest_resistance else 0,
        upper["quality_score"] if upper else 0,
        lower["quality_score"] if lower else 0,
    ]
    non_zero_quality = [value for value in quality_inputs if value > 0]
    quality_score = int(round(float(np.mean(non_zero_quality)))) if non_zero_quality else 0

    return {
        "is_valid": True,
        "algorithm_version": "experimental-v2",
        "current_price": cur_close,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "dist_support_pct": dist_support,
        "dist_resistance_pct": dist_resistance,
        "support_levels": sorted(supports, key=lambda level: level["price"], reverse=True)[:4],
        "resistance_levels": sorted(resistances, key=lambda level: level["price"])[:4],
        "upper_trendline": upper,
        "lower_trendline": lower,
        "breakout_type": breakout_type,
        "status_badge": status_badge,
        "status_color": status_color,
        "status_desc": status_desc,
        "peaks": peaks,
        "valleys": valleys,
        "quality_score": quality_score,
        "diagnostics": {
            **pivot_meta,
            "atr": round(atr_value, 4),
            "zone_tolerance_pct": round(tolerance_pct * 100, 3),
            "volume_ratio": round(volume_ratio, 3),
        },
    }


def _pattern_quality(pattern: Dict[str, Any], df: pd.DataFrame, atr_value: float) -> Dict[str, Any]:
    cur_close = float(df["close"].iloc[-1])
    neckline = float(pattern["neckline"])
    key_indices = [int(point["idx"]) for point in pattern.get("key_points", []) if "idx" in point]
    age_bars = max(0, len(df) - 1 - max(key_indices)) if key_indices else len(df)
    prior_volume = float(df["volume"].iloc[-21:-1].mean()) if len(df) > 21 else float(df["volume"].iloc[:-1].mean())
    volume_ratio = float(df["volume"].iloc[-1] / max(prior_volume, 1e-9))
    is_bearish = pattern.get("type") == "bearish"
    price_confirmed = cur_close < neckline - atr_value * 0.25 if is_bearish else cur_close > neckline + atr_value * 0.25
    volume_confirmed = volume_ratio >= 1.20
    freshness_score = max(0.0, 100.0 - age_bars * 2.0)
    risk_pct = abs(float(pattern.get("risk_pct", 0.0)))
    risk_score = float(np.clip(110.0 - risk_pct * 8.0, 20.0, 100.0))
    volume_score = float(np.clip(35.0 + volume_ratio * 35.0, 25.0, 100.0))
    base_confidence = float(pattern.get("confidence", 60))
    confidence = int(np.clip(0.50 * base_confidence + 0.20 * freshness_score + 0.15 * risk_score + 0.15 * volume_score, 0, 99))

    warnings: List[str] = []
    if price_confirmed and not volume_confirmed:
        warnings.append("돌파 거래량이 20일 평균의 1.2배 미만")
    if age_bars > 30:
        warnings.append("마지막 핵심 피벗이 30봉보다 오래됨")
    if risk_pct > 10:
        warnings.append("패턴 손절 폭이 10% 초과")
    confirmed = bool(price_confirmed and volume_confirmed)
    quality_grade = "A" if confidence >= 85 and not warnings else "B" if confidence >= 72 else "C" if confidence >= 60 else "D"

    enriched = dict(pattern)
    enriched.update(
        {
            "is_breakout": confirmed,
            "price_confirmed": bool(price_confirmed),
            "volume_confirmed": bool(volume_confirmed),
            "volume_ratio": round(volume_ratio, 2),
            "age_bars": int(age_bars),
            "confidence": confidence,
            "quality_grade": quality_grade,
            "warnings": warnings,
            "confirmation_text": "가격+거래량 확인" if confirmed else "가격 확인·거래량 대기" if price_confirmed else "패턴 형성 중",
        }
    )
    return enriched


def analyze_chart_patterns_v2(df: pd.DataFrame) -> Dict[str, Any]:
    """[B] Detect classic patterns with adaptive pivots and confirmation gates."""
    clean = _prepare_ohlcv(df)
    empty = {
        "has_pattern": False,
        "algorithm_version": "experimental-v2",
        "primary_pattern": None,
        "detected_patterns": [],
        "summary_badge": "패턴 진행 중 아님",
        "summary_color": "#94a3b8",
        "summary_desc": "ATR 적응형 피벗에서 유효한 고전 패턴을 찾지 못했습니다.",
        "diagnostics": {},
    }
    if len(clean) < 30:
        return empty

    peaks, valleys, pivot_meta = find_adaptive_pivots(clean)
    cur_close = float(clean["close"].iloc[-1])
    atr = calculate_atr(clean)
    atr_value = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else cur_close * 0.02
    candidates = [
        detect_inverse_head_and_shoulders(peaks, valleys, cur_close),
        detect_double_bottom(peaks, valleys, cur_close),
        detect_triangles(peaks, valleys, cur_close),
        detect_double_top(peaks, valleys, cur_close),
    ]
    detected = [_pattern_quality(pattern, clean, atr_value) for pattern in candidates if pattern]
    if not detected:
        empty["diagnostics"] = {**pivot_meta, "peak_count": len(peaks), "valley_count": len(valleys)}
        return empty

    detected.sort(
        key=lambda pattern: (
            pattern["is_breakout"],
            pattern["price_confirmed"],
            pattern["confidence"],
            -pattern["age_bars"],
        ),
        reverse=True,
    )
    primary = detected[0]
    return {
        "has_pattern": True,
        "algorithm_version": "experimental-v2",
        "primary_pattern": primary,
        "detected_patterns": detected,
        "summary_badge": primary["status_text"],
        "summary_color": primary["badge_color"],
        "summary_desc": f"{primary['description']} 품질 {primary['quality_grade']}등급, {primary['confirmation_text']} 상태입니다.",
        "diagnostics": {**pivot_meta, "peak_count": len(peaks), "valley_count": len(valleys)},
    }


def _linear_slope(values: pd.Series) -> float:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if len(array) < 3:
        return 0.0
    x = np.arange(len(array), dtype=float)
    return float(np.polyfit(x, array, 1)[0])


def analyze_vcp_v2(df: pd.DataFrame, base_window: int = 90) -> Dict[str, Any]:
    """[C] Add volatility/supply diagnostics and a weighted VCP quality score."""
    clean = _prepare_ohlcv(df)
    base = detect_vcp_pattern(clean, base_window=base_window)
    base["algorithm_version"] = "experimental-v2"
    if len(clean) < 30:
        base.update(
            {
                "quality_score": 0,
                "quality_grade": "N/A",
                "score_components": {},
                "volatility": {"atr_ratio_pct": 0.0, "is_contracting": False},
                "supply": {"volume_slope_pct": 0.0, "up_down_volume_ratio": 0.0},
                "breakout_confirmation": {"is_confirmed": False, "volume_ratio": 0.0},
            }
        )
        return base

    atr = calculate_atr(clean)
    atr_pct = atr / clean["close"].replace(0, np.nan) * 100
    recent_atr_pct = float(atr_pct.tail(10).median())
    baseline_atr_pct = float(atr_pct.tail(50).median())
    atr_ratio = recent_atr_pct / max(baseline_atr_pct, 1e-9) * 100
    is_atr_contracting = atr_ratio <= 80.0

    volume20 = clean["volume"].tail(20).replace(0, np.nan).dropna()
    log_volume = np.log(volume20) if not volume20.empty else pd.Series(dtype=float)
    volume_slope = _linear_slope(log_volume)
    volume_slope_pct = (np.exp(volume_slope) - 1.0) * 100 if np.isfinite(volume_slope) else 0.0
    returns = clean["close"].pct_change()
    recent = clean.tail(30)
    recent_returns = returns.tail(30)
    up_volume = float(recent.loc[recent_returns >= 0, "volume"].sum())
    down_volume = float(recent.loc[recent_returns < 0, "volume"].sum())
    up_down_volume_ratio = up_volume / max(down_volume, 1e-9)

    prior_volume = float(clean["volume"].iloc[-51:-1].mean()) if len(clean) > 51 else float(clean["volume"].iloc[:-1].mean())
    breakout_volume_ratio = float(clean["volume"].iloc[-1] / max(prior_volume, 1e-9))
    pivot = base["pivot"]
    cur_close = float(clean["close"].iloc[-1])
    is_price_breakout = pivot["price"] > 0 and cur_close >= pivot["price"]
    is_breakout_confirmed = bool(is_price_breakout and breakout_volume_ratio >= 1.40)

    depths = [abs(float(item["depth_pct"])) for item in base.get("contractions", [])]
    pair_scores = [1.0 if current <= previous * 0.95 else 0.5 if current <= previous * 1.05 else 0.0 for previous, current in zip(depths, depths[1:])]
    diminishing_quality = float(np.mean(pair_scores)) if pair_scores else 0.0
    last_depth = depths[-1] if depths else 99.0
    pivot_distance = abs(float(pivot.get("dist_pct", 99.0)))

    components = {
        "trend_template": round(float(base["trend_template"].get("score_pct", 0.0)) * 0.25, 1),
        "diminishing_contractions": round(diminishing_quality * 20.0, 1),
        "tight_last_contraction": round(float(np.clip((12.0 - last_depth) / 12.0, 0.0, 1.0)) * 15.0, 1),
        "volume_dry_up": 15.0 if base["volume_dryup"]["is_vdu"] else round(float(np.clip((110.0 - base["volume_dryup"]["ratio"]) / 60.0, 0.0, 1.0)) * 15.0, 1),
        "atr_contraction": round(float(np.clip((115.0 - atr_ratio) / 45.0, 0.0, 1.0)) * 15.0, 1),
        "pivot_proximity": round(float(np.clip((8.0 - pivot_distance) / 8.0, 0.0, 1.0)) * 10.0, 1),
    }
    quality_score = int(round(sum(components.values())))
    if float(pivot.get("risk_pct", 0.0)) > 10.0:
        quality_score = max(0, quality_score - 8)
    quality_grade = "A" if quality_score >= 80 else "B" if quality_score >= 65 else "C" if quality_score >= 50 else "D"

    if is_breakout_confirmed and base["trend_template"].get("is_stage_2"):
        base.update({"vcp_status": "BREAKOUT", "status_badge": "🚀 VCP 거래량 돌파 확인", "status_color": "#16a34a"})
    elif quality_score >= 72 and base["trend_template"].get("is_stage_2") and pivot_distance <= 5.0:
        base.update({"vcp_status": "READY", "status_badge": f"🟢 VCP 품질 {quality_score}점 ({quality_grade}) · 피봇 대기", "status_color": "#22c55e"})
    elif quality_score >= 55 and len(depths) >= 2:
        base.update({"vcp_status": "DEVELOPING", "status_badge": f"🟡 VCP 형성 중 · 품질 {quality_score}점", "status_color": "#eab308"})

    base.update(
        {
            "quality_score": quality_score,
            "quality_grade": quality_grade,
            "score_components": components,
            "volatility": {
                "recent_atr_pct": round(recent_atr_pct, 2),
                "baseline_atr_pct": round(baseline_atr_pct, 2),
                "atr_ratio_pct": round(atr_ratio, 1),
                "is_contracting": bool(is_atr_contracting),
            },
            "supply": {
                "volume_slope_pct": round(volume_slope_pct, 2),
                "is_volume_trending_down": bool(volume_slope_pct < 0),
                "up_down_volume_ratio": round(up_down_volume_ratio, 2),
            },
            "breakout_confirmation": {
                "is_price_breakout": bool(is_price_breakout),
                "is_confirmed": is_breakout_confirmed,
                "volume_ratio": round(breakout_volume_ratio, 2),
                "required_volume_ratio": 1.40,
            },
        }
    )
    return base
