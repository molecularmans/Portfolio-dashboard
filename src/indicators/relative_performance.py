"""S&P 500 종목군의 가중 수익률 분포를 이용한 일봉 RP 점수.

TrendSpider의 yearly RP 개념(3·6·9·12개월 40/20/20/20 및 백분위)을
근사한다. 거래일 63/126/189/252일을 사용하므로 동일한 값은 아니다.
"""

from __future__ import annotations

import bisect
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd


REFERENCE_PATH = Path(__file__).resolve().parents[2] / "data" / "rp_reference.json"
PERIODS = (63, 126, 189, 252)
WEIGHTS = (0.4, 0.2, 0.2, 0.2)


def yearly_performance(close: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """최근 분기에 더 높은 가중치를 둔 1년 가격 성과를 계산한다."""
    if isinstance(close, pd.DataFrame):
        close = close.apply(pd.to_numeric, errors="coerce")
    else:
        close = pd.to_numeric(close, errors="coerce")
    close = close.where(close > 0)
    returns = [(close / close.shift(days) - 1) * weight for days, weight in zip(PERIODS, WEIGHTS)]
    return sum(returns)


@lru_cache(maxsize=1)
def load_rp_reference() -> dict | None:
    if not REFERENCE_PATH.is_file():
        return None
    try:
        with REFERENCE_PATH.open(encoding="utf-8") as source:
            data = json.load(source)
        if data.get("schema_version") != 1 or not isinstance(data.get("daily"), dict):
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


def calculate_rp_history(df: pd.DataFrame, reference: dict | None) -> pd.DataFrame:
    """종목 수익률보다 낮은 S&P 500 종목의 비율을 0~100으로 반환한다.

    같은 날짜의 분포만 비교한다. 기준 날짜가 오래되면 과거 점수는 그래프에
    남기되 현재 템플릿 조건으로 사용하지 않도록 호출자가 날짜를 확인한다.
    """
    columns = ["date", "rp", "performance", "peer_count"]
    if reference is None or df is None or df.empty or not {"date", "close"}.issubset(df.columns):
        return pd.DataFrame(columns=columns)

    prices = df[["date", "close"]].copy()
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce").dt.normalize()
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices.dropna().query("close > 0").sort_values("date").drop_duplicates("date", keep="last")
    if len(prices) < max(PERIODS) + 1:
        return pd.DataFrame(columns=columns)

    prices["performance"] = yearly_performance(prices["close"])
    rows = []
    for date, performance in prices[["date", "performance"]].itertuples(index=False, name=None):
        if not np.isfinite(performance):
            continue
        peers = reference["daily"].get(date.strftime("%Y-%m-%d"))
        if not isinstance(peers, list) or len(peers) < 400:
            continue
        # 분포는 생성 시 오름차순 저장한다. 동점은 이긴 종목에 포함하지 않는다.
        below = bisect.bisect_left(peers, float(performance))
        rows.append({
            "date": date,
            "rp": round(below / len(peers) * 100.0, 1),
            "performance": float(performance),
            "peer_count": len(peers),
        })
    return pd.DataFrame(rows, columns=columns)


def current_rp_rating(df: pd.DataFrame, history: pd.DataFrame) -> float | None:
    """최근 주가와 동일한 날짜에 계산된 RP만 현재 템플릿에 전달한다."""
    if df is None or df.empty or history.empty:
        return None
    latest_price_date = pd.to_datetime(df["date"].iloc[-1], errors="coerce")
    if pd.isna(latest_price_date) or latest_price_date.normalize() != history["date"].iloc[-1]:
        return None
    return float(history["rp"].iloc[-1])
