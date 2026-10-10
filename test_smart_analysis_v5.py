"""Regression checks for the V5 chart context and score."""

import unittest

import numpy as np
import pandas as pd

from src.indicators.smart_analysis_v5 import (
    analyze_anchored_vwap,
    analyze_market_structure,
    analyze_smart_chart_v5,
    analyze_volume_profile,
)
from src.ui.charts import create_detail_chart, create_volume_profile_chart


def bars(close, volume=None):
    close = np.asarray(close, dtype=float)
    if volume is None:
        volume = np.full(len(close), 1_000_000.0)
    return pd.DataFrame({
        "date": pd.bdate_range("2025-01-01", periods=len(close)),
        "open": close - 0.2,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.asarray(volume, dtype=float),
    })


class SmartAnalysisV5Tests(unittest.TestCase):
    def test_swing_is_reported_only_after_right_hand_bars_close(self):
        close = np.linspace(100, 110, 45)
        close[30:37] = [110, 112, 115, 111, 109, 108, 107]
        frame = bars(close)
        before = analyze_market_structure(frame.iloc[:35], swing_bars=3)
        after = analyze_market_structure(frame.iloc[:36], swing_bars=3)
        self.assertFalse(any(item["pivot_idx"] == 32 for item in before["swings"]))
        self.assertTrue(any(item["pivot_idx"] == 32 and item["confirmed_idx"] == 35 for item in after["swings"]))
        self.assertTrue(all(item["pivot_date"].startswith("2025-") for item in after["swings"]))
        undated = analyze_market_structure(frame.drop(columns="date").iloc[:36], swing_bars=3)
        self.assertTrue(any(item["pivot_idx"] == 32 and item["pivot_date"] == "33번째 봉" for item in undated["swings"]))

    def test_vwap_anchor_changes_line_and_is_explicitly_approximate(self):
        frame = bars(np.linspace(100, 120, 70), np.linspace(1, 3, 70))
        early = analyze_anchored_vwap(frame, anchor_date=frame["date"].iloc[10])
        late = analyze_anchored_vwap(frame, anchor_date=frame["date"].iloc[40])
        self.assertTrue(early["is_valid"])
        self.assertTrue(late["is_valid"])
        self.assertGreater(late["vwap"], early["vwap"])
        self.assertEqual(early["anchor_idx"], 10)
        self.assertIn("근사치", early["estimate"])

    def test_profile_is_close_bucket_estimate_with_contiguous_value_area(self):
        frame = bars(np.tile([90, 100, 100, 100, 110], 25))
        profile = analyze_volume_profile(frame)
        self.assertTrue(profile["is_valid"])
        self.assertLessEqual(profile["val"], profile["poc"])
        self.assertLessEqual(profile["poc"], profile["vah"])
        self.assertAlmostEqual(sum(profile["volumes"]), frame["volume"].tail(120).sum())
        self.assertIn("추정치", profile["estimate"])
        chart = create_volume_profile_chart(frame, "TEST")
        self.assertEqual(len(chart.data), 1)
        self.assertIn("추정", chart.layout.title.text)

    def test_v5_score_uses_all_new_components_and_labels_validation_scope(self):
        x = np.arange(180)
        frame = bars(80 + x * 0.15 + np.sin(x / 6) * 2.0)
        result = analyze_smart_chart_v5(frame)
        self.assertEqual(result["algorithm_version"], "experimental-v5")
        self.assertEqual(result["validation_scope"], "v4-baseline-only")
        self.assertEqual(set(result["score_components"]), {
            "v4_baseline", "market_structure", "anchored_vwap", "volume_profile_estimate", "atr_risk"
        })
        self.assertEqual(result["composite_score"], round(sum(result["score_components"].values())))
        self.assertTrue(0 <= result["composite_score"] <= 100)

    def test_detail_chart_renders_v5_layers_without_widget_changes(self):
        x = np.arange(180)
        frame = bars(80 + x * 0.15 + np.sin(x / 6) * 2.0)
        figure = create_detail_chart(frame, "TEST", {
            "smart_analysis_engine": "v5", "selected_sub_indicators": [],
            "show_support_resistance": False, "show_trendlines": False,
            "show_pattern_lines": False,
        })
        names = [trace.name for trace in figure.data]
        self.assertTrue(any("VWAP" in name for name in names))
        self.assertTrue(any("ATR" in name for name in names))


if __name__ == "__main__":
    unittest.main()
