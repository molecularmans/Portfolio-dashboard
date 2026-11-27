"""Refresh dated public corporate facts for the dashboard's own watchlist."""
import calendar
import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UA = "Portfolio-dashboard public research contact: molecularmans@users.noreply.github.com"
SEC = "https://www.sec.gov"
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
PERIOD_FORMS = {"10-Q", "10-K", "20-F"}
ETFS = set("QQQ SPY BITO SOXX US10Y US30Y XLV XBI IBB GLD HYPEUSD XHB VOO DIA XLC XLY XLP XLE XLF XLI XLK XLB XLRE XLU".split())
GICS = dict(zip(("Communication Services","Consumer Discretionary","Consumer Staples","Energy","Financials","Health Care","Industrials","Information Technology","Materials","Real Estate","Utilities"), "XLC XLY XLP XLE XLF XLV XLI XLK XLB XLRE XLU".split()))
TAGS = (("OperatingIncomeLoss",), ("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"))

def fetch(url, *, json_data=False):
    # All requests are sequential, including access to the SEC archive.
    time.sleep(.22)
    try:
        response = requests.get(url, headers=HEADERS, timeout=(5,18))
        response.raise_for_status()
        return response.json() if json_data else response.text
    except (requests.RequestException, ValueError):
        return None

def load_file(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))

def quarterly_metrics(payload, old, on):
    previous = {r[0]: list(r) for r in old if len(r) == 3}
    taxonomy = (payload.get("facts") or {}).get("us-gaap", {})
    for col, names in enumerate(TAGS, 1):
        periods = {}
        annuals = {}
        for priority, tag in enumerate(names):
            values = taxonomy.get(tag, {}).get("units", {}).get("USD", [])
            for obs in values:
                start, end, filed = (obs.get(k, "") for k in ("start","end","filed"))
                if not (start and end and filed and filed <= on and end <= on and obs.get("form","").split("/")[0] in PERIOD_FORMS):
                    continue
                val = obs.get("val")
                if not isinstance(val,(int,float)) or not math.isfinite(val):
                    continue
                length = (date.fromisoformat(end)-date.fromisoformat(start)).days + 1
                dest = periods if 65 <= length <= 115 else annuals if 350 <= length <= 380 else None
                if dest is None:
                    continue
                rank = (filed,-priority)
                if end not in dest or rank > dest[end][0]:
                    dest[end] = (rank, val, start, tag)
        # Use one GAAP concept and contiguous dates for a derived fiscal Q4.
        for end, (_, total, start, tag) in annuals.items():
            if end in periods:
                continue
            components = sorted((d, v) for d,v in periods.items() if v[2] >= start and d < end and v[3] == tag)
            if len(components) != 3 or components[0][1][2] != start:
                continue
            if any(date.fromisoformat(b[1][2])-date.fromisoformat(a[0]) != timedelta(days=1) for a,b in zip(components,components[1:])):
                continue
            if 65 <= (date.fromisoformat(end)-date.fromisoformat(components[-1][0])).days <= 115:
                periods[end] = (None,total-sum(v[1] for _,v in components),None,tag)
        for end, (_,value,_,_) in periods.items():
            previous.setdefault(end,[end,None,None])[col] = value
    return sorted(previous.values(),key=lambda r:r[0],reverse=True)[:24]

def fiscal_label(prior, old_end, new_end):
    m = re.fullmatch(r"FY(\d{4}) Q([1-4])", prior or "")
    if not m or not old_end or not new_end:
        return None
    days = (date.fromisoformat(new_end)-date.fromisoformat(old_end)).days
    advance = round(days/91.3)
    if advance < 0 or abs(days-advance*91.3) > 15:
        return None
    y,q = map(int,m.groups())
    return f"FY{y+(q-1+advance)//4} Q{(q-1+advance)%4+1}"

def filings(sub, on):
    cols = sub.get("filings",{}).get("recent",{})
    keys = ("accessionNumber","filingDate","reportDate","form","items","primaryDocument")
    out = []
    for i, acc in enumerate(cols.get("accessionNumber",[])):
        row = {k: cols[k][i] if i < len(cols.get(k,[])) else "" for k in keys}
        if re.fullmatch(r"\d{10}-\d{2}-\d{6}", acc) and row["filingDate"] <= on:
            out.append(row)
    return sorted(out,key=lambda r:r["filingDate"],reverse=True)

def archive(cik,row,name):
    if not str(cik).isdigit() or not re.fullmatch(r"[a-zA-Z0-9_.-]+",name or ""):
        return ""
    return f"{SEC}/Archives/edgar/data/{int(cik)}/{row['accessionNumber'].replace('-','')}/{name}"

def words(html):
    if not html:
        return ""
    soup = BeautifulSoup(html,"html.parser")
    for tag in soup.find_all(["script","style","ix:hidden","ix:header"]):
        tag.decompose()
    return " ".join(soup.stripped_strings)

def release_url(cik, event):
    acc = event["accessionNumber"]
    index = fetch(archive(cik,event,acc+"-index.htm"))
    if not index:
        return ""
    for tr in BeautifulSoup(index,"html.parser").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) >= 4 and cells[3].get_text(strip=True).upper() in {"EX-99.1","EX-99.01","EX-99"}:
            link=cells[2].find("a",href=True)
            if link:
                return archive(cik,event,link["href"].split("/")[-1])
    return ""

def item(value, day, url):
    return {"value":value, "date":day, "url":url}

def signals(body, day, url, quarter_end):
    text = body.lower().replace("’","'")[:100000]
    out = {}
    for key, pos, neg in (
        ("guidance",r"(?:raises|raised|raising|increases|increased) (?:its |our |the )?(?:(?:full.year|fiscal.year|annual|fy\s?\d+|revenue|earnings|financial|profit|202\d)\s+){0,4}(?:guidance|outlook)",
         r"(?:lowers|lowered|reduces|reduced|withdraws) (?:its |our |the )?(?:(?:full.year|annual|fiscal.year|financial|revenue|earnings|202\d)\s+){0,4}(?:guidance|outlook)"),
        ("demand",r"(?:demand|bookings|orders|backlog) (?:growth )?(?:has |is |was |continued to )?(?:accelerat(?:ed|ing)|strengthen(?:ed|ing))",
         r"(?:demand|bookings|orders|backlog) (?:growth )?(?:has |is |was )?(?:weaken(?:ed|ing)|decelerat(?:ed|ing)|declin(?:ed|ing))"),
    ):
        positive, negative = bool(re.search(pos,text)), bool(re.search(neg,text))
        if positive != negative:
            out[key] = item("up" if positive else "down",day,url)
    # Only accept an explicitly GAAP, next-quarter, year-over-year forecast.
    m = re.search(r"(?:next|upcoming) (?:fiscal )?quarter[^.;]{0,90}?(?<!non-)(?<!non )\bgaap operating income (?:is expected to |will |to )?(grow|increase|decline|decrease) (?:by )?(\d+(?:\.\d+)?)\s*% (?:year.over.year|from (?:the )?(?:prior|previous).year)",text)
    if m and quarter_end:
        end = date.fromisoformat(quarter_end) + timedelta(days=91)
        out["forward"] = {"oi_yoy": float(m[2]) * (-1 if m[1] in ("decline","decrease") else 1),
                          "period_end":end.isoformat(),"date":day,"url":url}
    return out

def review(rows, cik, on, reported, quarter_end, old):
    now = date.fromisoformat(on)
    lower = (now-timedelta(days=135)).isoformat()
    recent = [r for r in rows if r["filingDate"] >= lower]
    quarterly = next((r for r in recent if r["form"] in PERIOD_FORMS),None)
    if not quarterly:
        return old
    primary = archive(cik,quarterly,quarterly["primaryDocument"])
    if not primary:
        return old
    adverse = next((r for r in recent if r["form"] in {"NT 10-Q","NT 10-K","424B5"} or
                    r["form"] == "8-K" and set(re.findall(r"\d\.\d\d",r["items"])) & {"1.03","2.04","3.01","4.02"}),None)
    risk_url = archive(cik,adverse,adverse["accessionNumber"]+"-index.htm") if adverse else primary
    oldrisk=old.get("risk",{})
    if adverse:
        risk=item("flagged",adverse["filingDate"],risk_url)
    elif oldrisk.get("url") == primary and oldrisk.get("date")==quarterly["filingDate"] and oldrisk.get("value") in ("flagged","screened"):
        risk=oldrisk
    else:
        text = words(fetch(primary))
        if len(text)<5000:
            return old
        pattern = r"substantial doubt (?:exists )?(?:about|regarding) (?:our|the company.s) ability to continue as a going concern|(?:we|management) (?:identified|concluded that (?:there (?:is|was)|we had)) (?:a |one or more )?material weakness"
        risk=item("flagged" if re.search(pattern,text,re.I) else "screened",quarterly["filingDate"],primary)
    result = dict(old,checked=on,risk=risk)
    if reported:
        closest = [r for r in recent if r["form"] in {"6-K","8-K"} and (r["form"]=="6-K" or "2.02" in r["items"])
                   and abs((date.fromisoformat(reported)-date.fromisoformat(r["filingDate"])).days)<=3]
        if closest:
            event = min(closest,key=lambda r:abs((date.fromisoformat(reported)-date.fromisoformat(r["filingDate"])).days))
            if result.get("release_accession") != event["accessionNumber"]:
                url=release_url(cik,event)
                release=words(fetch(url)) if url else ""
                if len(release)>800:
                    for key in ("guidance","demand","forward"):
                        result.pop(key,None)
                    result.update(signals(release,event["filingDate"],url,quarter_end))
                    result["release_accession"]=event["accessionNumber"]
    return result

def revision_table(html, url, on, last_end):
    if not isinstance(html,str) or not html:
        return None
    for table in BeautifulSoup(html, "html.parser").find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        names = [c.get_text(" ",strip=True).lower() for c in rows[0].find_all(["td","th"])]
        if not {"period","30 days ago","now"} <= set(names):
            continue
        for row in rows[1:]:
            cells = [c.get_text(" ",strip=True) for c in row.find_all(["td","th"])]
            if len(cells) != len(names):
                continue
            label = cells[names.index("period")].replace("’","'")
            match = re.fullmatch(r"(?:Current|Next) quarter\s*\(([A-Za-z]{3})\s+'(\d\d)\)",label,re.I)
            if not match:
                continue
            try:
                month = datetime.strptime(" ".join(match.groups()),"%b %y").date()
                end = month.replace(day=calendar.monthrange(month.year,month.month)[1])
                if not 65 <= (end-date.fromisoformat(last_end)).days <= 116:
                    continue
                def value(key):
                    x = cells[names.index(key)].replace("$","").replace(",","").replace("−","-")
                    return float(re.sub(r"^\((.*)\)$",r"-\1",x))
                before, current = value("30 days ago"), value("now")
                if math.isfinite(before) and math.isfinite(current):
                    return {"period_end":end.isoformat(),"as_of":on,"prior_30d":before,"current":current,
                            "direction":"up" if current>before else "down" if current<before else "flat","url":url}
            except ValueError:
                continue
    return None

def forecast(ticker, on, last_end, prev):
    if not last_end:
        return prev
    raw=fetch(f"https://api.nasdaq.com/api/analyst/{ticker}/earnings-forecast",json_data=True)
    rows=(((raw or {}).get("data") or {}).get("quarterlyForecast") or {}).get("rows") or []
    samples=[]
    for row in rows:
        try:
            month=datetime.strptime(row["fiscalEnd"],"%b %Y").date()
            end=month.replace(day=calendar.monthrange(month.year,month.month)[1])
            gap=(end-date.fromisoformat(last_end)).days
            value=float(str(row["consensusEPSForecast"]).replace("$","").replace(",",""))
            if 65 <= gap <= 116 and math.isfinite(value):
                samples.append((end.isoformat(),value))
        except (ValueError,TypeError,KeyError):
            continue
    alt_url = f"https://www.quotelinks.com/forecast/{ticker.lower()}.html"
    if not samples:
        table = revision_table(fetch(alt_url),alt_url,on,last_end)
        return table or prev
    end, val=min(samples)
    history=dict(prev.get("history",{})) if end==prev.get("period_end") else {}
    history[on]=val
    history={d:v for d,v in history.items() if 0 <= (date.fromisoformat(on)-date.fromisoformat(d)).days <= 40}
    reference = [d for d in history if 7 <= (date.fromisoformat(on)-date.fromisoformat(d)).days <= 35]
    result={"as_of":on,"period_end":end,"history":history,"url":f"https://www.nasdaq.com/market-activity/stocks/{ticker.lower()}/earnings"}
    if reference:
        base=history[min(reference)]
        result["direction"]="up" if val>base else "down" if val<base else "flat"
    else:
        table = revision_table(fetch(alt_url),alt_url,on,last_end)
        if table and table["period_end"] == end:
            result = dict(table,history=history)
    return result

def main():
    import csv
    import io
    on=datetime.now(timezone.utc).date().isoformat()
    watch={r["ticker"] for r in load_file("user_config.json")["watchlist"]}
    earnings=load_file("watchlist_earnings.json")["records"]
    cycles=load_file("watchlist_screen.json")["screens"].get("W",{}).get("results",{})
    prior=load_file("leader_research.json")["records"]
    output={t:prior.get(t,{}) for t in sorted(watch)}
    unknown=[t for t,r in output.items() if not r.get("cik") and t not in ETFS]
    ids=fetch(SEC+"/files/company_tickers.json",json_data=True) if unknown else {}
    registry={v["ticker"]:str(v["cik_str"]).zfill(10) for v in (ids or {}).values()}
    sectors={}
    if any(not r.get("sector_etf") and t not in ETFS for t,r in output.items()):
        csv_text=fetch("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv")
        if csv_text:
            sectors={r["Symbol"]:GICS.get(r["GICS Sector"]) for r in csv.DictReader(io.StringIO(csv_text))}
    for ticker, fact in output.items():
        if ticker in ETFS:
            output[ticker]={"nonissuer":True}
            continue
        cik=fact.get("cik") or registry.get(ticker.replace(".","-"))
        if not cik or not re.fullmatch(r"[A-Z0-9.-]{1,10}",ticker):
            continue
        fact["cik"]=cik
        if not fact.get("sector_etf") and sectors.get(ticker):
            fact["sector_etf"]=sectors[ticker]
        active=(cycles.get(ticker,{}).get("cycle") or {}).get("state") in {"candidate","emerging"}
        er=earnings.get(ticker) or {}
        if not active and fact.get("fiscal_period") == er.get("period") and fact.get("quarters"):
            continue
        old=fact.get("quarters",[])
        if not old or fact.get("fiscal_period") != er.get("period") or active and fact.get("as_of")!=on:
            raw=fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json",json_data=True)
            if raw and raw.get("facts",{}).get("us-gaap"):
                updated=quarterly_metrics(raw,old,on)
                if updated:
                    fact["quarters"]=updated
                    old_end=max((r[0] for r in old),default=None)
                    label=fiscal_label(fact.get("fiscal_period"),old_end,updated[0][0])
                    fact["fiscal_period"]=label
                    fact["as_of"]=on
        if not active:
            continue
        last_end=max((r[0] for r in fact.get("quarters",[])),default=None)
        if fact.get("review",{}).get("checked")!=on or fact.get("review",{}).get("last_earnings")!=er.get("accession"):
            submission=fetch(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json",json_data=True)
            if submission and submission.get("filings"):
                rows=filings(submission,on)
                prior_review=fact.get("review",{})
                updated_review=review(rows,cik,on,er.get("reported_on"),last_end,prior_review)
                if updated_review and updated_review is not prior_review:
                    fact["review"]=dict(updated_review,last_earnings=er.get("accession"))
                if not fact.get("fiscal_period") and er.get("period") and any(
                    r["form"] in PERIOD_FORMS and r["reportDate"]==last_end and er.get("reported_on") and
                    abs((date.fromisoformat(r["filingDate"])-date.fromisoformat(er["reported_on"])).days)<=7
                    for r in rows):
                    fact["fiscal_period"]=er["period"]
        old_revision=fact.get("revision",{})
        if old_revision.get("as_of")!=on:
            rev=forecast(ticker,on,last_end,old_revision)
            if rev:
                fact["revision"]=rev
    lines=[f"    {json.dumps(k)}: {json.dumps(v,ensure_ascii=False,separators=(',',':'))}" for k,v in sorted(output.items())]
    (DATA/"leader_research.json").write_text('{\n  "version": 1,\n  "records": {\n'+',\n'.join(lines)+'\n  }\n}\n',encoding="utf-8")
    print(f"Watchlist {len(output)} | financial histories {sum(bool(v.get('quarters')) for v in output.values())} | SEC screens checked today {sum(v.get('review',{}).get('checked')==on for v in output.values())}")

if __name__ == "__main__":
    main()
