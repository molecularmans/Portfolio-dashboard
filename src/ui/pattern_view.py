import streamlit as st
import pandas as pd
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
from src.ui.vcp_view import render_vcp_analysis_panel


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

    # 1. 알고리즘 분석 실행 — 테스트 단계에서는 기존 엔진과 즉시 A/B 비교 가능
    if engine == "v4":
        v4_bundle = analyze_smart_chart_v4(df)
        v3_bundle = v4_bundle["v3_baseline"]
        sr_data = v4_bundle["support_resistance"]
        pattern_data = v4_bundle["patterns"]
        vcp_data = v4_bundle["vcp"]
    elif engine == "v3":
        v3_bundle = analyze_smart_chart_v3(df)
        sr_data = v3_bundle["support_resistance"]
        pattern_data = v3_bundle["patterns"]
        vcp_data = v3_bundle["vcp"]
    elif engine == "v2":
        sr_data = analyze_support_resistance_v2(df)
        pattern_data = analyze_chart_patterns_v2(df)
        vcp_data = analyze_vcp_v2(df)
    else:
        sr_data = analyze_support_resistance_and_trendlines(df)
        pattern_data = detect_all_chart_patterns(df)
        vcp_data = None

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

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.85) 100%);
        border: 1.5px solid rgba(56, 189, 248, 0.35);
        border-radius: 12px;
        padding: 16px 20px;
        margin-top: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <span style="font-size: 1.15rem; font-weight: 700; color: #f8fafc; margin-right: 10px;">
                    🎯 {ticker} 차트 종합 진단 엔진 (AI Pattern & Trendline)
                </span>
                <span style="font-size: 0.82rem; color: #94a3b8;">
                    {engine_label}{quality_label} · Support / Resistance · Trendlines · Classic Formations
                </span>
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <div style="
                    background-color: {sr_color}22;
                    border: 1px solid {sr_color};
                    color: {sr_color};
                    padding: 4px 12px;
                    border-radius: 16px;
                    font-size: 0.85rem;
                    font-weight: 600;
                ">
                    {sr_badge}
                </div>
                {f'''<div style="
                    background-color: {primary_pat['badge_color']}22;
                    border: 1px solid {primary_pat['badge_color']};
                    color: {primary_pat['badge_color']};
                    padding: 4px 12px;
                    border-radius: 16px;
                    font-size: 0.85rem;
                    font-weight: 600;
                ">
                    {primary_pat['name']}
                </div>''' if primary_pat else ''}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------
    # 탭 구성: [A] 지지/저항 & 추세선 | [B] 차트 포메이션 패턴 | [C] 미너비니 VCP
    # -------------------------------------------------------------
    tab_sr, tab_pattern, tab_vcp, tab_validation = st.tabs([
        "📐 [A] 자동 지지·저항 & 추세선",
        "💎 [B] 고전 차트 패턴 (쌍바닥·수렴)",
        "🧠 [C] 마크 미너비니 VCP 분석",
        "🧪 [D] 국면·캔들·워크포워드",
    ])

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
        if pattern_data["has_pattern"]:
            p = pattern_data["primary_pattern"]

            p_col1, p_col2, p_col3, p_col4 = st.columns(4)
            with p_col1:
                quality_suffix = f" · {p.get('quality_grade')}등급" if p.get("quality_grade") else ""
                st.metric(
                    label="감지된 차트 패턴",
                    value=p["name"].split("(")[0].strip(),
                    delta=f"신뢰도 {p['confidence']}%{quality_suffix}",
                )
            with p_col2:
                st.metric(
                    label="기준 돌파가 (Neckline)",
                    value=f"${p['neckline']:,.2f}",
                    delta="돌파 완료" if p["is_breakout"] else "돌파 대기",
                    delta_color="normal" if p["is_breakout"] else "off",
                )
            with p_col3:
                st.metric(
                    label="1차 목표가 (Target)",
                    value=f"${p['target_price']:,.2f}",
                    delta=f"상승여력 +{p['potential_upside_pct']}%",
                    delta_color="normal",
                )
            with p_col4:
                st.metric(
                    label="손절 기준가 (Stop Loss)",
                    value=f"${p['stop_loss']:,.2f}",
                    delta=f"리스크 -{p['risk_pct']}%",
                    delta_color="inverse",
                )

            st.markdown(f"""
            <div style="background-color: rgba(255, 255, 255, 0.03); border-left: 3px solid {p['badge_color']}; border-radius: 4px; padding: 12px 16px; margin-top: 10px;">
                <b style="color: {p['badge_color']};">패턴 상세 분석:</b> {p['description']}<br/>
                <span style="font-size: 0.85rem; color: #cbd5e1;">
                    💡 <b>매매 전략:</b> {p['status_text']} 구간입니다. 넥라인(${p['neckline']:,.2f}) 지지 여부를 체크하며 손절선(${p['stop_loss']:,.2f})을 엄격히 준수하세요.
                </span>
            </div>
            """, unsafe_allow_html=True)

            if use_v2:
                confirm_text = p.get("confirmation_text", "확인 중")
                volume_ratio = p.get("volume_ratio", 0.0)
                st.caption(f"🧪 v2 확인 필터: {confirm_text} · 돌파 거래량 {volume_ratio:.2f}× (기준 1.20×) · 패턴 신선도 {p.get('age_bars', 0)}봉")
                for warning in p.get("warnings", []):
                    st.warning(f"과최적화/오탐 주의: {warning}", icon="⚠️")

            if v3_bundle:
                candle = v3_bundle["candlesticks"].get("strongest")
                if candle:
                    direction = "상승" if candle["direction"] == "bullish" else "하락"
                    st.caption(
                        f"🕯️ v3 캔들 확인: {candle['name']} · {direction} 후보 · "
                        f"점수 {candle['score']} · 거래량 {candle['volume_ratio']:.2f}×"
                    )
            if v4_bundle:
                momentum = v4_bundle["momentum"]
                st.caption(f"📈 v4 모멘텀 확인: {momentum.get('summary', '분석 중')}")

            if len(pattern_data["detected_patterns"]) > 1:
                st.caption("기타 감지된 부가 패턴")
                for sub_p in pattern_data["detected_patterns"][1:]:
                    st.write(f"- **{sub_p['name']}**: {sub_p['status_text']} (신뢰도 {sub_p['confidence']}%)")
        else:
            st.info("현재 뚜렷한 고전 기하학적 차트 패턴(쌍바닥, 삼각수렴 등)이 진행 중이지 않습니다. 지지/저항선 및 VCP 분석 탭을 참고하세요.")

    # -------------------------------------------------------------
    # TAB C: 마크 미너비니 VCP 분석
    # -------------------------------------------------------------
    with tab_vcp:
        render_vcp_analysis_panel(df, ticker, analysis=vcp_data)
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
            regime = v3_bundle["regime"]
            candles = v3_bundle["candlesticks"]
            squeeze = v3_bundle["squeeze"]
            analysis_bundle = v4_bundle or v3_bundle
            validation = analysis_bundle["validation"]

            d1, d2, d3, d4 = st.columns(4)
            engine_name = "v4" if v4_bundle else "v3"
            d1.metric(f"{engine_name} 종합 점수", f"{analysis_bundle['composite_score']}점", f"{analysis_bundle['grade']}등급")
            d2.metric("현재 시장 국면", regime.get("regime", "분석 불가"), f"기울기 {regime.get('slope_pct_per_bar', 0):+.3f}%/봉")
            d3.metric("BB/KC 스퀴즈", "진행 중" if squeeze.get("squeeze_on") else "해제/대기", squeeze.get("summary", ""))
            strongest = candles.get("strongest")
            d4.metric("최강 캔들 신호", strongest["name"] if strongest else "없음", f"점수 {strongest['score']}" if strongest else "최근 12봉")

            if v4_bundle:
                momentum = v4_bundle["momentum"]
                flow = v4_bundle["volume_flow"]
                trend = v4_bundle["trend_strength"]
                v41, v42, v43, v44 = st.columns(4)
                v41.metric("모멘텀", f"{momentum.get('score', 0)}점", momentum.get("direction", "중립"))
                v42.metric("수급", f"{flow.get('score', 0)}점", flow.get("state", "중립"))
                v43.metric("추세 강도", f"{trend.get('score', 0)}점", f"ADX {trend.get('adx', 0):.1f}")
                suggested_stop = v4_bundle["risk_control"].get("suggested_stop", 0)
                v44.metric("제안 손절 기준", f"${suggested_stop:,.2f}" if suggested_stop else "산출 불가", "구조·SuperTrend 중 가까운 값")
                st.caption(
                    f"RSI/StochRSI: {momentum.get('summary', '')}  |  "
                    f"OBV/CMF/MFI: {flow.get('summary', '')}  |  ADX/DMI: {trend.get('summary', '')}"
                )

                st.markdown("#### v3 ↔ v4 동일 구간 워크포워드 비교")
                comparison = v4_bundle["comparison"]
                comparison_df = pd.DataFrame(
                    [
                        {
                            "엔진": name.upper(),
                            "표본": values["sample_count"],
                            "양(+) 수익 비율": f"{values['hit_rate_pct']:.1f}%",
                            "평균 순수익": f"{values['avg_return_pct']:+.2f}%",
                            "평균 최대 유리폭": f"{values['avg_mfe_pct']:+.2f}%",
                            "평균 최대 불리폭": f"{values['avg_mae_pct']:+.2f}%",
                        }
                        for name, values in (("v3", comparison["v3"]), ("v4", comparison["v4"]))
                    ]
                )
                st.dataframe(comparison_df, hide_index=True, use_container_width=True)
                if not comparison.get("comparable"):
                    st.warning("두 엔진 중 표본 5건 미만이 있어 우열 판단은 보류하세요.")

            st.markdown(f"#### {engine_name} 룩어헤드 방지 워크포워드 검증")
            w1, w2, w3, w4, w5 = st.columns(5)
            w1.metric("독립 신호 표본", f"{validation.get('sample_count', 0)}건")
            w2.metric("10일 양(+) 수익 비율", f"{validation.get('hit_rate_pct', 0):.1f}%")
            w3.metric("평균 10일 수익", f"{validation.get('avg_return_pct', 0):+.2f}%")
            w4.metric("평균 최대 유리폭", f"{validation.get('avg_mfe_pct', 0):+.2f}%")
            w5.metric("평균 최대 불리폭", f"{validation.get('avg_mae_pct', 0):+.2f}%")
            if validation.get("sample_count", 0) < 5:
                st.warning(validation.get("warning", "표본이 적어 결과 해석에 주의가 필요합니다."))
            else:
                st.caption(f"✅ 신호 계산은 당일 이전 20일 데이터만 사용합니다. {validation.get('warning', '')}")

            last_change = regime.get("last_change")
            if last_change:
                st.caption(
                    f"시장 구조 변화 후보: {last_change['bars_ago']}봉 전 · "
                    f"강도 {last_change['strength']:.2f} · 변화점은 ruptures식 분할 개념의 경량 구현입니다."
                )
            cost_note = f"왕복 비용 {validation.get('cost_pct', 0):.2f}% 반영" if v4_bundle else "슬리피지·수수료·세금 미반영"
            st.caption(f"연구용 진단이며 자동주문에는 연결되지 않습니다. {cost_note}.")
