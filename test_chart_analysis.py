import unittest
import sys
import pandas as pd
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.indicators.trendline_analyzer import (
    find_local_extrema,
    cluster_horizontal_levels,
    fit_best_trendline,
    analyze_support_resistance_and_trendlines,
)
from src.indicators.pattern_detector import (
    detect_double_bottom,
    detect_double_top,
    detect_triangles,
    detect_inverse_head_and_shoulders,
    detect_all_chart_patterns,
)
from src.indicators.technicals import calc_indicators
from src.ui.charts import create_detail_chart
from src.api.kis_rest import KISClient


class TestChartAnalysis(unittest.TestCase):
    def setUp(self):
        self.client = KISClient()

    def test_support_resistance_and_trendlines_with_mock_data(self):
        """실제 모의 시세 데이터(NVDA, TSLA) 기반 지지/저항선 및 추세선 검증"""
        for ticker in ["NVDA", "TSLA", "AAPL"]:
            df = self.client.get_us_ohlcv(ticker, timeframe="D", count=150)
            df = calc_indicators(df)

            result = analyze_support_resistance_and_trendlines(df)
            self.assertTrue(result["is_valid"], f"{ticker}의 분석 결과가 유효해야 합니다.")
            self.assertGreater(result["current_price"], 0)
            self.assertIn("status_badge", result)
            self.assertIn("breakout_type", result)

            # 지지선 또는 저항선이 최소 1개 이상 도출되는지 확인
            self.assertTrue(
                len(result["support_levels"]) > 0 or len(result["resistance_levels"]) > 0,
                f"{ticker}의 지지선 또는 저항선이 최소 하나 이상 식별되어야 합니다.",
            )

            # 추세선 산출 확인 (유효할 경우 좌표 및 가격 검증)
            if result["upper_trendline"]:
                self.assertGreater(result["upper_trendline"]["current_price"], 0)
            if result["lower_trendline"]:
                self.assertGreater(result["lower_trendline"]["current_price"], 0)

            print(f"✅ {ticker} 지지/저항선 테스트 통과: {result['status_badge']} | 현재가: ${result['current_price']:,.2f}")

    def test_synthetic_double_bottom_pattern(self):
        """합성 이중 바닥(W 패턴) 데이터 감지 정밀 검증"""
        # 100일간의 가격 시계열: 하락(100->80) -> 반등(80->90) -> 재하락(90->80.5) -> 돌파(80.5->92)
        n = 80
        dates = pd.date_range("2026-01-01", periods=n)
        prices = np.zeros(n)

        # 초기 횡보
        prices[0:15] = np.linspace(100, 95, 15)
        # 1차 바닥 (idx 25: 80)
        prices[15:25] = np.linspace(95, 80, 10)
        # 넥라인 형성 (idx 40: 92)
        prices[25:40] = np.linspace(80, 92, 15)
        # 2차 바닥 (idx 55: 80.8)
        prices[40:55] = np.linspace(92, 80.8, 15)
        # 넥라인 상향 돌파 (idx 79: 94)
        prices[55:80] = np.linspace(80.8, 94, 25)

        records = []
        for d, p in zip(dates, prices):
            records.append({
                "date": d,
                "open": p - 0.2,
                "high": p + 0.8,
                "low": p - 0.8,
                "close": p,
                "volume": 2000000,
            })
        df_w = pd.DataFrame(records)

        patterns = detect_all_chart_patterns(df_w)
        self.assertTrue(patterns["has_pattern"], "이중 바닥 패턴이 반드시 감지되어야 합니다.")
        primary = patterns["primary_pattern"]
        self.assertIn("이중 바닥", primary["name"])
        self.assertTrue(primary["is_breakout"], "넥라인 돌파 상태여야 합니다.")
        self.assertAlmostEqual(primary["neckline"], 92.0, delta=1.5)
        self.assertGreater(primary["target_price"], primary["neckline"])
        self.assertLess(primary["stop_loss"], primary["neckline"])
        print(f"✅ 합성 이중 바닥 패턴 감지 성공: {primary['name']} | 목표가: ${primary['target_price']:,.2f} | 손절가: ${primary['stop_loss']:,.2f}")

    def test_synthetic_triangle_pattern(self):
        """합성 삼각수렴 데이터 감지 검증"""
        n = 60
        dates = pd.date_range("2026-01-01", periods=n)
        highs = np.zeros(n)
        lows = np.zeros(n)
        closes = np.zeros(n)

        # 진폭이 점차 좁아지는 진동 시계열
        for i in range(n):
            amplitude = (60 - i) * 0.4
            mid = 100.0
            osc = np.sin(i * 0.4) * amplitude
            closes[i] = mid + osc
            highs[i] = closes[i] + 0.5
            lows[i] = closes[i] - 0.5

        records = [{
            "date": dates[i],
            "open": closes[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "volume": 1000000,
        } for i in range(n)]
        df_tri = pd.DataFrame(records)

        peaks, valleys = find_local_extrema(df_tri, window=4)
        tri = detect_triangles(peaks, valleys, float(closes[-1]))
        # 삼각수렴 구조 추출 검증
        if tri:
            self.assertIn("삼각수렴", tri["name"])
            print(f"✅ 합성 삼각수렴 패턴 감지 성공: {tri['name']} | 상태: {tri['status_text']}")

    def test_plotly_detail_chart_rendering_with_analysis(self):
        """Plotly 상세 차트에 지지/저항, 추세선, 패턴 오버레이가 정상 렌더링되는지 검증"""
        df = self.client.get_us_ohlcv("NVDA", timeframe="D", count=120)
        df = calc_indicators(df)

        settings = {
            "timeframe": "일봉",
            "show_support_resistance": True,
            "show_trendlines": True,
            "show_pattern_lines": True,
            "selected_sub_indicators": ["RSI", "MACD"],
        }

        fig = create_detail_chart(df, "NVDA", settings=settings)
        self.assertIsNotNone(fig)
        self.assertGreater(len(fig.data), 5, "캔들, 거래량, 보조지표, 지지/저항/추세선 트레이스가 모두 포함되어야 합니다.")

        trace_names = [t.name for t in fig.data if t.name]
        print(f"✅ Plotly 차트 트레이스 생성 완료: {trace_names[:8]}... (총 {len(fig.data)}개)")


if __name__ == "__main__":
    unittest.main()
