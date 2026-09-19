import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from src.indicators.trendline_analyzer import find_local_extrema


def detect_double_bottom(
    peaks: List[Dict[str, Any]],
    valleys: List[Dict[str, Any]],
    cur_close: float
) -> Optional[Dict[str, Any]]:
    """
    이중 바닥 (Double Bottom / W 패턴) 감지
    """
    if len(valleys) < 2 or len(peaks) < 1:
        return None

    # 최근 3개의 저점 및 2개의 고점 중 최적의 쌍바닥 조합 탐색
    candidate_valleys = valleys[-4:]
    for i in range(len(candidate_valleys) - 1):
        v1 = candidate_valleys[i]
        v2 = candidate_valleys[i + 1]

        # 저점 간의 시간 간격 (최소 7거래일 이상, 최대 70거래일)
        dt = v2["idx"] - v1["idx"]
        if not (7 <= dt <= 70):
            continue

        # 두 저점 간 가격 차이 허용치 (최대 3.5%)
        price_diff_pct = abs(v1["price"] - v2["price"]) / min(v1["price"], v2["price"])
        if price_diff_pct > 0.035:
            continue

        # 두 저점 사이에 고점(넥라인)이 존재하는지 확인
        between_peaks = [p for p in peaks if v1["idx"] < p["idx"] < v2["idx"]]
        if not between_peaks:
            continue

        neckline_peak = max(between_peaks, key=lambda p: p["price"])
        neckline_price = neckline_peak["price"]
        base_low = min(v1["price"], v2["price"])
        pattern_depth = neckline_price - base_low

        # 넥라인이 바닥 대비 최소 4% 이상 높아야 유효한 바닥 패턴
        if pattern_depth / base_low < 0.04:
            continue

        target_price = round(neckline_price + pattern_depth, 2)
        stop_loss = round(min(v1["price"], v2["price"]) * 0.985, 2)

        # 완성 및 돌파 상태 판정
        is_breakout = cur_close >= neckline_price * 0.998
        is_forming = not is_breakout and cur_close >= v2["price"]

        if not (is_breakout or is_forming):
            continue

        confidence = int(max(60, min(95, (1.0 - price_diff_pct * 10) * 100)))
        status_text = "🚀 넥라인 상향 돌파 (매수 급소)" if is_breakout else "⏳ 우측 바닥 완성 후 넥라인 테스트"

        return {
            "name": "이중 바닥 (Double Bottom / W패턴)",
            "type": "bullish",
            "status_text": status_text,
            "badge_color": "#26a69a" if is_breakout else "#00BCD4",
            "is_breakout": is_breakout,
            "neckline": round(neckline_price, 2),
            "target_price": target_price,
            "stop_loss": stop_loss,
            "potential_upside_pct": round((target_price - cur_close) / cur_close * 100, 1),
            "risk_pct": round((cur_close - stop_loss) / cur_close * 100, 1),
            "confidence": confidence,
            "key_points": [v1, neckline_peak, v2],
            "description": f"두 차례의 저점(${v1['price']:,.2f}, ${v2['price']:,.2f}) 지지 확인 후 넥라인(${neckline_price:,.2f})을 형성한 전형적인 상승 반전 패턴입니다.",
        }

    return None


def detect_double_top(
    peaks: List[Dict[str, Any]],
    valleys: List[Dict[str, Any]],
    cur_close: float
) -> Optional[Dict[str, Any]]:
    """
    이중 천장 (Double Top / M 패턴) 감지
    """
    if len(peaks) < 2 or len(valleys) < 1:
        return None

    candidate_peaks = peaks[-4:]
    for i in range(len(candidate_peaks) - 1):
        p1 = candidate_peaks[i]
        p2 = candidate_peaks[i + 1]

        dt = p2["idx"] - p1["idx"]
        if not (7 <= dt <= 70):
            continue

        price_diff_pct = abs(p1["price"] - p2["price"]) / max(p1["price"], p2["price"])
        if price_diff_pct > 0.035:
            continue

        between_valleys = [v for v in valleys if p1["idx"] < v["idx"] < p2["idx"]]
        if not between_valleys:
            continue

        neckline_valley = min(between_valleys, key=lambda v: v["price"])
        neckline_price = neckline_valley["price"]
        top_high = max(p1["price"], p2["price"])
        pattern_height = top_high - neckline_price

        if pattern_height / top_high < 0.04:
            continue

        target_price = round(neckline_price - pattern_height, 2)
        stop_loss = round(top_high * 1.015, 2)

        is_breakdown = cur_close <= neckline_price * 1.002

        if cur_close < neckline_price * 0.90:  # 너무 많이 무너진 과거 패턴은 무시
            continue

        confidence = int(max(60, min(95, (1.0 - price_diff_pct * 10) * 100)))
        status_text = "⚠️ 넥라인 하향 이탈 (하락 반전)" if is_breakdown else "🛑 우측 고점 저항 확인 (경계)"

        return {
            "name": "이중 천장 (Double Top / M패턴)",
            "type": "bearish",
            "status_text": status_text,
            "badge_color": "#ef5350" if is_breakdown else "#f59e0b",
            "is_breakout": is_breakdown,
            "neckline": round(neckline_price, 2),
            "target_price": target_price,
            "stop_loss": stop_loss,
            "potential_upside_pct": round((target_price - cur_close) / cur_close * 100, 1),
            "risk_pct": round((stop_loss - cur_close) / cur_close * 100, 1),
            "confidence": confidence,
            "key_points": [p1, neckline_valley, p2],
            "description": f"두 차례의 고점(${p1['price']:,.2f}, ${p2['price']:,.2f}) 돌파 실패 후 넥라인(${neckline_price:,.2f})을 위협하는 하락 반전 패턴입니다.",
        }

    return None


def detect_inverse_head_and_shoulders(
    peaks: List[Dict[str, Any]],
    valleys: List[Dict[str, Any]],
    cur_close: float
) -> Optional[Dict[str, Any]]:
    """
    역헤드앤숄더 (Inverse Head and Shoulders) 감지
    """
    if len(valleys) < 3 or len(peaks) < 2:
        return None

    # 최근 5개의 저점 중 좌측어깨(LS), 머리(Head), 우측어깨(RS) 구조 탐색
    for i in range(len(valleys) - 2):
        ls = valleys[i]
        head = valleys[i + 1]
        rs = valleys[i + 2]

        # 머리가 양 어깨보다 확실히 낮아야 함 (최소 2% 이상)
        if not (head["price"] < ls["price"] * 0.98 and head["price"] < rs["price"] * 0.98):
            continue

        # 좌/우 어깨의 가격 유사도 (5% 이내)
        shoulder_diff = abs(ls["price"] - rs["price"]) / min(ls["price"], rs["price"])
        if shoulder_diff > 0.05:
            continue

        # 중간 고점들 (넥라인 후보)
        p1_list = [p for p in peaks if ls["idx"] < p["idx"] < head["idx"]]
        p2_list = [p for p in peaks if head["idx"] < p["idx"] < rs["idx"]]
        if not p1_list or not p2_list:
            continue

        p1 = max(p1_list, key=lambda p: p["price"])
        p2 = max(p2_list, key=lambda p: p["price"])
        neckline_price = (p1["price"] + p2["price"]) / 2.0

        pattern_depth = neckline_price - head["price"]
        target_price = round(neckline_price + pattern_depth, 2)
        stop_loss = round(rs["price"] * 0.985, 2)

        is_breakout = cur_close >= neckline_price * 0.995

        confidence = int(max(65, min(95, (1.0 - shoulder_diff * 8) * 100)))
        status_text = "🚀 넥라인 돌파 완료 (강력 매수 신호)" if is_breakout else "⏳ 우측 어깨 형성 후 넥라인 접근 중"

        return {
            "name": "역헤드앤숄더 (Inverse Head & Shoulders)",
            "type": "bullish",
            "status_text": status_text,
            "badge_color": "#26a69a" if is_breakout else "#38bdf8",
            "is_breakout": is_breakout,
            "neckline": round(neckline_price, 2),
            "target_price": target_price,
            "stop_loss": stop_loss,
            "potential_upside_pct": round((target_price - cur_close) / cur_close * 100, 1),
            "risk_pct": round((cur_close - stop_loss) / cur_close * 100, 1),
            "confidence": confidence,
            "key_points": [ls, p1, head, p2, rs],
            "description": f"좌측 어깨(${ls['price']:,.2f}), 머리(${head['price']:,.2f}), 우측 어깨(${rs['price']:,.2f})가 완성된 신뢰도 높은 바닥 반전 패턴입니다.",
        }

    return None


def detect_triangles(
    peaks: List[Dict[str, Any]],
    valleys: List[Dict[str, Any]],
    cur_close: float
) -> Optional[Dict[str, Any]]:
    """
    삼각수렴 패턴 (Symmetrical / Ascending / Descending Triangle) 감지
    """
    if len(peaks) < 2 or len(valleys) < 2:
        return None

    # 최근 2개의 고점과 2개의 저점 확인
    p1, p2 = peaks[-2], peaks[-1]
    v1, v2 = valleys[-2], valleys[-1]

    # 시간 순서 검증 (최근 60거래일 이내)
    min_idx = min(p1["idx"], v1["idx"])
    max_idx = max(p2["idx"], v2["idx"])
    if max_idx - min_idx < 10 or max_idx - min_idx > 80:
        return None

    # 고점 기울기 vs 저점 기울기
    slope_high = (p2["price"] - p1["price"]) / (p2["idx"] - p1["idx"])
    slope_low = (v2["price"] - v1["price"]) / (v2["idx"] - v1["idx"])

    # 수렴 폭 계산 (처음 폭 vs 마지막 폭)
    initial_range = abs(p1["price"] - v1["price"])
    latest_range = abs(p2["price"] - v2["price"])

    if initial_range <= 0 or latest_range / initial_range > 0.75:
        return None  # 수축되지 않음

    triangle_type = "대칭 삼각수렴"
    badge_color = "#38bdf8"
    p_type = "neutral"

    # 상승 삼각수렴 (고점 평평, 저점 우상향)
    if abs(p2["price"] - p1["price"]) / p1["price"] < 0.02 and slope_low > 0:
        triangle_type = "상승 삼각수렴 (Ascending Triangle)"
        badge_color = "#26a69a"
        p_type = "bullish"
    # 하락 삼각수렴 (저점 평평, 고점 우하향)
    elif abs(v2["price"] - v1["price"]) / v1["price"] < 0.02 and slope_high < 0:
        triangle_type = "하락 삼각수렴 (Descending Triangle)"
        badge_color = "#ef5350"
        p_type = "bearish"
    elif slope_high < 0 and slope_low > 0:
        triangle_type = "대칭 삼각수렴 (Symmetrical Triangle)"
        badge_color = "#a855f7"
        p_type = "neutral"
    else:
        return None

    # 상단 돌파 및 하단 이탈 감지
    is_breakout = cur_close > p2["price"] * 1.005
    is_breakdown = cur_close < v2["price"] * 0.995

    target_price = round(p2["price"] + initial_range, 2)
    stop_loss = round(v2["price"] * 0.99, 2)

    status_text = "🚀 상단 수렴선 돌파 (상방 폭발)" if is_breakout else (
        "⚠️ 하단 지지선 이탈 (하방 경계)" if is_breakdown else "⚡ 수렴 끝자락 (방향성 분출 임박)"
    )

    return {
        "name": triangle_type,
        "type": p_type,
        "status_text": status_text,
        "badge_color": badge_color,
        "is_breakout": is_breakout,
        "neckline": round(p2["price"], 2),
        "target_price": target_price,
        "stop_loss": stop_loss,
        "potential_upside_pct": round((target_price - cur_close) / cur_close * 100, 1),
        "risk_pct": round((cur_close - stop_loss) / cur_close * 100, 1),
        "confidence": 80,
        "key_points": [p1, p2, v1, v2],
        "description": f"고점과 저점의 진폭이 {latest_range / initial_range * 100:.0f}% 수준으로 급격히 수축하여 큰 방향성 돌파가 임박한 상태입니다.",
    }


def detect_all_chart_patterns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    [B] 고전 차트 패턴 전체 자동 스캔 및 통합 진단
    """
    empty_result = {
        "has_pattern": False,
        "primary_pattern": None,
        "detected_patterns": [],
        "summary_badge": "패턴 진행 중 아님",
        "summary_color": "#94a3b8",
        "summary_desc": "현재 뚜렷한 고전 차트 포메이션이 탐지되지 않았습니다.",
    }

    if df.empty or len(df) < 30:
        return empty_result

    cur_close = float(df["close"].iloc[-1])
    peaks, valleys = find_local_extrema(df, window=5)

    detected = []

    # 1. 역헤드앤숄더 탐지
    ihs = detect_inverse_head_and_shoulders(peaks, valleys, cur_close)
    if ihs:
        detected.append(ihs)

    # 2. 이중 바닥 (쌍바닥) 탐지
    db = detect_double_bottom(peaks, valleys, cur_close)
    if db:
        detected.append(db)

    # 3. 삼각수렴 탐지
    tri = detect_triangles(peaks, valleys, cur_close)
    if tri:
        detected.append(tri)

    # 4. 이중 천장 (쌍봉) 탐지
    dt = detect_double_top(peaks, valleys, cur_close)
    if dt:
        detected.append(dt)

    if not detected:
        return empty_result

    # 우선순위: 돌파된 패턴 > 신뢰도 높은 패턴
    detected.sort(key=lambda x: (x["is_breakout"], x["confidence"]), reverse=True)
    primary = detected[0]

    return {
        "has_pattern": True,
        "primary_pattern": primary,
        "detected_patterns": detected,
        "summary_badge": f"{primary['status_text']}",
        "summary_color": primary["badge_color"],
        "summary_desc": primary["description"],
    }
