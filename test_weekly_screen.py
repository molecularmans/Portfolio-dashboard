import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.indicators.weekly_screen import completed_week_start, evaluate_weekly_ticker


class WeeklyScreenTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 8, 12, tzinfo=ZoneInfo("Asia/Seoul"))
        completed_friday = completed_week_start("TWST", self.now) + timedelta(days=4)
        closes = np.linspace(50.0, 100.0, 70)
        closes[-1] = 101.0
        self.df = pd.DataFrame({
            "date": pd.date_range(end=completed_friday, periods=70, freq="W-FRI"),
            "close": closes,
            "high": closes * 1.01,
            "low": closes * 0.98,
            "volume": np.r_[np.full(69, 1_000_000.0), 2_000_000.0],
        })

    def test_weekly_breakout_uses_last_completed_week(self):
        result = evaluate_weekly_ticker(self.df, "TWST", self.now)
        self.assertEqual(result["stage"], "ready")
        self.assertEqual(result["date"], "2026-10-02")
        self.assertEqual(result["volume_ratio"], 2.0)

    def test_current_partial_week_is_ignored(self):
        partial = self.df.iloc[-1].copy()
        partial["date"] = pd.Timestamp("2026-10-07")
        partial["close"] = 300.0
        partial["high"] = 310.0
        with_partial = pd.concat([self.df, pd.DataFrame([partial])], ignore_index=True)
        result = evaluate_weekly_ticker(with_partial, "TWST", self.now)
        self.assertEqual(result["stage"], "ready")
        self.assertEqual(result["close"], 101.0)

    def test_near_pivot_without_breakout_is_setup(self):
        df = self.df.copy()
        df.loc[df.index[-1], ["close", "high", "volume"]] = [98.5, 99.0, 1_000_000.0]
        self.assertEqual(evaluate_weekly_ticker(df, "TWST", self.now)["stage"], "setup")

    def test_stale_completed_week_is_unavailable(self):
        stale = self.df.iloc[:-1]
        self.assertEqual(evaluate_weekly_ticker(stale, "TWST", self.now)["stage"], "unavailable")


if __name__ == "__main__":
    unittest.main()
