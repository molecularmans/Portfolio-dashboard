import unittest

import pandas as pd

from src.indicators.integrated_assessment import build_integrated_assessment


class IntegratedAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({"close": [99.0] * 29 + [101.0], "volume": [100.0] * 29 + [150.0]})
        self.sr = {
            "breakout_type": "range",
            "status_badge": "박스권",
            "nearest_support": {"price": 95.0, "zone_low": 94.0},
            "nearest_resistance": {"price": 110.0, "zone_high": 111.0},
            "resistance_levels": [{"price": 110.0}],
        }
        self.patterns = {"primary_pattern": {
            "name": "이중 바닥", "type": "bullish", "neckline": 100.0,
            "stop_loss": 95.0, "target_price": 115.0, "is_breakout": True,
        }}
        self.vcp = {"vcp_status": "DEVELOPING", "status_badge": "수축 진행", "trend_template": {
            "is_stage_2": True, "pass_count": 9, "total_count": 10,
        }}
        self.v3 = {"regime": {"trend": "상승 추세", "volatility": "보통변동", "regime": "상승 추세 · 보통변동"}}

    def assess(self, **overrides):
        inputs = dict(df=self.df, sr=self.sr, patterns=self.patterns, vcp=self.vcp, v3=self.v3)
        inputs.update(overrides)
        return build_integrated_assessment(**inputs)

    def test_confirmed_bullish_setup_has_entry_stop_and_reward_risk(self):
        result = self.assess()
        self.assertEqual(result["verdict"], "조건 충족 · 확인 필요")
        self.assertEqual(result["entry"], 100.0)
        self.assertEqual(result["stop"], 95.0)
        self.assertGreater(result["reward_risk"], 2.0)

    def test_bearish_pattern_vetoes_long_entry_and_its_stop_is_not_reused(self):
        self.patterns["primary_pattern"] = {
            "name": "이중 천장", "type": "bearish", "neckline": 100.0,
            "stop_loss": 110.0, "target_price": 85.0, "is_breakout": True,
        }
        result = self.assess()
        self.assertEqual(result["verdict"], "신규 진입 보류")
        self.assertIn("[B] 하락 패턴이 우세", result["blockers"])
        self.assertNotEqual(result["stop"], 110.0)

    def test_no_structural_stop_does_not_qualify(self):
        self.sr["nearest_support"] = None
        self.patterns["primary_pattern"]["stop_loss"] = 0
        result = self.assess()
        self.assertEqual(result["verdict"], "신규 진입 보류")
        self.assertIsNone(result["stop"])

    def test_missing_d_cannot_receive_top_verdict(self):
        result = self.assess(v3=None)
        self.assertEqual(result["verdict"], "조건부 관찰")

    def test_downtrend_overrides_an_otherwise_confirmed_breakout(self):
        self.v3["regime"]["trend"] = "하락 추세"
        result = self.assess()
        self.assertEqual(result["verdict"], "신규 진입 보류")
        self.assertIn("[D] 하락 추세", result["blockers"])

    def test_wide_structural_stop_is_not_replaced_by_tighter_support(self):
        self.patterns["primary_pattern"]["stop_loss"] = 80.0
        result = self.assess()
        self.assertEqual(result["stop"], 80.0)
        self.assertEqual(result["verdict"], "신규 진입 보류")

    def test_v2_pattern_awaiting_atr_confirmation_is_only_observation(self):
        self.patterns["primary_pattern"].update({"price_confirmed": False, "is_breakout": False})
        result = self.assess()
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["verdict"], "조건부 관찰")


if __name__ == "__main__":
    unittest.main()
