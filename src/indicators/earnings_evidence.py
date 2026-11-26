"""Map the StockNow earnings sheet to public watchlist facts and SEC references."""

import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "watchlist_earnings.json"
SHEET_COLUMNS = ["티커", "회계연도", "분기", "발표일(KST)", "EPS", "예상 EPS", "EPS 차이(%)", "매출", "예상 매출", "매출 차이(%)"]
ACCESSION = re.compile(r"(?:SEC:)?(\d{10}-\d{2}-\d{6})")
FILING_FORMS = {"8-K", "10-Q", "10-K", "6-K", "20-F", "40-F"}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    return parsed if math.isfinite(parsed) else None


def announced_date(value):
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        if 0 < value < 100000:
            return date(1899, 12, 30) + timedelta(days=int(value))
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def sheet_records(blocks, watchlist, as_of):
    """Read aligned C:L, P:P and V:V blocks returned as unformatted values."""
    earnings, filings, forms = blocks
    if not earnings or earnings[0] != SHEET_COLUMNS or filings[:1] != [["공시ID"]] or forms[:1] != [["공시유형"]]:
        raise ValueError("실적 시트 열이 변경되었습니다.")
    allowed = set(watchlist)
    records = {}
    for index, row in enumerate(earnings[1:], 1):
        if not row or row[0] not in allowed:
            continue
        ticker = row[0]
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,15}", ticker):
            continue
        values = (row + [None] * 10)[:10]
        _, year, quarter, reported, eps, eps_est, _, sales, sales_est, _ = values
        day = announced_date(reported)
        if not day:
            raise ValueError("실적 발표일을 해석할 수 없습니다.")
        if day > as_of:
            continue
        year = str(year or "")
        quarter = str(quarter or "")
        fiscal = f"FY{year} {quarter}" if re.fullmatch(r"\d{4}", year) and re.fullmatch(r"Q[1-4]", quarter) else None
        raw_id = filings[index][0] if index < len(filings) and filings[index] else ""
        raw_form = forms[index][0] if index < len(forms) and forms[index] else ""
        accession = ACCESSION.fullmatch(str(raw_id).strip())
        form = str(raw_form).strip().upper()
        valid_ref = accession and form.removesuffix("/A") in FILING_FORMS
        record = {
            "reported_on": day.isoformat(), "period": fiscal,
            "eps": number(eps), "eps_estimate": number(eps_est),
            "revenue": number(sales), "revenue_estimate": number(sales_est),
            "accession": accession[1] if valid_ref else None, "form": form if valid_ref else None,
        }
        old = records.get(ticker)
        if old is None or (record["reported_on"], record["period"] or "", bool(valid_ref)) >= (
                old["reported_on"], old["period"] or "", bool(old["accession"])):
            records[ticker] = record
    return dict(sorted(records.items()))


def surprise(actual, estimate):
    if actual is None or estimate in (None, 0):
        return None
    return 100 * (actual - estimate) / abs(estimate)


def earnings_row(ticker, record):
    if not record:
        return {"종목": ticker, "실적 비교": "시트 자료 없음", "공시유형": None}
    eps, eps_est = record["eps"], record["eps_estimate"]
    sales, sales_est = record["revenue"], record["revenue_estimate"]
    if None in (eps, eps_est, sales, sales_est):
        comparison = "비교 자료 부족"
    elif eps > eps_est and sales > sales_est:
        comparison = "EPS·매출 모두 상회"
    elif eps < eps_est and sales < sales_est:
        comparison = "EPS·매출 모두 하회"
    elif eps == eps_est and sales == sales_est:
        comparison = "모두 예상치 부합"
    else:
        comparison = "엇갈림·일부 부합"
    return {
        "종목": ticker, "실적 비교": comparison, "공시유형": record["form"],
        "발표일(KST)": record["reported_on"], "회계분기": record["period"],
        "EPS": eps, "예상 EPS": eps_est, "EPS 차이(%)": surprise(eps, eps_est),
        "매출": sales, "예상 매출": sales_est, "매출 차이(%)": surprise(sales, sales_est),
        "SEC 접수번호": record["accession"],
        "EDGAR": f"https://www.sec.gov/edgar/browse/?CIK={ticker}" if record["accession"] else None,
    }


def read_snapshot(path=SNAPSHOT):
    with path.open(encoding="utf-8") as source:
        snapshot = json.load(source)
    if snapshot.get("version") != 1 or not isinstance(snapshot.get("records"), dict):
        raise ValueError("지원하지 않는 실적 데이터 형식입니다.")
    datetime.fromisoformat(snapshot["updated_at"])
    return snapshot
