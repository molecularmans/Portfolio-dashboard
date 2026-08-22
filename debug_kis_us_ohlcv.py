import sys
import json
import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

from src.api.kis_auth import KISAuth

def test_us_ohlcv_raw():
    auth = KISAuth()
    print("=" * 60)
    print("🔍 KIS 미국주식 시세 API (HHDFS76240000) 원인 정밀 분석")
    print("=" * 60)
    
    token = auth.get_access_token(1)
    if not token:
        print("❌ 토큰 발급 실패")
        return

    endpoint = f"{auth.base_url}/uapi/overseas-price/v1/quotations/dailyprice"
    headers = auth.get_common_headers(tr_id="HHDFS76240000", account_idx=1)
    
    test_tickers = [("GOOGL", "NAS"), ("MU", "NAS"), ("MRVL", "NAS"), ("HOOD", "NAS"), ("EME", "NYS"), ("BOTZ", "NAS")]
    
    for ticker, default_ex in test_tickers:
        print(f"\n[티커: {ticker}] 조회 테스트 중...")
        for excd in [default_ex, "NAS", "NYS", "AMS", "BAQ", "BAY", "BAA"]:
            params = {
                "AUTH": "",
                "EXCD": excd,
                "SYMB": ticker,
                "GUBN": "0",
                "BYMD": "",
                "MODP": "1",
            }
            try:
                res = requests.get(endpoint, headers=headers, params=params, timeout=5)
                data = res.json()
                rt_cd = data.get("rt_cd")
                msg_cd = data.get("msg_cd")
                msg1 = data.get("msg1")
                output2 = data.get("output2", [])
                
                if rt_cd == "0" and output2:
                    first = output2[0]
                    last = output2[-1]
                    print(f"  ✅ [성공] 거래소코드: {excd} | {len(output2)}건 수신!")
                    print(f"     최근일: {first.get('xymd')} | 종가: ${float(first.get('clos', 0)):,.2f} | 시가: ${float(first.get('open', 0)):,.2f}")
                    break
                else:
                    print(f"  ❌ [{excd}] 실패: rt_cd={rt_cd}, msg_cd={msg_cd}, msg={msg1}")
            except Exception as e:
                print(f"  ⚠️ 예외: {e}")

if __name__ == "__main__":
    test_us_ohlcv_raw()
