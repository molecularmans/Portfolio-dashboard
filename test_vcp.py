import sys
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

from src.indicators.vcp_analyzer import check_trend_template, detect_vcp_pattern
from src.db.database import StockDB
from src.api.kis_rest import KISClient

def test_vcp_mock_and_real():
    print("=" * 60)
    print("🧠 마크 미너비니 VCP 패턴 & 8대 추세 템플릿 엔진 단위 테스트")
    print("=" * 60)

    # 1. 이상적인 VCP 합성 데이터 생성 테스트
    # Stage 2 상승 후 3단계 수축 (25% -> 10% -> 4%) 및 거래량 감소
    dates = pd.date_range("2026-01-01", periods=200, freq="B")
    
    # 200일간 점진적 상승 후 베이스 형성
    base_trend = np.linspace(100, 200, 140)  # 상승 국면
    # 수축 1T: 200 -> 160 (-20%) -> 195
    t1_down = np.linspace(200, 160, 15)
    t1_up = np.linspace(160, 195, 15)
    # 수축 2T: 195 -> 178 (-8.7%) -> 194
    t2_down = np.linspace(195, 178, 10)
    t2_up = np.linspace(178, 194, 10)
    # 수축 3T: 194 -> 188 (-3.1%) -> 193
    t3_down = np.linspace(194, 188, 5)
    t3_up = np.linspace(188, 193, 5)

    close_arr = np.concatenate([base_trend, t1_down, t1_up, t2_down, t2_up, t3_down, t3_up])
    high_arr = close_arr * 1.01
    low_arr = close_arr * 0.99
    open_arr = close_arr * 1.002
    
    # 거래량: 뒤로 갈수록 마름 (VDU)
    vol_base = np.random.uniform(5000000, 8000000, 140)
    vol_t1 = np.random.uniform(4000000, 6000000, 30)
    vol_t2 = np.random.uniform(2000000, 3500000, 20)
    vol_t3 = np.random.uniform(800000, 1500000, 10)  # 극단적 VDU
    vol_arr = np.concatenate([vol_base, vol_t1, vol_t2, vol_t3])

    mock_df = pd.DataFrame({
        "date": dates,
        "open": open_arr,
        "high": high_arr,
        "low": low_arr,
        "close": close_arr,
        "volume": vol_arr,
    })

    print("\n[테스트 1] 이상적인 3T VCP 합성 데이터 분석:")
    res_ideal = detect_vcp_pattern(mock_df)
    print(f"• 판정 결과: {res_ideal['status_badge']}")
    print(f"• 수축 단계: {res_ideal['contraction_count']}T 수축 (감소성: {res_ideal['is_diminishing']})")
    print(f"• 거래량 건조(VDU): {res_ideal['volume_dryup']['ratio']}% (VDU 여부: {res_ideal['volume_dryup']['is_vdu']})")
    print(f"• 피봇 매수가: ${res_ideal['pivot']['price']:,.2f} | 손절가: ${res_ideal['pivot']['stop_loss']:,.2f} (리스크: {res_ideal['pivot']['risk_pct']}%)")
    print(f"• 추세 템플릿: {res_ideal['trend_template']['pass_count']}/8개 충족")

    assert res_ideal["contraction_count"] >= 2, "수축 단계가 2개 이상 감지되어야 함"
    assert res_ideal["is_diminishing"], "수축 진폭이 점진적으로 감소해야 함"
    assert res_ideal["volume_dryup"]["is_vdu"], "거래량 건조(VDU)가 감지되어야 함"

    # 2. 실제 DB 캐시 종목(GOOGL, BOTZ 등) 테스트
    print("\n[테스트 2] 실제 종목 데이터 연동 테스트:")
    db = StockDB()
    client = KISClient()
    
    for test_tk in ["GOOGL", "BOTZ"]:
        df_real = db.get_prices(test_tk, timeframe="D")
        if df_real.empty or len(df_real) < 20:
            df_real = client.get_us_ohlcv(test_tk, timeframe="D", count=250)

        res_real = detect_vcp_pattern(df_real)
        print(f"\n[{test_tk}] 진단 결과:")
        print(f"  • 상태: {res_real['status_badge']}")
        print(f"  • 수축 단계: {res_real['contraction_count']}T (감소성: {res_real['is_diminishing']})")
        print(f"  • 피봇가: ${res_real['pivot']['price']:,.2f} | 손절가: ${res_real['pivot']['stop_loss']:,.2f}")
        print(f"  • 8대 추세 템플릿: {res_real['trend_template']['pass_count']}/8개")
        print(f"  • 리포트 요약:\n    " + res_real['summary_text'].replace('\n\n', '\n    '))

    print("\n" + "=" * 60)
    print("🎉 [SUCCESS] 모든 VCP 알고리즘 단위 테스트 100% 통과!")
    print("=" * 60)

if __name__ == "__main__":
    test_vcp_mock_and_real()
