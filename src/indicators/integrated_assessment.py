"""A–D chart evidence distilled into a conditional long-entry plan."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def build_integrated_assessment(
    df: pd.DataFrame,
    sr: dict[str, Any],
    patterns: dict[str, Any],
    vcp: dict[str, Any] | None,
    v3: dict[str, Any] | None = None,
    v4: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe chart setup, conditional entry and invalidation without forecasting returns."""
    if df.empty or "close" not in df:
        return {"verdict": "자료 부족", "reason": "종가 데이터가 없습니다."}
    current = _price(df["close"].iloc[-1])
    if current is None:
        return {"verdict": "자료 부족", "reason": "유효한 최근 종가가 없습니다."}

    pattern = patterns.get("primary_pattern") or {}
    vcp = vcp or {}
    template = vcp.get("trend_template") or {}
    regime = (v3 or {}).get("regime") or {}
    flow = (v4 or {}).get("volume_flow") or {}
    trend = (v4 or {}).get("trend_strength") or {}
    momentum = (v4 or {}).get("momentum") or {}
    validation = (v4 or v3 or {}).get("validation") or {}
    sr_type = str(sr.get("breakout_type") or "")
    vcp_status = str(vcp.get("vcp_status") or "")

    volume_ratio = None
    if "volume" in df and len(df) >= 6:
        previous = pd.to_numeric(df["volume"].iloc[-21:-1], errors="coerce")
        last_volume = _price(df["volume"].iloc[-1])
        mean_volume = previous[previous > 0].mean()
        if last_volume and pd.notna(mean_volume) and mean_volume > 0:
            volume_ratio = last_volume / float(mean_volume)

    # Keep each selected entry tied to its own evidence; a nearby A level must
    # not silently replace a valid B/C breakout trigger.
    entry = None
    source = None
    required_volume = 1.2
    if pattern.get("type") == "bullish" and pattern.get("age_bars", 0) <= 30:
        entry = _price(pattern.get("neckline"))
        if entry:
            source = "[B] 상승 패턴 돌파선"
    if source is None and vcp_status in {"READY", "BREAKOUT"} and template.get("is_stage_2"):
        entry = _price((vcp.get("pivot") or {}).get("price"))
        if entry:
            source = "[C] VCP 피봇"
            required_volume = 1.4
    if source is None:
        resistance = sr.get("nearest_resistance") or {}
        upper = sr.get("upper_trendline") or {}
        candidates = [
            (_price(resistance.get("zone_high") or resistance.get("price")), "[A] 저항 구간 상단"),
            (_price(upper.get("current_price")), "[A] 상단 추세선"),
        ]
        candidates = [(value, label) for value, label in candidates if value and value >= current * 0.98]
        if candidates:
            entry, source = min(candidates, key=lambda item: abs(item[0] - current))

    # A stop must lie below both today's close and the hypothetical entry.
    # A bearish pattern's stop is for a short thesis and is never used here.
    primary_stops: list[tuple[float, str]] = []
    if source and source.startswith("[B]"):
        primary_stops.append((_price(pattern.get("stop_loss")) or 0, "[B] 패턴 저점"))
    if source and source.startswith("[C]"):
        primary_stops.append((_price((vcp.get("pivot") or {}).get("stop_loss")) or 0, "[C] 최종 수축 저점"))
    support = sr.get("nearest_support") or {}
    lower = sr.get("lower_trendline") or {}
    structural_stops = [
        (_price(support.get("zone_low") or support.get("price")) or 0, "[A] 지지 구간 하단"),
        (_price(lower.get("current_price")) or 0, "[A] 하단 추세선"),
    ]
    dynamic_stops = []
    if trend.get("supertrend_direction") == "상승":
        dynamic_stops.append((_price(trend.get("supertrend_stop")) or 0, "[D] SuperTrend"))
    ceiling = min(current, entry) if entry else current
    stop, stop_source = None, None
    for candidates in (primary_stops, structural_stops, dynamic_stops):
        valid = [(value, label) for value, label in candidates if 0 < value < ceiling * 0.997]
        if valid:
            stop, stop_source = max(valid, key=lambda item: item[0])
            break

    planning_entry = max(current, entry) if entry else None
    risk_pct = ((planning_entry - stop) / planning_entry * 100) if planning_entry and stop else None
    target = None
    target_source = None
    if pattern.get("type") == "bullish" and source and source.startswith("[B]"):
        target = _price(pattern.get("target_price"))
        target_source = "[B] 패턴 목표"
    if not target or (planning_entry and target <= planning_entry):
        resistances = sr.get("resistance_levels") or []
        above = [(_price(level.get("price")), "[A] 다음 저항") for level in resistances]
        above = [(value, label) for value, label in above if value and planning_entry and value > planning_entry]
        target, target_source = min(above, default=(None, None), key=lambda item: item[0])
    reward_risk = ((target - planning_entry) / (planning_entry - stop)) if target and planning_entry and stop else None

    bearish_pattern = pattern.get("type") == "bearish"
    downtrend = regime.get("trend") == "하락 추세" or (
        trend.get("is_valid") and trend.get("supertrend_direction") == "하락" and trend.get("plus_di", 0) < trend.get("minus_di", 0)
    )
    breakdown = sr_type == "lower_trendline_breakdown"
    stage_fail = vcp_status == "STAGE_FAIL"
    blockers = []
    if bearish_pattern:
        blockers.append("[B] 하락 패턴이 우세")
    if downtrend:
        blockers.append("[D] 하락 추세")
    if breakdown:
        blockers.append("[A] 하단 추세선 이탈")
    if stage_fail:
        blockers.append("[C] Stage 2 추세 조건 미달")
    if source and source.startswith("[B]") and (_price(pattern.get("stop_loss")) or 0) >= current:
        blockers.append("[B] 패턴 무효화 가격을 이미 이탈")
    if source and source.startswith("[C]") and (_price((vcp.get("pivot") or {}).get("stop_loss")) or 0) >= current:
        blockers.append("[C] VCP 무효화 가격을 이미 이탈")
    if flow.get("state") == "분산 우세":
        blockers.append("[D] 거래량 흐름에서 분산 우세")
    if entry is None:
        blockers.append("유효한 진입 기준 가격 없음")
    if stop is None:
        blockers.append("유효한 손절 기준 가격 없음")
    if risk_pct is not None and risk_pct > 10:
        blockers.append(f"가정 손절 폭 {risk_pct:.1f}% (10% 초과)")
    if reward_risk is not None and reward_risk < 1.5:
        blockers.append(f"참고 손익비 {reward_risk:.1f}:1 (1.5:1 미만)")

    confirmed = bool(entry and current >= entry and volume_ratio is not None and volume_ratio >= required_volume)
    if source and source.startswith("[B]") and "price_confirmed" in pattern:
        confirmed = confirmed and bool(pattern.get("is_breakout"))
    if source and source.startswith("[C]") and "breakout_confirmation" in vcp:
        confirmed = confirmed and bool(vcp["breakout_confirmation"].get("is_confirmed"))
    if source and source.startswith("[A]") and sr.get("algorithm_version") == "experimental-v2":
        expected_type = "upper_trendline_breakout_confirmed" if "추세선" in source else "resistance_breakout_confirmed"
        confirmed = confirmed and sr_type == expected_type
    extended = bool(entry and current > entry * 1.05)
    if extended:
        blockers.append("돌파선 대비 5% 넘게 이격되어 추격 진입 위험")
    if blockers:
        verdict = "신규 진입 보류"
    elif confirmed and v3 and template.get("is_stage_2"):
        verdict = "조건 충족 · 확인 필요"
    else:
        verdict = "조건부 관찰"

    shape = " · ".join(filter(None, [
        regime.get("trend") or "추세 환경 미제공",
        regime.get("volatility"),
        sr.get("status_badge") or "지지·저항 판정 없음",
        pattern.get("name") if pattern else None,
        vcp.get("status_badge") if vcp_status in {"READY", "BREAKOUT", "DEVELOPING"} else None,
    ]))
    rp = template.get("rp_rating")
    rp_text = f" · RP {rp:.1f}" if isinstance(rp, (int, float)) and math.isfinite(rp) else " · RP 미확인"
    sample_count = int(validation.get("sample_count") or 0)
    validation_text = (
        f" · 과거 신호 {sample_count}건/10일 평균 {validation.get('avg_return_pct', 0):+.1f}%"
        if sample_count >= 5 else f" · 과거 검증 표본 부족({sample_count}건)" if v3 else ""
    )
    evidence = [
        ("[A] 지지·저항", sr.get("status_badge") or "분석 없음"),
        ("[B] 가격 패턴", f"{pattern.get('name')} · {'돌파 확인' if pattern.get('is_breakout') else '형성/대기'}" if pattern else "뚜렷한 패턴 없음"),
        ("[C] 추세·VCP", f"템플릿 {template.get('pass_count', '–')}/{template.get('total_count', '–')}{rp_text} · {vcp.get('status_badge', '분석 없음')}"),
        ("[D] 추세·수급", f"{regime.get('regime', '엔진 v3/v4에서 제공')} · 수급 {flow.get('state', '미제공')} · 모멘텀 {momentum.get('direction', '미제공')}{validation_text}"),
    ]
    return {
        "verdict": verdict,
        "current": current,
        "shape": shape,
        "evidence": evidence,
        "entry": entry,
        "entry_source": source,
        "required_volume": required_volume,
        "volume_ratio": volume_ratio,
        "confirmed": confirmed,
        "stop": stop,
        "stop_source": stop_source,
        "risk_pct": risk_pct,
        "target": target,
        "target_source": target_source,
        "reward_risk": reward_risk,
        "blockers": blockers,
        "d_available": bool(v3),
    }
