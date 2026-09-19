import streamlit as st
import pandas as pd
from typing import Dict, Any

from src.indicators.trendline_analyzer import analyze_support_resistance_and_trendlines
from src.indicators.pattern_detector import detect_all_chart_patterns
from src.ui.vcp_view import render_vcp_analysis_panel


def render_pattern_analysis_dashboard(df: pd.DataFrame, ticker: str):
    """
    [A] 자동 추세선/지지저항선 + [B] 고전 차트 패턴 + 마크 미너비니 VCP를 총망라한 통합 분석 패널
    """
    if df.empty or len(df) < 30:
        st.info(f"📊 {ticker}의 정밀 차트 패턴 분석을 위한 충분한 과거 데이터가 부족합니다.")
        return

    # 1. 알고리즘 분석 실행
    sr_data = analyze_support_resistance_and_trendlines(df)
    pattern_data = detect_all_chart_patterns(df)

    # -------------------------------------------------------------
    # 섹션 1: 상단 종합 분석 브리핑 헤더
    # -------------------------------------------------------------
    primary_pat = pattern_data.get("primary_pattern")
    sr_badge = sr_data.get("status_badge", "분석 완료")
    sr_color = sr_data.get("status_color", "#38bdf8")

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
                    Support / Resistance · Trendlines · Classic Formations
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
    tab_sr, tab_pattern, tab_vcp = st.tabs([
        "📐 [A] 자동 지지·저항 & 추세선",
        "💎 [B] 고전 차트 패턴 (쌍바닥·수렴)",
        "🧠 [C] 마크 미너비니 VCP 분석"
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
                st.metric(
                    label="하단 지지 추세선",
                    value=f"${lower_tl['current_price']:,.2f}",
                    delta=slope_str,
                    delta_color="normal" if lower_tl["slope"] > 0 else "inverse",
                    help="최근 주요 저점들을 연결한 하단 지지선입니다. 이탈 시 손절 및 비중 축소가 권장됩니다.",
                )
            else:
                st.metric(label="하단 지지 추세선", value="계산 중")

        # 진단 해설 및 주요 레벨 목록
        st.markdown(f"""
        <div style="background-color: rgba(255, 255, 255, 0.03); border-radius: 8px; padding: 12px 16px; margin-top: 10px;">
            <b style="color: {sr_color};">📌 추세선 및 매물대 진단:</b> {sr_data.get('status_desc', '')}
        </div>
        """, unsafe_allow_html=True)

        col_sups, col_ress = st.columns(2)
        with col_sups:
            st.caption("🛡️ 하단 주요 지지 매물대 (터치 횟수 순)")
            if sr_data["support_levels"]:
                for s in sr_data["support_levels"]:
                    st.write(f"- **${s['price']:,.2f}** &nbsp; (지지의식 {s['touches']}회)")
            else:
                st.write("- 추가 지지 매물대 분석 중")

        with col_ress:
            st.caption("🛑 상단 주요 저항 매물대 (터치 횟수 순)")
            if sr_data["resistance_levels"]:
                for r in sr_data["resistance_levels"]:
                    st.write(f"- **${r['price']:,.2f}** &nbsp; (저항의식 {r['touches']}회)")
            else:
                st.write("- 상단 매물 부담 적음 (신고가 랠리 영역)")

    # -------------------------------------------------------------
    # TAB B: 고전 차트 패턴 (쌍바닥, 삼각수렴 등)
    # -------------------------------------------------------------
    with tab_pattern:
        if pattern_data["has_pattern"]:
            p = pattern_data["primary_pattern"]

            p_col1, p_col2, p_col3, p_col4 = st.columns(4)
            with p_col1:
                st.metric(
                    label="감지된 차트 패턴",
                    value=p["name"].split("(")[0].strip(),
                    delta=f"신뢰도 {p['confidence']}%",
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
        render_vcp_analysis_panel(df, ticker)
