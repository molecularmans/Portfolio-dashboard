import sys
import pandas as pd
from datetime import datetime
from src.db.database import StockDB

def test_pipeline():
    print("1. Testing DB, Trendlines (Horizontal & Diagonal Points)...")
    db = StockDB()
    
    # 1) 수평선 추가
    line_id = db.add_horizontal_line("NVDA", "일봉", 130.0, color="#FFD700", label="기준 지지선")
    assert len(line_id) > 0

    # 2) 대각 추세선 추가
    now = datetime.now()
    diag_id = db.add_trendline_points("NVDA", "일봉", 120.0, now, 140.0, now, color="#00E5FF", label="상승 추세선")
    assert len(diag_id) > 0
    print("   [+] Added diagonal trendline.")

    # 3) 조회
    lines = db.get_trendlines("NVDA", "일봉")
    assert len(lines) >= 2
    print(f"   [+] Queried lines count: {len(lines)}")

    # 4) 삭제
    db.clear_all_trendlines("NVDA", "일봉")
    assert len(db.get_trendlines("NVDA", "일봉")) == 0
    print("   [+] Cleared all lines.")

    print("\n[SUCCESS] Trendlines pipeline with add_trendline_points passed 100%!")

if __name__ == "__main__":
    test_pipeline()
