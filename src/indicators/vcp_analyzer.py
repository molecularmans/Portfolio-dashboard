import pandas as pd
import numpy as np
from datetime import datetime


def check_trend_template(df: pd.DataFrame) -> dict:
    """
    마크 미너비니 8대 추세 템플릿 (Trend Template - Stage 2 상승 국면) 정밀 검증
    1. 현재 주가 > 150일선 및 200일선
    2. 150일선 > 200일선
    3. 200일선이 최소 1개월(20거래일) 이상 우상향
    4. 50일선 > 150일선 및 200일선
    5. 현재 주가 > 50일선
    6. 현재 주가 >= 52주 최저가 대비 +25% 이상
    7. 현재 주가 >= 52주 최고가 대비 25% 이내 (최고가 근접)
    8. 상대강도/모멘텀: 최근 3개월/6개월 주가 추세 우상향
    """
    if df.empty or len(df) < 50:
        return {
            "pass_count": 0,
            "total_count": 8,
            "is_stage_2": False,
            "score_pct": 0.0,
            "checks": [],
        }

    close = float(df["close"].iloc[-1])
    
    # 이동평균선 계산
    sma_50 = df["close"].rolling(50, min_periods=10).mean()
    sma_150 = df["close"].rolling(150, min_periods=20).mean()
    sma_200 = df["close"].rolling(200, min_periods=30).mean()

    cur_sma50 = float(sma_50.iloc[-1])
    cur_sma150 = float(sma_150.iloc[-1])
    cur_sma200 = float(sma_200.iloc[-1])

    # 200일 전 또는 20거래일 전 200일선
    lookback_20 = min(20, len(sma_200) - 1)
    sma200_prev20 = float(sma_200.iloc[-1 - lookback_20])

    # 52주(약 250거래일) 최고가 / 최저가
    lookback_52w = min(250, len(df))
    high_52w = float(df["high"].tail(lookback_52w).max())
    low_52w = float(df["low"].tail(lookback_52w).min())

    dist_from_52w_low_pct = ((close - low_52w) / (low_52w + 1e-9)) * 100
    dist_from_52w_high_pct = ((close - high_52w) / (high_52w + 1e-9)) * 100

    # 모멘텀 (최근 60거래일 수익률)
    lookback_60 = min(60, len(df) - 1)
    return_60d = ((close - float(df["close"].iloc[-1 - lookback_60])) / (float(df["close"].iloc[-1 - lookback_60]) + 1e-9)) * 100

    checks = [
        {
            "id": 1,
            "name": "150일·200일선 위 주가",
            "desc": "현재 주가가 150일 및 200일 이동평균선 위에 위치",
            "passed": bool(close > cur_sma150 and close > cur_sma200),
            "current": f"${close:,.2f}",
            "required": f"> 150일선(${cur_sma150:,.2f}), 200일선(${cur_sma200:,.2f})",
        },
        {
            "id": 2,
            "name": "150일선 > 200일선",
            "desc": "150일 이평선이 200일 이평선 위에 위치 (중장기 정배열)",
            "passed": bool(cur_sma150 > cur_sma200),
            "current": f"150일선 ${cur_sma150:,.2f}",
            "required": f"> 200일선 ${cur_sma200:,.2f}",
        },
        {
            "id": 3,
            "name": "200일선 1개월 우상향",
            "desc": "200일 이평선이 최소 1개월(20거래일) 이상 상승 추세",
            "passed": bool(cur_sma200 >= sma200_prev20),
            "current": f"현재 ${cur_sma200:,.2f}",
            "required": f"≥ 20일전 ${sma200_prev20:,.2f}",
        },
        {
            "id": 4,
            "name": "50일선 정배열",
            "desc": "50일 이평선이 150일선과 200일선 위에 위치",
            "passed": bool(cur_sma50 > cur_sma150 and cur_sma50 > cur_sma200),
            "current": f"50일선 ${cur_sma50:,.2f}",
            "required": f"> 150일선 & 200일선",
        },
        {
            "id": 5,
            "name": "50일선 위 주가",
            "desc": "현재 주가가 50일 이평선 위에 위치 (단기 모멘텀 지지)",
            "passed": bool(close > cur_sma50),
            "current": f"${close:,.2f}",
            "required": f"> 50일선 ${cur_sma50:,.2f}",
        },
        {
            "id": 6,
            "name": "52주 최저가 대비 +25%↑",
            "desc": "현재 주가가 52주 최저가 대비 최소 25% 이상 상승",
            "passed": bool(dist_from_52w_low_pct >= 25.0),
            "current": f"+{dist_from_52w_low_pct:.1f}%",
            "required": "≥ +25.0%",
        },
        {
            "id": 7,
            "name": "52주 최고가 근접 (25% 이내)",
            "desc": "현재 주가가 52주 신고가 대비 25% 이내 근접 (이상적 10~15%)",
            "passed": bool(dist_from_52w_high_pct >= -25.0),
            "current": f"{dist_from_52w_high_pct:.1f}%",
            "required": "≥ -25.0%",
        },
        {
            "id": 8,
            "name": "중기 모멘텀 상승세",
            "desc": "최근 3개월(60일) 주가 모멘텀 우상향 양호",
            "passed": bool(return_60d >= 0),
            "current": f"{return_60d:+.1f}%",
            "required": "≥ 0.0%",
        },
    ]

    pass_count = sum(1 for c in checks if c["passed"])
    is_stage_2 = pass_count >= 6

    return {
        "pass_count": pass_count,
        "total_count": len(checks),
        "is_stage_2": is_stage_2,
        "score_pct": (pass_count / len(checks)) * 100.0,
        "checks": checks,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "dist_from_52w_high_pct": dist_from_52w_high_pct,
        "dist_from_52w_low_pct": dist_from_52w_low_pct,
    }


def extract_vcp_contractions(df: pd.DataFrame, min_reversal_pct: float = 2.5) -> list:
    """
    베이스 최고점 이후의 Zigzag 스윙 파동을 분석하여 VCP 수축 단계(1T, 2T, 3T...) 추출
    """
    n = len(df)
    if n < 10:
        return []

    highs = df["high"].values
    lows = df["low"].values
    dates = df["date"].values

    base_peak_idx = int(np.argmax(highs))
    if base_peak_idx >= n - 2:
        # 최고점이 최근 2봉 이내면 이전 구간에서 탐색
        sub_highs = highs[:-2]
        base_peak_idx = int(np.argmax(sub_highs)) if len(sub_highs) > 0 else 0

    swings = [{
        "type": "peak",
        "idx": base_peak_idx,
        "price": float(highs[base_peak_idx]),
        "date": str(dates[base_peak_idx])[:10],
    }]

    looking_for = "trough"
    extreme_idx = min(base_peak_idx + 1, n - 1)
    extreme_price = float(lows[extreme_idx])

    for i in range(base_peak_idx + 1, n):
        cur_high = float(highs[i])
        cur_low = float(lows[i])

        if looking_for == "trough":
            if cur_low < extreme_price:
                extreme_price = cur_low
                extreme_idx = i
            elif cur_high >= extreme_price * (1.0 + min_reversal_pct / 100.0) and (i - extreme_idx) >= 1:
                swings.append({
                    "type": "trough",
                    "idx": extreme_idx,
                    "price": extreme_price,
                    "date": str(dates[extreme_idx])[:10],
                })
                looking_for = "peak"
                extreme_idx = i
                extreme_price = cur_high
        else:
            if cur_high > extreme_price:
                extreme_price = cur_high
                extreme_idx = i
            elif cur_low <= extreme_price * (1.0 - min_reversal_pct / 100.0) and (i - extreme_idx) >= 1:
                swings.append({
                    "type": "peak",
                    "idx": extreme_idx,
                    "price": extreme_price,
                    "date": str(dates[extreme_idx])[:10],
                })
                looking_for = "trough"
                extreme_idx = i
                extreme_price = cur_low

    if extreme_idx != swings[-1]["idx"]:
        swings.append({
            "type": looking_for,
            "idx": extreme_idx,
            "price": extreme_price,
            "date": str(dates[extreme_idx])[:10],
        })

    # Peak -> Trough 쌍 매칭하여 수축 파동 계산 (최소 2봉 이상 & 2% 이상 진폭)
    contractions = []
    i = 0
    while i < len(swings) - 1:
        if swings[i]["type"] == "peak" and swings[i + 1]["type"] == "trough":
            p = swings[i]
            t = swings[i + 1]
            bars = t["idx"] - p["idx"]
            depth = ((t["price"] - p["price"]) / p["price"]) * 100.0
            if bars >= 2 and abs(depth) >= 2.0:
                contractions.append({
                    "stage": f"{len(contractions) + 1}T",
                    "peak_date": p["date"],
                    "peak_price": round(p["price"], 2),
                    "trough_date": t["date"],
                    "trough_price": round(t["price"], 2),
                    "depth_pct": round(depth, 1),
                    "bars": max(1, bars),
                })
            i += 2
        else:
            i += 1

    return contractions


def detect_vcp_pattern(df: pd.DataFrame, base_window: int = 90) -> dict:
    """
    마크 미너비니 VCP (Volatility Contraction Pattern, 변동성 축소 패턴) 정밀 감지
    """
    if df.empty or len(df) < 30:
        return {
            "vcp_status": "DATA_LACK",
            "status_badge": "⚪ 데이터 부족",
            "status_color": "#94a3b8",
            "contractions": [],
            "contraction_count": 0,
            "is_diminishing": False,
            "volume_dryup": {"is_vdu": False, "ratio": 1.0, "avg_50": 0, "recent_avg": 0},
            "pivot": {"price": 0.0, "stop_loss": 0.0, "risk_pct": 0.0, "dist_pct": 0.0},
            "summary_text": "분석에 필요한 캔들 데이터가 충분하지 않습니다.",
            "trend_template": {"pass_count": 0, "total_count": 8, "is_stage_2": False, "checks": []},
        }

    # 최근 base_window 봉 추출 (기본 90거래일 베이스)
    window_df = df.tail(min(len(df), base_window)).copy().reset_index(drop=True)
    cur_close = float(window_df["close"].iloc[-1])

    # 1. 거래량 건조(VDU) 분석
    vol_50_avg = float(df["volume"].tail(50).mean()) if len(df) >= 10 else float(df["volume"].mean())
    recent_5d_vol = float(window_df["volume"].tail(5).mean())
    vol_ratio = (recent_5d_vol / (vol_50_avg + 1e-9)) * 100
    is_vdu = vol_ratio <= 75.0  # 50일 평균 대비 75% 이하 시 VDU

    # 2. 스윙 기반 수축 파동 추출
    contractions = extract_vcp_contractions(window_df, min_reversal_pct=2.0)

    # 폴백: 파동이 0개일 경우 최근 30일 및 10일 단순 변동폭 계산
    if not contractions:
        p_max = float(window_df["high"].max())
        t_min = float(window_df["low"].min())
        d_pct = round(((t_min - p_max) / p_max) * 100.0, 1)
        contractions = [
            {"stage": "1T", "peak_date": "Base High", "peak_price": round(p_max, 2), "trough_date": "Base Low", "trough_price": round(t_min, 2), "depth_pct": d_pct, "bars": len(window_df)},
        ]

    # 3. VCP 핵심: 베이스 우측의 최근 2~4개 수축 파동 집중 분석
    if len(contractions) > 4:
        contractions = contractions[-4:]
        for idx, c in enumerate(contractions):
            c["stage"] = f"{idx + 1}T"

    # 수축 감소(Diminishing) 검증 (최근 파동 진폭이 순차적으로 좁아지는지)
    is_diminishing = True
    for i in range(1, len(contractions)):
        prev_depth = abs(contractions[i - 1]["depth_pct"])
        curr_depth = abs(contractions[i]["depth_pct"])
        if curr_depth > prev_depth * 1.05:  # 이전 수축보다 5% 이상 커지면 수축 실패
            is_diminishing = False
            break

    # 4. 피봇 포인트 (Pivot Buy Point) 및 추천 손절가 도출
    last_c = contractions[-1]
    pivot_price = last_c["peak_price"]
    base_max_price = float(window_df["high"].max())

    if cur_close > pivot_price and base_max_price > cur_close:
        pivot_price = base_max_price

    stop_loss_price = last_c["trough_price"]
    if stop_loss_price >= pivot_price:
        stop_loss_price = pivot_price * 0.95

    risk_pct = round(((pivot_price - stop_loss_price) / pivot_price) * 100.0, 1)
    dist_to_pivot_pct = round(((cur_close - pivot_price) / pivot_price) * 100.0, 1)

    # 5. 종합 판정
    tt = check_trend_template(df)
    stage_count = len(contractions)
    last_depth = abs(last_c["depth_pct"])

    if not tt["is_stage_2"]:
        vcp_status = "STAGE_FAIL"
        status_badge = "🔴 추세 미달 (Stage 2 상승세 아님)"
        status_color = "#ef5350"
    elif stage_count >= 2 and is_diminishing and last_depth <= 8.5 and is_vdu and abs(dist_to_pivot_pct) <= 4.5:
        vcp_status = "READY"
        status_badge = f"🟢 VCP 완성 임박 ({stage_count}T 피봇 돌파 대기)"
        status_color = "#22c55e"
    elif stage_count >= 2 and is_diminishing:
        vcp_status = "DEVELOPING"
        status_badge = f"🟡 VCP 형성 중 ({stage_count}T 수축 진행형)"
        status_color = "#eab308"
    else:
        vcp_status = "NOT_VCP"
        status_badge = "⚪ VCP 조건 미충족 (일반 조정/박스권)"
        status_color = "#94a3b8"

    # 6. 자연어 해석 리포트 생성
    summary_text = generate_vcp_summary(
        vcp_status=vcp_status,
        stage_count=stage_count,
        contractions=contractions,
        vol_ratio=vol_ratio,
        is_vdu=is_vdu,
        pivot_price=pivot_price,
        stop_loss_price=stop_loss_price,
        risk_pct=risk_pct,
        dist_to_pivot_pct=dist_to_pivot_pct,
        tt=tt,
        cur_close=cur_close,
    )

    return {
        "vcp_status": vcp_status,
        "status_badge": status_badge,
        "status_color": status_color,
        "contractions": contractions,
        "contraction_count": stage_count,
        "is_diminishing": is_diminishing,
        "volume_dryup": {
            "is_vdu": is_vdu,
            "ratio": round(vol_ratio, 1),
            "avg_50": int(vol_50_avg),
            "recent_avg": int(recent_5d_vol),
        },
        "pivot": {
            "price": round(pivot_price, 2),
            "stop_loss": round(stop_loss_price, 2),
            "risk_pct": risk_pct,
            "dist_pct": dist_to_pivot_pct,
        },
        "trend_template": tt,
        "summary_text": summary_text,
    }


def generate_vcp_summary(vcp_status: str, stage_count: int, contractions: list, vol_ratio: float, is_vdu: bool,
                         pivot_price: float, stop_loss_price: float, risk_pct: float, dist_to_pivot_pct: float,
                         tt: dict, cur_close: float) -> str:
    """마크 미너비니 스타일의 정밀 자연어 차트 해석 리포트 생성"""
    lines = []

    # 1. 추세 템플릿 평가
    if tt["is_stage_2"]:
        lines.append(f"• **추세 국면**: 8대 추세 템플릿 중 **{tt['pass_count']}/8개**를 충족하여 완벽한 **Stage 2(기관 주도 상승 국면)**에 안착해 있습니다.")
    else:
        lines.append(f"• **추세 국면**: 8대 추세 템플릿 중 **{tt['pass_count']}/8개** 충족에 그쳐, 아직 장기 정배열 및 모멘텀 조건이 일부 미달된 상태입니다.")

    # 2. VCP 수축 파동 분석
    depth_str_list = [f"{c['stage']}({c['depth_pct']}%)" for c in contractions]
    depth_sequence = " ➔ ".join(depth_str_list)

    if stage_count >= 2:
        lines.append(f"• **변동성 축소**: 최근 베이스에서 총 **{stage_count}단계 수축**({depth_sequence})이 관측되었습니다. 주가의 상하 흔들림 폭이 순차적으로 줄어들며 매도 물량이 상당 부분 소화된 전형적인 VCP 궤적입니다.")
    else:
        lines.append(f"• **변동성 축소**: 현재 단일 조정 파동({depth_sequence})만 형성되어 있어, 의미 있는 연속 변동성 축소(2T/3T)가 더 진행되어야 합니다.")

    # 3. 거래량 건조(VDU) 평가
    if is_vdu:
        lines.append(f"• **거래량 건조 (VDU)**: 최근 5일 평균 거래량이 50일 평균 대비 **{vol_ratio:.1f}%** 수준으로 바짝 말랐습니다. 이는 상단 공급(악성 매물)이 거의 고갈되었음을 뜻하는 매우 긍정적인 신호입니다.")
    else:
        lines.append(f"• **거래량 건조 (VDU)**: 최근 거래량이 50일 평균의 **{vol_ratio:.1f}%** 수준으로, 완벽한 거래량 침체(VDU, 75% 이하)까지는 소폭 추가 관찰이 필요합니다.")

    # 4. 실전 전략 가이드
    if vcp_status == "READY":
        lines.append(f"• **실전 액션 플랜**: 피봇 매수가 **${pivot_price:,.2f}**(현재가 대비 {dist_to_pivot_pct:+.1f}%)를 **대량 거래량과 함께 강하게 돌파하는 시점**이 마크 미너비니의 최적 매수 급소입니다. 추천 손절가는 **${stop_loss_price:,.2f}**이며, 손절 리스크가 **{risk_pct:.1f}%**로 매우 타이트하여 이상적인 손익비(Risk/Reward)를 가집니다.")
    elif vcp_status == "DEVELOPING":
        lines.append(f"• **실전 액션 플랜**: 현재 수축이 진행 중이므로 섣부른 추격 매수보다는, 우측 베이스가 더 조여지며 피봇 **${pivot_price:,.2f}** 부근에서 거래량이 더 마르는지 확인 후 돌파 시 진입을 권장합니다.")
    else:
        lines.append(f"• **실전 액션 플랜**: VCP 매수 기준에 아직 완전히 부합하지 않으므로, 지지선 구축 및 50일선/200일선 정배열 회복 과정을 우선 관망하는 것이 유리합니다.")

    return "\n\n".join(lines)
