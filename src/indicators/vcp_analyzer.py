import pandas as pd
import numpy as np
from datetime import datetime


def check_trend_template(df: pd.DataFrame, rp_rating: float | None = None) -> dict:
    """스크린샷의 일봉 미너비니 추세 템플릿 10개 조건을 평가한다.

    RP는 종목 간 상대 성과 순위이므로 OHLCV만으로 만들지 않는다.
    값이 없거나 기간 데이터가 부족한 조건은 미확인으로 남긴다.
    """
    required_columns = {"close", "high", "low"}
    if df is None or df.empty or not required_columns.issubset(df.columns):
        prices = pd.DataFrame(columns=["close", "high", "low"])
    else:
        prices = df[list(required_columns)].apply(pd.to_numeric, errors="coerce")
        prices = prices.dropna()
        prices = prices[(prices > 0).all(axis=1)]

    n = len(prices)
    close = float(prices["close"].iloc[-1]) if n else None
    sma50 = float(prices["close"].tail(50).mean()) if n >= 50 else None
    sma150 = float(prices["close"].tail(150).mean()) if n >= 150 else None
    sma200 = float(prices["close"].tail(200).mean()) if n >= 200 else None
    sma200_prev30 = float(prices["close"].iloc[-230:-30].mean()) if n >= 230 else None

    # 이 프로젝트의 일봉 기준 52주는 약 250거래일이다.
    high_52w = float(prices["high"].tail(250).max()) if n >= 250 else None
    low_52w = float(prices["low"].tail(250).min()) if n >= 250 else None
    dist_high = (close / high_52w - 1) * 100 if high_52w else None
    dist_low = (close / low_52w - 1) * 100 if low_52w else None

    try:
        rp = float(rp_rating) if rp_rating is not None else None
    except (TypeError, ValueError):
        rp = None
    if rp is not None and (not np.isfinite(rp) or not 0 <= rp <= 100):
        rp = None

    def price(value):
        return f"{value:,.2f}" if value is not None else "데이터 부족"

    def add(name, desc, passed, current, required):
        checks.append({
            "id": len(checks) + 1,
            "name": name,
            "desc": desc,
            "passed": bool(passed) if passed is not None else None,
            "current": current,
            "required": required,
        })

    checks = []
    add("RP > 70", "S&P 500 종목군 대비 1년 가중 수익률 백분위(RP)", rp > 70 if rp is not None else None,
        f"{rp:.1f}" if rp is not None else "RP 데이터 없음", "> 70")
    add("주가 > 50일선", "현재 종가가 50일 단순이동평균 위", close > sma50 if sma50 is not None else None,
        price(close), f"> {price(sma50)}")
    add("주가 > 150일선", "현재 종가가 150일 단순이동평균 위", close > sma150 if sma150 is not None else None,
        price(close), f"> {price(sma150)}")
    add("주가 > 200일선", "현재 종가가 200일 단순이동평균 위", close > sma200 if sma200 is not None else None,
        price(close), f"> {price(sma200)}")
    add("50일선 > 150일선", "50일선이 150일선 위", sma50 > sma150 if sma150 is not None else None,
        price(sma50), f"> {price(sma150)}")
    add("50일선 > 200일선", "50일선이 200일선 위", sma50 > sma200 if sma200 is not None else None,
        price(sma50), f"> {price(sma200)}")
    add("150일선 > 200일선", "150일선이 200일선 위", sma150 > sma200 if sma200 is not None else None,
        price(sma150), f"> {price(sma200)}")
    add("52주 저점 대비 +30% 이상", "현재 종가가 52주 저점보다 30% 이상 높음",
        dist_low >= 30 if dist_low is not None else None,
        f"{dist_low:+.1f}%" if dist_low is not None else "데이터 부족", "≥ +30.0%")
    add("52주 고점의 25% 이내", "현재 종가가 52주 고점보다 25% 넘게 낮지 않음",
        dist_high >= -25 if dist_high is not None else None,
        f"{dist_high:+.1f}%" if dist_high is not None else "데이터 부족", "≥ -25.0%")
    add("200일선 상승 중", "현재 200일선이 30거래일 전보다 높음",
        sma200 > sma200_prev30 if sma200_prev30 is not None else None,
        price(sma200), f"> 30거래일 전 {price(sma200_prev30)}")

    pass_count = sum(c["passed"] is True for c in checks)
    evaluated_count = sum(c["passed"] is not None for c in checks)
    return {
        "pass_count": pass_count,
        "total_count": len(checks),
        "evaluated_count": evaluated_count,
        "template_complete": evaluated_count == len(checks),
        "is_stage_2": pass_count >= 8 and evaluated_count >= 9,
        "score_pct": pass_count / len(checks) * 100.0,
        "checks": checks,
        "rp_rating": rp,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "dist_from_52w_high_pct": dist_high,
        "dist_from_52w_low_pct": dist_low,
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


def detect_vcp_pattern(df: pd.DataFrame, base_window: int = 90, rp_rating: float | None = None) -> dict:
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
            "trend_template": check_trend_template(df, rp_rating=rp_rating),
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
    tt = check_trend_template(df, rp_rating=rp_rating)
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
    pending = tt["total_count"] - tt.get("evaluated_count", tt["total_count"])
    pending_text = f" · {pending}개 미확인" if pending else ""
    if tt["is_stage_2"]:
        lines.append(f"• **추세 국면**: 미너비니 추세 템플릿(D) **{tt['pass_count']}/{tt['total_count']}개 충족{pending_text}**. 가격 추세는 Stage 2 기준을 충족합니다.")
    else:
        lines.append(f"• **추세 국면**: 미너비니 추세 템플릿(D) **{tt['pass_count']}/{tt['total_count']}개 충족{pending_text}**. 추세 조건을 추가로 확인해야 합니다.")

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
