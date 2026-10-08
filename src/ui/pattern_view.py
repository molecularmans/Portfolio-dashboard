import streamlit as st
import pandas as pd
import math
from datetime import timedelta
from typing import Dict, Any

from src.indicators.trendline_analyzer import analyze_support_resistance_and_trendlines
from src.indicators.pattern_detector import detect_all_chart_patterns
from src.indicators.smart_analysis_v2 import (
    analyze_chart_patterns_v2,
    analyze_support_resistance_v2,
    analyze_vcp_v2,
)
from src.indicators.smart_analysis_v3 import analyze_smart_chart_v3
from src.indicators.smart_analysis_v4 import analyze_smart_chart_v4
from src.indicators.vcp_analyzer import detect_vcp_pattern
from src.indicators.integrated_assessment import build_integrated_assessment
from src.indicators.daily_screen import STAGE_LABELS, classify_entry_stage
from src.indicators.weekly_screen import WEEKLY_STAGE_LABELS, evaluate_weekly_ticker
from src.indicators.investment_risk_report import build_investment_risk_report
from src.indicators.relative_performance import calculate_rp_history, current_rp_rating, load_rp_reference
from src.ui.vcp_view import render_vcp_analysis_panel


PATTERN_HELP = {
    "pattern": "최근 고점과 저점의 모양을 비교해 가장 뚜렷하게 감지된 가격 패턴입니다. 신뢰도는 형태, 거래량, 최근성 등을 합산한 참고 점수입니다.",
    "breakout": "패턴이 완성됐다고 판단하는 기준 가격입니다. 종가가 이 가격을 넘고 거래량까지 늘어나는지 함께 확인합니다.",
    "target": "패턴의 높이를 돌파 기준 가격에 적용해 계산한 참고 목표입니다. 실제 도달을 보장하지 않습니다.",
    "stop": "패턴 해석이 틀렸다고 판단할 위험 관리 기준입니다. 실제 주문 가격은 투자 성향과 변동성에 맞게 조정해야 합니다.",
    "reward_risk": "현재 종가에서 예상 목표 가격까지의 이익폭을 위험 관리 가격까지의 손실폭으로 나눈 값입니다. 예: 2:1은 예상 이익폭이 손실폭의 2배라는 뜻입니다. 수수료와 실제 체결 가격은 반영하지 않습니다.",
    "entry_reward_risk": "패턴의 돌파 기준 가격에서 진입했다고 가정한 최초 손익비입니다. 이미 가격이 움직인 뒤에도 처음 계획의 기대수익과 위험을 비교할 수 있습니다.",
    "setup_strength": "패턴 신뢰도 35%, 지지·저항 품질 20%, 선택 엔진 종합 점수 25%, 돌파 기준 진입 손익비 20%를 합산한 참고 점수입니다. 실제 수익 가능성을 보장하지 않습니다.",
}

DASHBOARD_HELP = {
    "score": "지지·저항, 가격 패턴, VCP, 시장 흐름과 과거 검증 결과를 합산한 0~100점 참고 점수입니다.",
    "environment": "최근 가격 방향과 변동성 수준을 함께 요약합니다. 상승·하락·횡보와 변동성 높고 낮음을 구분합니다.",
    "compression": "가격 변동 폭이 평소보다 좁아졌는지 보여줍니다. 압축 뒤에는 움직임이 커질 수 있지만 방향은 보장되지 않습니다.",
    "candle": "최근 캔들 가운데 반전 또는 추세 지속 가능성이 가장 뚜렷한 신호입니다. 단독 매매 신호로 사용하지 않습니다.",
    "momentum": "RSI와 StochRSI로 최근 가격의 상승·하락 힘과 과열 여부를 평가합니다.",
    "flow": "OBV·CMF·MFI를 이용해 거래량이 매수 쪽으로 유입되는지, 매도 쪽으로 빠지는지 평가합니다.",
    "trend": "ADX와 +DI/-DI로 추세의 방향과 강도를 평가합니다. ADX가 높을수록 현재 방향성이 뚜렷하다는 뜻입니다.",
    "stop": "가격 구조상 손절선과 SuperTrend 기준 중 현재가에 더 가까운 유효 가격을 참고값으로 제시합니다.",
    "samples": "같은 신호가 연속으로 발생한 경우를 하나로 묶어 중복을 제거한 과거 사례 수입니다.",
    "hit_rate": "신호 발생 종가를 기준으로 10거래일 뒤 수익률이 0%보다 높았던 사례의 비율입니다.",
    "return": "각 신호 발생 후 10거래일 수익률의 평균입니다. v4에는 설정된 거래 비용이 반영됩니다.",
    "upside": "신호 발생 후 10거래일 동안 기록한 최고가 기준 상승폭의 평균입니다.",
    "downside": "신호 발생 후 10거래일 동안 기록한 최저가 기준 하락폭의 평균입니다.",
}


def _friendly_pattern_text(text: str) -> str:
    """Replace specialist pattern terms with reader-friendly Korean labels."""
    result = str(text or "")
    for original, replacement in (
        ("넥라인", "돌파 기준선"),
        ("매수 급소", "매수 관찰 구간"),
        ("상방 폭발", "강한 상승 가능성"),
        ("오탐", "잘못 감지"),
        ("핵심 피벗", "주요 고점·저점"),
    ):
        result = result.replace(original, replacement)
    return result


def _friendly_regime_text(text: str) -> str:
    result = str(text or "")
    return result.replace("고변동", "변동성 높음").replace("저변동", "변동성 낮음").replace("보통변동", "변동성 보통")


def _friendly_squeeze_text(text: str) -> str:
    result = str(text or "")
    return result.replace("스퀴즈", "변동성 압축").replace("모멘텀", "가격 움직임").replace("밴드 폭 백분위", "최근 변동성 위치")


def _report_pct(value: float | None, signed: bool = False) -> str:
    if value is None or not math.isfinite(value):
        return "자료 부족"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def _report_traded_value(value: float | None, currency: str) -> str:
    if value is None or not math.isfinite(value):
        return "자료 부족"
    if currency == "₩":
        if value >= 1e8:
            return f"₩{value / 1e8:,.1f}억"
        return f"₩{value / 1e4:,.1f}만" if value >= 1e4 else f"₩{value:,.0f}"
    if value >= 1e9:
        return f"${value / 1e9:,.1f}B"
    if value >= 1e6:
        return f"${value / 1e6:,.1f}M"
    return f"${value / 1e3:,.1f}K" if value >= 1e3 else f"${value:,.0f}"


def _stop_scenario_text(summary: Dict[str, Any], currency: str) -> str:
    """Keep a structural support line readable when no entry price exists."""
    stop = summary.get("stop")
    if stop is None:
        return "현재가 아래의 유효한 구조적 손절 기준을 찾지 못했습니다. 손절 기준이 잡히기 전에는 신규 진입을 보류합니다."
    prefix = f"**{summary['stop_source']} {currency}{stop:,.2f}**"
    if summary.get("risk_pct") is None:
        return prefix + "는 현재 차트의 지지 이탈 관찰선입니다. 진입 기준 가격이 없어 손절 폭은 아직 계산할 수 없습니다."
    return (
        prefix + " 아래 일봉 종가 마감 시 진입 가정을 재검토합니다. "
        f"가정 진입가 대비 손절 폭은 **{summary['risk_pct']:.1f}%**입니다."
    )


def render_weekly_assessment(df: pd.DataFrame, ticker: str) -> None:
    """Explain the weekly watchlist bucket beside the weekly chart."""
    result = evaluate_weekly_ticker(df, ticker)
    currency = "₩" if ticker.isdigit() and len(ticker) == 6 else "$"
    with st.container(border=True):
        st.subheader(f"{ticker} 완료 주봉 판정 · {WEEKLY_STAGE_LABELS[result['stage']]}")
        if result["stage"] == "unavailable":
            st.caption(result["reason"])
            return
        bar_date = pd.to_datetime(result["date"]).date()
        week_start = bar_date - timedelta(days=bar_date.weekday())
        st.caption(f"완료 주간: {week_start} ~ {week_start + timedelta(days=4)} · 미완성 이번 주 봉은 제외")
        st.write(result["reason"])
        w1, w2, w3, w4 = st.columns(4)
        w1.metric("주봉 종가", f"{currency}{result['close']:,.2f}")
        w2.metric("13주 / 26주선", f"{currency}{result['ma13']:,.2f} / {result['ma26']:,.2f}")
        w3.metric("52주선", f"{currency}{result['ma52']:,.2f}")
        w4.metric("이번 주 / 지난 20주 평균 거래량", f"{result['volume_ratio']:.2f}배" if result["volume_ratio"] is not None else "확인 불가")
        st.write(f"**진입 관찰선:** 직전 20주 고점 {currency}{result['pivot']:,.2f} 위 완료 주봉 종가와 거래량 1.2배 이상")
        if result["stop"] is not None:
            st.write(f"**무효화 관찰선:** {currency}{result['stop']:,.2f} 아래 주봉 종가 · 현재 주봉 종가 대비 {result['risk_pct']:.1f}%")
        else:
            st.write("현재가 아래 유효한 주봉 손절 관찰선이 없습니다.")
        st.caption("주봉 판정은 일봉 [A–D] 및 일봉 RP와 별도로 계산한 참고 신호입니다. 진입 실행 전 일봉 상황과 최신 시세를 확인하세요.")


def _pattern_reward_risk_result(pattern: Dict[str, Any], entry_price: float) -> Dict[str, Any]:
    """Return reward/risk plus a reader-friendly reason when it is not valid."""
    target = float(pattern["target_price"])
    stop = float(pattern["stop_loss"])
    if not all(math.isfinite(value) and value > 0 for value in (entry_price, target, stop)):
        return {"ratio": None, "status": "가격 데이터가 충분하지 않음"}
    if pattern.get("type") == "bearish":
        if target >= stop:
            return {"ratio": None, "status": "목표·위험 가격 순서 불일치"}
        if entry_price <= target:
            return {"ratio": None, "status": "목표 가격 도달 또는 초과"}
        if entry_price >= stop:
            return {"ratio": None, "status": "위험 관리 가격 이탈"}
        return {"ratio": (entry_price - target) / (stop - entry_price), "status": "하락 패턴 진입 가정"}
    if stop >= target:
        return {"ratio": None, "status": "목표·위험 가격 순서 불일치"}
    if entry_price >= target:
        return {"ratio": None, "status": "목표 가격 도달 또는 초과"}
    if entry_price <= stop:
        return {"ratio": None, "status": "위험 관리 가격 이탈"}
    return {"ratio": (target - entry_price) / (entry_price - stop), "status": "상승 패턴 진입 가정"}


def _pattern_reward_risk(pattern: Dict[str, Any], entry_price: float) -> float | None:
    return _pattern_reward_risk_result(pattern, entry_price)["ratio"]


def _entry_setup_strength(
    pattern: Dict[str, Any],
    structure_score: float,
    engine_score: float,
    entry_reward_risk: float | None,
) -> Dict[str, Any]:
    """Summarise chart quality without presenting it as a probability."""
    pattern_score = float(pattern.get("confidence", 50))
    ratio_score = 35.0 if entry_reward_risk is None else max(0.0, min(100.0, 25.0 + entry_reward_risk * 25.0))
    score = round(
        pattern_score * 0.35
        + max(0.0, min(100.0, structure_score)) * 0.20
        + max(0.0, min(100.0, engine_score)) * 0.25
        + ratio_score * 0.20
    )
    label = "매우 강함" if score >= 80 else "강함" if score >= 70 else "보통" if score >= 58 else "약함" if score >= 45 else "주의"
    if entry_reward_risk is None:
        interpretation = "진입 가격 조건을 먼저 확인하세요."
    elif entry_reward_risk < 1.0:
        interpretation = "예상 이익보다 위험이 커서 진입에 불리합니다."
    elif score >= 70 and entry_reward_risk >= 2.0:
        interpretation = "차트 조건과 최초 손익비가 함께 양호합니다."
    elif score >= 58 and entry_reward_risk >= 1.5:
        interpretation = "진입 후보로 관찰할 수 있으나 추가 확인이 필요합니다."
    else:
        interpretation = "일부 조건이 약해 보수적인 접근이 필요합니다."
    return {"score": int(score), "label": label, "interpretation": interpretation}


def render_pattern_analysis_dashboard(df: pd.DataFrame, ticker: str):
    """
    [A] 자동 추세선/지지저항선 + [B] 고전 차트 패턴 + 마크 미너비니 VCP를 총망라한 통합 분석 패널
    """
    if df.empty or len(df) < 30:
        st.info(f"📊 {ticker}의 정밀 차트 패턴 분석을 위한 충분한 과거 데이터가 부족합니다.")
        return

    engine = st.radio(
        "분석 엔진",
        options=["v1", "v2", "v3", "v4"],
        index=3,
        format_func=lambda value: {
            "v1": "Legacy v1",
            "v2": "Experimental v2",
            "v3": "Experimental v3 · 1k+⭐ OSS 검증",
            "v4": "Experimental v4 · 모멘텀·수급·추세",
        }[value],
        key=f"smart_analysis_engine_{ticker}",
        horizontal=True,
        help="각 엔진에 반영된 항목은 바로 아래 설명 팝오버에서 확인할 수 있습니다.",
    )
    with st.popover("ℹ️ 엔진별 반영 항목"):
        st.markdown(
            """
            - **v1**: 기존 지지·저항, 추세선, 고전 패턴, VCP
            - **v2**: v1 + ATR 적응형 가격대, 추세선/패턴 품질, 거래량 확인
            - **v3**: v2 + 캔들 패턴, BB/KC 스퀴즈, 시장 국면, 룩어헤드 방지 워크포워드
            - **v4**: v3 + RSI·StochRSI 다이버전스, OBV·CMF·MFI 수급, ADX·DMI 추세 강도, SuperTrend 손절선, v3/v4 비교

            GitHub 별 수는 참고 프로젝트의 인지도 기준이며 수익성을 보장하지 않습니다. 모든 결과는 연구·보조 판단용입니다.
            """
        )
    use_v2 = engine in {"v2", "v3", "v4"}
    v3_bundle = None
    v4_bundle = None

    # TrendSpider 화면의 RP(yearly, SPX500)에 대응하는 자체 산출 점수.
    # 국내 6자리 종목코드는 미국 S&P 500과 비교하지 않는다.
    rp_reference = load_rp_reference() if not (ticker.isdigit() and len(ticker) == 6) else None
    rp_history = calculate_rp_history(df, rp_reference)
    rp_rating = current_rp_rating(df, rp_history)

    # 1. 알고리즘 분석 실행 — 테스트 단계에서는 기존 엔진과 즉시 A/B 비교 가능
    if engine == "v4":
        v4_bundle = analyze_smart_chart_v4(df, rp_rating=rp_rating)
        v3_bundle = v4_bundle["v3_baseline"]
        sr_data = v4_bundle["support_resistance"]
        pattern_data = v4_bundle["patterns"]
        vcp_data = v4_bundle["vcp"]
    elif engine == "v3":
        v3_bundle = analyze_smart_chart_v3(df, rp_rating=rp_rating)
        sr_data = v3_bundle["support_resistance"]
        pattern_data = v3_bundle["patterns"]
        vcp_data = v3_bundle["vcp"]
    elif engine == "v2":
        sr_data = analyze_support_resistance_v2(df)
        pattern_data = analyze_chart_patterns_v2(df)
        vcp_data = analyze_vcp_v2(df, rp_rating=rp_rating)
    else:
        sr_data = analyze_support_resistance_and_trendlines(df)
        pattern_data = detect_all_chart_patterns(df)
        vcp_data = detect_vcp_pattern(df, rp_rating=rp_rating)

    # -------------------------------------------------------------
    # 섹션 1: 상단 종합 분석 브리핑 헤더
    # -------------------------------------------------------------
    primary_pat = pattern_data.get("primary_pattern")
    sr_badge = sr_data.get("status_badge", "분석 완료")
    sr_color = sr_data.get("status_color", "#38bdf8")
    if engine == "v4" and v4_bundle is not None:
        engine_label = (
            f"Experimental v4 · 종합 {v4_bundle['composite_score']}점/"
            f"{v4_bundle['grade']}등급 · {v4_bundle['verdict']}"
        )
    elif engine == "v3" and v3_bundle is not None:
        engine_label = f"Experimental v3 · 종합 {v3_bundle['composite_score']}점/{v3_bundle['grade']}등급"
    elif engine == "v2":
        engine_label = "Experimental v2"
    else:
        engine_label = "Legacy v1"
    quality_label = f" · A품질 {sr_data.get('quality_score', 0)}점" if use_v2 else ""

    with st.container(border=True):
        st.markdown(f"**🎯 {ticker} 차트 종합 진단 엔진**")
        st.caption(f"{engine_label}{quality_label} · Support / Resistance · Trendlines · Classic Formations")
        st.write(sr_badge)
        if primary_pat:
            st.write(primary_pat["name"])

    # -------------------------------------------------------------
    # 탭 구성: 종합판정·위험 점검과 [A]~[D] 세부 근거
    # -------------------------------------------------------------
    summary = build_integrated_assessment(df, sr_data, pattern_data, vcp_data, v3_bundle, v4_bundle)
    stage = classify_entry_stage(summary, vcp_data, v3_bundle, v4_bundle)
    risk_report = build_investment_risk_report(df, summary)
    currency = "₩" if ticker.isdigit() and len(ticker) == 6 else "$"
    tab_summary, tab_risk, tab_sr, tab_pattern, tab_vcp, tab_validation = st.tabs([
        "🎯 [A–D] 종합판정·진입/손절 시나리오",
        "🛡️ 매수 전 위험 점검 리포트",
        "📐 [A] 자동 지지·저항 & 추세선",
        "💎 [B] 가격 패턴 분석 (쌍바닥·삼각수렴)",
        "🧠 [C] 마크 미너비니 VCP 분석",
        "🧪 [D] 추세 환경·캔들 신호·과거 검증",
    ])

    with tab_summary:
        st.subheader(f"{ticker} 차트 판정 · {STAGE_LABELS[stage['stage']]}")
        last_date = pd.to_datetime(df["date"].iloc[-1]).strftime("%Y-%m-%d") if "date" in df else "최근 일봉"
        st.caption(f"기준: {last_date} 종가 · 현재가 {currency}{summary['current']:,.2f} · 당일 진입 신호: {summary['verdict']}")
        st.info(stage["reason"])
        st.markdown(f"**현재 차트 형태:** {summary['shape']}")
        for label, detail in summary["evidence"]:
            st.write(f"**{label}** · {detail}")

        st.markdown("#### 진입 시나리오")
        if summary["verdict"] == "신규 진입 보류":
            st.caption("아래 가격은 향후 관찰 기준이며 현재 신규 진입 실행 신호가 아닙니다.")
        if summary["entry"]:
            st.write(
                f"**{summary['entry_source']} {currency}{summary['entry']:,.2f}** 위 일봉 종가와 "
                f"직전 20거래일 평균 대비 **{summary['required_volume']:.1f}배 이상 거래량**을 함께 확인합니다."
            )
            volume_text = f"{summary['volume_ratio']:.2f}배" if summary["volume_ratio"] is not None else "확인 불가"
            st.caption(f"현재 거래량: {volume_text} · {'가격·거래량 조건 확인' if summary['confirmed'] else '가격 또는 거래량 조건 대기'}")
            if summary["current"] > summary["entry"]:
                st.write("이미 돌파선 위라면 재진입 전에 해당 가격대의 지지 여부와 현재 이격을 다시 확인합니다.")
        else:
            st.write("유효한 돌파 기준 가격을 찾지 못했습니다. 새로운 지지·저항 또는 패턴이 형성될 때까지 진입 판단을 보류합니다.")

        st.markdown("#### 손절·무효화 시나리오")
        st.write(_stop_scenario_text(summary, currency))
        if summary["target"]:
            ratio = f" · 참고 손익비 {summary['reward_risk']:.1f}:1" if summary["reward_risk"] is not None else ""
            st.caption(f"{summary['target_source']} {currency}{summary['target']:,.2f}{ratio} · 목표가와 손익비는 실현 수익을 보장하지 않습니다.")
        else:
            st.caption("현재 가격보다 높은 유효 목표/저항이 없어 참고 손익비를 산출하지 않았습니다.")

        st.markdown("#### 당일 진입 조건 점검")
        if summary["blockers"]:
            st.warning(" · ".join(summary["blockers"]))
        elif summary["verdict"] == "조건 충족 · 확인 필요":
            st.success("A–D의 핵심 조건이 맞아 기술적 진입 후보로 볼 수 있습니다. 실제 체결 전 최신 가격과 수급을 재확인하세요.")
        else:
            st.info("돌파·거래량·추세·손절 기준이 함께 맞을 때까지 관찰합니다.")
        if not summary["d_available"]:
            st.caption("[D] 판단은 v3/v4 엔진에서 제공됩니다. 현재 엔진에서는 종합판정을 보수적으로 표시합니다.")
        st.caption("차트 기반 참고 판정입니다. 기업 실적·밸류에이션·뉴스·계좌 위험 한도는 반영하지 않습니다. 손절 기준은 주문 체결가를 보장하지 않습니다.")

    with tab_risk:
        st.subheader(f"{ticker} 매수 전 위험 점검")
        if not risk_report["is_valid"]:
            st.warning("최근 종가가 없어 위험 지표를 계산할 수 없습니다.")
        else:
            report_date = risk_report["date"].isoformat() if risk_report["date"] else "날짜 정보 없음"
            age = f" · {risk_report['days_since']}일 경과" if risk_report["days_since"] is not None else ""
            st.caption(f"마지막 일봉 {report_date}{age} · 최근 가격·거래량 기록으로 계산")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("최근 20일 하루 변동성", _report_pct(risk_report["daily_vol_pct"]), help="최근 20개 일간 수익률의 표준편차입니다. 하루 가격 움직임의 과거 크기를 보여줍니다.")
            r2.metric("14일 ATR / 현재가", _report_pct(risk_report["atr_pct"]), help="갭을 포함한 최근 14개 일봉의 평균 가격 변동폭을 현재가로 나눈 값입니다.")
            r3.metric("최근 60일 최대 하락 개장 갭", _report_pct(risk_report["max_down_gap_pct"]), help="전일 종가에서 다음 거래일 시가까지의 하락폭 중 최근 60거래일 최대치입니다.")
            r4.metric("최근 20일 중앙 거래대금", _report_traded_value(risk_report["median_value_20"], currency), help="일별 종가×거래량의 중앙값입니다. 실제 호가 잔량이나 예상 체결가는 반영하지 않습니다.")

            s1, s2, s3 = st.columns(3)
            s1.metric("최근 20거래일 변화", _report_pct(risk_report["change_20_pct"], signed=True))
            s2.metric("최근 60거래일 변화", _report_pct(risk_report["change_60_pct"], signed=True))
            s3.metric("52주 고점 대비", _report_pct(risk_report["drawdown_52w_pct"], signed=True), help="250개 일봉이 있을 때만 계산합니다.")

            st.markdown("#### 계획 손절폭과 실제 변동 비교")
            if risk_report["stop_atr_multiple"] is not None:
                st.write(
                    f"가정 진입가 대비 손절폭 **{risk_report['stop_risk_pct']:.1f}%**는 "
                    f"최근 ATR의 **{risk_report['stop_atr_multiple']:.1f}배**입니다. "
                    "이 비율은 손절선이 평소 변동에 얼마나 가까운지 보는 참고값이며 손실 상한이 아닙니다."
                )
            else:
                st.write("손절선 또는 ATR 자료가 부족해 변동폭과 손절폭을 비교할 수 없습니다.")
            for warning in risk_report["warnings"]:
                st.warning(warning)
            st.caption("과거 변동성·갭·거래대금은 미래 수익이나 체결 품질을 예측하지 않습니다. 실적 발표 일정, 뉴스, 보유 종목과의 중복 위험은 별도 확인이 필요합니다.")

    # -------------------------------------------------------------
    # TAB A: 지지 / 저항선 및 추세선 분석
    # -------------------------------------------------------------
    with tab_sr:
        c1, c2, c3, c4 = st.columns(4)

        near_sup = sr_data.get("nearest_support")
        near_res = sr_data.get("nearest_resistance")
        upper_tl = sr_data.get("upper_trendline")
        lower_tl = sr_data.get("lower_trendline")

        with c1:
            if near_sup:
                st.metric(
                    label="핵심 지지선 (Support)",
                    value=f"${near_sup['price']:,.2f}",
                    delta=f"현재가 대비 -{sr_data['dist_support_pct']:.1f}%",
                    delta_color="normal",
                    help=f"과거 {near_sup['touches']}차례 저점 지지가 확인된 주요 가격대입니다.",
                )
            else:
                st.metric(label="핵심 지지선", value="최근 저점 탐색 중")

        with c2:
            if near_res:
                st.metric(
                    label="핵심 저항선 (Resistance)",
                    value=f"${near_res['price']:,.2f}",
                    delta=f"현재가 대비 +{sr_data['dist_resistance_pct']:.1f}%",
                    delta_color="inverse",
                    help=f"과거 {near_res['touches']}차례 고점 저항이 확인된 주요 매물대입니다.",
                )
            else:
                st.metric(label="핵심 저항선", value="신고가 영역")

        with c3:
            if upper_tl:
                slope_str = "하향 기울기" if upper_tl["slope"] < 0 else "상승 채널"
                if "quality_score" in upper_tl:
                    slope_str += f" · 품질 {upper_tl['quality_score']}점"
                st.metric(
                    label="상단 저항 추세선",
                    value=f"${upper_tl['current_price']:,.2f}",
                    delta=slope_str,
                    help="최근 주요 고점들을 연결한 상단 저항선입니다. 상향 돌파 시 강한 시세 분출이 기대됩니다.",
                )
            else:
                st.metric(label="상단 저항 추세선", value="계산 중")

        with c4:
            if lower_tl:
                slope_str = "우상향 지지" if lower_tl["slope"] > 0 else "하락 추세"
                if "quality_score" in lower_tl:
                    slope_str += f" · 품질 {lower_tl['quality_score']}점"
                st.metric(
                    label="하단 지지 추세선",
                    value=f"${lower_tl['current_price']:,.2f}",
                    delta=slope_str,
                    delta_color="normal" if lower_tl["slope"] > 0 else "inverse",
                    help="최근 주요 저점들을 연결한 하단 지지선입니다. 이탈 시 손절 및 비중 축소가 권장됩니다.",
                )
            else:
                st.metric(label="하단 지지 추세선", value="계산 중")

        if v4_bundle:
            trend = v4_bundle["trend_strength"]
            risk = v4_bundle["risk_control"]
            st.caption(
                f"🧭 v4 추세 확인: {trend.get('state', '분석 중')} · ADX {trend.get('adx', 0):.1f} · "
                f"+DI/-DI {trend.get('plus_di', 0):.1f}/{trend.get('minus_di', 0):.1f} · "
                f"SuperTrend 기준 ${risk.get('supertrend_stop', 0):,.2f}"
            )

        # 진단 해설 및 주요 레벨 목록
        st.markdown(f"""
        <div style="background-color: rgba(255, 255, 255, 0.03); border-radius: 8px; padding: 12px 16px; margin-top: 10px;">
            <b style="color: {sr_color};">📌 추세선 및 매물대 진단:</b> {sr_data.get('status_desc', '')}
        </div>
        """, unsafe_allow_html=True)

        col_sups, col_ress = st.columns(2)
        with col_sups:
            st.caption("🛡️ 주요 지지 구간 (과거 반응 횟수 순)")
            if sr_data["support_levels"]:
                for s in sr_data["support_levels"]:
                    zone = (
                        f" · 가격 구간 ${s['zone_low']:,.2f}~${s['zone_high']:,.2f}"
                        f" · 강도 {s['strength_score']}점"
                        if "zone_low" in s
                        else ""
                    )
                    st.write(f"- **${s['price']:,.2f}** · 지지 반응 {s['touches']}회{zone}")
            else:
                st.write("- 추가 지지 구간을 분석하고 있습니다.")

        with col_ress:
            st.caption("🛑 주요 저항 구간 (과거 반응 횟수 순)")
            if sr_data["resistance_levels"]:
                for r in sr_data["resistance_levels"]:
                    zone = (
                        f" · 가격 구간 ${r['zone_low']:,.2f}~${r['zone_high']:,.2f}"
                        f" · 강도 {r['strength_score']}점"
                        if "zone_low" in r
                        else ""
                    )
                    st.write(f"- **${r['price']:,.2f}** · 저항 반응 {r['touches']}회{zone}")
            else:
                st.write("- 뚜렷한 상단 저항이 없어 신고가 흐름을 관찰할 구간입니다.")

    # -------------------------------------------------------------
    # TAB B: 고전 차트 패턴 (쌍바닥, 삼각수렴 등)
    # -------------------------------------------------------------
    with tab_pattern:
        st.caption("항목 이름 옆 도움말 아이콘에 마우스를 올리면 계산 기준과 해석 방법을 볼 수 있습니다.")
        if pattern_data["has_pattern"]:
            p = pattern_data["primary_pattern"]

            p_col1, p_col2, p_col3, p_col4 = st.columns(4)
            with p_col1:
                quality_suffix = f" · {p.get('quality_grade')}등급" if p.get("quality_grade") else ""
                st.metric(
                    label="주요 가격 패턴",
                    value=p["name"].split("(")[0].strip(),
                    delta=f"신뢰도 {p['confidence']}%{quality_suffix}",
                    help=PATTERN_HELP["pattern"],
                )
            with p_col2:
                st.metric(
                    label="돌파 기준 가격",
                    value=f"${p['neckline']:,.2f}",
                    delta="돌파 완료" if p["is_breakout"] else "돌파 대기",
                    delta_color="normal" if p["is_breakout"] else "off",
                    help=PATTERN_HELP["breakout"],
                )
            with p_col3:
                st.metric(
                    label="예상 목표 가격",
                    value=f"${p['target_price']:,.2f}",
                    delta=f"상승여력 +{p['potential_upside_pct']}%",
                    delta_color="normal",
                    help=PATTERN_HELP["target"],
                )
            with p_col4:
                st.metric(
                    label="위험 관리 가격",
                    value=f"${p['stop_loss']:,.2f}",
                    delta=f"리스크 -{p['risk_pct']}%",
                    delta_color="inverse",
                    help=PATTERN_HELP["stop"],
                )

            current_price = float(df["close"].iloc[-1])
            current_rr = _pattern_reward_risk_result(p, current_price)
            entry_rr = _pattern_reward_risk_result(p, float(p["neckline"]))
            engine_score = (
                float(v4_bundle.get("composite_score", 50))
                if v4_bundle
                else float(v3_bundle.get("composite_score", 50))
                if v3_bundle
                else float(sr_data.get("quality_score", p.get("confidence", 50)))
            )
            setup_strength = _entry_setup_strength(
                p,
                float(sr_data.get("quality_score", 50)),
                engine_score,
                entry_rr["ratio"],
            )
            rr_current_col, rr_entry_col, strength_col = st.columns(3)
            rr_current_col.metric(
                label="현재가 기준 손익비",
                value=f"{current_rr['ratio']:.2f}:1" if current_rr["ratio"] is not None else "산출 제외",
                delta=current_rr["status"],
                delta_color="off" if current_rr["ratio"] is None else "normal",
                help=PATTERN_HELP["reward_risk"],
            )
            rr_entry_col.metric(
                label="돌파 기준 진입 손익비",
                value=f"{entry_rr['ratio']:.2f}:1" if entry_rr["ratio"] is not None else "산출 제외",
                delta=f"기준 가격 ${p['neckline']:,.2f} 진입 가정" if entry_rr["ratio"] is not None else entry_rr["status"],
                delta_color="off" if entry_rr["ratio"] is None else "normal",
                help=PATTERN_HELP["entry_reward_risk"],
            )
            strength_col.metric(
                label="진입 관점 차트 강도",
                value=f"{setup_strength['score']}점 · {setup_strength['label']}",
                delta=setup_strength["interpretation"],
                delta_color="off",
                help=PATTERN_HELP["setup_strength"],
            )

            pattern_description = _friendly_pattern_text(p["description"])
            pattern_status = _friendly_pattern_text(p["status_text"])
            st.markdown(f"""
            <div style="background-color: rgba(255, 255, 255, 0.03); border-left: 3px solid {p['badge_color']}; border-radius: 4px; padding: 12px 16px; margin-top: 10px;">
                <b style="color: {p['badge_color']};">패턴 해석:</b> {pattern_description}<br/>
                <span style="font-size: 0.85rem; color: #cbd5e1;">
                    💡 <b>참고 기준:</b> {pattern_status} 상태입니다. 돌파 기준 가격(${p['neckline']:,.2f})을 유지하는지 확인하고 위험 관리 가격(${p['stop_loss']:,.2f})을 참고하세요.
                </span>
            </div>
            """, unsafe_allow_html=True)

            if use_v2:
                confirm_text = {
                    "가격+거래량 확인": "가격과 거래량 모두 확인됨",
                    "가격 확인·거래량 대기": "가격 조건 충족, 거래량 확인 필요",
                    "패턴 형성 중": "패턴 완성 전",
                }.get(p.get("confirmation_text"), p.get("confirmation_text", "확인 중"))
                volume_ratio = p.get("volume_ratio", 0.0)
                st.caption(
                    f"🧪 v2 패턴 확인 조건: {confirm_text} · 거래량 {volume_ratio:.2f}배 "
                    f"(확인 기준 1.20배) · 마지막 주요 움직임 이후 {p.get('age_bars', 0)}개 봉",
                    help="가격이 돌파 기준을 넘었는지, 거래량이 최근 20개 봉 평균보다 충분히 늘었는지, 패턴이 너무 오래되지 않았는지를 확인합니다.",
                )
                for warning in p.get("warnings", []):
                    st.warning(f"해석 주의: {_friendly_pattern_text(warning)}", icon="⚠️")

            if v3_bundle:
                candle = v3_bundle["candlesticks"].get("strongest")
                if candle:
                    direction = "상승" if candle["direction"] == "bullish" else "하락"
                    st.caption(
                        f"🕯️ v3 캔들 신호: {candle['name']} · {direction} 가능성 · "
                        f"참고 점수 {candle['score']} · 거래량 {candle['volume_ratio']:.2f}배",
                        help=DASHBOARD_HELP["candle"],
                    )
            if v4_bundle:
                momentum = v4_bundle["momentum"]
                st.caption(
                    f"📈 v4 가격 움직임: {momentum.get('summary', '분석 중')}",
                    help=DASHBOARD_HELP["momentum"],
                )

            if len(pattern_data["detected_patterns"]) > 1:
                st.caption("함께 감지된 다른 패턴")
                for sub_p in pattern_data["detected_patterns"][1:]:
                    st.write(f"- **{sub_p['name']}**: {_friendly_pattern_text(sub_p['status_text'])} (신뢰도 {sub_p['confidence']}%)")
        else:
            st.info("현재 뚜렷한 가격 패턴(쌍바닥, 삼각수렴 등)은 감지되지 않았습니다. 지지·저항 및 VCP 분석을 함께 참고하세요.")

    # -------------------------------------------------------------
    # TAB C: 마크 미너비니 VCP 분석
    # -------------------------------------------------------------
    with tab_vcp:
        render_vcp_analysis_panel(df, ticker, analysis=vcp_data, rp_rating=rp_rating, rp_history=rp_history)
        if v4_bundle:
            flow = v4_bundle["volume_flow"]
            st.caption(f"💧 v4 수급 확인: {flow.get('summary', '분석 중')}")

    # -------------------------------------------------------------
    # TAB D: v3 시장 국면·캔들·스퀴즈·워크포워드 검증
    # -------------------------------------------------------------
    with tab_validation:
        if not v3_bundle:
            st.info("Experimental v3 또는 v4 엔진을 선택하면 추가 검증 결과를 볼 수 있습니다.")
        else:
            st.caption("항목 이름 옆 도움말 아이콘에 마우스를 올리면 지표의 뜻과 해석 방법을 볼 수 있습니다.")
            regime = v3_bundle["regime"]
            candles = v3_bundle["candlesticks"]
            squeeze = v3_bundle["squeeze"]
            analysis_bundle = v4_bundle or v3_bundle
            validation = analysis_bundle["validation"]

            d1, d2, d3, d4 = st.columns(4)
            engine_name = "v4" if v4_bundle else "v3"
            d1.metric(f"{engine_name} 종합 점수", f"{analysis_bundle['composite_score']}점", f"{analysis_bundle['grade']}등급", help=DASHBOARD_HELP["score"])
            d2.metric("현재 추세 환경", _friendly_regime_text(regime.get("regime", "분석 불가")), f"평균 변화 {regime.get('slope_pct_per_bar', 0):+.3f}%/봉", help=DASHBOARD_HELP["environment"])
            d3.metric("변동성 압축 상태", "압축 중" if squeeze.get("squeeze_on") else "해제 또는 대기", _friendly_squeeze_text(squeeze.get("summary", "")), help=DASHBOARD_HELP["compression"])
            strongest = candles.get("strongest")
            d4.metric("주요 캔들 신호", strongest["name"] if strongest else "뚜렷한 신호 없음", f"참고 점수 {strongest['score']}" if strongest else "최근 12개 봉", help=DASHBOARD_HELP["candle"])

            if v4_bundle:
                momentum = v4_bundle["momentum"]
                flow = v4_bundle["volume_flow"]
                trend = v4_bundle["trend_strength"]
                v41, v42, v43, v44 = st.columns(4)
                v41.metric("가격 상승·하락 힘", f"{momentum.get('score', 0)}점", momentum.get("direction", "중립"), help=DASHBOARD_HELP["momentum"])
                v42.metric("거래량 기반 매수·매도 흐름", f"{flow.get('score', 0)}점", flow.get("state", "중립"), help=DASHBOARD_HELP["flow"])
                v43.metric("추세 방향과 강도", f"{trend.get('score', 0)}점", f"추세 강도 수치 {trend.get('adx', 0):.1f}", help=DASHBOARD_HELP["trend"])
                suggested_stop = v4_bundle["risk_control"].get("suggested_stop", 0)
                v44.metric("위험 관리 기준 가격", f"${suggested_stop:,.2f}" if suggested_stop else "산출 불가", "가격 구조와 추세선 기준을 함께 반영", help=DASHBOARD_HELP["stop"])
                st.caption(
                    f"가격 움직임: {momentum.get('summary', '')}  |  "
                    f"거래량 흐름: {flow.get('summary', '')}  |  추세 상태: {trend.get('summary', '')}",
                    help="상세 계산에는 RSI·StochRSI, OBV·CMF·MFI, ADX·DMI 지표가 사용됩니다.",
                )

                st.markdown("#### v3·v4 과거 순차 검증 비교")
                st.caption(
                    "같은 과거 구간에서 각 시점 당시까지의 데이터만 사용해 두 엔진을 비교합니다.",
                    help="워크포워드 검증은 미래 데이터를 미리 보지 않고 날짜 순서대로 신호를 계산하는 방식입니다.",
                )
                comparison = v4_bundle["comparison"]
                comparison_df = pd.DataFrame(
                    [
                        {
                            "엔진": name.upper(),
                            "신호 수": values["sample_count"],
                            "10일 후 상승 비율": f"{values['hit_rate_pct']:.1f}%",
                            "10일 평균 수익률": f"{values['avg_return_pct']:+.2f}%",
                            "진입 후 최대 상승폭": f"{values['avg_mfe_pct']:+.2f}%",
                            "진입 후 최대 하락폭": f"{values['avg_mae_pct']:+.2f}%",
                        }
                        for name, values in (("v3", comparison["v3"]), ("v4", comparison["v4"]))
                    ]
                )
                st.dataframe(comparison_df, hide_index=True, use_container_width=True)
                if not comparison.get("comparable"):
                    st.warning("두 엔진 중 과거 신호가 5건 미만인 경우가 있어 성능 비교는 보류하세요.")

            st.markdown(f"#### {engine_name} 미래 데이터를 보지 않는 과거 순차 검증")
            w1, w2, w3, w4, w5 = st.columns(5)
            w1.metric("중복 제거 신호 수", f"{validation.get('sample_count', 0)}건", help=DASHBOARD_HELP["samples"])
            w2.metric("10일 후 상승 비율", f"{validation.get('hit_rate_pct', 0):.1f}%", help=DASHBOARD_HELP["hit_rate"])
            w3.metric("10일 평균 수익률", f"{validation.get('avg_return_pct', 0):+.2f}%", help=DASHBOARD_HELP["return"])
            w4.metric("진입 후 최대 상승폭", f"{validation.get('avg_mfe_pct', 0):+.2f}%", help=DASHBOARD_HELP["upside"])
            w5.metric("진입 후 최대 하락폭", f"{validation.get('avg_mae_pct', 0):+.2f}%", help=DASHBOARD_HELP["downside"])
            if validation.get("sample_count", 0) < 5:
                st.warning(validation.get("warning", "표본이 적어 결과 해석에 주의가 필요합니다."))
            else:
                st.caption(f"✅ 신호 계산은 당일 이전 20일 데이터만 사용합니다. {validation.get('warning', '')}")

            last_change = regime.get("last_change")
            if last_change:
                st.caption(
                    f"추세 환경이 달라진 시점 후보: {last_change['bars_ago']}개 봉 전 · "
                    f"변화 강도 {last_change['strength']:.2f}",
                    help="수익률과 변동성의 평균 수준이 이전 구간과 크게 달라진 지점을 찾은 결과입니다.",
                )
            cost_note = f"왕복 비용 {validation.get('cost_pct', 0):.2f}% 반영" if v4_bundle else "슬리피지·수수료·세금 미반영"
            st.caption(f"연구용 진단이며 자동주문에는 연결되지 않습니다. {cost_note}.")
