"""Display current watchlist cycles alongside the existing daily entry decision."""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from src.indicators.daily_screen import latest_closed_session_date, STAGE_LABELS
from src.indicators.earnings_evidence import earnings_row, read_snapshot
from src.indicators.leader_screen import CYCLE_LABELS
from src.indicators.leader_research import LABELS, assess, evidence, latest_us_session
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


def research_rows(tickers, daily, weekly, records, facts, now=None):
    now = pd.Timestamp.now(tz="Asia/Seoul") if now is None else pd.Timestamp(now)
    cutoff = latest_us_session(now.tz_convert("UTC").floor("min").isoformat())
    expected_week = completed_week_start("SPY", now)
    judgments = []
    for ticker in tickers:
        cycle = (weekly.get("results", {}).get(ticker, {}).get("cycle") or {}).copy()
        if not expected_week.isoformat() <= (cycle.get("date") or "") <= (expected_week + timedelta(days=6)).isoformat():
            cycle = {}
        fact = facts.get(ticker, {})
        market = daily.get("results", {}).get(ticker, {}).get("research_market") or {}
        if market.get("date") != cutoff:
            market = fact.get("market", {})
        row = assess(ticker, cycle, market, fact, records.get(ticker), now.tz_convert("Asia/Seoul").date().isoformat(), cutoff)
        day = daily.get("results", {}).get(ticker, {})
        row["일봉 판정"] = STAGE_LABELS.get(day.get("stage"), "확인 필요") if day.get("date") == cutoff else "확인 필요"
        row["섹터 기준 ETF"] = fact.get("sector_etf")
        if fact.get("cik"):
            row["기업 재무 원문"] = "https://www.sec.gov/edgar/browse/?CIK=" + str(fact["cik"])
        review = fact.get("review", {})
        row["공시 원문"] = (review.get("risk") or {}).get("url")
        row["가이던스 원문"] = (review.get("guidance") or {}).get("url")
        row["추정치 출처"] = (fact.get("revision") or {}).get("url")
        judgments.append(row)
    return judgments


def render_watchlist_leaders(tickers, daily, weekly):
    st.markdown("**관심종목 주도주 판정**")
    st.caption("기술 후보는 관심종목의 KIS 완료 주봉 종가 기준입니다. 4주 > 13주 > 26주 > 52주이고 현재 정배열이 시작된 지 2년 6개월 이내인 종목을 표시합니다.")
    try:
        snapshot = read_snapshot()
    except (OSError, ValueError, KeyError, TypeError):
        snapshot = None
    records = snapshot["records"] if snapshot else {}
    if weekly.get("cycle_version") != 1:
        st.info("주도주 판정은 ‘일봉·주봉 판정 새로고침’을 실행한 뒤 표시됩니다.")
    else:
        rows = watchlist_leader_rows(tickers, daily, weekly)
        candidates = [row.copy() for row in rows if row["주봉 분류"] == CYCLE_LABELS["candidate"]]
        ready = [row["종목"] for row in candidates if row["일봉 판정"] == STAGE_LABELS["ready"]]
        st.write(f"**당일 진입 조건까지 충족 ({len(ready)})** · " + (", ".join(ready) or "없음"))
        if candidates:
            supported = []
            for candidate in candidates:
                ticker = candidate["종목"]
                fact = earnings_row(ticker, records.get(ticker))
                if snapshot:
                    candidate["실적 비교"] = fact["실적 비교"]
                    candidate["SEC 공시"] = fact["공시유형"] or "자료 없음"
                    candidate["실적 발표일"] = fact.get("발표일(KST)")
                if fact["실적 비교"] == "EPS·매출 모두 상회" and fact["공시유형"]:
                    supported.append(ticker)
            if snapshot:
                st.write(f"**EPS·매출 모두 예상 상회 + SEC 공시 연결 ({len(supported)})** · " + (", ".join(supported) or "없음"))
            st.caption(f"기술적 후보 {len(candidates)}종목 · 주봉 분류와 일봉 판정")
            st.dataframe(pd.DataFrame(candidates), hide_index=True)
        else:
            st.caption("이번 판정에서 확인된 정배열 후보가 없습니다.")
        emerging = [row["종목"] for row in rows if row["주봉 분류"] == CYCLE_LABELS["emerging"]]
        if emerging:
            st.write(f"**정배열 직전 ({len(emerging)})** · " + ", ".join(emerging))
        with st.expander("장기 지속·자료 부족 등 전체 판정"):
            st.dataframe(pd.DataFrame(rows), hide_index=True)
    with st.expander("관심종목 실적·SEC 공시"):
        if snapshot:
            matched = sum(ticker in records for ticker in tickers)
            changed = datetime.fromisoformat(snapshot["updated_at"]).strftime("%Y-%m-%d %H:%M")
            st.caption(f"StockNow 실적 시트 · 반영된 자료의 수정 시각 {changed} KST · 관심종목 {len(tickers)}개 중 실적 {matched}개")
            st.caption("시트에 기록된 최근 발표 기준입니다. SEC 접수번호는 해당 행에 연결된 공시이며, EDGAR에서 종목별 원문을 조회할 수 있습니다.")
            details = [earnings_row(ticker, records.get(ticker)) for ticker in tickers]
            st.dataframe(pd.DataFrame(details), hide_index=True, column_config={
                "EDGAR": st.column_config.LinkColumn("SEC 원문 조회", display_text="EDGAR"),
                "EPS 차이(%)": st.column_config.NumberColumn(format="%.2f"),
                "매출 차이(%)": st.column_config.NumberColumn(format="%.2f"),
            })
        else:
            st.caption("실적·공시 동기화 자료를 읽을 수 없습니다.")
    judgments = research_rows(tickers, daily, weekly, records, evidence())
    with st.expander("최종 리서치 판정", expanded=True):
        leaders = [r for r in judgments if r["최종 등급"] in LABELS]
        pending = sum(r["최종 등급"] == "판정 보류" for r in judgments)
        st.write(f"**주도주 {len(leaders)}개** · 판정 보류 {pending}개 · 전체 {len(judgments)}개")
        ready_leaders = [r["종목"] for r in leaders if r["일봉 판정"] == STAGE_LABELS["ready"]]
        st.write(f"**주도주이면서 당일 진입 조건 충족 ({len(ready_leaders)})** · " + (", ".join(ready_leaders) or "없음"))
        if not leaders and pending:
            st.caption(f"확인된 주도주는 0개입니다. 자료가 부족한 {pending}개 종목은 보류로 표시합니다.")
        st.caption("완료 주봉·시장 대비 강도와 최근 기업 자료를 결합합니다. 조회일과 실적·공시 기준일은 다를 수 있습니다.")
        mode = st.radio("리서치 결과 보기", ["주도주·검토 대상", "전체 결과"], horizontal=True, key="research_scope")
        shown = [r for r in judgments if r["최종 등급"] not in ("조건 미충족", "장기 사이클", "대상 제외")] if mode == "주도주·검토 대상" else judgments
        order = {label: i for i, label in enumerate((*LABELS, "공시 위험 검토", "판정 보류"))}
        if shown:
            st.dataframe(pd.DataFrame(sorted(shown, key=lambda r: order.get(r["최종 등급"], 9))), hide_index=True,
                         column_config={k: st.column_config.LinkColumn(k, display_text="원문") for k in ("공시 원문","기업 재무 원문","가이던스 원문","추정치 출처")})
        else:
            st.caption("이번 판정에서 주도주 또는 검토 대상에 해당하는 종목이 없습니다.")
        st.caption("부상은 실적 가속과 선행 방향이 확인된 초기·잠정 후보입니다. 확정은 실제 Hans Delta와 수치형 Forward Delta가 필요합니다. 성숙은 40주 이상 정배열에서 이익은 성장하지만 가속도가 둔화한 경우입니다. 공시 자동 점검은 지정한 위험 신호 범위에 한합니다.")
