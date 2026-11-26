import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.sync_watchlist_earnings import synchronize
from src.indicators.earnings_evidence import SHEET_COLUMNS, earnings_row, sheet_records, surprise


def row(ticker, when, eps=-0.04, consensus=-0.05):
    return [ticker, 2026, "Q3", when, eps, consensus, 20, 110, 100, 10]


class EarningsEvidenceTests(unittest.TestCase):
    def test_filters_watchlist_corrects_filings_and_keeps_one_period(self):
        blocks = [[SHEET_COLUMNS, row("ABC", "2026-11-10"), row("HIDDEN", "2026-11-12"),
                   row("ABC", "2026-08-10"), row("ABC", "2026-11-27")],
                  [["공시ID"], ["SEC:0000000001-26-000001"]],
                  [["공시유형"], ["8-K"]]]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "out.json"
            payload = {"blocks": blocks, "updated_at": "2026-11-25T01:00:00Z"}
            synchronize(payload, {"ABC"}, path)
            self.assertEqual(list(json.loads(path.read_text())["records"]), ["ABC"])
            blocks[1][1] = ["SEC:0000000001-26-000002"]
            blocks[2][1] = ["10-Q"]
            synchronize(payload, {"ABC"}, path)
            entry = json.loads(path.read_text())["records"]["ABC"]
            self.assertEqual(entry["reported_on"], "2026-11-10")
            detail = earnings_row("ABC", entry)
            self.assertEqual(detail["실적 비교"], "EPS·매출 모두 상회")
            self.assertAlmostEqual(detail["EPS 차이(%)"], 20)
            self.assertEqual(detail["공시유형"], "10-Q")
            self.assertEqual(detail["SEC 접수번호"], "0000000001-26-000002")
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                synchronize({**payload, "blocks": [[], [], []]}, {"ABC"}, path)
            self.assertEqual(original, path.read_bytes())

    def test_missing_or_invalid_data_never_inherits_older_evidence(self):
        blocks = [[SHEET_COLUMNS, row("ABC", 46344.5, 0, None), row("ABC", "2026-08-10")],
                  [["공시ID"], ["not-an-accession"], ["SEC:0000000001-26-000001"]],
                  [["공시유형"], ["10-Q"], ["8-K"]]]
        records = sheet_records(blocks, {"ABC"}, date(2026, 11, 25))
        detail = earnings_row("ABC", records["ABC"])
        self.assertEqual(detail["발표일(KST)"], "2026-11-18")
        self.assertEqual(detail["실적 비교"], "비교 자료 부족")
        self.assertIsNone(detail["SEC 접수번호"])
        self.assertIsNone(surprise(1, 0))
        self.assertEqual(earnings_row("XYZ", None)["실적 비교"], "시트 자료 없음")


if __name__ == "__main__":
    unittest.main()
