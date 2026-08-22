import os
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import requests

from .kis_auth import KISAuth

# 미국 주요 거래소 매핑
US_EXCHANGE_MAP = {
    # NYSE 상장 종목
    "EME": "NYS", "ORCL": "NYS", "RTX": "NYS", "STRL": "NYS", "TSM": "NYS",
    "PLTR": "NYS", "BABA": "NYS", "NIO": "NYS", "SPOT": "NYS", "UBER": "NYS",
    "RBLX": "NYS", "SNOW": "NYS", "NET": "NYS", "DIS": "NYS", "KO": "NYS",
    "PFE": "NYS", "VST": "NYS", "DE": "NYS", "CAT": "NYS", "IBM": "NYS",
    # AMEX 상장 종목
    "SPY": "AMS", "IVV": "AMS", "VOO": "AMS", "DIA": "AMS", "IWM": "AMS",
}


class KISClient:
    """한국투자증권(KIS) REST API 클라이언트 (거래소 자동 탐색 및 최신 시세 수집)"""

    def __init__(self, auth: KISAuth = None):
        self.auth = auth or KISAuth()
        self.base_url = self.auth.base_url

    def is_configured(self) -> bool:
        return self.auth.is_configured

    # ==========================================
    # 1. 미국 주식 기간별 시세 (거래소 자동 탐색)
    # ==========================================
    def get_us_ohlcv(self, ticker: str, timeframe: str = "D", count: int = 250) -> pd.DataFrame:
        """미국 주식 일/주/월봉 데이터 조회 (HHDFS76240000 - NAS, NYS, AMS 자동 탐색)"""
        ticker_clean = ticker.upper().strip()
        if not self.is_configured():
            return self._generate_mock_ohlcv(ticker_clean, timeframe=timeframe, count=count)

        gubn_map = {"D": "0", "W": "1", "M": "2"}
        gubn = gubn_map.get(timeframe.upper(), "0")

        endpoint = f"{self.base_url}/uapi/overseas-price/v1/quotations/dailyprice"
        headers = self.auth.get_common_headers(tr_id="HHDFS76240000", account_idx=1)

        # 1순위: 매핑된 거래소, 없으면 NAS -> NYS -> AMS 순서로 시도
        preferred_ex = US_EXCHANGE_MAP.get(ticker_clean, "NAS")
        ex_candidates = [preferred_ex] + [e for e in ["NAS", "NYS", "AMS"] if e != preferred_ex]

        for excd in ex_candidates:
            all_records = []
            last_date = ""
            iterations = (count + 99) // 100

            success = False
            for _ in range(iterations):
                params = {
                    "AUTH": "",
                    "EXCD": excd,
                    "SYMB": ticker_clean,
                    "GUBN": gubn,
                    "BYMD": last_date,
                    "MODP": "1",
                }

                try:
                    res = requests.get(endpoint, headers=headers, params=params, timeout=8)
                    data = res.json()

                    if res.status_code != 200 or data.get("rt_cd") != "0":
                        break

                    output2 = data.get("output2", [])
                    if not output2:
                        break

                    for row in output2:
                        date_str = row.get("xymd", "")
                        if not date_str:
                            continue

                        all_records.append({
                            "date": pd.to_datetime(date_str, format="%Y%m%d"),
                            "open": float(row.get("open", 0)),
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "close": float(row.get("clos", 0)),
                            "volume": float(row.get("tvol", 0)),
                        })

                    last_item = output2[-1]
                    last_date = last_item.get("xymd", "")
                    success = True

                    if len(all_records) >= count:
                        break

                    time.sleep(0.1)

                except Exception:
                    break

            if success and len(all_records) >= 5:
                df = pd.DataFrame(all_records).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
                return df.tail(count)

        # 모든 거래소 탐색 실패 시에만 fallback
        return self._generate_mock_ohlcv(ticker_clean, timeframe=timeframe, count=count)

    # ==========================================
    # 2. 국내 주식 기간별 시세
    # ==========================================
    def get_kr_ohlcv(self, ticker: str, timeframe: str = "D", count: int = 250) -> pd.DataFrame:
        ticker_clean = ticker.strip()
        if not self.is_configured():
            return self._generate_mock_ohlcv(ticker_clean, timeframe=timeframe, count=count)

        endpoint = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        headers = self.auth.get_common_headers(tr_id="FHKST01010400", account_idx=1)

        days_back = count * (1.6 if timeframe == "D" else (7.5 if timeframe == "W" else 31.0))
        end_date = datetime.today().strftime("%Y%m%d")
        start_date = (datetime.today() - timedelta(days=int(days_back))).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker_clean,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": timeframe.upper(),
            "FID_ORG_ADJ_PRC": "0",
        }

        try:
            res = requests.get(endpoint, headers=headers, params=params, timeout=8)
            data = res.json()

            if res.status_code != 200 or data.get("rt_cd") != "0":
                return self._generate_mock_ohlcv(ticker_clean, timeframe=timeframe, count=count)

            records = []
            for row in data.get("output2", []):
                date_str = row.get("stck_bsop_date", "")
                if not date_str:
                    continue
                records.append({
                    "date": pd.to_datetime(date_str, format="%Y%m%d"),
                    "open": float(row.get("stck_oprc", 0)),
                    "high": float(row.get("stck_hgpr", 0)),
                    "low": float(row.get("stck_lwpr", 0)),
                    "close": float(row.get("stck_clpr", 0)),
                    "volume": float(row.get("acml_vol", 0)),
                })

            if not records:
                return self._generate_mock_ohlcv(ticker_clean, timeframe=timeframe, count=count)

            df = pd.DataFrame(records).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
            return df.tail(count)

        except Exception:
            return self._generate_mock_ohlcv(ticker_clean, timeframe=timeframe, count=count)

    # ==========================================
    # 3. 해외주식 잔고 조회 (계좌별 독립 토큰/헤더 호출)
    # ==========================================
    def get_overseas_balance(self, account_idx: int = 1) -> list:
        acc = next((a for a in self.auth.accounts if a["idx"] == account_idx), None)
        if not acc:
            acc = self.auth.accounts[0] if self.auth.accounts else None
        if not acc:
            return self._get_mock_portfolio()

        tr_id = "VTTS3012R" if self.auth.is_paper else "TTTS3012R"
        endpoint = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        headers = self.auth.get_common_headers(tr_id=tr_id, account_idx=acc["idx"])

        items_dict = {}

        for excg in ["NASD", "NYSE", "AMEX", ""]:
            params = {
                "CANO": acc["cano"],
                "ACNT_PRDT_CD": acc["acnt_prdt_cd"],
                "OVRS_EXCG_CD": excg,
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            }

            try:
                res = requests.get(endpoint, headers=headers, params=params, timeout=8)
                data = res.json()
                if data.get("rt_cd") == "0":
                    for item in data.get("output1", []):
                        ticker = item.get("ovrs_pdno", "").strip().upper()
                        if not ticker:
                            continue

                        qty = float(item.get("ovrs_cblc_qty", 0) or item.get("ord_psbl_qty", 0) or item.get("cblc_qty13", 0) or 0)
                        if qty > 0 and ticker not in items_dict:
                            avg_p = float(item.get("pchs_avg_pric", 0) or 0)
                            now_p = float(item.get("now_pric2", 0) or item.get("ovrs_now_pric1", 0) or 0)
                            pl_rt = float(item.get("evlu_pfls_rt", 0) or 0)
                            eval_amt = float(item.get("ovrs_stck_evlu_amt", 0) or (qty * now_p))

                            items_dict[ticker] = {
                                "ticker": ticker,
                                "name": item.get("ovrs_item_name", ticker).strip(),
                                "qty": qty,
                                "avg_price": avg_p,
                                "current_price": now_p,
                                "profit_rate": pl_rt,
                                "eval_amount": eval_amt,
                                "account": acc["name"],
                            }
                time.sleep(0.1)
            except Exception:
                pass

        return list(items_dict.values())

    def get_combined_balance(self) -> list:
        accounts = self.auth.get_accounts_list()
        if not accounts:
            return self.get_overseas_balance(1)

        combined_map = {}
        for acc in accounts:
            acc_items = self.get_overseas_balance(account_idx=acc["idx"])
            for it in acc_items:
                tk = it["ticker"]
                if tk not in combined_map:
                    combined_map[tk] = it.copy()
                else:
                    prev = combined_map[tk]
                    total_qty = prev["qty"] + it["qty"]
                    tot_buy = (prev["qty"] * prev["avg_price"]) + (it["qty"] * it["avg_price"])
                    new_avg = tot_buy / total_qty if total_qty > 0 else 0
                    new_eval = prev["eval_amount"] + it["eval_amount"]
                    new_profit_rate = ((it["current_price"] - new_avg) / new_avg * 100) if new_avg > 0 else 0

                    combined_map[tk] = {
                        "ticker": tk,
                        "name": it["name"],
                        "qty": total_qty,
                        "avg_price": new_avg,
                        "current_price": it["current_price"],
                        "profit_rate": new_profit_rate,
                        "eval_amount": new_eval,
                        "account": "전체 계좌 합산",
                    }

        return list(combined_map.values())

    # ==========================================
    # 4. Mock Data Generator (최신 일자 기준 생성)
    # ==========================================
    def _generate_mock_ohlcv(self, ticker: str, timeframe: str = "D", count: int = 250) -> pd.DataFrame:
        seed = sum(ord(c) for c in ticker) + (10 if timeframe == "W" else (20 if timeframe == "M" else 0))
        np.random.seed(seed)

        end_date = datetime.today()
        if timeframe == "M":
            dates = pd.date_range(end=end_date, periods=count, freq="ME")
            volatility = 0.05
            drift = 0.008
        elif timeframe == "W":
            dates = pd.date_range(end=end_date, periods=count, freq="W-FRI")
            volatility = 0.035
            drift = 0.002
        else:
            dates = pd.bdate_range(end=end_date, periods=count)
            volatility = 0.02
            drift = 0.0008

        base_price_map = {
            "NVDA": 130.0, "AAPL": 225.0, "MSFT": 415.0, "GOOGL": 165.0,
            "AMZN": 185.0, "TSLA": 210.0, "ORCL": 140.0, "MRVL": 75.0,
            "BOTZ": 36.0, "MU": 105.0, "HOOD": 22.0, "EME": 380.0, "COHR": 85.0,
        }
        start_price = base_price_map.get(ticker.upper(), 100.0)

        daily_returns = np.random.normal(drift, volatility, count)
        price_series = start_price * np.cumprod(1 + daily_returns)

        records = []
        for d, close in zip(dates, price_series):
            bar_vol = close * np.random.uniform(0.01, volatility * 1.2)
            open_p = close + np.random.uniform(-bar_vol * 0.5, bar_vol * 0.5)
            high_p = max(open_p, close) + abs(np.random.uniform(0, bar_vol * 0.7))
            low_p = min(open_p, close) - abs(np.random.uniform(0, bar_vol * 0.7))
            vol_mult = 4.0 if timeframe == "W" else (16.0 if timeframe == "M" else 1.0)
            vol = int(np.random.uniform(1000000, 8000000) * vol_mult)

            records.append({
                "date": pd.to_datetime(d),
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close, 2),
                "volume": vol,
            })

        return pd.DataFrame(records)

    def _get_mock_portfolio(self) -> list:
        return [
            {"ticker": "GOOGL", "name": "알파벳 A", "qty": 37, "avg_price": 237.94, "current_price": 344.82, "profit_rate": 44.92, "eval_amount": 12758.34},
            {"ticker": "BOTZ", "name": "Global X Robotics & AI", "qty": 32, "avg_price": 37.58, "current_price": 36.04, "profit_rate": -4.10, "eval_amount": 1153.28},
        ]
