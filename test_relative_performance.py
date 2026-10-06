import unittest

import numpy as np
import pandas as pd

from src.indicators.relative_performance import (
    calculate_rp_history,
    current_rp_rating,
    yearly_performance,
)
from src.indicators.smart_analysis_v2 import analyze_vcp_v2


class RelativePerformanceTests(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range("2025-01-01", periods=300, freq="B")
        closes = np.linspace(50, 100, len(dates))
        self.prices = pd.DataFrame({
            "date": dates,
            "close": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "volume": np.full(len(dates), 1_000_000),
        })

    def test_weighted_yearly_performance(self):
        prices = pd.Series(np.full(253, 100.0))
        prices.iloc[-1] = 120.0
        self.assertAlmostEqual(yearly_performance(prices).iloc[-1], 0.20)

    def test_percentile_and_current_date(self):
        last_date = self.prices["date"].iloc[-1].strftime("%Y-%m-%d")
        reference = {"schema_version": 1, "daily": {last_date: [0.0] * 300 + [1.0] * 100}}
        history = calculate_rp_history(self.prices, reference)
        self.assertEqual(len(history), 1)
        self.assertEqual(current_rp_rating(self.prices, history), 75.0)

        next_day = self.prices.copy()
        next_row = next_day.iloc[-1].copy()
        next_row["date"] = self.prices["date"].iloc[-1] + pd.Timedelta(days=1)
        next_day.loc[len(next_day)] = next_row
        self.assertIsNone(current_rp_rating(next_day, history))

    def test_rp_flows_into_ten_condition_template(self):
        result = analyze_vcp_v2(self.prices, rp_rating=82.5)
        trend = result["trend_template"]
        self.assertEqual(trend["rp_rating"], 82.5)
        self.assertTrue(trend["checks"][0]["passed"])


if __name__ == "__main__":
    unittest.main()
