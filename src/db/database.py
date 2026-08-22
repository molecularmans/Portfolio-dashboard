import os
import uuid
import json
import sqlite3
import pandas as pd
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DB_PATH = os.path.join(DB_DIR, "stock_cache.db")

DEFAULT_MA_FLAGS = {
    "show_ema5": True,
    "show_ma10": False,
    "show_ma20": True,
    "show_ma30": False,
    "show_ma50": True,
    "show_ma150": False,
    "show_ma200": True,
}


class StockDB:
    """SQLite 기반 초경량 로컬 캐시 및 설정 데이터베이스 (설정 영구 저장 지원)"""

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_tables()

    def _get_connection(self):
        con = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def _init_tables(self):
        """기본 테이블 스키마 초기화"""
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stock_prices (
                    ticker TEXT,
                    timeframe TEXT,
                    date TIMESTAMP,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    updated_at TIMESTAMP,
                    PRIMARY KEY (ticker, timeframe, date)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS custom_groups (
                    group_name TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    ticker TEXT PRIMARY KEY,
                    name TEXT,
                    group_name TEXT DEFAULT '빅테크/AI',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS trendlines (
                    id TEXT PRIMARY KEY,
                    ticker TEXT,
                    timeframe TEXT,
                    line_type TEXT,
                    price1 REAL,
                    date1 TIMESTAMP,
                    price2 REAL,
                    date2 TIMESTAMP,
                    color TEXT,
                    label TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 기본 그룹 데이터 초기화
            cur.execute("SELECT COUNT(*) FROM custom_groups")
            grp_count = cur.fetchone()[0]
            if grp_count == 0:
                cur.execute("INSERT OR IGNORE INTO custom_groups (group_name) VALUES ('빅테크/AI')")
                cur.execute("INSERT OR IGNORE INTO custom_groups (group_name) VALUES ('반도체')")
                cur.execute("INSERT OR IGNORE INTO custom_groups (group_name) VALUES ('클라우드/SaaS')")

            # 기본 관심종목 데이터 초기화
            cur.execute("SELECT COUNT(*) FROM watchlist")
            count = cur.fetchone()[0]
            if count == 0:
                default_items = [
                    ("NVDA", "NVIDIA", "빅테크/AI"),
                    ("AAPL", "Apple", "빅테크/AI"),
                    ("MSFT", "Microsoft", "빅테크/AI"),
                    ("GOOGL", "Alphabet", "빅테크/AI"),
                    ("AMZN", "Amazon", "빅테크/AI"),
                    ("TSLA", "Tesla", "빅테크/AI"),
                    ("BOTZ", "Global X Robotics & AI", "빅테크/AI"),
                    ("ORCL", "Oracle", "클라우드/SaaS"),
                    ("MRVL", "Marvell Tech", "반도체"),
                ]
                cur.executemany(
                    "INSERT OR IGNORE INTO watchlist (ticker, name, group_name) VALUES (?, ?, ?)",
                    default_items,
                )
            con.commit()

    # ==========================================
    # 이동평균선 선택 설정 영구 저장
    # ==========================================
    def get_ma_settings(self) -> dict:
        """저장된 이동평균선 설정 로드"""
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT value FROM user_settings WHERE key = 'ma_flags'")
            row = cur.fetchone()
            if row and row[0]:
                try:
                    loaded = json.loads(row[0])
                    merged = DEFAULT_MA_FLAGS.copy()
                    merged.update(loaded)
                    return merged
                except Exception:
                    pass
        return DEFAULT_MA_FLAGS.copy()

    def save_ma_settings(self, ma_flags: dict):
        """이동평균선 선택 설정 영구 저장"""
        val_str = json.dumps(ma_flags)
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO user_settings (key, value, updated_at)
                VALUES ('ma_flags', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, [val_str])
            con.commit()

    # ==========================================
    # 영구 추세선 / 지지·저항선 CRUD
    # ==========================================
    def get_trendlines(self, ticker: str, timeframe: str = "일봉") -> list:
        with self._get_connection() as con:
            df = pd.read_sql_query("""
                SELECT id, ticker, timeframe, line_type, price1, date1, price2, date2, color, label 
                FROM trendlines 
                WHERE ticker = ? AND (timeframe = ? OR timeframe = 'ALL')
                ORDER BY created_at ASC
            """, con, params=[ticker.upper().strip(), timeframe])
            return df.to_dict(orient="records")

    def add_horizontal_line(self, ticker: str, timeframe: str, price: float, color: str = "#FFD700", label: str = "지지/저항선") -> str:
        line_id = str(uuid.uuid4())[:8]
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO trendlines (id, ticker, timeframe, line_type, price1, color, label)
                VALUES (?, ?, ?, 'horizontal', ?, ?, ?)
            """, [line_id, ticker.upper().strip(), timeframe, float(price), color, label])
            con.commit()
        return line_id

    def add_trendline_points(self, ticker: str, timeframe: str, price1: float, date1, price2: float, date2, color: str = "#00E5FF", label: str = "추세선") -> str:
        line_id = str(uuid.uuid4())[:8]
        with self._get_connection() as con:
            cur = con.cursor()
            d1_str = str(date1)[:19] if date1 else None
            d2_str = str(date2)[:19] if date2 else None
            cur.execute("""
                INSERT INTO trendlines (id, ticker, timeframe, line_type, price1, date1, price2, date2, color, label)
                VALUES (?, ?, ?, 'trendline', ?, ?, ?, ?, ?, ?)
            """, [line_id, ticker.upper().strip(), timeframe, float(price1), d1_str, float(price2), d2_str, color, label])
            con.commit()
        return line_id

    def duplicate_trendline(self, line_id: str, offset_pct: float = 0.0) -> str:
        new_id = str(uuid.uuid4())[:8]
        with self._get_connection() as con:
            item = pd.read_sql_query("SELECT * FROM trendlines WHERE id = ?", con, params=[line_id])
            if item.empty:
                return ""
            row = item.iloc[0]
            mult = 1.0 + (offset_pct / 100.0)
            p1 = float(row["price1"]) * mult if pd.notna(row["price1"]) else None
            p2 = float(row["price2"]) * mult if pd.notna(row["price2"]) else None
            new_label = f"{row['label']} (복사)"

            cur = con.cursor()
            cur.execute("""
                INSERT INTO trendlines (id, ticker, timeframe, line_type, price1, date1, price2, date2, color, label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [new_id, row["ticker"], row["timeframe"], row["line_type"], p1, row["date1"], p2, row["date2"], row["color"], new_label])
            con.commit()
        return new_id

    def update_trendline_price(self, line_id: str, price_delta: float):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                UPDATE trendlines 
                SET price1 = price1 + ?, 
                    price2 = CASE WHEN price2 IS NOT NULL THEN price2 + ? ELSE NULL END
                WHERE id = ?
            """, [price_delta, price_delta, line_id])
            con.commit()

    def delete_trendline(self, line_id: str):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM trendlines WHERE id = ?", [line_id])
            con.commit()

    def clear_all_trendlines(self, ticker: str, timeframe: str = None):
        with self._get_connection() as con:
            cur = con.cursor()
            if timeframe:
                cur.execute("DELETE FROM trendlines WHERE ticker = ? AND timeframe = ?", [ticker.upper().strip(), timeframe])
            else:
                cur.execute("DELETE FROM trendlines WHERE ticker = ?", [ticker.upper().strip()])
            con.commit()

    # ==========================================
    # 그룹 관리 CRUD
    # ==========================================
    def get_groups(self) -> list:
        with self._get_connection() as con:
            df = pd.read_sql_query("SELECT group_name FROM custom_groups ORDER BY created_at ASC", con)
            return df["group_name"].tolist() if not df.empty else ["빅테크/AI", "반도체", "클라우드/SaaS"]

    def add_group(self, group_name: str):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("INSERT OR IGNORE INTO custom_groups (group_name) VALUES (?)", [group_name.strip()])
            con.commit()

    def rename_group(self, old_name: str, new_name: str):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("UPDATE custom_groups SET group_name = ? WHERE group_name = ?", [new_name.strip(), old_name.strip()])
            cur.execute("UPDATE watchlist SET group_name = ? WHERE group_name = ?", [new_name.strip(), old_name.strip()])
            con.commit()

    def delete_group(self, group_name: str, fallback_group: str = "빅테크/AI"):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("UPDATE watchlist SET group_name = ? WHERE group_name = ?", [fallback_group, group_name.strip()])
            cur.execute("DELETE FROM custom_groups WHERE group_name = ?", [group_name.strip()])
            con.commit()

    # ==========================================
    # 관심종목 CRUD
    # ==========================================
    def get_watchlist(self, group_name: str = None) -> pd.DataFrame:
        with self._get_connection() as con:
            if group_name and group_name != "전체 관심종목":
                return pd.read_sql_query("SELECT * FROM watchlist WHERE group_name = ? ORDER BY created_at ASC", con, params=[group_name])
            return pd.read_sql_query("SELECT * FROM watchlist ORDER BY group_name, created_at ASC", con)

    def add_watchlist_item(self, ticker: str, name: str = "", group_name: str = "빅테크/AI"):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO watchlist (ticker, name, group_name) 
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET group_name = excluded.group_name
            """, [ticker.upper().strip(), name, group_name])
            con.commit()

    def remove_watchlist_item(self, ticker: str):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM watchlist WHERE ticker = ?", [ticker.upper().strip()])
            con.commit()

    # ==========================================
    # 주가 데이터 캐시
    # ==========================================
    def save_prices(self, ticker: str, timeframe: str, df: pd.DataFrame):
        if df.empty:
            return

        ticker = ticker.upper().strip()
        timeframe = timeframe.upper().strip()

        with self._get_connection() as con:
            cur = con.cursor()
            for _, row in df.iterrows():
                d_val = row["date"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(row["date"], (pd.Timestamp, datetime)) else str(row["date"])
                cur.execute("""
                    INSERT INTO stock_prices (ticker, timeframe, date, open, high, low, close, volume, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(ticker, timeframe, date) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        volume = excluded.volume,
                        updated_at = CURRENT_TIMESTAMP
                """, [
                    ticker,
                    timeframe,
                    d_val,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["volume"]),
                ])
            con.commit()

    def clear_all_prices(self):
        """과거 시세 캐시 일괄 초기화"""
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM stock_prices")
            con.commit()

    def get_prices(self, ticker: str, timeframe: str = "D", limit: int = 500) -> pd.DataFrame:
        ticker = ticker.upper().strip()
        timeframe = timeframe.upper().strip()

        with self._get_connection() as con:
            df = pd.read_sql_query("""
                SELECT date, open, high, low, close, volume 
                FROM stock_prices 
                WHERE ticker = ? AND timeframe = ?
                ORDER BY date ASC
            """, con, params=[ticker, timeframe])

            if not df.empty:
                df["date"] = pd.to_datetime(df["date"])
                return df.tail(limit).reset_index(drop=True)
            return pd.DataFrame()
