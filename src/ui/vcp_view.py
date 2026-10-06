import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from src.indicators.vcp_analyzer import detect_vcp_pattern, check_trend_template
from src.indicators.relative_performance import load_rp_reference


def render_vcp_analysis_panel(df: pd.DataFrame, ticker: str, analysis: dict | None = None,
                              rp_rating: float | None = None, rp_history: pd.DataFrame | None = None):
    """
    마크 미너비니 VCP 패턴 및 일봉 추세 템플릿 분석 대시보드 렌더링
    """
    if df.empty or len(df) < 30:
        st.info(f"📊 {ticker}의 VCP 정밀 분석을 위한 충분한 과거 데이터가 부족합니다.")
        return

    # VCP 정밀 알고리즘 분석 실행
    vcp_data = analysis if analysis is not None else detect_vcp_pattern(df, rp_rating=rp_rating)
    tt = vcp_data["trend_template"]
    pivot = vcp_data["pivot"]
    vdu = vcp_data["volume_dryup"]
    contractions = vcp_data["contractions"]

    status_badge = vcp_data["status_badge"]
    status_color = vcp_data["status_color"]

    # 컨테이너 스타일링
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1.5px solid {status_color}55;
        border-radius: 12px;
        padding: 16px 20px;
        margin-top: 18px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <span style="font-size: 1.1rem; font-weight: 700; color: #f8fafc; margin-right: 12px;">
                    🧠 마크 미너비니 VCP(변동성 축소) 차트 패턴 해석
                </span>
                <span style="font-size: 0.82rem; color: #94a3b8;">
                    Trend Template & Volatility Contraction Pattern Analysis
                </span>
            </div>
            <div style="
                background-color: {status_color}22;
                border: 1px solid {status_color};
                color: {status_color};
                padding: 5px 14px;
                border-radius: 20px;
                font-size: 0.88rem;
                font-weight: 700;
            ">
                {status_badge}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 핵심 4대 지표 카드
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            label="VCP 수축 단계",
            value=f"{vcp_data['contraction_count']}T 수축",
            delta="수축 축소 확인됨" if vcp_data["is_diminishing"] else "수축 불규칙",
            delta_color="normal" if vcp_data["is_diminishing"] else "inverse",
            help="최근 고점 이후 상하 진폭이 몇 차례 좁아졌는지를 나타냅니다 (보통 2T~4T에서 돌파 발생).",
        )

    with c2:
        dist_str = f"{pivot['dist_pct']:+.1f}%"
        st.metric(
            label="피봇 돌파 매수가 (Buy Point)",
            value=f"${pivot['price']:,.2f}",
            delta=f"현재가 대비 {dist_str}",
            help="마지막 수축 파동의 고점 또는 베이스 상단 저항선입니다. 대량 거래량과 함께 돌파 시 매수 급소입니다.",
        )

    with c3:
        st.metric(
            label="추천 손절 기준가 (Stop Loss)",
            value=f"${pivot['stop_loss']:,.2f}",
            delta=f"리스크 -{pivot['risk_pct']:.1f}%",
            delta_color="inverse",
            help="마지막 최저점 수축 구간입니다. 피봇 대비 손절 폭이 좁을수록 뛰어난 손익비를 제공합니다.",
        )

    with c4:
        vdu_delta_str = "매도세 고갈 (VDU)" if vdu["is_vdu"] else "추가 거래량 건조 필요"
        st.metric(
            label="거래량 건조 지수 (VDU)",
            value=f"{vdu['ratio']:.1f}%",
            delta=vdu_delta_str,
            delta_color="normal" if vdu["is_vdu"] else "off",
            help="최근 5일 평균 거래량이 50일 평균 거래량의 몇 % 수준으로 말랐는지를 나타냅니다 (70% 이하 시 VDU 충족).",
        )

    if "quality_score" in vcp_data:
        volatility = vcp_data.get("volatility", {})
        supply = vcp_data.get("supply", {})
        breakout = vcp_data.get("breakout_confirmation", {})
        st.caption(
            f"🧪 **VCP 품질 {vcp_data['quality_score']}점 ({vcp_data.get('quality_grade', 'N/A')}등급)** · "
            f"ATR 축소비 {volatility.get('atr_ratio_pct', 0):.1f}% · "
            f"거래량 추세 {supply.get('volume_slope_pct', 0):+.2f}%/봉 · "
            f"돌파 거래량 {breakout.get('volume_ratio', 0):.2f}×"
        )

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # 3개 상세 분석 탭
    tab_waves, tab_trend, tab_report = st.tabs([
        "🌊 변동성 수축 파동 (Contractions)",
        "📋 미너비니 추세 템플릿 (D·10개 조건)",
        "💡 미너비니 종합 리포트 & 실전 전략"
    ])

    # 탭 1: 수축 파동 단계별 시각화
    with tab_waves:
        st.markdown("##### 🔍 단계별 변동성 수축 파동 상세")
        if contractions:
            cols = st.columns(len(contractions))
            for idx, c in enumerate(contractions):
                with cols[idx]:
                    st.markdown(f"""
                    <div style="
                        background-color: rgba(255, 255, 255, 0.04);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        border-radius: 8px;
                        padding: 12px;
                        text-align: center;
                    ">
                        <div style="font-size: 0.85rem; font-weight: 700; color: #38bdf8; margin-bottom: 4px;">
                            {c['stage']} 단계 수축
                        </div>
                        <div style="font-size: 1.25rem; font-weight: 700; color: #ef5350;">
                            {c['depth_pct']}%
                        </div>
                        <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 6px;">
                            고점: ${c['peak_price']:,.2f} ({c['peak_date']})<br>
                            저점: ${c['trough_price']:,.2f} ({c['trough_date']})<br>
                            소요: 약 {c['bars']}봉
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            # 수축폭 비교 프로그레스 안내
            is_valid_diminish = vcp_data["is_diminishing"]
            diminish_text = "✅ **수축 감소성 통과**: 각 수축 단계마다 진폭이 점진적으로 좁아지고 있어 매도 물량이 말라가는 전형적인 VCP 규칙을 만족합니다." if is_valid_diminish else "⚠️ **수축 불규칙**: 최근 수축 폭이 이전보다 다소 넓어져 변동성이 아직 완전히 안정되지 않았습니다."
            st.markdown(diminish_text)
        else:
            st.caption("최근 90일 구간 내 감지된 수축 파동이 없습니다.")

    # 탭 2: 스크린샷의 10개 조건별 추세 템플릿 검증표
    with tab_trend:
        st.markdown(f"##### 📋 Minervini Trend Template (D) — {tt['pass_count']}/{tt['total_count']}")
        
        table_rows = []
        for chk in tt["checks"]:
            mark = "➖ 확인 불가" if chk["passed"] is None else "✅ 통과" if chk["passed"] else "❌ 미달"
            table_rows.append({
                "검증 항목": chk["name"],
                "설명": chk["desc"],
                "현재 수치": chk["current"],
                "필요 기준": chk["required"],
                "판정": mark,
            })

        df_table = pd.DataFrame(table_rows)
        st.dataframe(df_table, use_container_width=True, hide_index=True)

        st.markdown("**현재 값 (Current Values)**")
        rp_col, high_col, low_col = st.columns(3)
        rp = tt.get("rp_rating")
        dist_high = tt.get("dist_from_52w_high_pct")
        dist_low = tt.get("dist_from_52w_low_pct")
        rp_col.metric("RP", f"{rp:.1f}" if rp is not None else "확인 불가")
        high_col.metric("주가 vs 52주 고점", f"{dist_high:+.1f}%" if dist_high is not None else "데이터 부족")
        low_col.metric("주가 vs 52주 저점", f"{dist_low:+.1f}%" if dist_low is not None else "데이터 부족")

        st.markdown("**RP 상대강도 추이 · S&P 500 종목군 대비**")
        if rp_history is not None and not rp_history.empty:
            points = rp_history.tail(60)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=points["date"], y=points["rp"], mode="lines+markers",
                name="RP", line=dict(color="#38bdf8", width=3),
                marker=dict(size=4), hovertemplate="%{x|%Y-%m-%d}<br>RP %{y:.1f}<extra></extra>",
            ))
            fig.add_hline(y=70, line_dash="dash", line_color="#f59e0b",
                          annotation_text="템플릿 기준 70", annotation_position="top left")
            fig.update_layout(
                height=290, margin=dict(l=10, r=10, t=15, b=10),
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(title="RP 점수", range=[0, 100]),
                xaxis=dict(title=None), showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
            latest_rp_date = points["date"].iloc[-1].strftime("%Y-%m-%d")
            reference = load_rp_reference() or {}
            st.caption(
                f"자체 산출 RP · 최근 기준일 {latest_rp_date} · 비교 종목 {int(points['peer_count'].iloc[-1])}개 · "
                "3/6/9/12개월 수익률 40/20/20/20 가중(63/126/189/252거래일 근사). "
                f"기준 자료 업데이트: {reference.get('as_of', '확인 불가')}. TrendSpider 점수와 다를 수 있습니다."
            )
        elif ticker.isdigit() and len(ticker) == 6:
            st.caption("현재 RP 기준 종목군은 미국 S&P 500입니다. 국내 종목 RP는 제공하지 않습니다.")
        else:
            st.caption("RP 기준 자료 또는 1년 이상의 일봉 데이터가 아직 없어 그래프를 표시할 수 없습니다.")

        pending_count = tt["total_count"] - tt.get("evaluated_count", tt["total_count"])
        if pending_count:
            reason = "RP는 최신 S&P 500 기준 자료와 1년 이상의 일봉이 있어야 판정할 수 있습니다. " if rp is None else ""
            st.caption(f"{pending_count}개 항목 미확인 · {reason}이 화면은 일봉 약 250거래일을 기준으로 합니다.")

        if tt["is_stage_2"]:
            if pending_count:
                st.info(f"가격 추세는 Stage 2 기준을 충족합니다 ({tt['pass_count']}/{tt['total_count']}). 미확인 항목은 별도 확인이 필요합니다.")
            else:
                st.success(f"Stage 2 추세 기준 충족: {tt['pass_count']}/{tt['total_count']}개 항목 통과")
        else:
            st.warning(f"추세 기준 미충족 또는 자료 부족: {tt['pass_count']}/{tt['total_count']}개 통과. 미달·미확인 항목을 확인하세요.")

    # 탭 3: 자연어 해석 리포트 & 실전 전략
    with tab_report:
        st.markdown("##### 🎙️ 미너비니 투자 관점 종합 브리핑")
        st.markdown(f"""
        <div style="
            background-color: rgba(15, 23, 42, 0.6);
            border-left: 4px solid {status_color};
            border-radius: 4px;
            padding: 14px 18px;
            line-height: 1.7;
            font-size: 0.92rem;
            color: #e2e8f0;
        ">
            {vcp_data['summary_text'].replace(chr(10), '<br>')}
        </div>
        """, unsafe_allow_html=True)
