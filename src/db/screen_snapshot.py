"""Last completed watchlist screens, shared across browser sessions and app restarts."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Callable
from zoneinfo import ZoneInfo

import requests

from src.db.github_sync import GitHubSync
from src.indicators.daily_screen import evaluate_daily_ticker, scan_day
from src.indicators.weekly_screen import completed_week_start, evaluate_weekly_ticker


SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "data" / "watchlist_screen.json"
REMOTE_PATH = "data/watchlist_screen.json"


class ScreenSnapshotStore:
    def __init__(self, path: Path = SNAPSHOT_PATH, github_sync: GitHubSync | None = None):
        self.path = path
        self.github_sync = github_sync or GitHubSync()

    def load(self) -> dict:
        try:
            with self.path.open(encoding="utf-8") as source:
                content = json.load(source)
            if content.get("schema_version") == 1 and isinstance(content.get("screens"), dict):
                return content["screens"]
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def save(self, screens: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"schema_version": 1, "screens": screens}, ensure_ascii=False, indent=2)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self.path)

    def save_to_github(self, screens: dict) -> bool:
        """Persist ticker-only screen results in the existing dashboard repository."""
        sync = self.github_sync
        if not sync.is_configured:
            return False
        url = f"{sync.api_base}/repos/{sync.repo}/contents/{REMOTE_PATH}"
        encoded = base64.b64encode(
            json.dumps({"schema_version": 1, "screens": screens}, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("ascii")
        for _ in range(2):
            try:
                existing = requests.get(url, headers=sync.get_headers(), timeout=8)
                if existing.status_code not in (200, 404):
                    return False
                payload = {"message": "Update watchlist screen snapshot", "content": encoded}
                if existing.status_code == 200:
                    payload["sha"] = existing.json()["sha"]
                response = requests.put(url, headers=sync.get_headers(), json=payload, timeout=12)
                if response.status_code in (200, 201):
                    return True
                if response.status_code not in (409, 422):
                    return False
            except (requests.RequestException, KeyError, ValueError):
                return False
        return False


class ScreenRuntime:
    """One process-wide worker; opening another tab only reads the saved result."""

    def __init__(self, store: ScreenSnapshotStore):
        self.store = store
        self._lock = Lock()
        self._screens = store.load()
        self._auto_day = scan_day()
        self._job: dict | None = None

    def screen(self, timeframe: str) -> dict | None:
        with self._lock:
            return self._screens.get(timeframe)

    def status(self) -> dict | None:
        with self._lock:
            return dict(self._job) if self._job else None

    def start(self, tickers: list[str], load_data: Callable, db, client, *, scheduled: bool = False) -> bool:
        day = scan_day()
        with self._lock:
            if scheduled:
                if day == self._auto_day:
                    return False
            if self._job and self._job["running"]:
                return False
            if scheduled:
                self._auto_day = day
            weekly_due = not scheduled or (self._screens.get("W") or {}).get("week_start") != completed_week_start("AAPL").isoformat()
            periods = ("D", "W") if weekly_due else ("D",)
            self._job = {"running": True, "done": 0, "total": len(tickers) * len(periods), "ticker": "", "error": None}
        Thread(target=self._run, args=(tuple(tickers), day, periods, load_data, db, client), daemon=True).start()
        return True

    def _run(self, tickers: tuple[str, ...], day: str, periods: tuple[str, ...], load_data: Callable, db, client) -> None:
        try:
            for timeframe, label, evaluator in (
                ("D", "일봉", evaluate_daily_ticker),
                ("W", "주봉", evaluate_weekly_ticker),
            ):
                if timeframe not in periods:
                    continue
                results = {}
                for ticker in tickers:
                    with self._lock:
                        self._job["ticker"] = f"{label} {ticker}"
                    try:
                        df = load_data(ticker, db, client, force_refresh=True, timeframe=label)
                        results[ticker] = evaluator(df, ticker)
                    except Exception:
                        results[ticker] = {"stage": "unavailable", "date": None}
                    with self._lock:
                        self._job["done"] += 1
                screen = {
                    "scan_day": day,
                    "tickers": list(tickers),
                    "results": results,
                    "completed_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="minutes"),
                }
                if timeframe == "W":
                    screen["week_start"] = completed_week_start("AAPL").isoformat()
                with self._lock:
                    self._screens[timeframe] = screen
                    self.store.save(self._screens)
            if not self.store.save_to_github(self._screens):
                with self._lock:
                    self._job["error"] = "클라우드 영구 저장 실패 · 앱 재시작 후 결과가 사라질 수 있습니다."
        except Exception as exc:
            with self._lock:
                self._job["error"] = f"판정 저장 실패: {type(exc).__name__}"
        finally:
            with self._lock:
                self._job["running"] = False
                self._job["ticker"] = ""
