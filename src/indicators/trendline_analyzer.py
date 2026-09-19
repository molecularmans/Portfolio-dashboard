import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple


def find_local_extrema(df: pd.DataFrame, window: int = 5) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    주가 시계열에서 국소 고점(Peaks)과 저점(Valleys) 추출
    """
    if len(df) < window * 2 + 1:
        return [], []

    highs = df["high"].values
    lows = df["low"].values
    dates = df["date"].values if "date" in df.columns else np.arange(len(df))

    peaks = []
    valleys = []

    for i in range(window, len(df) - window):
        # 고점 판별 (좌우 window 구간 중 최고)
        if highs[i] == np.max(highs[i - window : i + window + 1]):
            # 동일 가격 중복 방지
            if not peaks or i - peaks[-1]["idx"] >= window // 2:
                peaks.append({
                    "idx": i,
                    "date": dates[i],
                    "price": float(highs[i]),
                })

        # 저점 판별 (좌우 window 구간 중 최저)
        if lows[i] == np.min(lows[i - window : i + window + 1]):
            if not valleys or i - valleys[-1]["idx"] >= window // 2:
                valleys.append({
                    "idx": i,
                    "date": dates[i],
                    "price": float(lows[i]),
                })

    return peaks, valleys


def cluster_horizontal_levels(
    points: List[Dict[str, Any]],
    tolerance_pct: float = 0.015,
    min_touches: int = 2
) -> List[Dict[str, Any]]:
    """
    고점 또는 저점들을 가격 근접도(tolerance_pct) 기준으로 클러스터링하여 주요 수평 지지/저항선 도출
    """
    if not points:
        return []

    sorted_pts = sorted(points, key=lambda x: x["price"])
    clusters = []
    current_cluster = [sorted_pts[0]]

    for pt in sorted_pts[1:]:
        base_price = np.mean([p["price"] for p in current_cluster])
        if abs(pt["price"] - base_price) / base_price <= tolerance_pct:
            current_cluster.append(pt)
        else:
            if len(current_cluster) >= min_touches:
                clusters.append(current_cluster)
            current_cluster = [pt]

    if len(current_cluster) >= min_touches:
        clusters.append(current_cluster)

    levels = []
    for cl in clusters:
        avg_price = float(np.mean([p["price"] for p in cl]))
        touch_count = len(cl)
        last_touch_idx = max(p["idx"] for p in cl)
        levels.append({
            "price": round(avg_price, 2),
            "touches": touch_count,
            "last_idx": last_touch_idx,
            "indices": [p["idx"] for p in cl],
        })

    # 터치 횟수 많은 순 및 최근 순으로 정렬
    levels.sort(key=lambda x: (x["touches"], x["last_idx"]), reverse=True)
    return levels


def fit_best_trendline(
    points: List[Dict[str, Any]],
    n_bars: int,
    is_upper: bool = True
) -> Optional[Dict[str, Any]]:
    """
    주요 변곡점 2~3개를 연결하여 유효한 대각선 추세선 산출
    """
    if len(points) < 2:
        return None

    # 최근 n_bars 이내의 점들 우선 고려
    recent_pts = [p for p in points if p["idx"] >= max(0, n_bars - 120)]
    if len(recent_pts) < 2:
        recent_pts = points[-5:]

    best_line = None
    best_score = -1

    # 후보 쌍 조합 탐색
    for i in range(len(recent_pts)):
        for j in range(i + 1, len(recent_pts)):
            p1 = recent_pts[i]
            p2 = recent_pts[j]

            dx = p2["idx"] - p1["idx"]
            if dx < 5:  # 너무 가까운 점 제외
                continue

            slope = (p2["price"] - p1["price"]) / dx
            intercept = p1["price"] - (slope * p1["idx"])

            # 상단 추세선의 경우 기울기가 너무 급격한 것은 제외
            current_proj = slope * (n_bars - 1) + intercept
            if current_proj <= 0:
                continue

            # 추세선 터치 및 침범 검증
            touches = 2
            penalty = 0
            for k, p in enumerate(recent_pts):
                if k == i or k == j:
                    continue
                expected_y = slope * p["idx"] + intercept
                diff_pct = abs(p["price"] - expected_y) / (p["price"] + 1e-9)

                if diff_pct <= 0.015:  # 1.5% 이내로 닿으면 추가 터치 인정
                    touches += 1
                elif is_upper and p["price"] > expected_y * 1.025:  # 상향 크게 뚫고 나간 점
                    penalty += 1
                elif not is_upper and p["price"] < expected_y * 0.975:  # 하향 크게 이탈한 점
                    penalty += 1

            score = touches * 2 - penalty
            if score > best_score:
                best_score = score
                best_line = {
                    "start_idx": int(p1["idx"]),
                    "start_price": float(p1["price"]),
                    "end_idx": int(p2["idx"]),
                    "end_price": float(p2["price"]),
                    "slope": float(slope),
                    "intercept": float(intercept),
                    "current_price": float(current_proj),
                    "touches": touches,
                    "type": "resistance" if is_upper else "support",
                }

    return best_line


def analyze_support_resistance_and_trendlines(df: pd.DataFrame) -> Dict[str, Any]:
    """
    [A] 자동 지지/저항선 및 추세선 종합 분석 엔진
    """
    empty_result = {
        "is_valid": False,
        "current_price": 0.0,
        "nearest_support": None,
        "nearest_resistance": None,
        "support_levels": [],
        "resistance_levels": [],
        "upper_trendline": None,
        "lower_trendline": None,
        "breakout_status": "데이터 부족",
        "status_badge": "분석 불가",
        "status_color": "#94a3b8",
        "status_desc": "분석을 위한 충분한 과거 데이터가 없습니다.",
    }

    if df.empty or len(df) < 25:
        return empty_result

    cur_close = float(df["close"].iloc[-1])
    n_bars = len(df)

    # 1. 국소 변곡점 추출 (단기 5일 윈도우 + 중기 10일 윈도우 혼합)
    peaks_5, valleys_5 = find_local_extrema(df, window=5)
    peaks_10, valleys_10 = find_local_extrema(df, window=10)

    all_peaks = {p["idx"]: p for p in peaks_5 + peaks_10}
    all_valleys = {v["idx"]: v for v in valleys_5 + valleys_10}

    peaks = sorted(all_peaks.values(), key=lambda x: x["idx"])
    valleys = sorted(all_valleys.values(), key=lambda x: x["idx"])

    # 2. 수평 지지/저항 레벨 클러스터링
    resistance_clusters = cluster_horizontal_levels(peaks, tolerance_pct=0.018, min_touches=2)
    support_clusters = cluster_horizontal_levels(valleys, tolerance_pct=0.018, min_touches=2)

    # 현재가 대비 지지선(현재가 이하) 및 저항선(현재가 이상) 분류
    supports = [s for s in support_clusters if s["price"] < cur_close * 1.005]
    resistances = [r for r in resistance_clusters if r["price"] > cur_close * 0.995]

    # 현재가에 가장 가까운 핵심 레벨
    nearest_sup = max(supports, key=lambda x: x["price"]) if supports else None
    nearest_res = min(resistances, key=lambda x: x["price"]) if resistances else None

    # 이격률(%) 계산
    dist_sup_pct = ((cur_close - nearest_sup["price"]) / nearest_sup["price"] * 100) if nearest_sup else None
    dist_res_pct = ((nearest_res["price"] - cur_close) / cur_close * 100) if nearest_res else None

    # 3. 대각 추세선 계산 (상단 저항 추세선 / 하단 지지 추세선)
    upper_tl = fit_best_trendline(peaks, n_bars=n_bars, is_upper=True)
    lower_tl = fit_best_trendline(valleys, n_bars=n_bars, is_upper=False)

    # 4. 돌파 및 위치 상태 진단
    status_badge = "박스권 횡보"
    status_color = "#38bdf8"
    status_desc = "주가가 주요 지지선과 저항선 사이에서 수렴 중입니다."
    breakout_type = "range"

    # 추세선 돌파 여부 확인
    if upper_tl and cur_close > upper_tl["current_price"] * 1.008:
        status_badge = "🚀 상단 추세선 돌파"
        status_color = "#26a69a"
        status_desc = f"하향/상승 저항 추세선(${upper_tl['current_price']:,.2f})을 상향 돌파하여 강한 매수 모멘텀이 발생했습니다."
        breakout_type = "upper_trendline_breakout"
    elif nearest_res and dist_res_pct is not None and cur_close >= nearest_res["price"]:
        status_badge = "🔥 주요 저항선 돌파"
        status_color = "#26a69a"
        status_desc = f"강력한 수평 저항 매물대(${nearest_res['price']:,.2f})를 뚫고 상향 돌파 중입니다."
        breakout_type = "resistance_breakout"
    elif lower_tl and cur_close < lower_tl["current_price"] * 0.992:
        status_badge = "⚠️ 하단 추세선 이탈"
        status_color = "#ef5350"
        status_desc = f"하단 지지 추세선(${lower_tl['current_price']:,.2f})을 하향 이탈하여 리스크 관리가 필요합니다."
        breakout_type = "lower_trendline_breakdown"
    elif nearest_sup and dist_sup_pct is not None and dist_sup_pct <= 1.5:
        status_badge = "🛡️ 지지선 반등 구간"
        status_color = "#f59e0b"
        status_desc = f"핵심 지지선(${nearest_sup['price']:,.2f})에 근접하여 반등 지지가 기대되는 손익비 우수 구간입니다."
        breakout_type = "near_support"
    elif nearest_res and dist_res_pct is not None and dist_res_pct <= 1.5:
        status_badge = "🛑 저항선 근접 경계"
        status_color = "#f59e0b"
        status_desc = f"상단 저항선(${nearest_res['price']:,.2f})에 도달하여 단기 매물 출회 및 조정 가능성이 있습니다."
        breakout_type = "near_resistance"

    return {
        "is_valid": True,
        "current_price": cur_close,
        "nearest_support": nearest_sup,
        "nearest_resistance": nearest_res,
        "dist_support_pct": dist_sup_pct,
        "dist_resistance_pct": dist_res_pct,
        "support_levels": sorted(supports, key=lambda x: x["price"], reverse=True)[:4],
        "resistance_levels": sorted(resistances, key=lambda x: x["price"])[:4],
        "upper_trendline": upper_tl,
        "lower_trendline": lower_tl,
        "breakout_type": breakout_type,
        "status_badge": status_badge,
        "status_color": status_color,
        "status_desc": status_desc,
        "peaks": peaks,
        "valleys": valleys,
    }
