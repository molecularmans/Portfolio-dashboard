import unittest

import numpy as np
import pandas as pd

from src.indicators.vcp_analyzer import check_trend_template, detect_vcp_pattern


def make_prices(closes, high=None, low=None):
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=len(closes), freq="B"),
        "close": closes,
        "high": np.asarray(high if high is not None else closes * 1.01, dtype=float),
        "low": np.asarray(low if low is not None else closes * 0.99, dtype=float),
        "volume": np.full(len(closes), 1000),
    })


class TrendTemplateTests(unittest.TestCase):
    def test_ten_checks_in_screenshot_order_and_unknown_rp(self):
        prices = make_prices(np.linspace(50, 130, 250))
        result = check_trend_template(prices)

        self.assertEqual(result["total_count"], 10)
        self.assertEqual(result["pass_count"], 9)
        self.assertEqual(result["evaluated_count"], 9)
        self.assertIsNone(result["checks"][0]["passed"])
        self.assertTrue(all(check["passed"] for check in result["checks"][1:]))
        self.assertEqual(result["checks"][7]["name"], "52주 저점 대비 +30% 이상")
        self.assertEqual(result["checks"][9]["name"], "200일선 상승 중")
        self.assertTrue(result["is_stage_2"])
        self.assertFalse(result["template_complete"])

        with_rp = check_trend_template(prices, rp_rating=93.6)
        self.assertEqual(with_rp["pass_count"], 10)
        self.assertTrue(with_rp["template_complete"])
        self.assertEqual(check_trend_template(prices, rp_rating=70)["checks"][0]["passed"], False)

    def test_52_week_boundary_values(self):
        closes = np.full(250, 100.0)
        closes[-1] = 104.0
        prices = make_prices(closes, high=np.full(250, 130.0), low=np.full(250, 80.0))
        result = check_trend_template(prices)
        self.assertTrue(result["checks"][7]["passed"])  # +30% exactly
        self.assertTrue(result["checks"][8]["passed"])  # -20% from high

        prices.loc[249, "close"] = 96.0
        self.assertFalse(check_trend_template(prices)["checks"][8]["passed"])  # -26.2%
        prices.loc[249, "close"] = 97.5
        self.assertFalse(check_trend_template(prices)["checks"][7]["passed"])  # +21.9%

    def test_screenshot_values_produce_nine_of_ten(self):
        closes = np.linspace(35, 74.5, 250)
        low = np.full(250, 74.5 / 2.245)
        prices = make_prices(closes, high=np.full(250, 100.0), low=low)
        result = check_trend_template(prices, rp_rating=93.6)

        self.assertEqual(result["pass_count"], 9)
        self.assertEqual(result["evaluated_count"], 10)
        self.assertEqual([check["passed"] for check in result["checks"]],
                         [True] * 8 + [False, True])
        self.assertAlmostEqual(result["dist_from_52w_high_pct"], -25.5)
        self.assertAlmostEqual(result["dist_from_52w_low_pct"], 124.5)

    def test_missing_history_is_not_treated_as_a_failed_check(self):
        prices = make_prices(np.linspace(50, 100, 229))
        result = check_trend_template(prices)
        self.assertIsNone(result["checks"][7]["passed"])
        self.assertIsNone(result["checks"][8]["passed"])
        self.assertIsNone(result["checks"][9]["passed"])
        self.assertFalse(result["is_stage_2"])

        short = detect_vcp_pattern(make_prices(np.linspace(50, 60, 25)))
        self.assertEqual(short["trend_template"]["total_count"], 10)
        self.assertEqual(len(short["trend_template"]["checks"]), 10)


if __name__ == "__main__":
    unittest.main()
