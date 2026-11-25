"""Display current watchlist cycles alongside the existing daily entry decision."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from src.indicators.daily_screen import latest_closed_session_date, STAGE_LABELS
from src.indicators.leader_screen import CYCLE_LABELS, read_final_leaders
from src.indicators.weekly_screen import completed_week_start


def watchlist_leader_rows(tickers, daily, weekly, now=None):
    rows = []
    for ticker in tickers:
        day = daily.get("results", {}).get(ticker, {})
        current_day = latest_closed_session_date(ticker, now).isoformat()
        stage = day.get("stage") if day.get("date") == current_day else None
        cycle = weekly.get("results", {}).get(ticker, {}).get("cycle") or {}
        as_of = cycle.get("date")
        expected = completed_week_start(ticker, now)
        if not as_of or not expected.isoformat() <= as_of <= (expected + timedelta(days=6)).isoformat():
            cycle = {}
        state = cycle.get("state", "unavailable")
        age = cycle.get("weeks")
        if age is None:
            duration = "—"
        else:
            duration = f"{age}주" if cycle.get("first_date") else f"최소 {age}주"
        rows.append({
            "종목": ticker, "주봉 분류": CYCLE_LABELS[state],
            "일봉 판정": STAGE_LABELS.get(stage, "확인 필요"),
            "정배열 시작일": cycle.get("first_date") or "—",
            "경과 기간": duration, "주봉 기준일": as_of or "—", "일봉 기준일": day.get("date") or "—",
        })
    return rows


def render_watchlist_leaders(tickers, daily, weekly):
    st.markdown("**관심종목 주도주 판정**")
    st.caption("기술 후보는 관심종목의 KIS 완료 주봉 종가 기준입니다. 4주 > 13주 > 26주 > 52주이고 현재 정배열이 시작된 지 2년 6개월 이내인 종목을 표시합니다.")
    if weekly.get("cycle_version") != 1:
        st.info("주도주 판정은 ‘일봉·주봉 판정 새로고침’을 실행한 뒤 표시됩니다.")
    else:
        rows = watchlist_leader_rows(tickers, daily, weekly)
        candidates = [row for row in rows if row["주봉 분류"] == CYCLE_LABELS["candidate"]]
        ready = [row["종목"] for row in candidates if row["일봉 판정"] == STAGE_LABELS["ready"]]
        st.write(f"**당일 진입 조건까지 충족 ({len(ready)})** · " + (", ".join(ready) or "없음"))
        if candidates:
            st.caption(f"기술적 후보 {len(candidates)}종목 · 주봉 분류와 일봉 판정")
            st.dataframe(pd.DataFrame(candidates), hide_index=True)
        else:
            st.caption("이번 판정에서 확인된 정배열 후보가 없습니다.")
        emerging = [row["종목"] for row in rows if row["주봉 분류"] == CYCLE_LABELS["emerging"]]
        if emerging:
            st.write(f"**정배열 직전 ({len(emerging)})** · " + ", ".join(emerging))
        with st.expander("장기 지속·자료 부족 등 전체 판정"):
            st.dataframe(pd.DataFrame(rows), hide_index=True)
    leaders, message = read_final_leaders()
    with st.expander("실적·공시 검증 주도주", expanded=bool(leaders)):
        if message:
            st.caption(message)
        else:
            selected = [row for row in leaders if row["종목"] in tickers]
            if selected:
                for row in selected:
                    day = daily.get("results", {}).get(row["종목"], {})
                    current = latest_closed_session_date(row["종목"]).isoformat()
                    row["일봉 판정"] = STAGE_LABELS.get(day.get("stage"), "확인 필요") if day.get("date") == current else "확인 필요"
                st.dataframe(pd.DataFrame(selected), hide_index=True)
            else:
                st.caption("검증 결과에 현재 관심종목으로 등록된 주도주가 없습니다.")
