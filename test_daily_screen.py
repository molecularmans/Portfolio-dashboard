import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np

from src.indicators.daily_screen import classify_entry_stage, evaluate_daily_ticker, latest_closed_session_date, scan_day


class DailyScreenTests(unittest.TestCase):
    def setUp(self):
        self.summary = {
            "verdict": "신규 진입 보류",
            "current": 205.0,
            "entry": None,
            "stop": 107.65,
            "blockers": ["유효한 진입 기준 가격 없음"],
        }
        self.vcp = {"trend_template": {"is_stage_2": True, "rp_rating": 99.6}}
        self.v3 = {"regime": {"trend": "상승 추세"}}
        self.v4 = {"composite_score": 64}

    def classify(self):
        return classify_entry_stage(self.summary, self.vcp, self.v3, self.v4)["stage"]

    def test_strong_trend_without_breakout_price_is_watch_priority(self):
        self.assertEqual(self.classify(), "watch")

    def test_nearby_valid_setup_waits_for_daily_trigger(self):
        self.summary.update(verdict="조건부 관찰", entry=207.0, stop=195.0, blockers=[])
        self.assertEqual(self.classify(), "setup")

    def test_strictly_confirmed_setup_is_separate_bucket(self):
        self.summary.update(verdict="조건 충족 · 확인 필요", entry=202.0, blockers=[])
        self.assertEqual(self.classify(), "ready")

    def test_bearish_warning_prevents_priority(self):
        self.summary["blockers"] = ["[B] 하락 패턴이 우세", "유효한 진입 기준 가격 없음"]
        self.assertEqual(self.classify(), "hold")

    def test_faraway_entry_is_research_watch_not_setup(self):
        self.summary.update(verdict="조건부 관찰", entry=230.0, stop=190.0, blockers=[])
        self.assertEqual(self.classify(), "watch")

    def test_strong_trend_can_be_watched_when_rp_reference_is_missing(self):
        self.vcp["trend_template"] = {"is_stage_2": False, "rp_rating": None}
        self.v4["composite_score"] = 72
        self.assertEqual(self.classify(), "watch")

    def test_old_price_is_never_shown_as_current_candidate(self):
        old = datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=12)
        df = pd.DataFrame({"date": pd.date_range(end=old.date(), periods=35)})
        self.assertEqual(evaluate_daily_ticker(df, "TWST")["stage"], "unavailable")

    def test_daily_scan_rolls_after_us_close(self):
        tz = ZoneInfo("Asia/Seoul")
        self.assertEqual(scan_day(datetime(2026, 10, 6, 9, 29, tzinfo=tz)), "2026-10-02")
        self.assertEqual(scan_day(datetime(2026, 10, 6, 9, 30, tzinfo=tz)), "2026-10-05")
        self.assertEqual(scan_day(datetime(2026, 10, 11, 12, tzinfo=tz)), "2026-10-09")

    def test_last_closed_us_day_skips_weekend(self):
        tz = ZoneInfo("Asia/Seoul")
        self.assertEqual(latest_closed_session_date("TWST", datetime(2026, 10, 11, 12, tzinfo=tz)).isoformat(), "2026-10-09")

    def test_current_daily_bar_uses_full_detail_analysis_pipeline(self):
        latest = latest_closed_session_date("TWST")
        close = np.linspace(80.0, 120.0, 300)
        df = pd.DataFrame({
            "date": pd.bdate_range(end=latest, periods=300),
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.985,
            "close": close,
            "volume": np.full(300, 1_000_000.0),
        })
        result = evaluate_daily_ticker(df, "TWST")
        self.assertIn(result["stage"], {"ready", "setup", "watch", "hold"})
        self.assertEqual(result["date"], latest.isoformat())


if __name__ == "__main__":
    unittest.main()
