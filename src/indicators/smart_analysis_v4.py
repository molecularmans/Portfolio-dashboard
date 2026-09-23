"""Experimental v4 confirmation engine.

V4 keeps the structural A/B/C analysis from v3 and adds momentum, money-flow,
trend-strength and dynamic-risk confirmation.  The formulas are implemented in
NumPy/Pandas so deployment does not require TA-Lib or a trading framework.

Design references (ideas only, no copied implementation):
* TA-Lib Python / bukosabino-ta: RSI, StochRSI, MFI, OBV, CMF and ADX/DMI.
* Jesse: multi-indicator confirmation and SuperTrend-style dynamic stops.
* Backtrader / QuantConnect Lean: identical-event strategy comparison.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from src.indicators.smart_analysis_v2 import _prepare_ohlcv, calculate_atr, find_adaptive_pivots
from src.indicators.smart_analysis_v3 import analyze_smart_chart_v3


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def _grade(score: float) -> str:
    return "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    result = 100.0 - 100.0 / (1.0 + rs)
    return result.where(loss > 0, 100.0).clip(0, 100)


def _momentum_series(clean: pd.DataFrame) -> Dict[str, pd.Series]:
    rsi = _rsi(clean["close"], 14)
    rsi_low = rsi.rolling(14, min_periods=8).min()
    rsi_high = rsi.rolling(14, min_periods=8).max()
    stoch_rsi = (rsi - rsi_low) / (rsi_high - rsi_low).replace(0, np.nan) * 100.0
    k = stoch_rsi.rolling(3, min_periods=1).mean()
    d = k.rolling(3, min_periods=1).mean()
    return {"rsi": rsi, "stoch_rsi": stoch_rsi, "stoch_k": k, "stoch_d": d}


def analyze_momentum_confirmation(df: pd.DataFrame) -> Dict[str, Any]:
    """Score RSI/StochRSI direction and price/momentum divergences."""
    clean = _prepare_ohlcv(df)
    if len(clean) < 35:
        return {"is_valid": False, "score": 50, "direction": "중립", "divergence": "없음"}

    series = _momentum_series(clean)
    rsi = series["rsi"]
    k = series["stoch_k"]
    d = series["stoch_d"]
    peaks, valleys, _ = find_adaptive_pivots(clean)
    recent_floor = max(0, len(clean) - 120)
    peaks = [point for point in peaks if point["idx"] >= recent_floor and pd.notna(rsi.iloc[point["idx"]])]
    valleys = [point for point in valleys if point["idx"] >= recent_floor and pd.notna(rsi.iloc[point["idx"]])]

    bullish_divergence = False
    bearish_divergence = False
    divergence_detail = "없음"
    if len(valleys) >= 2:
        first, second = valleys[-2], valleys[-1]
        rsi_first, rsi_second = float(rsi.iloc[first["idx"]]), float(rsi.iloc[second["idx"]])
        bullish_divergence = second["price"] < first["price"] * 0.995 and rsi_second > rsi_first + 3.0
        if bullish_divergence:
            divergence_detail = f"상승 다이버전스 · RSI {rsi_first:.1f}→{rsi_second:.1f}"
    if len(peaks) >= 2:
        first, second = peaks[-2], peaks[-1]
        rsi_first, rsi_second = float(rsi.iloc[first["idx"]]), float(rsi.iloc[second["idx"]])
        bearish_divergence = second["price"] > first["price"] * 1.005 and rsi_second < rsi_first - 3.0
        if bearish_divergence:
            divergence_detail = f"하락 다이버전스 · RSI {rsi_first:.1f}→{rsi_second:.1f}"

    current_rsi = _safe_float(rsi.iloc[-1], 50.0)
    current_k = _safe_float(k.iloc[-1], 50.0)
    current_d = _safe_float(d.iloc[-1], 50.0)
    rsi_change = current_rsi - _safe_float(rsi.iloc[-4], current_rsi)
    bullish_cross = bool(current_k > current_d and _safe_float(k.iloc[-2]) <= _safe_float(d.iloc[-2]))
    bearish_cross = bool(current_k < current_d and _safe_float(k.iloc[-2]) >= _safe_float(d.iloc[-2]))

    score = 50.0
    score += float(np.clip(rsi_change * 1.5, -12, 12))
    score += 8 if current_rsi >= 50 else -8
    score += 8 if current_k > current_d else -8
    score += 22 if bullish_divergence else -22 if bearish_divergence else 0
    score += 7 if bullish_cross else -7 if bearish_cross else 0
    if current_rsi >= 78:
        score -= 10
    elif current_rsi <= 22:
        score += 5
    score = int(np.clip(round(score), 0, 100))
    direction = "상승 우세" if score >= 62 else "하락 우세" if score <= 38 else "중립"
    return {
        "is_valid": True,
        "score": score,
        "direction": direction,
        "rsi": round(current_rsi, 1),
        "rsi_change_3d": round(rsi_change, 1),
        "stoch_rsi_k": round(current_k, 1),
        "stoch_rsi_d": round(current_d, 1),
        "bullish_cross": bullish_cross,
        "bearish_cross": bearish_cross,
        "bullish_divergence": bool(bullish_divergence),
        "bearish_divergence": bool(bearish_divergence),
        "divergence": divergence_detail,
        "summary": f"{direction} · RSI {current_rsi:.1f} · StochRSI {current_k:.1f}/{current_d:.1f} · {divergence_detail}",
    }


def _volume_flow_series(clean: pd.DataFrame) -> Dict[str, pd.Series]:
    close, high, low, volume = clean["close"], clean["high"], clean["low"], clean["volume"]
    direction = np.sign(close.diff()).fillna(0.0)
    obv = (direction * volume).cumsum()
    multiplier = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    money_flow_volume = multiplier.fillna(0.0) * volume
    cmf = money_flow_volume.rolling(20, min_periods=10).sum() / volume.rolling(20, min_periods=10).sum().replace(0, np.nan)

    typical = (high + low + close) / 3.0
    raw_flow = typical * volume
    positive = raw_flow.where(typical.diff() > 0, 0.0)
    negative = raw_flow.where(typical.diff() < 0, 0.0).abs()
    pos_sum = positive.rolling(14, min_periods=8).sum()
    neg_sum = negative.rolling(14, min_periods=8).sum()
    ratio = pos_sum / neg_sum.replace(0, np.nan)
    mfi = (100.0 - 100.0 / (1.0 + ratio)).where(neg_sum > 0, 100.0).clip(0, 100)
    return {"obv": obv, "cmf": cmf, "mfi": mfi}


def _normalised_slope(values: pd.Series, scale: float) -> float:
    array = values.dropna().to_numpy(dtype=float)
    if len(array) < 5:
        return 0.0
    slope = float(np.polyfit(np.arange(len(array), dtype=float), array, 1)[0])
    return slope / max(abs(scale), 1e-9)


def analyze_volume_flow(df: pd.DataFrame) -> Dict[str, Any]:
    """Measure accumulation/distribution with OBV, CMF and MFI consensus."""
    clean = _prepare_ohlcv(df)
    if len(clean) < 35:
        return {"is_valid": False, "score": 50, "state": "중립"}

    series = _volume_flow_series(clean)
    avg_volume = _safe_float(clean["volume"].tail(30).mean(), 1.0)
    obv_slope = _normalised_slope(series["obv"].tail(20), avg_volume)
    price_slope = _normalised_slope(clean["close"].tail(20), _safe_float(clean["close"].tail(20).mean(), 1.0))
    cmf = _safe_float(series["cmf"].iloc[-1])
    mfi = _safe_float(series["mfi"].iloc[-1], 50.0)
    bullish_divergence = price_slope < -0.001 and obv_slope > 0.03
    bearish_divergence = price_slope > 0.001 and obv_slope < -0.03

    score = 50.0
    score += float(np.clip(obv_slope * 18.0, -18, 18))
    score += float(np.clip(cmf * 65.0, -18, 18))
    score += float(np.clip((mfi - 50.0) * 0.45, -15, 15))
    score += 10 if bullish_divergence else -10 if bearish_divergence else 0
    if mfi >= 85:
        score -= 8
    score = int(np.clip(round(score), 0, 100))
    state = "매집 우세" if score >= 62 else "분산 우세" if score <= 38 else "중립"
    return {
        "is_valid": True,
        "score": score,
        "state": state,
        "obv_slope": round(obv_slope, 3),
        "cmf_20": round(cmf, 3),
        "mfi_14": round(mfi, 1),
        "bullish_divergence": bool(bullish_divergence),
        "bearish_divergence": bool(bearish_divergence),
        "summary": f"{state} · OBV 기울기 {obv_slope:+.3f} · CMF {cmf:+.3f} · MFI {mfi:.1f}",
    }


def _trend_strength_series(clean: pd.DataFrame, period: int = 14, multiplier: float = 3.0) -> Dict[str, pd.Series]:
    high, low, close = clean["high"], clean["low"], clean["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = calculate_atr(clean, period).bfill()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100.0
    adx = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    trend = pd.Series(1, index=clean.index, dtype=int)
    for idx in range(1, len(clean)):
        if basic_upper.iloc[idx] < final_upper.iloc[idx - 1] or close.iloc[idx - 1] > final_upper.iloc[idx - 1]:
            final_upper.iloc[idx] = basic_upper.iloc[idx]
        else:
            final_upper.iloc[idx] = final_upper.iloc[idx - 1]
        if basic_lower.iloc[idx] > final_lower.iloc[idx - 1] or close.iloc[idx - 1] < final_lower.iloc[idx - 1]:
            final_lower.iloc[idx] = basic_lower.iloc[idx]
        else:
            final_lower.iloc[idx] = final_lower.iloc[idx - 1]

        if close.iloc[idx] > final_upper.iloc[idx - 1]:
            trend.iloc[idx] = 1
        elif close.iloc[idx] < final_lower.iloc[idx - 1]:
            trend.iloc[idx] = -1
        else:
            trend.iloc[idx] = trend.iloc[idx - 1]
            if trend.iloc[idx] > 0 and final_lower.iloc[idx] < final_lower.iloc[idx - 1]:
                final_lower.iloc[idx] = final_lower.iloc[idx - 1]
            if trend.iloc[idx] < 0 and final_upper.iloc[idx] > final_upper.iloc[idx - 1]:
                final_upper.iloc[idx] = final_upper.iloc[idx - 1]
    supertrend = final_lower.where(trend > 0, final_upper)
    return {"adx": adx, "plus_di": plus_di, "minus_di": minus_di, "supertrend": supertrend, "trend": trend}


def analyze_trend_strength(df: pd.DataFrame) -> Dict[str, Any]:
    """Confirm direction with ADX/DMI and calculate a SuperTrend stop."""
    clean = _prepare_ohlcv(df)
    if len(clean) < 45:
        return {"is_valid": False, "score": 50, "state": "데이터 부족", "supertrend_stop": 0.0}
    series = _trend_strength_series(clean)
    adx = _safe_float(series["adx"].iloc[-1])
    plus_di = _safe_float(series["plus_di"].iloc[-1])
    minus_di = _safe_float(series["minus_di"].iloc[-1])
    trend = int(series["trend"].iloc[-1])
    stop = _safe_float(series["supertrend"].iloc[-1])
    strength = min(30.0, adx * 0.8)
    score = 50.0 + strength if plus_di > minus_di else 50.0 - strength
    score += 8 if trend > 0 else -8
    score = int(np.clip(round(score), 0, 100))
    trend_label = "상승" if plus_di > minus_di else "하락"
    strength_label = "강한 추세" if adx >= 25 else "약한 추세" if adx >= 18 else "횡보 가능"
    return {
        "is_valid": True,
        "score": score,
        "state": f"{trend_label} · {strength_label}",
        "adx": round(adx, 1),
        "plus_di": round(plus_di, 1),
        "minus_di": round(minus_di, 1),
        "supertrend_direction": "상승" if trend > 0 else "하락",
        "supertrend_stop": round(stop, 4),
        "summary": f"{trend_label} {strength_label} · ADX {adx:.1f} · +DI {plus_di:.1f} / -DI {minus_di:.1f}",
    }


def _evaluate_events(clean: pd.DataFrame, signal: pd.Series, horizon: int, cost_pct: float) -> Dict[str, Any]:
    signal_indices: List[int] = []
    next_allowed = 0
    for idx in np.flatnonzero(signal.fillna(False).to_numpy()):
        if idx >= next_allowed and idx + horizon < len(clean):
            signal_indices.append(int(idx))
            next_allowed = int(idx) + horizon + 1

    events: List[Dict[str, Any]] = []
    for idx in signal_indices:
        entry = float(clean["close"].iloc[idx])
        future = clean.iloc[idx + 1 : idx + horizon + 1]
        gross_return = (float(clean["close"].iloc[idx + horizon]) / entry - 1.0) * 100.0
        events.append(
            {
                "idx": idx,
                "date": str(clean["date"].iloc[idx]),
                "net_return_pct": round(gross_return - cost_pct, 2),
                "mfe_pct": round((float(future["high"].max()) / entry - 1.0) * 100.0, 2),
                "mae_pct": round((float(future["low"].min()) / entry - 1.0) * 100.0, 2),
            }
        )
    returns = np.asarray([event["net_return_pct"] for event in events], dtype=float)
    mfes = np.asarray([event["mfe_pct"] for event in events], dtype=float)
    maes = np.asarray([event["mae_pct"] for event in events], dtype=float)
    count = len(events)
    hit_rate = float(np.mean(returns > 0) * 100.0) if count else 0.0
    avg_return = float(np.mean(returns)) if count else 0.0
    score = int(np.clip(50 + avg_return * 5 + (hit_rate - 50) * 0.5, 0, 100)) if count else 50
    return {
        "is_valid": count >= 5,
        "sample_count": count,
        "horizon_days": horizon,
        "hit_rate_pct": round(hit_rate, 1),
        "avg_return_pct": round(avg_return, 2),
        "median_return_pct": round(float(np.median(returns)), 2) if count else 0.0,
        "avg_mfe_pct": round(float(np.mean(mfes)), 2) if count else 0.0,
        "avg_mae_pct": round(float(np.mean(maes)), 2) if count else 0.0,
        "cost_pct": cost_pct,
        "score": score,
        "signals": events,
        "no_lookahead": True,
        "warning": "표본 5건 미만: v3/v4 우열 판단을 보류하세요." if count < 5 else "수수료·슬리피지 가정이 반영된 과거 결과입니다.",
    }


def walk_forward_v4_validation(df: pd.DataFrame, horizon: int = 10, cost_pct: float = 0.20) -> Dict[str, Any]:
    """Validate breakout events after momentum/flow/trend confirmation."""
    clean = _prepare_ohlcv(df)
    if len(clean) < 80:
        return _evaluate_events(clean, pd.Series(False, index=clean.index), horizon, cost_pct)

    prior_high = clean["high"].rolling(20, min_periods=20).max().shift(1)
    prior_volume = clean["volume"].rolling(20, min_periods=20).mean().shift(1)
    width = clean["close"].rolling(20).std(ddof=0) * 4.0 / clean["close"].rolling(20).mean().replace(0, np.nan)
    width_threshold = width.rolling(60, min_periods=30).quantile(0.40).shift(1)
    compressed = (width.shift(1) <= width_threshold).rolling(10, min_periods=1).max().fillna(0).astype(bool)
    base_breakout = (clean["close"] > prior_high) & (clean["volume"] >= prior_volume * 1.15) & compressed

    momentum = _momentum_series(clean)
    flow = _volume_flow_series(clean)
    trend = _trend_strength_series(clean)
    momentum_ok = (momentum["rsi"] >= 45) & (momentum["rsi"] <= 78) & (momentum["rsi"] > momentum["rsi"].shift(3))
    flow_ok = (flow["cmf"] > -0.05) & (flow["mfi"] >= 45) & (flow["obv"] > flow["obv"].rolling(10).mean().shift(1))
    trend_ok = (trend["adx"] >= 18) & (trend["plus_di"] > trend["minus_di"]) & (trend["trend"] > 0)
    confirmation_count = momentum_ok.astype(int) + flow_ok.astype(int) + trend_ok.astype(int)
    signal = (base_breakout & (confirmation_count >= 2)).fillna(False)
    result = _evaluate_events(clean, signal, horizon, cost_pct)
    result["confirmation_rule"] = "돌파 + 모멘텀/수급/추세 중 2개 이상"
    return result


def _engine_comparison(v3_validation: Dict[str, Any], v4_validation: Dict[str, Any], cost_pct: float = 0.20) -> Dict[str, Any]:
    v3_avg_net = _safe_float(v3_validation.get("avg_return_pct")) - cost_pct if v3_validation.get("sample_count", 0) else 0.0
    return {
        "v3": {
            "sample_count": int(v3_validation.get("sample_count", 0)),
            "hit_rate_pct": _safe_float(v3_validation.get("hit_rate_pct")),
            "avg_return_pct": round(v3_avg_net, 2),
            "avg_mfe_pct": _safe_float(v3_validation.get("avg_mfe_pct")),
            "avg_mae_pct": _safe_float(v3_validation.get("avg_mae_pct")),
        },
        "v4": {
            "sample_count": int(v4_validation.get("sample_count", 0)),
            "hit_rate_pct": _safe_float(v4_validation.get("hit_rate_pct")),
            "avg_return_pct": _safe_float(v4_validation.get("avg_return_pct")),
            "avg_mfe_pct": _safe_float(v4_validation.get("avg_mfe_pct")),
            "avg_mae_pct": _safe_float(v4_validation.get("avg_mae_pct")),
        },
        "cost_pct": cost_pct,
        "comparable": min(int(v3_validation.get("sample_count", 0)), int(v4_validation.get("sample_count", 0))) >= 5,
    }


def analyze_smart_chart_v4(df: pd.DataFrame) -> Dict[str, Any]:
    """Run v3 structural analysis plus v4 confirmation and comparison layers."""
    v3 = analyze_smart_chart_v3(df)
    momentum = analyze_momentum_confirmation(df)
    volume_flow = analyze_volume_flow(df)
    trend_strength = analyze_trend_strength(df)
    validation = walk_forward_v4_validation(df)
    comparison = _engine_comparison(v3["validation"], validation, validation.get("cost_pct", 0.20))

    components = {
        "v3_structure": _safe_float(v3.get("composite_score", 50)) * 0.50,
        "momentum": _safe_float(momentum.get("score", 50)) * 0.15,
        "volume_flow": _safe_float(volume_flow.get("score", 50)) * 0.15,
        "trend_strength": _safe_float(trend_strength.get("score", 50)) * 0.20,
    }
    composite = int(np.clip(round(sum(components.values())), 0, 100))
    verdict = "긍정 우세" if composite >= 72 else "관찰" if composite >= 58 else "중립" if composite >= 43 else "위험 우세"

    current_price = _safe_float(_prepare_ohlcv(df)["close"].iloc[-1]) if len(_prepare_ohlcv(df)) else 0.0
    pattern = v3["patterns"].get("primary_pattern")
    structural_stop = _safe_float(pattern.get("stop_loss")) if pattern else 0.0
    dynamic_stop = _safe_float(trend_strength.get("supertrend_stop"))
    valid_stops = [stop for stop in (structural_stop, dynamic_stop) if 0 < stop < current_price]
    suggested_stop = max(valid_stops) if valid_stops else 0.0

    return {
        "algorithm_version": "experimental-v4",
        "support_resistance": v3["support_resistance"],
        "patterns": v3["patterns"],
        "vcp": v3["vcp"],
        "candlesticks": v3["candlesticks"],
        "squeeze": v3["squeeze"],
        "regime": v3["regime"],
        "momentum": momentum,
        "volume_flow": volume_flow,
        "trend_strength": trend_strength,
        "validation": validation,
        "comparison": comparison,
        "v3_baseline": v3,
        "composite_score": composite,
        "grade": _grade(composite),
        "verdict": verdict,
        "score_components": {key: round(value, 1) for key, value in components.items()},
        "risk_control": {
            "structural_stop": round(structural_stop, 4),
            "supertrend_stop": round(dynamic_stop, 4),
            "suggested_stop": round(suggested_stop, 4),
        },
        "research_only": True,
    }
