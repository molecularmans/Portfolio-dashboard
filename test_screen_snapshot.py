import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.db.screen_snapshot import ScreenRuntime, ScreenSnapshotStore
from src.indicators.weekly_screen import completed_week_start


class _NoGitHub:
    is_configured = False


class ScreenSnapshotTests(unittest.TestCase):
    def test_saved_screen_is_available_in_a_new_runtime_without_rescanning(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ScreenSnapshotStore(Path(folder) / "screen.json", github_sync=_NoGitHub())
            screen = {"D": {"scan_day": "2026-10-07", "tickers": ["TWST"], "results": {"TWST": {"stage": "watch", "date": "2026-10-07"}}, "completed_at": "2026-10-08T09:30+09:00"}}
            store.save(screen)
            runtime = ScreenRuntime(ScreenSnapshotStore(store.path, github_sync=_NoGitHub()))
            self.assertEqual(runtime.screen("D"), screen["D"])
            self.assertIsNone(runtime.status())
            self.assertEqual(json.loads(store.path.read_text(encoding="utf-8"))["schema_version"], 1)

    def test_opening_today_does_not_scan_but_next_0930_rollover_does(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ScreenSnapshotStore(Path(folder) / "screen.json", github_sync=_NoGitHub())
            with patch("src.db.screen_snapshot.scan_day", return_value="2026-10-07"):
                runtime = ScreenRuntime(store)
                self.assertFalse(runtime.start(["TWST"], lambda *_args, **_kwargs: pd.DataFrame(), None, None, scheduled=True))
            with patch("src.db.screen_snapshot.scan_day", return_value="2026-10-08"):
                self.assertTrue(runtime.start(["TWST"], lambda *_args, **_kwargs: pd.DataFrame(), None, None, scheduled=True))
            deadline = time.monotonic() + 2
            while runtime.status()["running"] and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(runtime.status()["running"])
            self.assertEqual(runtime.screen("D")["scan_day"], "2026-10-08")
            self.assertEqual(runtime.screen("W")["results"]["TWST"]["stage"], "unavailable")

    def test_scheduled_refresh_skips_weekly_when_same_week_is_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ScreenSnapshotStore(Path(folder) / "screen.json", github_sync=_NoGitHub())
            store.save({"W": {"week_start": completed_week_start("AAPL").isoformat(), "results": {}}})
            with patch("src.db.screen_snapshot.scan_day", side_effect=["2026-10-07", "2026-10-08"]):
                runtime = ScreenRuntime(store)
                self.assertTrue(runtime.start(["TWST"], lambda *_args, **_kwargs: pd.DataFrame(), None, None, scheduled=True))
            self.assertEqual(runtime.status()["total"], 1)
            deadline = time.monotonic() + 2
            while runtime.status()["running"] and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(runtime.status()["running"])


if __name__ == "__main__":
    unittest.main()
