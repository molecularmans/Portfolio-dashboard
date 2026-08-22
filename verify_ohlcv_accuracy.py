import sys
import json
import requests
from dotenv import load_dotenv
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

from src.api.kis_auth import KISAuth
from src.api.kis_rest import KISClient

def test_all_portfolio_ohlcv():
    auth = KISAuth()
    client = KISClient(auth)
    
    print("=" * 60)
    print("🔍 내 포트폴리오 실제 종목별 KIS 시세 정확성 정밀 검증")
    print("=" * 60)
    
    portfolio = client.get_combined_balance()
    print(f"총 {len(portfolio)}개 보유 종목 발견\n")
    
    for item in portfolio:
        ticker = item["ticker"]
        cur_p = item["current_price"]
        pl_rt = item["profit_rate"]
        
        df = client.get_us_ohlcv(ticker, timeframe="D", count=5)
        if not df.empty:
            latest = df.iloc[-1]
            last_date = latest["date"].strftime("%Y-%m-%d")
            chart_close = latest["close"]
            diff = abs(cur_p - chart_close)
            status = "✅ 일치" if diff < (cur_p * 0.05) else f"⚠️ 차이큼 (잔고: ${cur_p:,.2f} vs 차트: ${chart_close:,.2f})"
            print(f"• [{ticker}] 잔고가: ${cur_p:,.2f} ({pl_rt:+.2f}%) | 차트종가({last_date}): ${chart_close:,.2f} -> {status}")
        else:
            print(f"• [{ticker}] ❌ 시세 수집 실패")

if __name__ == "__main__":
    test_all_portfolio_ohlcv()
