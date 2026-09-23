"""Offline regression tests for the experimental smart-chart v2 engine."""

import unittest

import numpy as np
import pandas as pd

from src.indicators.smart_analysis_v2 import (
    analyze_chart_patterns_v2,
    analyze_support_resistance_v2,
    analyze_vcp_v2,
    find_adaptive_pivots,
)


def make_ohlcv(close, volume, spread=0.8):
    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=len(close), freq="B"),
            "open": close * 0.999,
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": volume,
        }
    )


class TestSmartAnalysisV2(unittest.TestCase):
    def test_a_adaptive_zones_and_trendline_diagnostics(self):
        x = np.arange(180)
        close = 100 + x * 0.04 + np.sin(x * np.pi / 12) * 5.0
        df = make_ohlcv(close, np.full(len(close), 1_000_000.0))

        result = analyze_support_resistance_v2(df)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["algorithm_version"], "experimental-v2")
        self.assertGreater(result["diagnostics"]["atr"], 0)
        self.assertGreater(result["diagnostics"]["reversal_pct"], 0)
        self.assertTrue(result["support_levels"] or result["resistance_levels"])
        self.assertTrue(result["upper_trendline"] or result["lower_trendline"])
        self.assertGreaterEqual(result["quality_score"], 0)
        self.assertLessEqual(result["quality_score"], 100)

        level = (result["support_levels"] or result["resistance_levels"])[0]
        self.assertLess(level["zone_low"], level["zone_high"])
        self.assertIn("strength_score", level)

    def test_b_double_bottom_requires_price_and_volume_confirmation(self):
        close = np.concatenate(
            [
                np.linspace(100, 96, 15),
                np.linspace(96, 80, 11),
                np.linspace(80, 92, 15),
                np.linspace(92, 81, 15),
                np.linspace(81, 94, 24),
            ]
        )
        quiet_volume = np.full(len(close), 1_000_000.0)
        breakout_volume = quiet_volume.copy()
        breakout_volume[-1] = 2_000_000.0

        quiet = analyze_chart_patterns_v2(make_ohlcv(close, quiet_volume))
        confirmed = analyze_chart_patterns_v2(make_ohlcv(close, breakout_volume))

        self.assertTrue(quiet["has_pattern"])
        self.assertTrue(confirmed["has_pattern"])
        self.assertIn("이중 바닥", confirmed["primary_pattern"]["name"])
        self.assertTrue(confirmed["primary_pattern"]["price_confirmed"])
        self.assertTrue(confirmed["primary_pattern"]["volume_confirmed"])
        self.assertTrue(confirmed["primary_pattern"]["is_breakout"])
        self.assertFalse(quiet["primary_pattern"]["volume_confirmed"])

    def test_c_vcp_quality_score_and_supply_metrics(self):
        base = np.linspace(100, 200, 140)
        close = np.concatenate(
            [
                base,
                np.linspace(200, 160, 15),
                np.linspace(160, 195, 15),
                np.linspace(195, 178, 10),
                np.linspace(178, 194, 10),
                np.linspace(194, 188, 5),
                np.linspace(188, 193, 5),
            ]
        )
        volume = np.concatenate(
            [
                np.linspace(8_000_000, 6_000_000, 140),
                np.linspace(6_000_000, 4_000_000, 30),
                np.linspace(3_500_000, 2_000_000, 20),
                np.linspace(1_500_000, 700_000, 10),
            ]
        )
        df = make_ohlcv(close, volume, spread=close * 0.008)

        result = analyze_vcp_v2(df)

        self.assertEqual(result["algorithm_version"], "experimental-v2")
        self.assertGreaterEqual(result["contraction_count"], 2)
        self.assertIn(result["quality_grade"], {"A", "B", "C", "D"})
        self.assertGreaterEqual(result["quality_score"], 0)
        self.assertLessEqual(result["quality_score"], 100)
        self.assertIn("atr_ratio_pct", result["volatility"])
        self.assertIn("volume_slope_pct", result["supply"])
        self.assertIn("volume_ratio", result["breakout_confirmation"])
        self.assertTrue(result["supply"]["is_volume_trending_down"])

    def test_adaptive_pivots_do_not_mutate_input(self):
        close = 50 + np.sin(np.arange(80) / 4) * 3
        df = make_ohlcv(close, np.full(80, 500_000.0))
        before = df.copy(deep=True)

        peaks, valleys, meta = find_adaptive_pivots(df)

        pd.testing.assert_frame_equal(df, before)
        self.assertGreater(len(peaks), 0)
        self.assertGreater(len(valleys), 0)
        self.assertGreaterEqual(meta["window"], 3)


if __name__ == "__main__":
    unittest.main()
