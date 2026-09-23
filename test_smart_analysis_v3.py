"""Offline regression tests for the experimental smart-chart v3 engine."""

import unittest

import numpy as np
import pandas as pd

from src.indicators.smart_analysis_v3 import (
    analyze_candlestick_patterns,
    analyze_market_regime,
    analyze_smart_chart_v3,
    analyze_volatility_squeeze,
    walk_forward_breakout_validation,
)


def make_ohlcv(close, volume=None, spread=0.7, open_values=None):
    close = np.asarray(close, dtype=float)
    if volume is None:
        volume = np.full(len(close), 1_000_000.0)
    volume = np.asarray(volume, dtype=float)
    opens = np.asarray(open_values, dtype=float) if open_values is not None else close * 0.999
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


class TestSmartAnalysisV3(unittest.TestCase):
    def test_bullish_engulfing_uses_context_and_volume(self):
        close = np.linspace(110, 100, 28).tolist() + [97.0, 101.5]
        opens = np.asarray(close) * 1.001
        opens[-2] = 100.0
        opens[-1] = 96.5
        volume = np.full(30, 1_000_000.0)
        volume[-1] = 1_600_000.0

        result = analyze_candlestick_patterns(make_ohlcv(close, volume, open_values=opens))

        names = [signal["name"] for signal in result["signals"]]
        self.assertIn("상승 장악형", names)
        engulfing = next(signal for signal in result["signals"] if signal["name"] == "상승 장악형")
        self.assertTrue(engulfing["context_confirmed"])
        self.assertGreaterEqual(engulfing["volume_ratio"], 1.25)

    def test_bollinger_keltner_squeeze_detects_low_volatility(self):
        x = np.arange(100)
        close = 100 + np.sin(x / 3) * 0.04
        df = make_ohlcv(close, spread=0.9)

        result = analyze_volatility_squeeze(df)

        self.assertTrue(result["is_valid"])
        self.assertTrue(result["squeeze_on"])
        self.assertGreater(result["squeeze_count"], 0)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_regime_detects_piecewise_uptrend(self):
        flat = 100 + np.sin(np.arange(90) / 5) * 0.4
        rising = np.linspace(100, 145, 70) + np.sin(np.arange(70) / 4) * 0.3
        result = analyze_market_regime(make_ohlcv(np.concatenate([flat, rising])))

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["trend"], "상승 추세")
        self.assertGreater(result["slope_pct_per_bar"], 0)
        self.assertTrue(result["change_points"])

    def test_walk_forward_output_is_explicitly_no_lookahead(self):
        rng = np.random.default_rng(7)
        close = 100 + np.cumsum(rng.normal(0.06, 0.35, 220))
        volume = np.full(220, 1_000_000.0)
        for idx in (80, 125, 170):
            close[idx] = np.max(close[idx - 20 : idx]) + 2.0
            close[idx + 1 : idx + 11] = np.linspace(close[idx] + 0.2, close[idx] + 4.0, 10)
            volume[idx] = 1_700_000.0
        result = walk_forward_breakout_validation(make_ohlcv(close, volume))

        self.assertTrue(result["no_lookahead"])
        self.assertGreaterEqual(result["sample_count"], 0)
        self.assertIn("warning", result)
        self.assertGreaterEqual(result["hit_rate_pct"], 0)
        self.assertLessEqual(result["hit_rate_pct"], 100)

    def test_bundle_schema_and_score_bounds(self):
        x = np.arange(190)
        close = 80 + x * 0.15 + np.sin(x / 7) * 2.5
        result = analyze_smart_chart_v3(make_ohlcv(close))

        self.assertEqual(result["algorithm_version"], "experimental-v3")
        self.assertTrue(result["research_only"])
        for key in ("support_resistance", "patterns", "vcp", "candlesticks", "squeeze", "regime", "validation"):
            self.assertIn(key, result)
        self.assertGreaterEqual(result["composite_score"], 0)
        self.assertLessEqual(result["composite_score"], 100)
        self.assertIn(result["grade"], {"A", "B", "C", "D"})


if __name__ == "__main__":
    unittest.main()
