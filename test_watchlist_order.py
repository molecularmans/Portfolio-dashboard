import gc
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.db.database import StockDB


def make_db(path):
    with patch.object(StockDB, "_initial_restore_fast"), patch.object(StockDB, "trigger_github_backup"):
        return StockDB(str(path))


class WatchlistOrderTests(unittest.TestCase):
    def test_move_and_config_round_trip(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            db = make_db(Path(directory) / "watchlist.db")
            with db._get_connection() as con:
                con.execute("DELETE FROM watchlist")

            with patch.object(db, "trigger_github_backup"):
                for ticker in ("AAA", "BBB", "CCC"):
                    db.add_watchlist_item(ticker, group_name="빅테크/AI")
                self.assertEqual(db.get_watchlist("빅테크/AI")["ticker"].tolist(), ["AAA", "BBB", "CCC"])
                self.assertTrue(db.move_watchlist_item("CCC", 1))
                self.assertEqual(db.get_watchlist("빅테크/AI")["ticker"].tolist(), ["CCC", "AAA", "BBB"])
                self.assertFalse(db.move_watchlist_item("CCC", 1))

                saved = db.export_config()
                db.import_config(saved, trigger_backup=False)
                self.assertEqual(db.get_watchlist("빅테크/AI")["ticker"].tolist(), ["CCC", "AAA", "BBB"])

                db.add_watchlist_item("DDD", group_name="빅테크/AI")
                self.assertEqual(db.get_watchlist("빅테크/AI")["ticker"].tolist(), ["CCC", "AAA", "BBB", "DDD"])
                db.add_watchlist_item("BBB", group_name="반도체")
                self.assertEqual(db.get_watchlist("반도체")["ticker"].tolist(), ["BBB"])
                self.assertEqual(db.get_watchlist("빅테크/AI")["ticker"].tolist(), ["CCC", "AAA", "DDD"])
            del db, con
            gc.collect()

    def test_legacy_schema_and_config_keep_existing_order(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "legacy.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE watchlist (ticker TEXT PRIMARY KEY, name TEXT, group_name TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                con.executemany(
                    "INSERT INTO watchlist (ticker, group_name, created_at) VALUES (?, '빅테크/AI', '2026-10-10 00:00:00')",
                    [(ticker,) for ticker in ("BBB", "AAA", "CCC")],
                )

            db = make_db(path)
            self.assertEqual(db.get_watchlist("빅테크/AI")["ticker"].tolist(), ["BBB", "AAA", "CCC"])

            db.import_config(
                {"watchlist": [
                    {"ticker": "Z", "group_name": "빅테크/AI"},
                    {"ticker": "X", "group_name": "빅테크/AI"},
                    {"ticker": "Y", "group_name": "빅테크/AI"},
                ]},
                trigger_backup=False,
            )
            self.assertEqual(db.get_watchlist("빅테크/AI")["ticker"].tolist(), ["Z", "X", "Y"])
            del db, con
            gc.collect()


if __name__ == "__main__":
    unittest.main()
