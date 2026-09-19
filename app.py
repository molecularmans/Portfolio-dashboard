import streamlit as st
import pandas as pd

from src.db.database import StockDB
from src.api.kis_rest import KISClient
from src.indicators.technicals import calc_indicators
from src.ui.charts import create_detail_chart, CHART_CONFIG
from src.ui.tradingview import render_tradingview_chart, render_tradingview_mini_chart
from src.ui.sidebar import render_sidebar
from src.ui.vcp_view import render_vcp_analysis_panel
from src.ui.pattern_view import render_pattern_analysis_dashboard

# 1. Streamlit 페이지 기본 설정
st.set_page_config(
    page_title="Personal Stock Terminal",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 커스텀 스타일 (상단 여백 및 메트릭 카드)
st.markdown("""
<style>
    .block-container {
        padding-top: 3.8rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    
    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 8px 12px;
        min-width: 0;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: #cbd5e1 !important;
        margin-bottom: 4px !important;
        white-space: nowrap !important;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        color: #f8fafc !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.78rem !important;
        line-height: 1.1 !important;
        margin-top: 2px !important;
    }

    .total-eval-box {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1.5px solid rgba(56, 189, 248, 0.4);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        border-radius: 8px;
        padding: 8px 14px;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .total-eval-label {
        font-size: 0.8rem;
        color: #94a3b8;
        font-weight: 500;
        margin-bottom: 3px;
    }
    .total-eval-val {
        font-size: 1.25rem;
        font-weight: 700;
        color: #38bdf8;
        letter-spacing: -0.3px;
        white-space: nowrap;
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
        border-radius: 4px;
        font-size: 0.82rem;
        padding: 3px 10px;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def init_services():
    """DB 및 KIS 클라이언트 초기화 (싱글톤 캐싱으로 0.001초 응답)"""
    db = StockDB()
    client = KISClient()
    return db, client


def load_and_calc_stock_data(ticker: str, db: StockDB, client: KISClient, force_refresh: bool = False, timeframe: str = "일봉") -> pd.DataFrame:
    ticker = ticker.upper().strip()
    tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    tf_code = tf_map.get(timeframe, "D")
    count_target = 300 if tf_code == "D" else (200 if tf_code == "W" else 120)

    df = pd.DataFrame()
    if not force_refresh:
        df = db.get_prices(ticker, timeframe=tf_code)

    need_fetch = df.empty or len(df) < 20 or force_refresh
    if not need_fetch and not df.empty and tf_code == "D":
        latest_d = pd.to_datetime(df.iloc[-1]["date"])
        if (pd.Timestamp.now() - latest_d).days > 3:
            need_fetch = True

    if need_fetch:
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

    # 대상 티커 목록 및 포트폴리오 결정
    view_mode = settings["view_mode"]
    tickers = []
    portfolio_items = []
    is_portfolio_mode = "포트폴리오" in view_mode or "잔고" in view_mode
    accounts = client.auth.get_accounts_list()

    if is_portfolio_mode:
        if "통합" in view_mode or "전체" in view_mode or len(accounts) <= 1:
            portfolio_items = client.get_combined_balance()
        else:
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
    # 상단 요약 바 (총 평가금액 및 실시간 보유종목)
    # ==========================================
    portfolio_map = {it["ticker"]: it for it in portfolio_items}

    if is_portfolio_mode and portfolio_items:
        total_eval = sum(item["eval_amount"] for item in portfolio_items)
        
        c_total, c_items = st.columns([1.6, 8.4])
        with c_total:
            st.markdown(f"""
            <div class="total-eval-box">
                <div class="total-eval-label">총 평가금액</div>
                <div class="total-eval-val">${total_eval:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        with c_items:
            num_show = min(len(portfolio_items), 10)
            item_cols = st.columns(num_show)
            for i in range(num_show):
                it = portfolio_items[i]
                with item_cols[i]:
                    st.metric(
                        label=f"{it['ticker']} ({int(it['qty'])}주)",
                        value=f"${it['current_price']:,.2f}",
                        delta=f"{it['profit_rate']:+.2f}%",
                    )
        st.divider()

    # ==========================================
    # VIEW 모드 1: 특정 종목 상세 확대 분석 뷰 (트레이딩뷰 프로 차트)
    # ==========================================
    if st.session_state.selected_ticker:
        sel_ticker = st.session_state.selected_ticker

        col_back, col_title, col_tf, col_nav = st.columns([1.5, 3.2, 1.8, 3.2])
        if col_back.button("← 전체 멀티차트", use_container_width=True):
            st.session_state.selected_ticker = None
            st.rerun()

        col_title.subheader(f"{sel_ticker} 상세 기술적 분석")
        detail_tf = col_tf.radio(
            "차트 주기",
            ["일봉", "주봉", "월봉"],
            index=["일봉", "주봉", "월봉"].index(timeframe),
            horizontal=True,
            key="detail_tf_select",
        )

        # 우측: 그룹 내 다른 종목 바로가기 네비게이터
        if tickers:
            avail_tickers = tickers if sel_ticker in tickers else [sel_ticker] + [t for t in tickers if t != sel_ticker]
            cur_idx = avail_tickers.index(sel_ticker) if sel_ticker in avail_tickers else 0
            
            with col_nav:
                st.caption(f"📌 **{view_mode}** 종목 바로가기 ({cur_idx + 1}/{len(avail_tickers)})")
                c_prev, c_sel, c_next = st.columns([1, 4.2, 1])
                with c_prev:
                    if st.button("◀", key="nav_btn_prev", help="이전 종목으로 바로가기", use_container_width=True):
                        st.session_state.selected_ticker = avail_tickers[(cur_idx - 1) % len(avail_tickers)]
                        st.rerun()
                with c_sel:
                    def _format_ticker(t):
                        if t in portfolio_map:
                            pr = portfolio_map[t].get("profit_rate", 0)
                            sign = "+" if pr >= 0 else ""
                            return f"{t} ({sign}{pr:.1f}%)"
                        return t

                    new_sel = st.selectbox(
                        "종목 빠른 전환",
                        options=avail_tickers,
                        index=cur_idx,
                        format_func=_format_ticker,
                        label_visibility="collapsed",
                    )
                    if new_sel != sel_ticker:
                        st.session_state.selected_ticker = new_sel
                        st.rerun()
                with c_next:
                    if st.button("▶", key="nav_btn_next", help="다음 종목으로 바로가기", use_container_width=True):
                        st.session_state.selected_ticker = avail_tickers[(cur_idx + 1) % len(avail_tickers)]
                        st.rerun()

        detail_settings = settings.copy()
        detail_settings["timeframe"] = detail_tf

        # 상단 핵심 메트릭 (잔고 실시간 데이터 우선 연동)
        if sel_ticker in portfolio_map:
            it_p = portfolio_map[sel_ticker]
            c1, c2, c3 = st.columns(3)
            c1.metric("현재가", f"${it_p['current_price']:,.2f}", f"{it_p['profit_rate']:+.2f}%")
            c2.metric("보유 수량", f"{int(it_p['qty'])}주")
            c3.metric("평가 금액", f"${it_p['eval_amount']:,.2f}")

        # 시세 데이터 로드
        df_stock = load_and_calc_stock_data(sel_ticker, db, client, force_refresh=False, timeframe=detail_tf)

        # 차트 보기 모드 탭 (스마트 분석 차트 vs 트레이딩뷰 프로 차트)
        tab_chart_smart, tab_chart_tv = st.tabs(["📊 스마트 분석 차트 (자동 작도)", "📈 TradingView 프로 (수동 작도)"])

        with tab_chart_smart:
            tcol_txt, tcol_sr, tcol_tl, tcol_pat = st.columns([3.8, 2.2, 2.0, 2.2])
            with tcol_txt:
                st.caption("알고리즘이 계산한 지지·저항, 추세선, 패턴 넥라인 인터랙티브 차트 (마우스 휠 줌/드래그 지원)")
            with tcol_sr:
                layer_sr = st.checkbox("🛡️ 지지·저항선 [A]", value=detail_settings.get("show_support_resistance", True), key="inline_layer_sr")
            with tcol_tl:
                layer_tl = st.checkbox("📐 자동 추세선 [A]", value=detail_settings.get("show_trendlines", True), key="inline_layer_tl")
            with tcol_pat:
                layer_pat = st.checkbox("💎 패턴 넥라인 [B]", value=detail_settings.get("show_pattern_lines", True), key="inline_layer_pat")

            detail_settings["show_support_resistance"] = layer_sr
            detail_settings["show_trendlines"] = layer_tl
            detail_settings["show_pattern_lines"] = layer_pat

            if not df_stock.empty:
                fig = create_detail_chart(df_stock, sel_ticker, settings=detail_settings)
                st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
            else:
                st.info(f"📊 {sel_ticker}의 시세 데이터를 불러오는 중입니다...")

        with tab_chart_tv:
            st.caption("트레이딩뷰 좌측 툴바에서 추세선, 수평선, 피보나치, 채널 등을 마우스로 직접 긋고, 클릭하여 복사/삭제/색상변경을 자유롭게 사용할 수 있습니다.")
            render_tradingview_chart(sel_ticker, timeframe=detail_tf, settings=detail_settings, height=750)

        # 종합 진단 엔진 ([A] 지지/저항 & 추세선 + [B] 고전 패턴 + [C] 마크 미너비니 VCP)
        df_daily = df_stock if detail_tf == "일봉" else load_and_calc_stock_data(sel_ticker, db, client, force_refresh=False, timeframe="일봉")
        render_pattern_analysis_dashboard(df_daily, sel_ticker)
        return

    # ==========================================
    # VIEW 모드 2: 멀티 차트 그리드 (트레이딩뷰 실시간 정품 캔들 엔진 탑재)
    # ==========================================
    st.markdown(f"##### {view_mode} ({len(tickers)} 종목) · {timeframe}")

    if not tickers:
        st.info("해당 포트폴리오/그룹에 등록된 종목이 없습니다. 좌측 메뉴에서 종목을 추가해보세요.")
        return

    # 3열 반응형 그리드 레이아웃 (트레이딩뷰 캔들스틱 + 이평선 실시간 위젯)
    NUM_COLS = 3
    rows = [tickers[i:i + NUM_COLS] for i in range(0, len(tickers), NUM_COLS)]

    for row in rows:
        cols = st.columns(NUM_COLS)
        for idx, ticker in enumerate(row):
            with cols[idx]:

                # 종목 상단 헤더 & 자세히 보기 버튼
                head_col1, head_col2 = st.columns([3.2, 1.8])
                with head_col1:
                    if ticker in portfolio_map:
                        it_p = portfolio_map[ticker]
                        show_price = it_p["current_price"]
                        show_delta = it_p["profit_rate"]
                        color_class = "positive-text" if show_delta >= 0 else "negative-text"
                        sign = "+" if show_delta >= 0 else ""
                        st.markdown(f"**{ticker}** &nbsp; <span class='{color_class}'>${show_price:,.2f} ({sign}{show_delta:.2f}%)</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"**{ticker}**", unsafe_allow_html=True)

                with head_col2:
                    if st.button("자세히 보기", key=f"btn_zoom_{ticker}", use_container_width=True):
                        st.session_state.selected_ticker = ticker
                        st.rerun()

                # 트레이딩뷰 정품 실시간 캔들 위젯 (주기별 4대 이평선 자동 주입)
                render_tradingview_mini_chart(ticker, timeframe=timeframe, height=330)

        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid rgba(255,255,255,0.05);'>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
