import os
import uuid
import duckdb
import pandas as pd
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DB_PATH = os.path.join(DB_DIR, "stock_cache.duckdb")


class StockDB:
    """DuckDB 로컬 캐시 데이터베이스 관리자 (추세선 복사, 이동, 삭제, 전체 지우기 완벽 지원)"""

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_tables()

    def _get_connection(self):
        return duckdb.connect(self.db_path)

    def _init_tables(self):
        """기본 테이블 스키마 초기화"""
        with self._get_connection() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS stock_prices (
                    ticker VARCHAR,
                    timeframe VARCHAR,
                    date TIMESTAMP,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume DOUBLE,
                    updated_at TIMESTAMP,
                    PRIMARY KEY (ticker, timeframe, date)
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS custom_groups (
                    group_name VARCHAR PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    ticker VARCHAR PRIMARY KEY,
                    name VARCHAR,
                    group_name VARCHAR DEFAULT '빅테크/AI',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS trendlines (
                    id VARCHAR PRIMARY KEY,
                    ticker VARCHAR,
                    timeframe VARCHAR,
                    line_type VARCHAR,
                    price1 DOUBLE,
                    date1 TIMESTAMP,
                    price2 DOUBLE,
                    date2 TIMESTAMP,
                    color VARCHAR DEFAULT '#FFD700',
                    label VARCHAR DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            grp_count = con.execute("SELECT COUNT(*) FROM custom_groups").fetchone()[0]
            if grp_count == 0:
                con.execute("INSERT OR IGNORE INTO custom_groups VALUES ('빅테크/AI', CURRENT_TIMESTAMP)")
                con.execute("INSERT OR IGNORE INTO custom_groups VALUES ('반도체', CURRENT_TIMESTAMP)")
                con.execute("INSERT OR IGNORE INTO custom_groups VALUES ('클라우드/SaaS', CURRENT_TIMESTAMP)")

            count = con.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
            if count == 0:
                default_items = [
                    ("NVDA", "NVIDIA", "빅테크/AI"),
                    ("AAPL", "Apple", "빅테크/AI"),
                    ("MSFT", "Microsoft", "빅테크/AI"),
                    ("GOOGL", "Alphabet", "빅테크/AI"),
                    ("AMZN", "Amazon", "빅테크/AI"),
                    ("TSLA", "Tesla", "빅테크/AI"),
                    ("ORCL", "Oracle", "클라우드/SaaS"),
                    ("MRVL", "Marvell Tech", "반도체"),
                ]
                con.executemany(
                    "INSERT OR IGNORE INTO watchlist (ticker, name, group_name) VALUES (?, ?, ?)",
                    default_items,
                )

    # ==========================================
    # 영구 추세선 / 지지·저항선 CRUD & 복사/이동/전체삭제
    # ==========================================
    def get_trendlines(self, ticker: str, timeframe: str = "일봉") -> list:
        with self._get_connection() as con:
            df = con.execute("""
                SELECT id, ticker, timeframe, line_type, price1, date1, price2, date2, color, label 
                FROM trendlines 
                WHERE ticker = ? AND (timeframe = ? OR timeframe = 'ALL')
                ORDER BY created_at ASC
            """, [ticker.upper().strip(), timeframe]).df()
            return df.to_dict(orient="records")

    def add_horizontal_line(self, ticker: str, timeframe: str, price: float, color: str = "#FFD700", label: str = "지지/저항선") -> str:
        line_id = str(uuid.uuid4())[:8]
        with self._get_connection() as con:
            con.execute("""
                INSERT INTO trendlines (id, ticker, timeframe, line_type, price1, color, label)
                VALUES (?, ?, ?, 'horizontal', ?, ?, ?)
            """, [line_id, ticker.upper().strip(), timeframe, float(price), color, label])
        return line_id

    def add_trendline_points(self, ticker: str, timeframe: str, price1: float, date1, price2: float, date2, color: str = "#00E5FF", label: str = "추세선") -> str:
        """2개 기준점 대각 추세선 추가"""
        line_id = str(uuid.uuid4())[:8]
        with self._get_connection() as con:
            con.execute("""
                INSERT INTO trendlines (id, ticker, timeframe, line_type, price1, date1, price2, date2, color, label)
                VALUES (?, ?, ?, 'trendline', ?, ?, ?, ?, ?, ?)
            """, [line_id, ticker.upper().strip(), timeframe, float(price1), date1, float(price2), date2, color, label])
        return line_id

    def duplicate_trendline(self, line_id: str, offset_pct: float = 0.0) -> str:
        """기존 선을 복사하여 평행선/신규선 생성"""
        new_id = str(uuid.uuid4())[:8]
        with self._get_connection() as con:
            item = con.execute("SELECT * FROM trendlines WHERE id = ?", [line_id]).df()
            if item.empty:
                return ""
            row = item.iloc[0]
            mult = 1.0 + (offset_pct / 100.0)
            p1 = float(row["price1"]) * mult if pd.notna(row["price1"]) else None
            p2 = float(row["price2"]) * mult if pd.notna(row["price2"]) else None
            new_label = f"{row['label']} (복사)"

            con.execute("""
                INSERT INTO trendlines (id, ticker, timeframe, line_type, price1, date1, price2, date2, color, label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [new_id, row["ticker"], row["timeframe"], row["line_type"], p1, row["date1"], p2, row["date2"], row["color"], new_label])
        return new_id

    def update_trendline_price(self, line_id: str, price_delta: float):
        """선의 가격을 위/아래로 이동"""
        with self._get_connection() as con:
            con.execute("""
                UPDATE trendlines 
                SET price1 = price1 + ?, 
                    price2 = CASE WHEN price2 IS NOT NULL THEN price2 + ? ELSE NULL END
                WHERE id = ?
            """, [price_delta, price_delta, line_id])

    def delete_trendline(self, line_id: str):
        with self._get_connection() as con:
            con.execute("DELETE FROM trendlines WHERE id = ?", [line_id])

    def clear_all_trendlines(self, ticker: str, timeframe: str = None):
        """특정 종목의 모든 추세선 일괄 삭제"""
        with self._get_connection() as con:
            if timeframe:
                con.execute("DELETE FROM trendlines WHERE ticker = ? AND timeframe = ?", [ticker.upper().strip(), timeframe])
            else:
                con.execute("DELETE FROM trendlines WHERE ticker = ?", [ticker.upper().strip()])

    # ==========================================
    # 그룹 관리 CRUD
    # ==========================================
    def get_groups(self) -> list:
        try:
            with self._get_connection() as con:
                df = con.execute("""
                    SELECT group_name FROM custom_groups
                    UNION
                    SELECT DISTINCT group_name FROM watchlist WHERE group_name IS NOT NULL
                    ORDER BY group_name
                """).df()
                groups = df["group_name"].dropna().tolist()
                return groups if groups else ["기본 관심종목"]
        except Exception:
            return ["빅테크/AI", "반도체", "클라우드/SaaS"]

    def add_group(self, group_name: str) -> bool:
        name = group_name.strip()
        if not name:
            return False
        with self._get_connection() as con:
            con.execute("INSERT OR IGNORE INTO custom_groups (group_name) VALUES (?)", [name])
        return True

    def rename_group(self, old_name: str, new_name: str) -> bool:
        old_name = old_name.strip()
        new_name = new_name.strip()
        if not old_name or not new_name or old_name == new_name:
            return False

        with self._get_connection() as con:
            con.execute("INSERT OR IGNORE INTO custom_groups (group_name) VALUES (?)", [new_name])
            con.execute("UPDATE watchlist SET group_name = ? WHERE group_name = ?", [new_name, old_name])
            con.execute("DELETE FROM custom_groups WHERE group_name = ?", [old_name])
        return True

    def delete_group(self, group_name: str):
        group_name = group_name.strip()
        with self._get_connection() as con:
            con.execute("INSERT OR IGNORE INTO custom_groups (group_name) VALUES ('기본 관심종목')")
            con.execute("UPDATE watchlist SET group_name = '기본 관심종목' WHERE group_name = ?", [group_name])
            con.execute("DELETE FROM custom_groups WHERE group_name = ?", [group_name])

    # ==========================================
    # 관심종목(Watchlist) CRUD
    # ==========================================
    def get_watchlist(self, group_name: str = None) -> pd.DataFrame:
        with self._get_connection() as con:
            if group_name and group_name != "전체":
                return con.execute("SELECT ticker, name, group_name FROM watchlist WHERE group_name = ? ORDER BY ticker", [group_name]).df()
            return con.execute("SELECT ticker, name, group_name FROM watchlist ORDER BY group_name, ticker").df()

    def add_watchlist_item(self, ticker: str, name: str = "", group_name: str = "기본 관심종목"):
        ticker = ticker.strip().upper()
        if not name:
            name = ticker
        if not group_name:
            group_name = "기본 관심종목"

        with self._get_connection() as con:
            con.execute("INSERT OR IGNORE INTO custom_groups (group_name) VALUES (?)", [group_name])
            con.execute("""
                INSERT OR REPLACE INTO watchlist (ticker, name, group_name)
                VALUES (?, ?, ?)
            """, [ticker, name, group_name])

    def remove_watchlist_item(self, ticker: str):
        with self._get_connection() as con:
            con.execute("DELETE FROM watchlist WHERE ticker = ?", [ticker.strip().upper()])

    # ==========================================
    # 일/주/월봉 시세 캐시 CRUD
    # ==========================================
    def save_prices(self, ticker: str, timeframe: str, df: pd.DataFrame):
        if df.empty:
            return

        tf = timeframe.upper().strip()
        df_to_save = df.copy()
        df_to_save["ticker"] = ticker.upper().strip()
        df_to_save["timeframe"] = tf
        df_to_save["updated_at"] = datetime.now()

        if not pd.api.types.is_datetime64_any_dtype(df_to_save["date"]):
            df_to_save["date"] = pd.to_datetime(df_to_save["date"])

        with self._get_connection() as con:
            con.register("temp_prices", df_to_save)
            con.execute("""
                DELETE FROM stock_prices 
                WHERE ticker = ? AND timeframe = ? AND date IN (SELECT date FROM temp_prices)
            """, [ticker.upper(), tf])

            con.execute("""
                INSERT INTO stock_prices (ticker, timeframe, date, open, high, low, close, volume, updated_at)
                SELECT ticker, timeframe, date, open, high, low, close, volume, updated_at FROM temp_prices
            """)

    def get_prices(self, ticker: str, timeframe: str = "D") -> pd.DataFrame:
        tf = timeframe.upper().strip()
        with self._get_connection() as con:
            query = """
                SELECT date, open, high, low, close, volume 
                FROM stock_prices 
                WHERE ticker = ? AND timeframe = ?
                ORDER BY date ASC
            """
            df = con.execute(query, [ticker.upper().strip(), tf]).df()
            return df
