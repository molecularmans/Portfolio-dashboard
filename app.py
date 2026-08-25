import streamlit as st
import pandas as pd

from src.db.database import StockDB
from src.api.kis_rest import KISClient
from src.indicators.technicals import calc_indicators
from src.ui.charts import create_detail_chart, CHART_CONFIG
from src.ui.tradingview import render_tradingview_chart, render_tradingview_mini_chart
from src.ui.sidebar import render_sidebar

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


def init_services():
    """DB 및 KIS 클라이언트 초기화"""
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

        col_back, col_title, col_tf = st.columns([1.8, 4, 2.2])
        if col_back.button("← 전체 멀티차트로 돌아가기", use_container_width=True):
            st.session_state.selected_ticker = None
            st.rerun()

        col_title.subheader(f"{sel_ticker} 상세 기술적 분석")
        detail_tf = col_tf.radio("차트 주기", ["일봉", "주봉", "월봉"], index=["일봉", "주봉", "월봉"].index(timeframe), horizontal=True, key="detail_tf_select")
        
        detail_settings = settings.copy()
        detail_settings["timeframe"] = detail_tf

        # 상단 핵심 메트릭 (잔고 실시간 데이터 우선 연동)
        if sel_ticker in portfolio_map:
            it_p = portfolio_map[sel_ticker]
            c1, c2, c3 = st.columns(3)
            c1.metric("현재가", f"${it_p['current_price']:,.2f}", f"{it_p['profit_rate']:+.2f}%")
            c2.metric("보유 수량", f"{int(it_p['qty'])}주")
            c3.metric("평가 금액", f"${it_p['eval_amount']:,.2f}")

        st.caption("트레이딩뷰 좌측 툴바에서 추세선, 수평선, 피보나치, 채널 등을 마우스로 직접 긋고, 클릭하여 복사/삭제/색상변경을 자유롭게 사용할 수 있습니다. (자동 저장 지원)")
        render_tradingview_chart(sel_ticker, timeframe=detail_tf, settings=detail_settings, height=750)
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
                df = load_and_calc_stock_data(ticker, db, client, force_refresh, timeframe=timeframe)

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
