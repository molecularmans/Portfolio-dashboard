import unittest
from collections import Counter
from unittest.mock import patch

import pandas as pd

from scripts import update_leader_evidence as updater
from src.ui.leader_view import research_rows
from src.indicators.leader_research import assess, completed_us_week, latest_us_session, performance

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.on="2026-11-27"
        self.cycle={"state":"candidate","first_date":"2024-11-22","weeks":104,"date":"2026-11-20"}
        quarters=[]
        for i,t in enumerate(pd.date_range("2021-03-31","2026-09-30",freq="QE")):
            quarters.append([t.date().isoformat(),round(100*(1.004**(i*i)),4),round(300*(1.003**(i*i)),4)])
        system={"value":"up","date":"2026-11-05","url":"https://example.test/source"}
        self.fact={"fiscal_period":"FY2026 Q3","quarters":quarters,
                   "review":{"checked":self.on,"risk":dict(system,value="screened"),
                             "guidance":system.copy(),"demand":system.copy(),
                             "forward":dict(system,oi_yoy=150,period_end="2026-12-31")},
                   "revision":{"as_of":self.on,"period_end":"2026-12-31","direction":"up","url":"https://example.test/eps"}}
        self.market={"date":"2026-11-25","stock":{"20":1,"60":4,"120":5},"sector":{"20":1,"60":3,"120":4}}
        self.earnings={"period":"FY2026 Q3","reported_on":"2026-11-05"}
    def grade(self):
        return assess("EXAMPLE",self.cycle,self.market,self.fact,self.earnings,self.on,"2026-11-25")
    def test_positive_confirmed_and_provisional(self):
        self.assertEqual(self.grade()["최종 등급"],"확정 주도주")
        del self.fact["review"]["forward"]
        self.assertEqual(self.grade()["최종 등급"],"부상 주도주")
    def test_incomplete_and_failed_are_distinct(self):
        self.market["sector"]["20"]=-2
        self.assertEqual(self.grade()["최종 등급"],"조건 미충족")
        self.market["date"]="2026-11-24"
        self.assertEqual(self.grade()["최종 등급"],"판정 보류")
        self.assertIn("SPY",self.grade()["미확인 항목"])
    def test_earnings_rollover_and_risk(self):
        self.earnings["period"]="FY2026 Q4"
        self.assertIn("최신 발표 분기",self.grade()["미확인 항목"])
        self.fact["review"]["risk"]["value"]="flagged"
        self.assertEqual(self.grade()["최종 등급"],"공시 위험 검토")
        self.fact["review"]["checked"]="2026-08-01"
        self.assertEqual(self.grade()["최종 등급"],"판정 보류")
    def test_trading_calendar_and_early_close(self):
        self.assertEqual(latest_us_session("2026-11-26T23:00:00+00:00"),"2026-11-25")
        self.assertEqual(latest_us_session("2026-11-27T17:00:00+00:00"),"2026-11-25")
        self.assertEqual(latest_us_session("2026-11-27T18:31:00+00:00"),"2026-11-27")
        self.assertEqual(completed_us_week("2026-11-27").isoformat(),"2026-11-23")
        self.assertEqual(completed_us_week("2026-11-25").isoformat(),"2026-11-16")
    def test_aligned_prices(self):
        prices=pd.Series(range(100,221),dtype=float)
        self.assertEqual(performance(prices,prices),{"20":0,"60":0,"120":0})
        self.assertEqual(performance(prices.drop(112),prices),{})
    def test_only_standalone_quarters_and_verified_q4(self):
        observations=[{"start":a,"end":b,"val":v,"filed":"2026-02-02","form":"10-K"} for a,b,v in
                      [("2025-01-01","2025-03-31",1),("2025-04-01","2025-06-30",2),("2025-07-01","2025-09-30",3),
                       ("2025-01-01","2025-09-30",6),("2025-01-01","2025-12-31",10)]]
        raw={"facts":{"us-gaap":{"OperatingIncomeLoss":{"units":{"USD":observations}}}}}
        self.assertEqual([r[1] for r in updater.quarterly_metrics(raw,[],self.on)],[4,3,2,1])
    def test_same_period_forecast_history(self):
        base={"data":{"quarterlyForecast":{"rows":[{"fiscalEnd":"Dec 2026","consensusEPSForecast":"2.10"}]}}}
        with patch.object(updater,"fetch",return_value=base):
            first=updater.forecast("EXAMPLE","2026-11-10","2026-09-30",{})
            self.assertNotIn("direction",first)
            base["data"]["quarterlyForecast"]["rows"][0]["consensusEPSForecast"]="2.20"
            updated=updater.forecast("EXAMPLE",self.on,"2026-09-30",first)
            self.assertEqual(updated["direction"],"up")
            self.assertIs(updater.forecast("EXAMPLE",self.on,"2026-12-31",updated),updated)
    def test_monthly_revision_has_to_match_the_unreported_quarter(self):
        html="<table><tr><th>Period</th><th>30 days ago</th><th>Now</th></tr><tr><td>Current quarter (Dec '26)</td><td>$2.03</td><td>$2.09</td></tr></table>"
        sample=updater.revision_table(html,"https://example.test/forecast",self.on,"2026-09-30")
        self.assertEqual((sample["period_end"],sample["direction"]),("2026-12-31","up"))
        self.assertIsNone(updater.revision_table(html,"https://example.test/forecast",self.on,"2026-06-30"))
    def test_render_dashboard_research_table(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string("""
from scripts.update_leader_evidence import load_file
from src.ui.leader_view import render_watchlist_leaders
screens=load_file("watchlist_screen.json")["screens"]
render_watchlist_leaders(["AAPL","SPY"],screens["D"],screens["W"])
""").run(timeout=35)
        self.assertFalse(app.exception)
        self.assertTrue(any(e.label=="최종 리서치 판정" for e in app.expander))
        app.radio[0].set_value("전체 결과").run()
        self.assertIn("최종 등급",app.dataframe[-1].value.columns)
    def test_demand_and_guidance_need_explicit_direction(self):
        row=updater.signals("Raises full year guidance. Demand is strengthening.","2026-11-12","https://example.test/report","2026-09-30")
        self.assertEqual((row["guidance"]["value"],row["demand"]["value"]),("up","up"))
        row=updater.signals("We reaffirm our guidance. Demand was stable.","2026-11-12","https://example.test/report","2026-09-30")
        self.assertEqual(row,{})
    def test_dashboard_joins_snapshots_and_reports_coverage(self):
        screens=updater.load_file("watchlist_screen.json")["screens"]
        watch=[r["ticker"] for r in updater.load_file("user_config.json")["watchlist"]]
        facts=updater.load_file("leader_research.json")["records"]
        earnings=updater.load_file("watchlist_earnings.json")["records"]
        rows=research_rows(watch,screens.get("D",{}),screens.get("W",{}),earnings,facts)
        self.assertEqual([r["종목"] for r in rows],watch)
        self.assertTrue(all("일봉 판정" in r and "판정 근거" in r for r in rows))
        print("Dashboard research coverage:",dict(Counter(r["최종 등급"] for r in rows)))
    def test_snapshot_keeps_only_public_filing_links(self):
        facts=updater.load_file("leader_research.json")["records"]
        for f in facts.values():
            for k in ("risk","demand","guidance","forward"):
                source=f.get("review",{}).get(k)
                if source:
                    self.assertTrue(source["url"].startswith("https://www.sec.gov/Archives/"))
if __name__=="__main__":
    unittest.main()
