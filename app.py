import streamlit as st
import pandas as pd
from html import escape
from datetime import timedelta

from src.db.database import StockDB
from src.api.kis_rest import KISClient, looks_like_mock_ohlcv
from src.indicators.technicals import calc_indicators
from src.indicators.daily_screen import STAGE_LABELS, scan_day
from src.indicators.weekly_screen import WEEKLY_STAGE_LABELS
from src.db.screen_snapshot import ScreenRuntime, ScreenSnapshotStore
from src.ui.charts import create_detail_chart, CHART_CONFIG
from src.ui.tradingview import render_tradingview_chart, render_tradingview_mini_chart
from src.ui.sidebar import render_sidebar
from src.ui.vcp_view import render_vcp_analysis_panel
from src.ui.pattern_view import render_pattern_analysis_dashboard
from src.ui.pattern_view import render_weekly_assessment

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
    .holdings-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
        gap: 7px;
    }
    .holding-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 7px 10px;
        min-width: 0;
    }
    .holding-name {font-size: .78rem; color: #cbd5e1; font-weight: 600;}
    .holding-price {font-size: 1rem; color: #f8fafc; font-weight: 600; white-space: nowrap;}
    .holding-return {font-size: .78rem; font-weight: 600;}
    
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


@st.cache_resource
def get_screen_runtime():
    return ScreenRuntime(ScreenSnapshotStore())


def load_and_calc_stock_data(ticker: str, db: StockDB, client: KISClient, force_refresh: bool = False, timeframe: str = "일봉") -> pd.DataFrame:
    ticker = ticker.upper().strip()
    tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    tf_code = tf_map.get(timeframe, "D")
    count_target = 300 if tf_code == "D" else (200 if tf_code == "W" else 120)

    df = db.get_prices(ticker, timeframe=tf_code)
    if client.is_configured() and looks_like_mock_ohlcv(df, ticker, tf_code):
        # Older versions cached synthetic fallback prices after KIS failures.
        db.delete_prices(ticker, tf_code)
        df = pd.DataFrame()

    need_fetch = df.empty or len(df) < 20 or force_refresh
    if not need_fetch and not df.empty and tf_code == "D":
        latest_d = pd.to_datetime(df.iloc[-1]["date"])
        if (pd.Timestamp.now() - latest_d).days > 3:
            need_fetch = True

    if need_fetch:
        if ticker.isdigit() and len(ticker) == 6:
            fetched = client.get_kr_ohlcv(ticker, timeframe=tf_code, count=count_target)
        else:
            fetched = client.get_us_ohlcv(ticker, timeframe=tf_code, count=count_target)

        if not fetched.empty:
            df = fetched
            if client.is_configured():
                db.save_prices(ticker, tf_code, df)

    return calc_indicators(df)


@st.fragment(run_every="15s")
def schedule_watchlist_screen(db: StockDB, client: KISClient) -> None:
    """Detect the 09:30 rollover in any open dashboard view."""
    if not client.is_configured():
        return
    runtime = get_screen_runtime()
    watchlist = db.get_watchlist()
    tickers = list(dict.fromkeys(ticker for ticker in watchlist["ticker"].dropna().astype(str).str.strip().str.upper() if ticker)) if not watchlist.empty else []
    if tickers:
        runtime.start(tickers, load_and_calc_stock_data, db, client, scheduled=True)


@st.fragment(run_every="15s")
def render_watchlist_screen(db: StockDB, client: KISClient, refresh_requested: bool = False) -> None:
    """Show the saved screen; run a worker only at the active 09:30 rollover or on request."""
    st.markdown("##### 📅 관심종목 종가 판정")
    st.caption("일봉·주봉 마지막 저장 결과를 즉시 표시합니다. 앱이 켜져 있으면 오전 9시 30분(한국시간)에 일봉을, 새 완료 주가 생기면 주봉도 갱신합니다. 아래 버튼으로 언제든 다시 계산할 수 있습니다.")
    if not client.is_configured():
        st.info("KIS 실전 시세가 연결되면 관심종목 판정을 시작합니다.")
        return

    watchlist = db.get_watchlist()
    tickers = list(dict.fromkeys(ticker for ticker in watchlist["ticker"].dropna().astype(str).str.strip().str.upper() if ticker)) if not watchlist.empty else []
    if not tickers:
        st.info("등록된 관심종목이 없습니다.")
        return

    runtime = get_screen_runtime()
    col_period, col_refresh = st.columns([4, 2])
    with col_period:
        selected = st.radio("판정 주기", ["일봉", "주봉"], horizontal=True, key="watchlist_screen_period")
    with col_refresh:
        manual = st.button("일봉·주봉 판정 새로고침", use_container_width=True)
    if manual or refresh_requested:
        runtime.start(tickers, load_and_calc_stock_data, db, client)

    job = runtime.status()
    if job and job["running"]:
        st.progress(job["done"] / max(job["total"], 1), text=f"판정 갱신 중 · {job['done']}/{job['total']} · {job['ticker']}")
    elif job and job["error"]:
        st.warning(job["error"])

    code = "D" if selected == "일봉" else "W"
    labels = STAGE_LABELS if code == "D" else WEEKLY_STAGE_LABELS
    screen = runtime.screen(code)
    if not screen:
        st.info(f"저장된 {selected} 판정이 없습니다. ‘일봉·주봉 판정 새로고침’을 눌러 처음 계산해 주세요.")
        st.divider()
        return

    results = {ticker: screen["results"].get(ticker, {"stage": "unavailable", "date": None}) for ticker in tickers}
    changed = set(tickers) != set(screen["tickers"])
    if changed:
        st.caption("관심종목 목록이 변경되었습니다. 새 종목은 자료 부족으로 표시되며, 새로고침 후 반영됩니다.")
    st.caption(f"마지막 저장: {screen['completed_at'].replace('T', ' ')} (한국시간) · 판정 대상 {len(screen['tickers'])}종목")
    if screen["scan_day"] != scan_day():
        st.caption("새 거래일 결과가 아직 저장되지 않아 이전 판정을 표시합니다.")
    dates = sorted({item["date"] for item in results.values() if item.get("date") and item["stage"] != "unavailable"})
    if dates:
        if code == "W":
            starts = [pd.to_datetime(value).date() - timedelta(days=pd.to_datetime(value).weekday()) for value in dates]
            st.caption(f"판정에 사용한 완료 주간: {min(starts)} ~ {max(starts) + timedelta(days=4)}")
        else:
            date_text = dates[-1] if len(dates) == 1 else f"{dates[0]} ~ {dates[-1]}"
            st.caption(f"판정에 사용한 일봉 종가 기준일: {date_text}")

    buckets = {
        stage: [ticker for ticker, result in results.items() if result["stage"] == stage]
        for stage in labels
    }
    cols = st.columns(3)
    for col, stage in zip(cols, ("ready", "setup", "watch")):
        with col:
            st.markdown(f"**{labels[stage]} ({len(buckets[stage])})**")
            st.write(" · ".join(buckets[stage]) if buckets[stage] else "없음")
    with st.expander(f"{labels['hold']} ({len(buckets['hold'])})", expanded=False):
        st.write(" · ".join(buckets["hold"]) if buckets["hold"] else "없음")
    if buckets["unavailable"]:
        with st.expander(f"{labels['unavailable']} ({len(buckets['unavailable'])})", expanded=False):
            st.write(" · ".join(buckets["unavailable"]))
    if code == "W":
        st.caption("주봉은 완료된 주의 13·26·52주선, 직전 20주 고점, 주간 거래량과 손절폭으로 판정합니다. 일봉 [A–D]와는 독립된 참고 기준입니다.")
    else:
        st.caption("관심 우선순위와 진입 준비는 매수 신호가 아닙니다. 당일 조건 충족도 최신 가격·거래량과 개인 위험 한도를 확인해야 합니다.")
    st.divider()


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
    schedule_watchlist_screen(db, client)

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
        
        c_total, c_items = st.columns([2, 8])
        with c_total:
            st.markdown(f"""
            <div class="total-eval-box">
                <div class="total-eval-label">총 평가금액</div>
                <div class="total-eval-val">${total_eval:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        with c_items:
            st.caption(f"보유종목 현황 · {len(portfolio_items)}종목 전체")
            cards = []
            for it in portfolio_items:
                rate = float(it["profit_rate"])
                color = "#26a69a" if rate >= 0 else "#ef5350"
                currency = "₩" if str(it["ticker"]).isdigit() and len(str(it["ticker"])) == 6 else "$"
                cards.append(
                    f'<div class="holding-card"><div class="holding-name">{escape(str(it["ticker"]))} ({int(it["qty"])}주)</div>'
                    f'<div class="holding-price">{currency}{float(it["current_price"]):,.2f}</div>'
                    f'<div class="holding-return" style="color:{color}">{rate:+.2f}%</div></div>'
                )
            st.markdown('<div class="holdings-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
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
        detail_settings["smart_analysis_engine"] = st.session_state.get(
            f"smart_analysis_engine_{sel_ticker}", "v4"
        )
        # Keep the old flag for compatibility with any secondary chart paths.
        detail_settings["smart_analysis_v2"] = detail_settings["smart_analysis_engine"] != "v1"
        detail_settings["timeframe"] = detail_tf
        currency = "₩" if sel_ticker.isdigit() and len(sel_ticker) == 6 else "$"

        # 계좌 잔고 평가가는 과거 일봉 종가와 시점이 다를 수 있다.
        if sel_ticker in portfolio_map:
            it_p = portfolio_map[sel_ticker]
            c1, c2, c3 = st.columns(3)
            c1.metric("잔고 평가 기준가", f"{currency}{it_p['current_price']:,.2f}", f"{it_p['profit_rate']:+.2f}%")
            c2.metric("보유 수량", f"{int(it_p['qty'])}주")
            c3.metric("평가 금액", f"${it_p['eval_amount']:,.2f}")

        # 시세 데이터 로드
        df_stock = load_and_calc_stock_data(sel_ticker, db, client, force_refresh=force_refresh, timeframe=detail_tf)

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
                last_bar = df_stock.iloc[-1]
                last_bar_date = pd.to_datetime(last_bar["date"]).strftime("%Y-%m-%d")
                source_label = "KIS" if client.is_configured() else "데모"
                st.caption(f"자동 차트: {source_label} {detail_tf} · {last_bar_date} 종가 {currency}{last_bar['close']:,.2f}")
            else:
                st.info(f"📊 {sel_ticker}의 시세 데이터를 불러오는 중입니다...")

        with tab_chart_tv:
            st.caption("트레이딩뷰 좌측 툴바에서 추세선, 수평선, 피보나치, 채널 등을 마우스로 직접 긋고, 클릭하여 복사/삭제/색상변경을 자유롭게 사용할 수 있습니다.")
            st.caption("TradingView는 별도 시세원입니다. 아래 [A–D] 분석은 KIS 일봉 종가를 사용하므로 시점·가격 조정 방식에 따라 표시 가격이 다를 수 있습니다.")
            render_tradingview_chart(sel_ticker, timeframe=detail_tf, settings=detail_settings, height=750)

        # 종합 진단 엔진 ([A] 지지/저항 & 추세선 + [B] 고전 패턴 + [C] 마크 미너비니 VCP)
        if detail_tf == "주봉":
            render_weekly_assessment(df_stock, sel_ticker)
        df_daily = df_stock if detail_tf == "일봉" else load_and_calc_stock_data(sel_ticker, db, client, force_refresh=force_refresh, timeframe="일봉")
        if detail_tf != "일봉" and not df_daily.empty:
            st.caption("아래 [A–D] 분석은 선택한 주봉·월봉 차트와 별도로 일봉 데이터로 계산합니다.")
        if sel_ticker in portfolio_map and not df_daily.empty:
            quote = float(portfolio_map[sel_ticker]["current_price"])
            daily_close = float(df_daily["close"].iloc[-1])
            if daily_close > 0 and abs(quote / daily_close - 1) >= 0.005:
                bar_date = pd.to_datetime(df_daily["date"].iloc[-1]).strftime("%Y-%m-%d")
                st.info(f"잔고 평가 현재가 {currency}{quote:,.2f}와 분석 기준 {bar_date} 일봉 종가 {currency}{daily_close:,.2f}는 시점이 다릅니다. [A–D] 분석은 일봉 종가를 사용합니다.")
        render_pattern_analysis_dashboard(df_daily, sel_ticker)
        return

    # ==========================================
    # VIEW 모드 2: 멀티 차트 그리드 (트레이딩뷰 실시간 정품 캔들 엔진 탑재)
    # ==========================================
    render_watchlist_screen(db, client, refresh_requested=force_refresh)
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
                        price_currency = "₩" if ticker.isdigit() and len(ticker) == 6 else "$"
                        st.markdown(f"**{ticker}** · 잔고 평가가 &nbsp; <span class='{color_class}'>{price_currency}{show_price:,.2f} ({sign}{show_delta:.2f}%)</span>", unsafe_allow_html=True)
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
