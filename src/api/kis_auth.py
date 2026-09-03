import os
import json
import logging
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("KISAuth")


def get_secret_val(key: str, default: str = "") -> str:
    """환경변수(.env) 또는 Streamlit Cloud Secrets에서 안전하게 설정값 읽기"""
    val = os.getenv(key, "")
    if val:
        return val

    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass

    return default


REAL_URL = "https://openapi.koreainvestment.com:9443"
PAPER_URL = "https://openapivts.koreainvestment.com:29443"
TOKEN_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


class KISAuth:
    """한국투자증권(KIS) 계좌별 독립 AppKey/Secret 및 토큰 관리자 (최신 공식 GitHub 스펙 반영)"""

    def __init__(self):
        is_paper_str = get_secret_val("KIS_IS_PAPER_TRADING", "false").lower()
        self.is_paper = is_paper_str == "true"
        self.base_url = PAPER_URL if self.is_paper else REAL_URL

        # 등록된 계좌별 인증 정보 로드 (최대 5개 계좌 지원)
        self.accounts = self._load_accounts()

    def _load_accounts(self) -> list:
        accounts = []

        # 1번 계좌 (기본)
        k1 = get_secret_val("KIS_APP_KEY", "").strip()
        s1 = get_secret_val("KIS_APP_SECRET", "").strip()
        c1 = get_secret_val("KIS_CANO", "").strip()
        p1 = get_secret_val("KIS_ACNT_PRDT_CD", "01").strip()
        if k1 and s1 and c1 and not k1.startswith("your_"):
            accounts.append({"idx": 1, "name": f"계좌 1 ({c1[-4:]}-{p1})", "app_key": k1, "app_secret": s1, "cano": c1, "acnt_prdt_cd": p1})

        # 2번 계좌 (별도 AppKey / Secret)
        k2 = get_secret_val("KIS_APP_KEY_2", "").strip()
        s2 = get_secret_val("KIS_APP_SECRET_2", "").strip()
        c2 = get_secret_val("KIS_CANO_2", "").strip()
        p2 = get_secret_val("KIS_ACNT_PRDT_CD_2", "01").strip()
        if c2 and not c2.startswith("your_"):
            k2 = k2 if k2 else k1
            s2 = s2 if s2 else s1
            if k2 and s2:
                accounts.append({"idx": 2, "name": f"계좌 2 ({c2[-4:]}-{p2})", "app_key": k2, "app_secret": s2, "cano": c2, "acnt_prdt_cd": p2})

        # 3번 계좌 (별도 AppKey / Secret)
        k3 = get_secret_val("KIS_APP_KEY_3", "").strip()
        s3 = get_secret_val("KIS_APP_SECRET_3", "").strip()
        c3 = get_secret_val("KIS_CANO_3", "").strip()
        p3 = get_secret_val("KIS_ACNT_PRDT_CD_3", "01").strip()
        if c3 and not c3.startswith("your_"):
            k3 = k3 if k3 else k1
            s3 = s3 if s3 else s1
            if k3 and s3:
                accounts.append({"idx": 3, "name": f"계좌 3 ({c3[-4:]}-{p3})", "app_key": k3, "app_secret": s3, "cano": c3, "acnt_prdt_cd": p3})

        return accounts

    @property
    def is_configured(self) -> bool:
        return len(self.accounts) > 0

    @property
    def app_key(self) -> str:
        return self.accounts[0]["app_key"] if self.accounts else ""

    @property
    def app_secret(self) -> str:
        return self.accounts[0]["app_secret"] if self.accounts else ""

    @property
    def cano(self) -> str:
        return self.accounts[0]["cano"] if self.accounts else ""

    @property
    def acnt_prdt_cd(self) -> str:
        return self.accounts[0]["acnt_prdt_cd"] if self.accounts else "01"

    def get_accounts_list(self) -> list:
        return self.accounts

    def get_access_token(self, account_idx: int = 1) -> str:
        """특정 계좌의 AppKey/Secret으로 발급된 유효 토큰 반환 (1일 1회 발급 원칙 및 24시간 캐시)"""
        acc = next((a for a in self.accounts if a["idx"] == account_idx), None)
        if not acc:
            acc = self.accounts[0] if self.accounts else None
        if not acc:
            return ""

        cache_file = os.path.join(TOKEN_CACHE_DIR, f"kis_token_acc{acc['idx']}.json")

        # 1. 로컬 캐시 유효성 확인
        cached = self._read_cached_token(cache_file)
        if cached:
            return cached

        # 2. 만료 시 신규 발급
        return self._issue_new_token(acc, cache_file)

    def _read_cached_token(self, cache_file: str) -> str:
        if not os.path.exists(cache_file):
            return ""

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            expires_at = datetime.fromisoformat(data.get("expires_at", "2000-01-01T00:00:00"))
            # 만료 1시간 전까지는 기존 캐시된 토큰을 유지하여 잦은 발급 알림톡 방지
            if datetime.now() + timedelta(hours=1) < expires_at:
                return data.get("access_token", "")
        except Exception:
            pass

        return ""

    def _issue_new_token(self, acc: dict, cache_file: str) -> str:
        endpoint = f"{self.base_url}/oauth2/tokenP"
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        body = {
            "grant_type": "client_credentials",
            "appkey": acc["app_key"],
            "appsecret": acc["app_secret"],
        }

        try:
            res = requests.post(endpoint, headers=headers, json=body, timeout=10)
            data = res.json()

            if res.status_code == 200 and "access_token" in data:
                token = data["access_token"]

                # KIS 공식 응답의 만료 일시 파싱 (access_token_token_expired)
                expired_str = data.get("access_token_token_expired", "")
                if expired_str:
                    try:
                        expires_at = datetime.strptime(expired_str, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        expires_in = int(data.get("expires_in", 86400))
                        expires_at = datetime.now() + timedelta(seconds=expires_in)
                else:
                    expires_in = int(data.get("expires_in", 86400))
                    expires_at = datetime.now() + timedelta(seconds=expires_in)

                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "access_token": token,
                            "expires_at": expires_at.isoformat(),
                            "access_token_token_expired": expired_str,
                            "token_type": data.get("token_type", "Bearer"),
                        },
                        f,
                        indent=2,
                    )
                return token
            else:
                err_msg = data.get("error_description", data.get("msg1", res.text))
                print(f"[KISAuth] Token error ({res.status_code}): {err_msg}")
                return ""
        except Exception as e:
            print(f"[KISAuth] Token request failed: {e}")
            return ""

    def get_hashkey(self, body: dict, account_idx: int = 1) -> str:
        """KIS 공식 Hashkey 발급 (POST 주문 요청 무결성 검증용)"""
        acc = next((a for a in self.accounts if a["idx"] == account_idx), None) or self.accounts[0]
        endpoint = f"{self.base_url}/uapi/hashkey"
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "appkey": acc["app_key"],
            "appsecret": acc["app_secret"],
        }
        try:
            res = requests.post(endpoint, headers=headers, json=body, timeout=5)
            if res.status_code == 200:
                return res.json().get("HASH", "")
        except Exception:
            pass
        return ""

    def get_common_headers(self, tr_id: str, account_idx: int = 1, tr_cont: str = "", hashkey: str = "") -> dict:
        """KIS API 표준 공통 헤더 생성"""
        acc = next((a for a in self.accounts if a["idx"] == account_idx), None)
        if not acc:
            acc = self.accounts[0] if self.accounts else {"app_key": "", "app_secret": ""}

        token = self.get_access_token(account_idx=acc.get("idx", 1))
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "authorization": f"Bearer {token}",
            "appkey": acc["app_key"],
            "appsecret": acc["app_secret"],
            "tr_id": tr_id,
            "custtype": "P",
        }
        if tr_cont:
            headers["tr_cont"] = tr_cont
        if hashkey:
            headers["hashkey"] = hashkey

        return headers
