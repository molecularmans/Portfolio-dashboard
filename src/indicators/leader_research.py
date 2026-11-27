"""Evidence-based watchlist research using completed prices and dated issuer data."""
import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/leader_research.json"
LABELS = ("확정 주도주", "부상 주도주", "성숙 주도주")
HORIZONS = (20, 60, 120)


def evidence():
    try:
        with DATA.open(encoding="utf-8") as f:
            content = json.load(f)
        return content["records"] if content.get("version") == 1 else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


@lru_cache(maxsize=8)
def latest_us_session(now_minute):
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS")
    now = pd.Timestamp(now_minute)
    day = cal.date_to_session(now.date(), direction="previous")
    if cal.session_close(day) > now:
        day = cal.previous_session(day)
    return day.date().isoformat()


def closing_prices(frame, cutoff):
    if frame is None or frame.empty or not {"date", "close"}.issubset(frame):
        return pd.Series(dtype=float)
    dates = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    close = pd.Series(pd.to_numeric(frame["close"], errors="coerce").to_numpy(), index=dates)
    close = close[close.index.notna() & close.gt(0) & close.lt(float("inf"))]
    return close[~close.index.duplicated(keep="last")].sort_index().loc[:cutoff]


def performance(prices, spy):
    if len(spy) < 121 or not len(prices):
        return {}
    aligned = prices.reindex(spy.tail(121).index)
    if aligned.isna().any():
        return {}
    return {str(n): round(100 * (aligned.iloc[-1] / aligned.iloc[-1-n] -
                                  spy.iloc[-1] / spy.iloc[-1-n]), 3) for n in HORIZONS}


def growth(new, old):
    return 100 * (new / old - 1) if old is not None and old > 0 and new is not None else None


def acceleration(quarters, first, on):
    """Compare consecutive same-quarter YoY changes and cycle-anchored 4Q sums."""
    rows = sorted(q for q in quarters if len(q) == 3 and q[0] <= on)
    rows = list({r[0]: r for r in rows}.values())
    def tail_at(cut, n):
        eligible = [r for r in rows if r[0] <= cut][-n:]
        if len(eligible) < n:
            return []
        dates = [date.fromisoformat(r[0]) for r in eligible]
        if (date.fromisoformat(cut) - dates[-1]).days > 120:
            return []
        return eligible if all(65 <= (b-a).days <= 115 for a,b in zip(dates,dates[1:])) else []
    def delta(a,b):
        return a-b if a is not None and b is not None else None
    recent = tail_at(on,6)
    out = {"oi_yoy": None, "oi_delta": None, "sales_delta": None, "hans": None,
           "quarter_end": rows[-1][0] if rows else None}
    if recent:
        for col, key in ((1,"oi_delta"),(2,"sales_delta")):
            last = growth(recent[-1][col],recent[-5][col])
            out[key] = delta(last,growth(recent[-2][col],recent[-6][col]))
            if col == 1:
                out["oi_yoy"] = last
    if first:
        anchor = date.fromisoformat(first)
        totals = []
        for offset in (0,52,104):
            cut = (anchor + timedelta(weeks=offset)).isoformat()
            window = tail_at(cut,4) if cut <= on else []
            totals.append(sum(r[1] for r in window) if window and all(r[1] is not None for r in window) else None)
        out["hans"] = delta(growth(totals[2],totals[1]),growth(totals[1],totals[0]))
    return out


def within(day, on, days):
    try:
        return 0 <= (date.fromisoformat(on)-date.fromisoformat(day)).days <= days
    except (ValueError, TypeError):
        return False


def assess(ticker, cycle, market, fact, earnings, on, price_day=None):
    state = cycle.get("state")
    fact = fact or {}
    missing, failed, reasons = [], [], []
    dates = dict(가격=(market or {}).get("date"), 주봉=cycle.get("date"))
    numbers = {}
    def result(label):
        return {"종목":ticker,"최종 등급":label,"판정 근거":" · ".join(failed+reasons) or "—",
                "미확인 항목":" · ".join(dict.fromkeys(missing)) or "—","판정 기준일":on,
                "자료 기준일":" / ".join(k+" "+str(v) for k,v in dates.items() if v),
                **numbers}
    if fact.get("nonissuer"):
        reasons.append("ETF·지수 등 기업 실적 평가 대상 외")
        return result("대상 제외")
    if state == "other":
        reasons.append("주봉 정배열 및 정배열 직전 조건 미충족")
        return result("조건 미충족")
    if state == "mature":
        reasons.append("정배열 30개월 초과 · 신규 후보 제외")
        return result("장기 사이클")
    if not fact and not earnings:
        missing.append("기업 실적 수집 대상·거래소 확인")
        return result("판정 보류")
    if state not in ("candidate","emerging"):
        missing.append("완료 주봉 또는 정배열 시작일")
        return result("판정 보류")
    weeks = cycle.get("weeks")
    reasons.append(f"정배열 {weeks}주" if state == "candidate" else "정배열 직전")
    market = market or {}
    for key, label in (("stock","종목"),("sector","섹터")):
        spreads = market.get(key) or {}
        if market.get("date") != (price_day or on) or any(spreads.get(str(n)) is None for n in HORIZONS):
            missing.append(label+"의 SPY 대비 20·60·120일 성과")
        else:
            a,b,c = [spreads[str(n)] for n in HORIZONS]
            numbers[label+" 초과수익률 20/60/120일(%p)"] = f"{a:+.1f} / {b:+.1f} / {c:+.1f}"
            if a > 0 and b > 0:
                reasons.append(label+" 시장 주도")
            elif a > 0 and a/20 > b/60 > c/120:
                reasons.append(label+" 상대강도 개선")
            else:
                failed.append(label+" 상대강도 조건 미충족")
    fundamentals = acceleration(fact.get("quarters",[]), cycle.get("first_date"), on)
    qend = fundamentals["quarter_end"]
    dates["실적"] = qend
    fiscal = (earnings or {}).get("period")
    if fiscal and fact.get("fiscal_period") and fiscal != fact["fiscal_period"]:
        missing.append("최신 발표 분기 재무제표 대조")
    for field, label in (("oi_delta","분기 영업이익 가속도"),("sales_delta","분기 매출 가속도")):
        val = fundamentals[field]
        if val is None:
            missing.append(label)
        else:
            numbers[label+"(%p)"] = round(val,2)
            if val <= 0:
                failed.append(label+" 둔화·정체")
    hans = fundamentals["hans"]
    if hans is not None:
        numbers["Hans Delta(%p)"] = round(hans,2)
        if hans < 0:
            failed.append("사이클 영업이익 성장률 둔화")
    elif state == "candidate" and (weeks or 0) >= 104:
        missing.append("사이클 기준 영업이익 3개 시점")
    else:
        reasons.append("사이클 2년 실측 전")
    doc = fact.get("review",{})
    checked = doc.get("checked")
    dates["공시 점검"] = checked
    report_date = (earnings or {}).get("reported_on","")
    doc_current = within(checked,on,10)
    for key,label,positive,negative in (
        ("risk","SEC 위험 검토",{"screened"},{"flagged"}),
        ("guidance","회사 가이던스",{"up"},{"down"}),
        ("demand","수요",{"up"},{"down"}),
    ):
        item=doc.get(key) or {}
        if not doc_current or not item.get("url") or not within(item.get("date"),on,135) or (
                key != "risk" and report_date and item.get("date","") < (date.fromisoformat(report_date)-timedelta(days=2)).isoformat()):
            missing.append(label)
            continue
        if item.get("value") in negative:
            failed.append(label+(" 위험 신호" if key == "risk" else " 하향·둔화"))
        elif item.get("value") in positive:
            reasons.append("공시 자동 점검 통과" if key == "risk" else label+" 개선")
        else:
            missing.append(label)
    forward = doc.get("forward") or {}
    if doc_current and within(forward.get("date"),on,120) and forward.get("url") and forward.get("period_end","") > (qend or on) and (
        not report_date or forward.get("date","") >= (date.fromisoformat(report_date)-timedelta(days=2)).isoformat()
    ) and fundamentals["oi_yoy"] is not None and isinstance(forward.get("oi_yoy"),(float,int)):
        fd = forward["oi_yoy"] - fundamentals["oi_yoy"]
        numbers["Forward Delta(%p)"] = round(fd,2)
        if fd <= 0:
            failed.append("다음 분기 영업이익 가속도 둔화·정체")
    elif doc_current and not any(x in missing for x in ("회사 가이던스","수요")) and doc.get("guidance",{}).get("value")=="up" and doc.get("demand",{}).get("value")=="up":
        reasons.append("선행 방향 잠정 양호(가이던스·수요 대용)")
    else:
        missing.append("다음 분기 영업이익 전망")
    rev = fact.get("revision",{})
    if within(rev.get("as_of"),on,10) and rev.get("period_end","") >= on and rev.get("url") and rev.get("direction") in ("up","down","flat"):
        dates["추정치"] = rev["as_of"]
        if rev["direction"] != "up":
            failed.append("차기 분기 EPS 추정치 하향·정체")
        else:
            reasons.append("차기 분기 EPS 추정치 상향")
    else:
        missing.append("동일 분기 EPS 추정치 수정")
    if doc_current and doc.get("risk",{}).get("value")=="flagged" and "SEC 위험 검토" not in missing:
        return result("공시 위험 검토")
    if missing:
        return result("판정 보류")
    if failed:
        cooling = {"분기 영업이익 가속도 둔화·정체", "분기 매출 가속도 둔화·정체", "사이클 영업이익 성장률 둔화", "다음 분기 영업이익 가속도 둔화·정체"}
        if state == "candidate" and (weeks or 0) >= 40 and set(failed) <= cooling and (fundamentals["oi_yoy"] or 0) > 0:
            return result("성숙 주도주")
        return result("조건 미충족")
    if state == "emerging" or hans is None or "Forward Delta(%p)" not in numbers or (weeks or 0)<27:
        return result("부상 주도주")
    return result("확정 주도주")
