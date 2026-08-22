import streamlit as st
from src.db.database import StockDB
from src.api.kis_rest import KISClient


def render_sidebar(db: StockDB, client: KISClient) -> dict:
    """좌측 사이드바 메뉴 렌더링 (그룹 순서 변경 & 이동평균선 영구 저장 지원)"""
    with st.sidebar:
        st.subheader("Terminal Controller")

        # 1. KIS API 연결 상태 및 등록된 계좌 정보
        if client.is_configured():
            paper_str = "모의투자" if client.auth.is_paper else "실전투자"
            accounts = client.auth.get_accounts_list()
            acc_count_str = f" · {len(accounts)}개 계좌 연동" if len(accounts) > 1 else ""
            st.success(f"KIS API 연동 중 ({paper_str}{acc_count_str})")
        else:
            st.warning("KIS 키 미설정 (데모 모드)")
            with st.expander("API 키 등록 안내"):
                st.caption("프로젝트 폴더의 `.env` 파일에 KIS API Key/Secret을 입력하면 실제 시세와 계좌 잔고가 자동 연동됩니다.")

        st.divider()

        # 2. 데이터 보기 모드
        accounts = client.auth.get_accounts_list()
        portfolio_options = ["내 포트폴리오 (전체 계좌 합산)"]
        
        if len(accounts) > 1:
            for acc in accounts:
                portfolio_options.append(f"[{acc['name']}] 개별 잔고")

        groups = db.get_groups()
        view_options = portfolio_options + ["전체 관심종목"] + [f"{g}" for g in groups]
        
        view_mode = st.selectbox(
            "데이터 보기 모드",
            options=view_options,
            index=0,
            help="차트에 표시할 포트폴리오(전체 계좌 합산/개별 계좌) 또는 관심종목 그룹을 선택하세요.",
        )

        # 3. 차트 주기 (일봉 / 주봉 / 월봉) 선택
        timeframe = st.radio(
            "차트 주기 (타임프레임)",
            options=["일봉", "주봉", "월봉"],
            index=0,
            horizontal=True,
            help="전체 차트의 캔들 주기를 일봉/주봉/월봉으로 전환합니다.",
        )

        st.divider()

        # 4. 관심종목 및 그룹 관리
        with st.expander("관심종목 및 그룹 관리", expanded=False):
            tab_item, tab_grp = st.tabs(["종목 추가/삭제", "그룹 관리"])

            # 탭 1: 종목 추가 및 삭제
            with tab_item:
                target_group = st.selectbox("추가할 그룹 선택", options=groups, index=0)
                c_in, c_btn = st.columns([3, 1])
                new_ticker = c_in.text_input("티커 입력", placeholder="예: NVDA, TSLA", label_visibility="collapsed").strip().upper()
                if c_btn.button("추가", use_container_width=True) and new_ticker:
                    db.add_watchlist_item(new_ticker, group_name=target_group)
                    st.toast(f"[{target_group}]에 {new_ticker} 추가 완료")
                    st.rerun()

                st.caption("등록된 종목 목록")
                all_items = db.get_watchlist()
                if not all_items.empty:
                    for grp, df_grp in all_items.groupby("group_name"):
                        st.markdown(f"**{grp}**")
                        for _, row in df_grp.iterrows():
                            t = row["ticker"]
                            c1, c2 = st.columns([3, 1])
                            c1.write(f"- `{t}`")
                            if c2.button("삭제", key=f"del_{grp}_{t}", help=f"{t} 삭제"):
                                db.remove_watchlist_item(t)
                                st.toast(f"{t} 삭제 완료")
                                st.rerun()

            # 탭 2: 그룹 관리 (순서 변경 추가)
            with tab_grp:
                st.markdown("**1) 그룹 순서 변경 (위/아래 이동)**")
                for i, gname in enumerate(groups):
                    c_name, c_up, c_down = st.columns([3.5, 1, 1])
                    c_name.markdown(f"`{i + 1}` **{gname}**")
                    if i > 0:
                        if c_up.button("▲", key=f"btn_up_{gname}", help=f"{gname} 위로"):
                            db.move_group_up(gname)
                            st.rerun()
                    else:
                        c_up.write("")

                    if i < len(groups) - 1:
                        if c_down.button("▼", key=f"btn_down_{gname}", help=f"{gname} 아래로"):
                            db.move_group_down(gname)
                            st.rerun()
                    else:
                        c_down.write("")

                st.divider()

                st.markdown("**2) 새 그룹 생성**")
                g_col1, g_col2 = st.columns([3, 1])
                new_gname = g_col1.text_input("새 그룹명", placeholder="예: 바이오, 배당주", label_visibility="collapsed").strip()
                if g_col2.button("생성", use_container_width=True) and new_gname:
                    db.add_group(new_gname)
                    st.toast(f"그룹 '{new_gname}' 생성 완료")
                    st.rerun()

                st.divider()

                st.markdown("**3) 그룹명 변경**")
                target_rename_grp = st.selectbox("변경할 그룹 선택", options=groups, key="sel_rename_grp")
                r_col1, r_col2 = st.columns([3, 1])
                renamed_title = r_col1.text_input("새 이름", value=target_rename_grp, label_visibility="collapsed").strip()
                if r_col2.button("변경", use_container_width=True) and renamed_title and renamed_title != target_rename_grp:
                    db.rename_group(target_rename_grp, renamed_title)
                    st.toast(f"'{target_rename_grp}' → '{renamed_title}' 변경 완료")
                    st.rerun()

                st.divider()

                st.markdown("**4) 그룹 삭제**")
                del_grp = st.selectbox("삭제할 그룹 선택", options=groups, key="sel_del_grp")
                if st.button(f"'{del_grp}' 그룹 삭제", use_container_width=True):
                    db.delete_group(del_grp)
                    st.toast(f"'{del_grp}' 그룹 삭제 완료")
                    st.rerun()

        st.divider()

        # 5. 이동평균선 설정 (영구 저장 연동)
        st.subheader("이동평균선 설정")
        saved_ma = db.get_ma_settings()

        show_ema5 = st.checkbox("5 EMA", value=saved_ma.get("show_ema5", True), key="chk_ema5")
        show_ma10 = st.checkbox("10 MA", value=saved_ma.get("show_ma10", False), key="chk_ma10")
        show_ma20 = st.checkbox("20 MA", value=saved_ma.get("show_ma20", True), key="chk_ma20")
        show_ma30 = st.checkbox("30 MA", value=saved_ma.get("show_ma30", False), key="chk_ma30")
        show_ma50 = st.checkbox("50 MA", value=saved_ma.get("show_ma50", True), key="chk_ma50")
        show_ma150 = st.checkbox("150 MA", value=saved_ma.get("show_ma150", False), key="chk_ma150")
        show_ma200 = st.checkbox("200 MA", value=saved_ma.get("show_ma200", True), key="chk_ma200")

        current_ma = {
            "show_ema5": show_ema5,
            "show_ma10": show_ma10,
            "show_ma20": show_ma20,
            "show_ma30": show_ma30,
            "show_ma50": show_ma50,
            "show_ma150": show_ma150,
            "show_ma200": show_ma200,
        }

        # 변경 시 DB 자동 영구 저장
        if current_ma != saved_ma:
            db.save_ma_settings(current_ma)

        st.divider()

        # 6. 보조지표 다중 선택
        st.subheader("보조지표 다중 선택")
        selected_sub_indicators = st.multiselect(
            "동시에 볼 보조지표 선택",
            options=["Stochastic", "Williams %R", "RSI", "MACD"],
            default=["Stochastic", "RSI"],
            help="선택한 보조지표들이 상세 차트 하단에 각각의 서브패널로 동시에 모두 표시됩니다.",
        )

        st.divider()

        # 7. 시세 새로고침
        if st.button("시세 데이터 새로고침", use_container_width=True):
            db.clear_all_prices()
            st.session_state["force_refresh"] = True
            st.rerun()

        settings = {
            "view_mode": view_mode,
            "timeframe": timeframe,
            "show_ema5": show_ema5,
            "show_ma10": show_ma10,
            "show_ma20": show_ma20,
            "show_ma30": show_ma30,
            "show_ma50": show_ma50,
            "show_ma150": show_ma150,
            "show_ma200": show_ma200,
            "ma_flags": current_ma,
            "selected_sub_indicators": selected_sub_indicators,
        }

        return settings
