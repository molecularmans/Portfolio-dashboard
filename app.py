import streamlit as st
import pandas as pd

from src.db.database import StockDB
from src.api.kis_rest import KISClient
from src.indicators.technicals import calc_indicators
from src.ui.charts import create_mini_chart, create_detail_chart, CHART_CONFIG
from src.ui.tradingview import render_tradingview_chart
from src.ui.sidebar import render_sidebar

# 1. Streamlit 페이지 기본 설정 (와이드 모드)
st.set_page_config(
    page_title="Personal Stock Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 커스텀 스타일 적용
st.markdown("""
<style>
    .metric-card {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
    }
    .positive-text {
        color: #26a69a;
        font-weight: 600;
    }
    .negative-text {
        color: #ef5350;
        font-weight: 600;
    }
    .stButton>button {
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)


def init_services():
    """DB 및 KIS 클라이언트 초기화"""
    db = StockDB()
    client = KISClient()
    return db, client


def load_and_calc_stock_data(ticker: str, db: StockDB, client: KISClient, force_refresh: bool = False, timeframe: str = "일봉") -> pd.DataFrame:
    ticker = ticker.upper().strip()
    tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    tf_code = tf_map.get(timeframe, "D")
    min_required = 80 if tf_code == "D" else (40 if tf_code == "W" else 20)
    count_target = 300 if tf_code == "D" else (200 if tf_code == "W" else 120)

    df = pd.DataFrame()
    if not force_refresh:
        df = db.get_prices(ticker, timeframe=tf_code)

    if df.empty or len(df) < min_required or force_refresh:
        if ticker.isdigit() and len(ticker) == 6:
            df = client.get_kr_ohlcv(ticker, timeframe=tf_code, count=count_target)
        else:
            df = client.get_us_ohlcv(ticker, timeframe=tf_code, count=count_target)

        if not df.empty:
            db.save_prices(ticker, tf_code, df)

    return calc_indicators(df)


def main():
    db, client = init_services()

    # Session State 초기화
    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = None
    if "force_refresh" not in st.session_state:
        st.session_state.force_refresh = False

    # 좌측 사이드바 렌더링
    settings = render_sidebar(db, client)
    force_refresh = st.session_state.get("force_refresh", False)
    st.session_state["force_refresh"] = False
    timeframe = settings.get("timeframe", "일봉")

    # 대상 티커 목록 및 포트폴리오 결정 (다중 계좌 지원)
    view_mode = settings["view_mode"]
    tickers = []
    portfolio_items = []
    is_portfolio_mode = "포트폴리오" in view_mode or "잔고" in view_mode
    accounts = client.auth.get_accounts_list()

    if is_portfolio_mode:
        if "통합" in view_mode or len(accounts) <= 1:
            portfolio_items = client.get_combined_balance()
        else:
            # 특정 계좌 선택 시 매칭
            target_acc = None
            for acc in accounts:
                if acc["name"] in view_mode:
                    target_acc = acc
                    break
            if target_acc:
                portfolio_items = client.get_overseas_balance(account_idx=target_acc["idx"])
            else:
                portfolio_items = client.get_combined_balance()

        # 수익률 기준 내림차순 정렬 (높은 순 > 낮은 순)
        portfolio_items = sorted(portfolio_items, key=lambda x: float(x.get("profit_rate", 0)), reverse=True)
        tickers = [item["ticker"] for item in portfolio_items]

    elif "전체 관심종목" in view_mode:
        watchlist_df = db.get_watchlist()
        tickers = watchlist_df["ticker"].tolist() if not watchlist_df.empty else []
    else:
        selected_grp = view_mode.replace("📁 ", "").strip()
        watchlist_df = db.get_watchlist(group_name=selected_grp)
        tickers = watchlist_df["ticker"].tolist() if not watchlist_df.empty else []

    # ==========================================
    # 상단 서머리 헤더 바
    # ==========================================
    st.title("📈 Stock Terminal & Multi-Chart Dashboard")

    if is_portfolio_mode and portfolio_items:
        total_eval = sum(item["eval_amount"] for item in portfolio_items)
        st.caption(f"💼 {view_mode} 실시간 현황")
        m_cols = st.columns(len(portfolio_items) + 1)
        m_cols[0].metric("총 평가금액", f"${total_eval:,.2f}")
        for i, item in enumerate(portfolio_items):
            m_cols[i + 1].metric(
                label=f"{item['ticker']} ({item['qty']}주)",
                value=f"${item['current_price']:,.2f}",
                delta=f"{item['profit_rate']:+.2f}%",
            )
        st.divider()

    # ==========================================
    # VIEW 모드 1: 특정 종목 상세 확대 분석 뷰 (트레이딩뷰 프로 차트)
    # ==========================================
    if st.session_state.selected_ticker:
        sel_ticker = st.session_state.selected_ticker

        col_back, col_title, col_tf = st.columns([1.5, 4, 2])
        if col_back.button("⬅️ 전체 멀티차트로 돌아가기", use_container_width=True):
            st.session_state.selected_ticker = None
            st.rerun()

        col_title.subheader(f"🔍 {sel_ticker} 상세 기술적 분석")
        detail_tf = col_tf.radio("차트 주기", ["일봉", "주봉", "월봉"], index=["일봉", "주봉", "월봉"].index(timeframe), horizontal=True, key="detail_tf_select")
        
        detail_settings = settings.copy()
        detail_settings["timeframe"] = detail_tf

        # 데이터 로드 및 계산
        with st.spinner(f"{sel_ticker} 데이터 불러오는 중..."):
            df = load_and_calc_stock_data(sel_ticker, db, client, force_refresh, timeframe=detail_tf)

        if not df.empty and len(df) >= 5:
            latest = df.iloc[-1]
            pct_1d = latest.get("pct_change_1d", 0)

            # 상단 핵심 메트릭 카드
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("현재가", f"${latest['close']:,.2f}", f"{pct_1d:+.2f}%")
            c2.metric(f"RVOL ({detail_tf} 20기간 대비)", f"{latest.get('rvol', 1.0):.2f}x")
            c3.metric("최고가 대비 이격도", f"{latest.get('dist_52w_high', 0):+.2f}%")
            c4.metric("RSI (14)", f"{latest.get('rsi_14', 50):.1f}")

            # 이동평균선 현황 카드
            with st.expander(f"📊 {detail_tf} 기준 7대 이동평균선 수치 요약", expanded=False):
                m_c1, m_c2, m_c3, m_c4, m_c5, m_c6, m_c7 = st.columns(7)
                m_c1.metric("5 EMA", f"${latest.get('ema_5', 0):,.2f}")
                m_c2.metric("10 MA", f"${latest.get('sma_10', 0):,.2f}")
                m_c3.metric("20 MA", f"${latest.get('sma_20', 0):,.2f}")
                m_c4.metric("30 MA", f"${latest.get('sma_30', 0):,.2f}")
                m_c5.metric("50 MA", f"${latest.get('sma_50', 0):,.2f}")
                m_c6.metric("150 MA", f"${latest.get('sma_150', 0):,.2f}")
                m_c7.metric("200 MA", f"${latest.get('sma_200', 0):,.2f}")

        # 차트 보기 모드 탭
        chart_tab1, chart_tab2 = st.tabs(["🔥 트레이딩뷰 프로 차트 (추세선/HTS 풀도구 지원)", "📊 멀티 서브플롯 차트"])

        with chart_tab1:
            st.caption("💡 **트레이딩뷰 좌측 툴바**에서 추세선, 수평선, 피보나치, 채널 등을 마우스로 직접 긋고, 클릭하여 복사/삭제/색상변경을 자유롭게 사용할 수 있습니다. (자동 저장 지원)")
            render_tradingview_chart(sel_ticker, timeframe=detail_tf, settings=detail_settings, height=750)

        with chart_tab2:
            detail_fig = create_detail_chart(df, sel_ticker, detail_settings)
            st.plotly_chart(detail_fig, use_container_width=True, config=CHART_CONFIG)

        if not df.empty:
            with st.expander(f"📋 최근 10개 {detail_tf} 지표 데이터"):
                display_cols = [
                    "date", "open", "high", "low", "close", "volume",
                    "ema_5", "sma_10", "sma_20", "sma_30", "sma_50", "sma_150", "sma_200",
                    "rvol", "rsi_14", "stoch_k", "williams_r", "macd_line"
                ]
                existing_cols = [c for c in display_cols if c in df.columns]
                st.dataframe(df[existing_cols].tail(10).sort_values("date", ascending=False), use_container_width=True)

        return

    # ==========================================
    # VIEW 모드 2: 멀티 차트 그리드 요약 뷰
    # ==========================================
    st.subheader(f"📊 {view_mode} ({len(tickers)} 종목) · {timeframe}")

    if not tickers:
        st.info("해당 포트폴리오/그룹에 등록된 종목이 없습니다. 좌측에서 다른 모드를 선택해보세요.")
        return

    st.caption(f"현재 **[{timeframe}]** 주기로 표시 중입니다. '🔍 자세히 보기'를 클릭하면 상세 분석 모드로 전환됩니다.")

    # 3열 반응형 그리드 레이아웃
    NUM_COLS = 3
    rows = [tickers[i:i + NUM_COLS] for i in range(0, len(tickers), NUM_COLS)]

    for row in rows:
        cols = st.columns(NUM_COLS)
        for idx, ticker in enumerate(row):
            with cols[idx]:
                df = load_and_calc_stock_data(ticker, db, client, force_refresh, timeframe=timeframe)
                if df.empty or len(df) < 5:
                    st.warning(f"{ticker} 데이터 없음")
                    continue

                latest = df.iloc[-1]
                pct_1d = latest.get("pct_change_1d", 0)
                rvol = latest.get("rvol", 1.0)
                color_class = "positive-text" if pct_1d >= 0 else "negative-text"
                sign = "+" if pct_1d >= 0 else ""

                # 종목 상단 헤더 & 자세히 보기 버튼
                head_col1, head_col2 = st.columns([3, 2])
                with head_col1:
                    st.markdown(f"**{ticker}** &nbsp; <span class='{color_class}'>${latest['close']:,.2f} ({sign}{pct_1d:.2f}%)</span>", unsafe_allow_html=True)
                    st.caption(f"RVOL: **{rvol:.2f}x** | 52W: **{latest.get('dist_52w_high', 0):+.1f}%**")
                with head_col2:
                    if st.button("🔍 자세히 보기", key=f"btn_zoom_{ticker}", use_container_width=True):
                        st.session_state.selected_ticker = ticker
                        st.rerun()

                # 미니 차트 렌더링
                mini_fig = create_mini_chart(df, ticker, settings)
                st.plotly_chart(mini_fig, use_container_width=True, key=f"chart_{ticker}", config=CHART_CONFIG)

        st.markdown("<hr style='margin: 10px 0; border: none; border-top: 1px solid rgba(255,255,255,0.05);'>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
