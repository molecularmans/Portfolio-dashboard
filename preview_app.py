"""Local, isolated preview of the dashboard changes before deployment."""

import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PREVIEW_DIR = ROOT / ".preview"
PREVIEW_DIR.mkdir(exist_ok=True)

# The preview must never use account credentials or write to the live GitHub repo.
os.environ["GITHUB_TOKEN"] = "preview"
os.environ["KIS_APP_KEY"] = "your_preview"
os.environ["KIS_CANO_2"] = "your_preview"
os.environ["KIS_CANO_3"] = "your_preview"

for filename in ("user_config.json", "watchlist_screen.json"):
    source = ROOT / "data" / filename
    destination = PREVIEW_DIR / filename
    if source.exists() and not destination.exists():
        shutil.copy2(source, destination)

import src.db.github_sync as github_sync  # noqa: E402
from src.db.database import StockDB  # noqa: E402
from src.db.screen_snapshot import ScreenSnapshotStore  # noqa: E402

github_sync.CONFIG_PATH = ".preview/user_config.json"

import streamlit as st  # noqa: E402
import app as dashboard  # noqa: E402

dashboard.StockDB = lambda: StockDB(db_path=str(PREVIEW_DIR / "stock_cache.db"))
dashboard.ScreenSnapshotStore = lambda: ScreenSnapshotStore(path=PREVIEW_DIR / "watchlist_screen.json")

st.info("🧪 테스트 화면 · 그룹 이동과 차트 페이지를 확인해 주세요. 이 화면의 설정 변경은 운영 대시보드에 반영되지 않습니다.")
dashboard.main()
