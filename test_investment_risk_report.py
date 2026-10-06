import unittest

import pandas as pd

from src.indicators.investment_risk_report import build_investment_risk_report


class InvestmentRiskReportTests(unittest.TestCase):
    def setUp(self):
        dates = pd.bdate_range("2026-01-01", periods=70)
        self.df = pd.DataFrame({
            "date": dates,
            "open": [100.0] * 69 + [90.0],
            "high": [101.0] * 70,
            "low": [99.0] * 69 + [89.0],
            "close": [100.0] * 70,
            "volume": [1000] * 70,
        })
        self.assessment = {"verdict": "조건부 관찰", "risk_pct": 5.0}

    def test_gap_larger_than_stop_is_reported_without_approving_entry(self):
        result = build_investment_risk_report(
            self.df, self.assessment, today=pd.Timestamp(self.df["date"].iloc[-1])
        )
        self.assertTrue(result["is_valid"])
        self.assertAlmostEqual(result["max_down_gap_pct"], 10.0)
        self.assertAlmostEqual(result["daily_vol_pct"], 0.0)
        self.assertGreater(result["atr_pct"], 2.0)
        self.assertAlmostEqual(result["median_value_20"], 100000.0)
        self.assertTrue(any("하락 개장 갭" in warning for warning in result["warnings"]))

    def test_missing_history_and_stop_are_explicit(self):
        result = build_investment_risk_report(self.df.tail(30), {"verdict": "신규 진입 보류", "risk_pct": None})
        self.assertIsNone(result["max_down_gap_pct"])
        self.assertIsNone(result["drawdown_52w_pct"])
        self.assertTrue(any("손절선" in warning for warning in result["warnings"]))

    def test_stale_daily_data_is_flagged(self):
        last = pd.Timestamp(self.df["date"].iloc[-1])
        result = build_investment_risk_report(self.df, self.assessment, today=last + pd.Timedelta(days=7))
        self.assertTrue(any("새 시세" in warning for warning in result["warnings"]))

    def test_stop_narrower_than_average_range_is_flagged(self):
        assessment = {"verdict": "조건부 관찰", "risk_pct": 1.0}
        result = build_investment_risk_report(self.df, assessment)
        self.assertLess(result["stop_atr_multiple"], 1)
        self.assertTrue(any("ATR" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
