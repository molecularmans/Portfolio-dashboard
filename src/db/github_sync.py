import os
import json
import base64
import requests
from datetime import datetime

CONFIG_PATH = "data/user_config.json"
DEFAULT_REPO = "molecularmans/Portfolio-dashboard"


def get_github_env_val(key: str, default: str = "") -> str:
    """환경변수 또는 Streamlit Secrets에서 값 읽기"""
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


class GitHubSync:
    """GitHub 저장소를 통한 사용자 설정(그룹, 관심종목, 이평선) 영구 동기화 엔진"""

    def __init__(self):
        self.token = get_github_env_val("GITHUB_TOKEN", "").strip()
        self.repo = get_github_env_val("GITHUB_REPO", DEFAULT_REPO).strip()
        self.api_base = "https://api.github.com"

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.repo)

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def fetch_config_from_github(self) -> dict:
        """GitHub 저장소에서 user_config.json 읽어오기"""
        if not self.is_configured:
            # 토큰이 없으면 로컬 파일에서 읽기 시도
            return self.read_local_config()

        url = f"{self.api_base}/repos/{self.repo}/contents/{CONFIG_PATH}"
        try:
            res = requests.get(url, headers=self.get_headers(), timeout=6)
            if res.status_code == 200:
                data = res.json()
                content_b64 = data.get("content", "")
                decoded = base64.b64decode(content_b64).decode("utf-8")
                config = json.loads(decoded)
                # 로컬에도 캐싱
                self.save_local_config(config)
                return config
            elif res.status_code == 404:
                return self.read_local_config()
        except Exception as e:
            print(f"[GitHubSync] fetch error: {e}")

        return self.read_local_config()

    def save_config_to_github(self, config_dict: dict) -> bool:
        """GitHub 저장소에 user_config.json 자동 커밋 & 푸시"""
        # 1. 로컬에 먼저 안전하게 저장
        self.save_local_config(config_dict)

        if not self.is_configured:
            return False

        url = f"{self.api_base}/repos/{self.repo}/contents/{CONFIG_PATH}"
        headers = self.get_headers()

        # 기존 파일의 SHA 해시값 확인 (PUT 요청에 필요)
        sha = None
        try:
            get_res = requests.get(url, headers=headers, timeout=5)
            if get_res.status_code == 200:
                sha = get_res.json().get("sha")
        except Exception:
            pass

        content_str = json.dumps(config_dict, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": f"Auto-sync user settings [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]",
            "content": content_b64,
        }
        if sha:
            payload["sha"] = sha

        try:
            put_res = requests.put(url, headers=headers, json=payload, timeout=8)
            return put_res.status_code in [200, 201]
        except Exception as e:
            print(f"[GitHubSync] push error: {e}")
            return False

    def read_local_config(self) -> dict:
        local_file = os.path.join(os.path.dirname(__file__), "..", "..", CONFIG_PATH)
        if os.path.exists(local_file):
            try:
                with open(local_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_local_config(self, config_dict: dict):
        local_file = os.path.join(os.path.dirname(__file__), "..", "..", CONFIG_PATH)
        os.makedirs(os.path.dirname(local_file), exist_ok=True)
        try:
            with open(local_file, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[GitHubSync] local save error: {e}")
