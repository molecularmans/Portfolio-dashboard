import sys
import json
import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

from src.api.kis_auth import KISAuth

def mask_string(s: str, visible: int = 4) -> str:
    if not s or len(s) <= visible:
        return "****"
    return s[:visible] + "*" * (len(s) - visible)

def test_balance():
    auth = KISAuth()
    print("=" * 60)
    print("🔍 KIS 계좌 잔고 상세 진단 (해외주식 + 국내주식)")
    print("=" * 60)
    
    token = auth.get_access_token()
    if not token:
        print("❌ 토큰 발급 실패")
        return

    # 1. 해외주식 잔고 조회 (TTTS3012R / VTTS3012R) - 주요 거래소(NASD, NYSE, AMEX, 전체) 순회
    print("\n[1] 해외주식 잔고 조회 테스트...")
    tr_id = "VTTS3012R" if auth.is_paper else "TTTS3012R"
    endpoint = f"{auth.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
    headers = auth.get_common_headers(tr_id=tr_id)

    # 거래소 코드 테스트 (NASD, NYSE, AMEX, 공백)
    exchanges = ["NASD", "NYSE", "AMEX", ""]
    found_overseas = []

    for excg in exchanges:
        params = {
            "CANO": auth.cano,
            "ACNT_PRDT_CD": auth.acnt_prdt_cd,
            "OVRS_EXCG_CD": excg,
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        try:
            res = requests.get(endpoint, headers=headers, params=params, timeout=10)
            data = res.json()
            rt_cd = data.get("rt_cd")
            msg1 = data.get("msg1")
            
            if rt_cd == "0":
                output1 = data.get("output1", [])
                output2 = data.get("output2", {})
                if output1:
                    print(f"  • 거래소 [{excg if excg else '전체'}]: {len(output1)}개 종목 발견!")
                    for row in output1:
                        ticker = row.get("ovrs_pdno", "").strip()
                        name = row.get("ovrs_item_name", "").strip()
                        qty = float(row.get("ovrs_cblc_qty", 0) or row.get("ord_psbl_qty", 0))
                        avg_p = float(row.get("pchs_avg_pric", 0))
                        now_p = float(row.get("now_pric2", 0) or row.get("ovrs_now_pric1", 0))
                        pl_rt = float(row.get("evlu_pfls_rt", 0))
                        eval_amt = float(row.get("ovrs_stck_evlu_amt", 0))
                        
                        if qty > 0:
                            found_overseas.append({
                                "ticker": ticker,
                                "name": name,
                                "qty": qty,
                                "avg_price": avg_p,
                                "current_price": now_p,
                                "profit_rate": pl_rt,
                                "eval_amount": eval_amt,
                            })
                            print(f"    - {ticker} ({name}): {qty}주 | 평단 ${avg_p:,.2f} | 현재가 ${now_p:,.2f} | 손익률 {pl_rt:+.2f}% | 평가금액 ${eval_amt:,.2f}")
                else:
                    print(f"  • 거래소 [{excg if excg else '전체'}]: 보유 내역 없음 (응답 정상)")
            else:
                print(f"  • 거래소 [{excg if excg else '전체'}] 호출 오류: {msg1}")
        except Exception as e:
            print(f"  • 요청 예외 ({excg}): {e}")

    # 2. 국내주식 잔고 조회 (TTTC8434R / VTTC8434R)
    print("\n[2] 국내주식 잔고 조회 테스트...")
    kr_tr_id = "VTTC8434R" if auth.is_paper else "TTTC8434R"
    kr_endpoint = f"{auth.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
    kr_headers = auth.get_common_headers(tr_id=kr_tr_id)
    kr_params = {
        "CANO": auth.cano,
        "ACNT_PRDT_CD": auth.acnt_prdt_cd,
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
        res = requests.get(kr_endpoint, headers=kr_headers, params=kr_params, timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0":
            kr_output1 = data.get("output1", [])
            if kr_output1:
                print(f"  • 국내주식: {len(kr_output1)}개 종목 발견!")
                for row in kr_output1:
                    code = row.get("pdno", "").strip()
                    name = row.get("prdt_name", "").strip()
                    qty = float(row.get("hldg_qty", 0))
                    avg_p = float(row.get("pchs_avg_pric", 0))
                    now_p = float(row.get("prpr", 0))
                    pl_rt = float(row.get("evlu_pfls_rt", 0))
                    print(f"    - {code} ({name}): {qty}주 | 평단 {avg_p:,.0f}원 | 현재가 {now_p:,.0f}원 | 손익률 {pl_rt:+.2f}%")
            else:
                print("  • 국내주식: 보유 내역 없음 (0건)")
        else:
            print(f"  • 국내 잔고 응답: {data.get('msg1')}")
    except Exception as e:
        print(f"  • 국내 잔고 예외: {e}")

if __name__ == "__main__":
    test_balance()
