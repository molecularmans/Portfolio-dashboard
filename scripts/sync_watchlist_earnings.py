"""Project three authenticated Sheets values ranges from stdin onto the public watchlist.

Input JSON contains blocks (C:L, P:P, V:V, each with its header, starting at row 1)
and updated_at (the source revision timestamp with timezone). Output is limited to
corporate facts. An identical projection leaves the checked-in snapshot unchanged.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.indicators.earnings_evidence import SNAPSHOT, read_snapshot, sheet_records


def synchronize(payload, watchlist, path):
    source_time = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00"))
    if source_time.tzinfo is None:
        raise ValueError("시트 수정 시각에 시간대가 필요합니다.")
    source_time = source_time.astimezone(ZoneInfo("Asia/Seoul"))
    records = sheet_records(payload["blocks"], watchlist, source_time.date())
    if not records:
        raise ValueError("관심종목 실적 데이터가 없어 기존 결과를 보존합니다.")
    if path.exists():
        saved = read_snapshot(path)
        if datetime.fromisoformat(saved["updated_at"]) > source_time:
            raise ValueError("이전 시트 버전으로 덮어쓸 수 없습니다.")
        if records == saved["records"]:
            return
    snapshot = {"version": 1, "updated_at": source_time.isoformat(), "records": records}
    with NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    os.replace(file.name, path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", type=Path, default=ROOT / "data/user_config.json")
    parser.add_argument("--output", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    with args.watchlist.open(encoding="utf-8") as config:
        tickers = {r["ticker"] for r in json.load(config)["watchlist"]}
    synchronize(json.load(sys.stdin), tickers, args.output)
