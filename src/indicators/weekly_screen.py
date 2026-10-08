"""Completed-week watchlist assessment, independent of the daily A–D engine."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd


WEEKLY_STAGE_LABELS = {
    "ready": "주봉 돌파 조건 충족",
    "setup": "주봉 진입 준비",
    "watch": "주봉 관심 우선순위",
    "hold": "주봉 보류",
    "unavailable": "자료 부족·주봉 지연",
}


def completed_week_start(ticker: str, now: datetime | None = None) -> date:
    """Return the Monday of the latest fully closed market week."""
    current = now or datetime.now(ZoneInfo("Asia/Seoul"))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    korea = ticker.isdigit() and len(ticker) == 6
    market_now = current.astimezone(ZoneInfo("Asia/Seoul" if korea else "America/New_York"))
    monday = market_now.date() - timedelta(days=market_now.weekday())
    if market_now.weekday() > 4 or (market_now.weekday() == 4 and market_now.time() >= (time(16) if korea else time(16, 30))):
        return monday
    return monday - timedelta(days=7)


def evaluate_weekly_ticker(df: pd.DataFrame, ticker: str, now: datetime | None = None) -> dict:
    """Assess only closed weekly bars with 13/26/52-week trend and a 20-week pivot."""
    unavailable = {"stage": "unavailable", "date": None, "reason": "완료된 주봉 자료가 부족합니다."}
    required = {"date", "close", "high", "low", "volume"}
    if df is None or df.empty or not required.issubset(df.columns):
        return unavailable

    prices = df[list(required)].copy()
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    for column in required - {"date"}:
        prices[column] = pd.to_numeric(prices[column], errors="coerce")
    prices = prices.dropna().sort_values("date").drop_duplicates("date", keep="last")
    prices = prices[(prices[["close", "high", "low"]] > 0).all(axis=1) & (prices["volume"] >= 0)]
    expected_monday = completed_week_start(ticker, now)
    week_mondays = prices["date"].dt.date.map(lambda day: day - timedelta(days=day.weekday()))
    prices = prices.loc[week_mondays <= expected_monday]
    if len(prices) < 58:
        return unavailable

    last_date = prices["date"].iloc[-1].date()
    last_monday = last_date - timedelta(days=last_date.weekday())
    if last_monday != expected_monday:
        return {"stage": "unavailable", "date": last_date.isoformat(), "reason": "최근 완료 주봉이 아직 도착하지 않았습니다."}

    close = float(prices["close"].iloc[-1])
    ma13 = float(prices["close"].tail(13).mean())
    ma26 = float(prices["close"].tail(26).mean())
    ma52 = float(prices["close"].tail(52).mean())
    ma52_prior = float(prices["close"].iloc[-57:-5].mean())
    pivot = float(prices["high"].iloc[-21:-1].max())
    previous_low = float(prices["low"].iloc[-11:-1].min())
    stop_candidates = [price for price in (previous_low, ma13) if 0 < price < close]
    stop = max(stop_candidates, default=None)
    risk_pct = (close - stop) / close * 100 if stop else None
    previous_volume = float(prices["volume"].iloc[-21:-1].mean())
    volume_ratio = float(prices["volume"].iloc[-1] / previous_volume) if previous_volume > 0 else None
    trend = close > ma13 > ma26 > ma52 and ma52 > ma52_prior
    breakout = close > pivot and volume_ratio is not None and volume_ratio >= 1.2

    if trend and breakout and risk_pct is not None and risk_pct <= 15:
        stage, reason = "ready", "완료된 주봉 종가가 직전 20주 고점을 넘고 거래량이 20주 평균의 1.2배 이상입니다."
    elif trend and close >= pivot * 0.95 and close <= pivot and risk_pct is not None and risk_pct <= 15:
        stage, reason = "setup", "상승 추세에서 20주 고점 5% 이내이며 주봉 손절 관찰선이 있습니다."
    elif close > ma26 and ma26 >= ma52:
        stage, reason = "watch", "중기 상승 구조를 관찰합니다. 주봉 돌파·거래량·위험 조건은 아직 확인되지 않았습니다."
    else:
        stage, reason = "hold", "26주·52주 추세 또는 현재 주가 위치가 주봉 진입 기준에 미달합니다."
    return {
        "stage": stage,
        "date": last_date.isoformat(),
        "reason": reason,
        "close": round(close, 4),
        "ma13": round(ma13, 4),
        "ma26": round(ma26, 4),
        "ma52": round(ma52, 4),
        "pivot": round(pivot, 4),
        "stop": round(stop, 4) if stop else None,
        "risk_pct": round(risk_pct, 1) if risk_pct is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
    }
