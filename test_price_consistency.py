import unittest
from unittest.mock import Mock, patch
import os
import tempfile
import gc

import pandas as pd

from app import load_and_calc_stock_data
from src.api.kis_rest import KISClient, looks_like_mock_ohlcv
from src.indicators.technicals import calc_indicators
from src.db.database import StockDB
from src.ui.charts import create_detail_chart
from src.ui.pattern_view import _stop_scenario_text


class PriceConsistencyTests(unittest.TestCase):
    def test_no_entry_with_structural_stop_has_readable_scenario(self):
        text = _stop_scenario_text({"stop": 162.43, "stop_source": "[A] 지지선", "risk_pct": None}, "$")
        self.assertIn("$162.43", text)
        self.assertIn("진입 기준 가격이 없어", text)

    def test_legacy_demo_cache_is_detected(self):
        client = KISClient()
        demo = client._generate_mock_ohlcv("TWST", count=300)
        self.assertTrue(looks_like_mock_ohlcv(demo, "TWST", "D"))
        real = demo.copy()
        real["close"] = 205.0
        self.assertFalse(looks_like_mock_ohlcv(real, "TWST", "D"))
        mixed = demo.copy()
        mixed.loc[mixed.index[-50:], "close"] = 205.0
        self.assertTrue(looks_like_mock_ohlcv(mixed, "TWST", "D"))

    def test_configured_kis_failure_does_not_invent_prices(self):
        auth = Mock(is_configured=True, base_url="https://example.test")
        auth.get_common_headers.return_value = {}
        client = KISClient(auth=auth)
        with patch("src.api.kis_rest.requests.get", side_effect=TimeoutError):
            self.assertTrue(client.get_us_ohlcv("TWST", count=20).empty)
            self.assertTrue(client.get_kr_ohlcv("005930", count=20).empty)

    def test_exchange_lookup_prefers_newer_bars_over_old_preferred_listing(self):
        auth = Mock(is_configured=True, base_url="https://example.test")
        auth.get_common_headers.return_value = {}
        client = KISClient(auth=auth)
        today = pd.Timestamp.now().normalize()

        def reply(*_args, **kwargs):
            exchange = kwargs["params"]["EXCD"]
            end = today - pd.Timedelta(days=100) if exchange == "NYS" else today
            rows = [
                {"xymd": day.strftime("%Y%m%d"), "open": "100", "high": "101",
                 "low": "99", "clos": "100", "tvol": "1000"}
                for day in pd.bdate_range(end=end, periods=5)[::-1]
            ]
            return Mock(status_code=200, json=lambda: {"rt_cd": "0", "output2": rows})

        with patch("src.api.kis_rest.requests.get", side_effect=reply):
            result = client.get_us_ohlcv("EME", count=5)
        latest_business_day = pd.bdate_range(end=today, periods=1)[-1]
        self.assertEqual(pd.Timestamp(result["date"].iloc[-1]).normalize(), latest_business_day)

    def test_old_demo_cache_is_replaced_by_real_history(self):
        demo = KISClient()._generate_mock_ohlcv("TWST", count=300)
        real = demo.tail(30).copy()
        real["close"] = 205.0
        db = Mock()
        db.get_prices.return_value = demo
        client = Mock()
        client.is_configured.return_value = True
        client.get_us_ohlcv.return_value = real
        result = load_and_calc_stock_data("TWST", db, client)
        db.delete_prices.assert_called_once_with("TWST", "D")
        db.save_prices.assert_called_once()
        self.assertEqual(result["close"].iloc[-1], 205.0)

    def test_failed_refresh_keeps_real_cached_bars(self):
        cached = KISClient()._generate_mock_ohlcv("TWST", count=30)
        cached["close"] = 205.0
        db = Mock()
        db.get_prices.return_value = cached
        client = Mock()
        client.is_configured.return_value = True
        client.get_us_ohlcv.return_value = pd.DataFrame()
        result = load_and_calc_stock_data("TWST", db, client, force_refresh=True)
        self.assertEqual(result["close"].iloc[-1], 205.0)
        db.save_prices.assert_not_called()

    def test_new_download_replaces_old_bars_in_cache(self):
        demo = KISClient()._generate_mock_ohlcv("TWST", count=300)
        real = demo.tail(30).copy()
        real["close"] = 205.0
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(StockDB, "_initial_restore_fast"):
                db = StockDB(db_path=os.path.join(directory, "test.db"))
            db.save_prices("TWST", "D", demo)
            db.save_prices("TWST", "D", real)
            cached = db.get_prices("TWST", "D")
            gc.collect()  # sqlite3 context managers commit but do not close on Windows.
        self.assertEqual(len(cached), 30)
        self.assertEqual(cached["close"].iloc[-1], 205.0)

    def test_chart_overlays_use_same_full_history_as_analysis(self):
        dates = pd.bdate_range("2025-01-01", periods=300)
        raw = pd.DataFrame({
            "date": dates, "open": [100.0] * 300, "high": [101.0] * 300,
            "low": [99.0] * 300, "close": [100.0] * 299 + [105.0],
            "volume": [1000.0] * 300,
        })
        source = calc_indicators(raw)
        sr = {
            "is_valid": True, "nearest_support": None, "nearest_resistance": None,
            "upper_trendline": {"start_idx": 100, "slope": 0.1, "intercept": 70.1, "current_price": 100.0},
            "lower_trendline": None,
        }
        bundle = {"v3_baseline": {"support_resistance": sr, "patterns": {"has_pattern": False}},
                  "trend_strength": {"supertrend_stop": 0}}
        with patch("src.ui.charts.analyze_smart_chart_v4", return_value=bundle) as analyzer:
            fig = create_detail_chart(source, "TWST", {"timeframe": "일봉", "smart_analysis_engine": "v4"})
        self.assertEqual(len(analyzer.call_args.args[0]), 300)
        self.assertEqual(float(fig.data[0].close[-1]), 105.0)
        line = next(trace for trace in fig.data if trace.name == "저항 추세선 ($100.00)")
        self.assertEqual(float(line.y[-1]), 100.0)


if __name__ == "__main__":
    unittest.main()
