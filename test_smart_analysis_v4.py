"""Offline regression tests for the experimental smart-chart v4 engine."""

import unittest

import numpy as np
import pandas as pd

from src.indicators.smart_analysis_v4 import (
    analyze_momentum_confirmation,
    analyze_smart_chart_v4,
    analyze_trend_strength,
    analyze_volume_flow,
    walk_forward_v4_validation,
)


def make_ohlcv(close, volume=None, spread=0.8):
    close = np.asarray(close, dtype=float)
    if volume is None:
        volume = np.full(len(close), 1_000_000.0)
    volume = np.asarray(volume, dtype=float)
    opens = np.r_[close[0] * 0.999, close[:-1] * 1.001]
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=len(close), freq="B"),
            "open": opens,
            "high": np.maximum(opens, close) + spread,
            "low": np.minimum(opens, close) - spread,
            "close": close,
            "volume": volume,
        }
    )


class TestSmartAnalysisV4(unittest.TestCase):
    def test_momentum_has_rsi_stoch_and_divergence_fields(self):
        x = np.arange(150)
        close = 90 + x * 0.10 + np.sin(x / 5) * 3.0
        result = analyze_momentum_confirmation(make_ohlcv(close))

        self.assertTrue(result["is_valid"])
        self.assertGreaterEqual(result["rsi"], 0)
        self.assertLessEqual(result["rsi"], 100)
        self.assertGreaterEqual(result["stoch_rsi_k"], 0)
        self.assertLessEqual(result["stoch_rsi_k"], 100)
        self.assertIn("divergence", result)

    def test_volume_flow_detects_accumulation_bias(self):
        close = np.linspace(70, 115, 120) + np.sin(np.arange(120) / 5) * 0.4
        volume = np.linspace(800_000, 1_800_000, 120)
        result = analyze_volume_flow(make_ohlcv(close, volume))

        self.assertTrue(result["is_valid"])
        self.assertGreater(result["score"], 50)
        self.assertGreater(result["cmf_20"], -0.01)
        self.assertIn(result["state"], {"매집 우세", "중립"})

    def test_adx_dmi_and_supertrend_confirm_uptrend(self):
        close = np.linspace(65, 135, 160) + np.sin(np.arange(160) / 8) * 0.6
        result = analyze_trend_strength(make_ohlcv(close, spread=0.5))

        self.assertTrue(result["is_valid"])
        self.assertGreater(result["plus_di"], result["minus_di"])
        self.assertGreater(result["adx"], 18)
        self.assertGreater(result["supertrend_stop"], 0)
        self.assertLess(result["supertrend_stop"], close[-1])

    def test_walk_forward_is_no_lookahead_and_cost_aware(self):
        rng = np.random.default_rng(11)
        close = 100 + np.cumsum(rng.normal(0.05, 0.30, 230))
        volume = np.full(230, 1_000_000.0)
        result = walk_forward_v4_validation(make_ohlcv(close, volume))

        self.assertTrue(result["no_lookahead"])
        self.assertEqual(result["cost_pct"], 0.20)
        self.assertIn("confirmation_rule", result)
        self.assertGreaterEqual(result["hit_rate_pct"], 0)
        self.assertLessEqual(result["hit_rate_pct"], 100)

    def test_bundle_schema_comparison_and_score_bounds(self):
        x = np.arange(210)
        close = 80 + x * 0.16 + np.sin(x / 7) * 2.2
        result = analyze_smart_chart_v4(make_ohlcv(close))

        self.assertEqual(result["algorithm_version"], "experimental-v4")
        self.assertTrue(result["research_only"])
        for key in (
            "support_resistance",
            "patterns",
            "vcp",
            "momentum",
            "volume_flow",
            "trend_strength",
            "validation",
            "comparison",
            "risk_control",
            "v3_baseline",
        ):
            self.assertIn(key, result)
        self.assertEqual(set(result["comparison"]), {"v3", "v4", "cost_pct", "comparable"})
        self.assertGreaterEqual(result["composite_score"], 0)
        self.assertLessEqual(result["composite_score"], 100)
        self.assertIn(result["grade"], {"A", "B", "C", "D"})


if __name__ == "__main__":
    unittest.main()
