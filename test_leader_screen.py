import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.indicators.leader_screen import read_final_leaders, weekly_cycle
from src.ui.leader_view import watchlist_leader_rows


def bars(values, end="2026-11-20"):
    return pd.DataFrame({"date": pd.date_range(end=end, periods=len(values), freq="W-FRI"), "close": values})


def cycle(frame):
    return weekly_cycle(frame, frame.iloc[-1]["date"].to_period("W-SUN").start_time.date())


class LeaderScreenTests(unittest.TestCase):
    def test_transition_week_zero_then_recalculates_after_break(self):
        frame = bars([100.0] * 55 + [110.0, 120.0])
        result = cycle(frame)
        self.assertEqual((result["state"], result["weeks"]), ("candidate", 1))
        self.assertEqual(result["first_date"], frame.date.iloc[-2].date().isoformat())
        self.assertEqual(cycle(bars([100.0] * 55 + [110.0, 90.0] + [100.0] * 55 + [105.0]))["weeks"], 0)

    def test_incomplete_and_missing_bars(self):
        frame = bars([100.0] * 55 + [101.0, 102.0])
        self.assertEqual(weekly_cycle(frame, frame.date.iloc[-2].to_period("W-SUN").start_time.date())["weeks"], 0)
        self.assertEqual(cycle(frame.drop(index=30))["state"], "unavailable")
        self.assertEqual(cycle(bars(range(1, 52)))["state"], "unavailable")

    def test_unknown_start_short_history_and_old_cycle(self):
        result = cycle(bars(range(1, 71)))
        self.assertEqual((result["state"], result["weeks"], result["first_date"]), ("unknown_start", 18, None))
        self.assertEqual(cycle(bars(range(1, 201)))["state"], "mature")
        self.assertEqual(cycle(bars([100] * 55 + list(range(101, 244))))["state"], "mature")

    def test_emerging_and_equal_averages(self):
        self.assertEqual(cycle(bars([150]*30 + [50]*22 + list(range(51, 63))))["state"], "emerging")
        self.assertEqual(cycle(bars(np.full(55, 100)))["state"], "other")

    def test_cross_only_uses_latest_daily_and_completed_week(self):
        now = datetime(2026, 11, 25, 11, tzinfo=ZoneInfo("Asia/Seoul"))
        weekly = {"results": {"A": {"cycle": {"state": "candidate", "date": "2026-11-20"}},
                              "B": {"cycle": {"state": "candidate", "date": "2026-11-13"}}}}
        daily = {"results": {"A": {"stage": "ready", "date": "2026-11-23"},
                             "B": {"stage": "ready", "date": "2026-11-24"}}}
        first, second = watchlist_leader_rows(["A", "B"], daily, weekly, now)
        self.assertEqual((first["주봉 분류"], first["일봉 판정"]), ("정배열 후보", "확인 필요"))
        self.assertEqual((second["주봉 분류"], second["일봉 판정"]), ("주봉 확인 필요", "당일 진입 조건 충족"))

    def test_only_explicit_leaders_from_final_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "leaders.csv"
            self.assertTrue(read_final_leaders(path)[1])
            path.write_text("Ticker,Final Status,as_of\nNASDAQ:AAA,CONFIRMED LEADER,2026-11-20\nBBB,CP WATCH,2026-11-20\n", encoding="utf-8-sig")
            rows, error = read_final_leaders(path)
            self.assertFalse(error)
            self.assertEqual([row["종목"] for row in rows], ["AAA"])
