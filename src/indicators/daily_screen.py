"""Daily watchlist buckets derived from the same A–D assessment as detail view."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from src.indicators.integrated_assessment import build_integrated_assessment
from src.indicators.relative_performance import calculate_rp_history, current_rp_rating, load_rp_reference
from src.indicators.smart_analysis_v5 import analyze_smart_chart_v5


STAGE_LABELS = {
    "ready": "당일 진입 조건 충족",
    "setup": "진입 준비",
    "watch": "관심 우선순위",
    "hold": "보류",
    "unavailable": "자료 부족·시세 지연",
}

_DIRECTIONAL_WARNINGS = (
    "[B] 하락 패턴이 우세",
    "[D] 하락 추세",
    "[A] 하단 추세선 이탈",
    "[B] 패턴 무효화 가격을 이미 이탈",
    "[C] VCP 무효화 가격을 이미 이탈",
    "[D] 거래량 흐름에서 분산 우세",
)


def scan_day(now: datetime | None = None) -> str:
    """Identify the latest US weekday after the 09:30 KST RP update window."""
    current = now or datetime.now(ZoneInfo("Asia/Seoul"))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    candidate = (current.astimezone(ZoneInfo("Asia/Seoul")) - timedelta(hours=9, minutes=30)).date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.isoformat()


def latest_closed_session_date(ticker: str, now: datetime | None = None) -> date:
    """Conservative weekday cutoff; an exchange holiday remains unclassified."""
    current = now or datetime.now(ZoneInfo("Asia/Seoul"))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    korea = ticker.isdigit() and len(ticker) == 6
    market_now = current.astimezone(ZoneInfo("Asia/Seoul" if korea else "America/New_York"))
    close_time = time(16, 0) if korea else time(16, 30)
    closed_day = market_now.date() if market_now.time() >= close_time else market_now.date() - timedelta(days=1)
    while closed_day.weekday() >= 5:
        closed_day -= timedelta(days=1)
    return closed_day


def classify_entry_stage(
    summary: dict[str, Any],
    vcp: dict[str, Any] | None,
    v3: dict[str, Any] | None,
    v4: dict[str, Any] | None,
    v5: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Separate research priority, setup readiness, and the strict daily trigger."""
    if summary.get("verdict") == "자료 부족":
        return {"stage": "unavailable", "reason": "일봉 자료가 부족합니다."}
    if summary.get("verdict") == "조건 충족 · 확인 필요":
        return {"stage": "ready", "reason": "진입선·거래량·추세·위험 조건이 종가 기준으로 함께 확인됐습니다."}

    blockers = summary.get("blockers") or []
    if any(any(blocker.startswith(warning) for warning in _DIRECTIONAL_WARNINGS) for blocker in blockers):
        return {"stage": "hold", "reason": "하락·이탈·분산 등 방향성 위험 신호가 있습니다."}

    vcp = vcp or {}
    template = vcp.get("trend_template") or {}
    trend = ((v3 or {}).get("regime") or {}).get("trend")
    stage_two = bool(template.get("is_stage_2"))
    rp = template.get("rp_rating")
    score = (v5 or v4 or {}).get("composite_score")
    rp_strong = isinstance(rp, (int, float)) and rp >= 70
    score_strong = isinstance(score, (int, float)) and score >= 70
    rising = trend == "상승 추세"

    entry = summary.get("entry")
    current = summary.get("current")
    close_to_entry = bool(entry and current and abs(entry / current - 1) <= 0.05)
    pullback = summary.get("v5_pullback") or {}
    if pullback.get("is_candidate") and not any(
        any(blocker.startswith(warning) for warning in _DIRECTIONAL_WARNINGS)
        for blocker in blockers
    ):
        return {"stage": "setup", "reason": "V5 상승 구조와 시작점 VWAP 근처의 눌림 후보입니다. 지지 확인과 위험 한도 점검이 필요합니다."}
    if (
        close_to_entry
        and summary.get("stop")
        and not blockers
        and (rising or stage_two)
    ):
        return {"stage": "setup", "reason": "가까운 진입선과 손절선이 있으며 당일 확인 조건을 기다립니다."}

    if rising and (stage_two or rp_strong or score_strong):
        return {"stage": "watch", "reason": "상승 추세의 연구 후보입니다. 유효한 진입 가격과 위험을 별도로 확인해야 합니다."}

    return {"stage": "hold", "reason": "상승 추세와 진입 준비 조건이 충분히 확인되지 않았습니다."}


def evaluate_daily_ticker(df: pd.DataFrame, ticker: str) -> dict[str, Any]:
    """Use the default V5 anchor and the same closed bars as detailed analysis."""
    if df.empty or len(df) < 30 or "date" not in df:
        return {"stage": "unavailable", "date": None}
    cutoff = latest_closed_session_date(ticker)
    dates = pd.to_datetime(df["date"], errors="coerce")
    closed_df = df.loc[dates.dt.date <= cutoff].copy()
    if len(closed_df) < 30:
        return {"stage": "unavailable", "date": None}
    last_date = pd.to_datetime(closed_df["date"].iloc[-1], errors="coerce")
    if pd.isna(last_date):
        return {"stage": "unavailable", "date": None}
    # Do not classify an unfinished market day or a stale/holiday quote as today's signal.
    if last_date.date() != cutoff:
        return {"stage": "unavailable", "date": last_date.date().isoformat()}

    reference = None if ticker.isdigit() and len(ticker) == 6 else load_rp_reference()
    rp = current_rp_rating(closed_df, calculate_rp_history(closed_df, reference))
    v5 = analyze_smart_chart_v5(closed_df, rp_rating=rp)
    v4 = v5["v4_baseline"]
    v3 = v4["v3_baseline"]
    summary = build_integrated_assessment(
        closed_df, v5["support_resistance"], v5["patterns"], v5["vcp"], v3, v4, v5
    )
    stage = classify_entry_stage(summary, v5["vcp"], v3, v4, v5)["stage"]
    return {"stage": stage, "date": last_date.date().isoformat()}
