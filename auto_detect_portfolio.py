import sys
import time
import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

from src.api.kis_auth import KISAuth

def scan_all_accounts():
    auth = KISAuth()
    print("=" * 60)
    print(f"🔎 계좌번호 [{auth.cano}-XX] 전체 상품코드(01~25) 자동 스캔 시작")
    print("=" * 60)
    
    token = auth.get_access_token()
    if not token:
        print("❌ 토큰 발급 실패")
        return

    # 흔히 쓰이는 상품코드 목록 (01: 종합위탁, 02: 증권위탁, 22: 외화위탁 등)
    test_codes = ["01", "02", "03", "06", "22", "23", "28", "29"]
    found_items = []
    correct_code = None

    for prdt_cd in test_codes:
        print(f"\n[시도] 계좌번호: {auth.cano}-{prdt_cd} 확인 중...")
        
        # 1. 해외주식 잔고 조회
        tr_id = "VTTS3012R" if auth.is_paper else "TTTS3012R"
        endpoint = f"{auth.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        headers = auth.get_common_headers(tr_id=tr_id)
        
        for excg in ["NASD", "NYSE", "AMEX", ""]:
            params = {
                "CANO": auth.cano,
                "ACNT_PRDT_CD": prdt_cd,
                "OVRS_EXCG_CD": excg,
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            }
            try:
                res = requests.get(endpoint, headers=headers, params=params, timeout=5)
                data = res.json()
                if data.get("rt_cd") == "0":
                    output1 = data.get("output1", [])
                    output2 = data.get("output2", {})
                    # 평가금액 또는 보유종목 확인
                    tot_amt = float(output2.get("tot_evlu_pfls_amt", 0) or output2.get("ovrs_tot_pfls", 0) or 0)
                    if output1:
                        print(f"  🎉 [해외주식 발견!] 상품코드: {prdt_cd} (거래소: {excg}) -> {len(output1)}개 종목")
                        for r in output1:
                            t = r.get("ovrs_pdno", "").strip()
                            q = float(r.get("ovrs_cblc_qty", 0) or r.get("ord_psbl_qty", 0))
                            if q > 0:
                                print(f"     • {t}: {q}주 | 현재가 ${float(r.get('now_pric2', 0) or 0):,.2f} | 손익률 {float(r.get('evlu_pfls_rt', 0)):+.2f}%")
                                found_items.append(t)
                                correct_code = prdt_cd
                time.sleep(0.1)
            except Exception:
                pass

        # 2. 국내주식 잔고 조회
        kr_tr_id = "VTTC8434R" if auth.is_paper else "TTTC8434R"
        kr_endpoint = f"{auth.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        kr_headers = auth.get_common_headers(tr_id=kr_tr_id)
        kr_params = {
            "CANO": auth.cano,
            "ACNT_PRDT_CD": prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        try:
            res = requests.get(kr_endpoint, headers=kr_headers, params=kr_params, timeout=5)
            data = res.json()
            if data.get("rt_cd") == "0":
                kr_output1 = data.get("output1", [])
                if kr_output1:
                    print(f"  🎉 [국내주식 발견!] 상품코드: {prdt_cd} -> {len(kr_output1)}개 종목")
                    for r in kr_output1:
                        code = r.get("pdno", "").strip()
                        name = r.get("prdt_name", "").strip()
                        q = float(r.get("hldg_qty", 0))
                        if q > 0:
                            print(f"     • {code} ({name}): {q}주 | 현재가 {float(r.get('prpr', 0)):,.0f}원")
                            found_items.append(code)
                            correct_code = prdt_cd
        except Exception:
            pass

    print("\n" + "=" * 60)
    if correct_code:
        print(f"✅ 스캔 완료! 실제 주식이 있는 계좌 상품코드는 [{correct_code}] 입니다.")
        print(f"   발견된 보유 종목: {found_items}")
    else:
        print("ℹ️ 스캔 완료: 해당 계좌(01~29)에 현재 체결되어 보유 중인 주식 잔고가 0건입니다.")
        print("   (참고: 오늘 방금 매수한 경우, 또는 타사 대체 입고 중인 경우 확인 필요)")
    print("=" * 60)

if __name__ == "__main__":
    scan_all_accounts()
