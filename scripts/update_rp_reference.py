"""현재 S&P 500 구성종목의 RP 기준 분포를 재생성한다.

실행 환경: GitHub Actions (yfinance 설치). 실패 시 기존 JSON은 그대로 둔다.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.indicators.relative_performance import yearly_performance  # noqa: E402


CONSTITUENTS_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
OUTPUT_PATH = ROOT / "data" / "rp_reference.json"


def fetch_symbols() -> list[str]:
    response = requests.get(CONSTITUENTS_URL, timeout=30)
    response.raise_for_status()
    constituents = pd.read_csv(io.StringIO(response.text))
    symbols = sorted(set(constituents["Symbol"].dropna().astype(str).str.replace(".", "-", regex=False)))
    if not 450 <= len(symbols) <= 550:
        raise RuntimeError(f"S&P 500 구성종목 수가 예상 범위를 벗어났습니다: {len(symbols)}")
    return symbols


def fetch_closes(symbols: list[str]) -> pd.DataFrame:
    chunks = []
    for start in range(0, len(symbols), 50):
        batch = symbols[start:start + 50]
        prices = yf.download(
            batch, period="2y", interval="1d", auto_adjust=True,
            progress=False, threads=True, group_by="column", timeout=30,
        )
        if prices.empty:
            continue
        if isinstance(prices.columns, pd.MultiIndex):
            closes = prices["Close"]
        else:
            closes = prices[["Close"]].rename(columns={"Close": batch[0]})
        chunks.append(closes)
        print(f"Downloaded {start + len(batch)}/{len(symbols)} symbols", flush=True)

    if not chunks:
        raise RuntimeError("가격 데이터를 다운로드하지 못했습니다.")
    closes = pd.concat(chunks, axis=1)
    closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    closes = closes.ffill(limit=3)
    if closes.shape[1] < 400:
        raise RuntimeError(f"유효한 비교 종목이 부족합니다: {closes.shape[1]}")
    return closes


def build_reference(closes: pd.DataFrame, constituent_count: int) -> dict:
    performance = yearly_performance(closes)
    daily = {}
    for date, row in performance.tail(90).iterrows():
        values = row.dropna().to_numpy(dtype=float)
        if len(values) >= 400:
            daily[date.strftime("%Y-%m-%d")] = sorted(round(float(value), 8) for value in values)
    if len(daily) < 30:
        raise RuntimeError(f"유효한 RP 날짜가 부족합니다: {len(daily)}")

    as_of = max(daily)
    if (pd.Timestamp.now(tz="UTC").normalize() - pd.Timestamp(as_of, tz="UTC")).days > 5:
        raise RuntimeError(f"기준 종가가 오래되었습니다: {as_of}")
    return {
        "schema_version": 1,
        "as_of": as_of,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe": "S&P 500 current constituents",
        "constituent_count": constituent_count,
        "method": "weighted price returns: 63d 40%, 126d 20%, 189d 20%, 252d 20%; percentile strictly below",
        "daily": daily,
    }


def main() -> None:
    symbols = fetch_symbols()
    closes = fetch_closes(symbols)
    reference = build_reference(closes, len(symbols))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(reference, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(f"Saved {len(reference['daily'])} dates; as_of={reference['as_of']}; peers={len(reference['daily'][reference['as_of']])}")


if __name__ == "__main__":
    main()
