import os
import uuid
import json
import sqlite3
import pandas as pd
from datetime import datetime

from src.db.github_sync import GitHubSync

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DB_PATH = os.path.join(DB_DIR, "stock_cache.db")

# 타임프레임별 기본 이동평균선 프리셋
DEFAULT_TIMEFRAME_MA = {
    "일봉": {
        "show_d_ema5": {"enabled": True, "length": 5, "type": "EMA", "label": "5 EMA"},
        "show_d_ma10": {"enabled": False, "length": 10, "type": "SMA", "label": "10 MA"},
        "show_d_ma20": {"enabled": True, "length": 20, "type": "SMA", "label": "20 MA"},
        "show_d_ma30": {"enabled": False, "length": 30, "type": "SMA", "label": "30 MA"},
        "show_d_ma50": {"enabled": True, "length": 50, "type": "SMA", "label": "50 MA"},
        "show_d_ma150": {"enabled": False, "length": 150, "type": "SMA", "label": "150 MA"},
        "show_d_ma200": {"enabled": True, "length": 200, "type": "SMA", "label": "200 MA"},
    },
    "주봉": {
        "show_w_ma4": {"enabled": True, "length": 4, "type": "SMA", "label": "4주 MA (1달)"},
        "show_w_ma10": {"enabled": False, "length": 10, "type": "SMA", "label": "10주 MA"},
        "show_w_ma13": {"enabled": True, "length": 13, "type": "SMA", "label": "13주 MA (1분기)"},
        "show_w_ma26": {"enabled": True, "length": 26, "type": "SMA", "label": "26주 MA (반기)"},
        "show_w_ma40": {"enabled": False, "length": 40, "type": "SMA", "label": "40주 MA"},
        "show_w_ma52": {"enabled": True, "length": 52, "type": "SMA", "label": "52주 MA (1년)"},
    },
    "월봉": {
        "show_m_ma6": {"enabled": True, "length": 6, "type": "SMA", "label": "6월 MA (반기)"},
        "show_m_ma12": {"enabled": True, "length": 12, "type": "SMA", "label": "12월 MA (1년)"},
        "show_m_ma24": {"enabled": True, "length": 24, "type": "SMA", "label": "24월 MA (2년)"},
        "show_m_ma60": {"enabled": True, "length": 60, "type": "SMA", "label": "60월 MA (5년)"},
    },
}


class StockDB:
    """SQLite 기반 로컬 캐시 및 설정 데이터베이스 (타임프레임별 이평선 분리 & GitHub 자동 동기화)"""

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.github_sync = GitHubSync()
        self._init_tables()
        self._sync_restore_from_github()

    def _get_connection(self):
        con = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def _init_tables(self):
        """기본 테이블 스키마 초기화 및 마이그레이션"""
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
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("PRAGMA table_info(custom_groups)")
            cols = [row[1] for row in cur.fetchall()]
            if "sort_order" not in cols:
                try:
                    cur.execute("ALTER TABLE custom_groups ADD COLUMN sort_order INTEGER DEFAULT 0")
                except Exception:
                    pass

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
                cur.execute("INSERT OR IGNORE INTO custom_groups (group_name, sort_order) VALUES ('빅테크/AI', 0)")
                cur.execute("INSERT OR IGNORE INTO custom_groups (group_name, sort_order) VALUES ('반도체', 1)")
                cur.execute("INSERT OR IGNORE INTO custom_groups (group_name, sort_order) VALUES ('클라우드/SaaS', 2)")

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
    # GitHub 자동 백업 및 복원
    # ==========================================
    def _sync_restore_from_github(self):
        """앱 기동 시 GitHub 또는 로컬 config 파일로부터 최신 설정 복원"""
        try:
            config = self.github_sync.fetch_config_from_github()
            if config and ("groups" in config or "watchlist" in config):
                self.import_config(config, trigger_backup=False)
        except Exception as e:
            print(f"[StockDB] GitHub restore failed: {e}")

    def trigger_github_backup(self):
        """설정 변경 시 GitHub 저장소로 자동 커밋 백업"""
        try:
            config = self.export_config()
            self.github_sync.save_config_to_github(config)
        except Exception as e:
            print(f"[StockDB] GitHub backup failed: {e}")

    def export_config(self) -> dict:
        """현재 DB의 모든 그룹, 관심종목, 타임프레임별 이동평균선 설정을 딕셔너리로 추출"""
        with self._get_connection() as con:
            df_groups = pd.read_sql_query("SELECT group_name, sort_order FROM custom_groups ORDER BY sort_order ASC, created_at ASC", con)
            groups = df_groups.to_dict(orient="records")

            df_wl = pd.read_sql_query("SELECT ticker, name, group_name FROM watchlist ORDER BY group_name, created_at ASC", con)
            watchlist = df_wl.to_dict(orient="records")

            cur = con.cursor()
            cur.execute("SELECT value FROM user_settings WHERE key = 'timeframe_ma_settings'")
            row = cur.fetchone()
            tf_ma = json.loads(row[0]) if row and row[0] else DEFAULT_TIMEFRAME_MA

            return {
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "groups": groups,
                "watchlist": watchlist,
                "timeframe_ma_settings": tf_ma,
            }

    def import_config(self, config: dict, trigger_backup: bool = True):
        """설정 딕셔너리를 DB에 덮어써서 복원"""
        if not config:
            return

        with self._get_connection() as con:
            cur = con.cursor()

            # 1. 그룹 복원
            if "groups" in config and config["groups"]:
                cur.execute("DELETE FROM custom_groups")
                for idx, g in enumerate(config["groups"]):
                    gname = g.get("group_name", "") if isinstance(g, dict) else str(g)
                    order = g.get("sort_order", idx) if isinstance(g, dict) else idx
                    if gname:
                        cur.execute("INSERT OR REPLACE INTO custom_groups (group_name, sort_order) VALUES (?, ?)", [gname.strip(), order])

            # 2. 관심종목 복원
            if "watchlist" in config and config["watchlist"]:
                cur.execute("DELETE FROM watchlist")
                for w in config["watchlist"]:
                    if isinstance(w, dict):
                        ticker = w.get("ticker", "").strip().upper()
                        name = w.get("name", "")
                        group_name = w.get("group_name", "빅테크/AI")
                        if ticker:
                            cur.execute("INSERT OR REPLACE INTO watchlist (ticker, name, group_name) VALUES (?, ?, ?)", [ticker, name, group_name])

            # 3. 타임프레임별 이동평균선 설정 복원
            if "timeframe_ma_settings" in config and config["timeframe_ma_settings"]:
                val_str = json.dumps(config["timeframe_ma_settings"])
                cur.execute("""
                    INSERT INTO user_settings (key, value, updated_at)
                    VALUES ('timeframe_ma_settings', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """, [val_str])

            con.commit()

        if trigger_backup:
            self.trigger_github_backup()

    # ==========================================
    # 타임프레임별 이동평균선 설정
    # ==========================================
    def get_timeframe_ma_settings(self, timeframe: str = "일봉") -> dict:
        """특정 타임프레임(일봉/주봉/월봉)에 해당하는 이동평균선 설정 로드"""
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT value FROM user_settings WHERE key = 'timeframe_ma_settings'")
            row = cur.fetchone()
            all_tf = DEFAULT_TIMEFRAME_MA.copy()
            if row and row[0]:
                try:
                    loaded = json.loads(row[0])
                    for tf_k in ["일봉", "주봉", "월봉"]:
                        if tf_k in loaded:
                            all_tf[tf_k].update(loaded[tf_k])
                except Exception:
                    pass
            return all_tf.get(timeframe, all_tf["일봉"])

    def save_timeframe_ma_settings(self, timeframe: str, ma_dict: dict):
        """특정 타임프레임의 이동평균선 설정 영구 저장 & GitHub 자동 동기화"""
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT value FROM user_settings WHERE key = 'timeframe_ma_settings'")
            row = cur.fetchone()
            all_tf = DEFAULT_TIMEFRAME_MA.copy()
            if row and row[0]:
                try:
                    all_tf.update(json.loads(row[0]))
                except Exception:
                    pass

            all_tf[timeframe] = ma_dict
            val_str = json.dumps(all_tf)

            cur.execute("""
                INSERT INTO user_settings (key, value, updated_at)
                VALUES ('timeframe_ma_settings', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, [val_str])
            con.commit()

        self.trigger_github_backup()

    # ==========================================
    # 그룹 관리 CRUD
    # ==========================================
    def get_groups(self) -> list:
        with self._get_connection() as con:
            df = pd.read_sql_query("SELECT group_name FROM custom_groups ORDER BY sort_order ASC, created_at ASC", con)
            return df["group_name"].tolist() if not df.empty else ["빅테크/AI", "반도체", "클라우드/SaaS"]

    def add_group(self, group_name: str):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM custom_groups")
            next_order = cur.fetchone()[0]
            cur.execute("INSERT OR IGNORE INTO custom_groups (group_name, sort_order) VALUES (?, ?)", [group_name.strip(), next_order])
            con.commit()
        self.trigger_github_backup()

    def reorder_groups(self, ordered_groups: list):
        with self._get_connection() as con:
            cur = con.cursor()
            for idx, gname in enumerate(ordered_groups):
                cur.execute("UPDATE custom_groups SET sort_order = ? WHERE group_name = ?", [idx, gname.strip()])
            con.commit()
        self.trigger_github_backup()

    def move_group_up(self, group_name: str):
        groups = self.get_groups()
        if group_name in groups:
            idx = groups.index(group_name)
            if idx > 0:
                groups[idx], groups[idx - 1] = groups[idx - 1], groups[idx]
                self.reorder_groups(groups)

    def move_group_down(self, group_name: str):
        groups = self.get_groups()
        if group_name in groups:
            idx = groups.index(group_name)
            if idx < len(groups) - 1:
                groups[idx], groups[idx + 1] = groups[idx + 1], groups[idx]
                self.reorder_groups(groups)

    def rename_group(self, old_name: str, new_name: str):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("UPDATE custom_groups SET group_name = ? WHERE group_name = ?", [new_name.strip(), old_name.strip()])
            cur.execute("UPDATE watchlist SET group_name = ? WHERE group_name = ?", [new_name.strip(), old_name.strip()])
            con.commit()
        self.trigger_github_backup()

    def delete_group(self, group_name: str, fallback_group: str = "빅테크/AI"):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("UPDATE watchlist SET group_name = ? WHERE group_name = ?", [fallback_group, group_name.strip()])
            cur.execute("DELETE FROM custom_groups WHERE group_name = ?", [group_name.strip()])
            con.commit()
        self.trigger_github_backup()

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
        self.trigger_github_backup()

    def remove_watchlist_item(self, ticker: str):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM watchlist WHERE ticker = ?", [ticker.upper().strip()])
            con.commit()
        self.trigger_github_backup()

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
