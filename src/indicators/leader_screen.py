"""Watchlist price candidates and the separately researched final leader list."""

import csv
from datetime import date
from pathlib import Path

import pandas as pd


FINAL_LEADERS = Path(__file__).resolve().parents[2] / "data/final/sec_validated_leaders.csv"
CYCLE_LABELS = {
    "candidate": "정배열 후보",
    "emerging": "정배열 직전",
    "mature": "2년 6개월 초과",
    "unknown_start": "정배열 시작일 미확인",
    "unavailable": "주봉 확인 필요",
    "other": "조건 미충족",
}


def weekly_cycle(df: pd.DataFrame, last_monday: date) -> dict:
    """Use one completed close per calendar week. Gaps interrupt the evidence."""
    unavailable = {"state": "unavailable"}
    if df is None or not {"date", "close"}.issubset(df.columns):
        return unavailable
    dates = pd.to_datetime(df["date"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    prices = pd.DataFrame({"date": dates, "close": close}).dropna(subset=["date"]).sort_values("date")
    prices["week"] = prices["date"].dt.to_period("W-SUN")
    week = pd.Period(last_monday, freq="W-SUN")
    prices = prices.loc[prices["week"] <= week].drop_duplicates("week", keep="last").set_index("week")
    if week not in prices.index:
        return unavailable
    prices = prices.reindex(pd.period_range(prices.index.min(), week, freq="W-SUN"))
    closes = prices["close"].where(prices["close"].gt(0) & prices["close"].lt(float("inf")))
    means = pd.DataFrame({n: closes.rolling(n).mean() for n in (4, 13, 26, 52)})
    if means.iloc[-1].isna().any():
        return unavailable
    latest = prices["date"].iloc[-1]
    result = {"date": latest.date().isoformat()}
    short_trend = (means[4] > means[13]) & (means[13] > means[26])
    aligned = short_trend & (means[26] > means[52])
    if not aligned.iloc[-1]:
        return dict(result, state="emerging" if short_trend.iloc[-1] else "other")

    # The first calculable window may already be in an older cycle.
    start = len(aligned) - 1
    while start > 0 and aligned.iloc[start - 1]:
        start -= 1
    known_start = start > 0 and pd.notna(means[52].iloc[start - 1])
    first = prices["date"].iloc[start]
    age = prices.index[-1].ordinal - prices.index[start].ordinal
    if latest > first + pd.DateOffset(months=30):
        state = "mature"
    else:
        state = "candidate" if known_start else "unknown_start"
    return dict(result, state=state, weeks=age, first_date=first.date().isoformat() if known_start else None)


def read_final_leaders(path: Path = FINAL_LEADERS) -> tuple[list[dict], str]:
    """Read explicit leader decisions from the research pipeline, with their dates."""
    if not path.is_file():
        return [], "섹터·이익 가속도·공시 위험을 종합한 최종 주도주 판정은 아직 없습니다."
    rows = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            reader.fieldnames = [key.strip().lower().replace(" ", "_") for key in reader.fieldnames or []]
            if not {"ticker", "final_status"}.issubset(reader.fieldnames):
                return [], "검증 결과에서 ticker와 final_status 열을 확인해 주세요."
            for row in reader:
                status = (row.get("final_status") or "").strip().upper().replace("_", " ")
                if status not in {"CONFIRMED LEADER", "EMERGING LEADER", "MATURE LEADER"}:
                    continue
                ticker = (row.get("ticker") or "").strip().upper().split(":")[-1]
                if ticker:
                    rows.append({"종목": ticker, "리서치 판정": status, "검증 기준일": row.get("as_of") or row.get("validated_at") or "미기재"})
    except (OSError, UnicodeError, csv.Error):
        return [], "실적·공시 검증 결과 파일을 읽지 못했습니다."
    return rows, ""
