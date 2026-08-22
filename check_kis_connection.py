import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

from src.api.kis_auth import KISAuth
from src.api.kis_rest import KISClient

def mask_string(s: str, visible: int = 4) -> str:
    if not s or len(s) <= visible:
        return "****"
    return s[:visible] + "*" * (len(s) - visible)

def main():
    print("=" * 60)
    print("🔍 [1/3] 한국투자증권(KIS) 등록 계좌 목록 및 독립 키 확인")
    print("=" * 60)
    
    auth = KISAuth()
    paper_str = "모의투자 (Paper)" if auth.is_paper else "실전투자 (Real)"
    accounts = auth.get_accounts_list()
    
    print(f"• 투자 모드: {paper_str}")
    print(f"• 접속 URL : {auth.base_url}")
    print(f"• 등록 계좌 수: {len(accounts)}개\n")
    
    if not accounts:
        print("❌ [경고] .env 파일에 KIS API Key가 입력되지 않았습니다.")
        return

    for acc in accounts:
        print(f"  [{acc['name']}]")
        print(f"   - App Key  : {mask_string(acc['app_key'], 6)}")
        print(f"   - AppSecret: {mask_string(acc['app_secret'], 6)}")
        print(f"   - 계좌번호 : {mask_string(acc['cano'], 4)}-{acc['acnt_prdt_cd']}")

    print("\n" + "=" * 60)
    print("🔑 [2/3] 각 계좌별 OAuth2 Access Token 발급 테스트")
    print("=" * 60)
    
    for acc in accounts:
        token = auth.get_access_token(account_idx=acc["idx"])
        if token:
            print(f"✅ [{acc['name']}] 독립 토큰 발급 성공! ({mask_string(token, 10)})")
        else:
            print(f"❌ [{acc['name']}] 토큰 발급 실패! AppKey/Secret을 확인하세요.")

    print("\n" + "=" * 60)
    print("💼 [3/3] 각 계좌별 잔고 및 전체 통합 합산 테스트")
    print("=" * 60)
    
    client = KISClient(auth)
    for acc in accounts:
        items = client.get_overseas_balance(account_idx=acc["idx"])
        print(f"\n📁 [{acc['name']}] 보유 종목: {len(items)}개")
        for it in items:
            print(f"   • {it['ticker']} ({it['name']}): {it['qty']}주 | 평단 ${it['avg_price']:,.2f} | 현재가 ${it['current_price']:,.2f} | 손익률 {it['profit_rate']:+.2f}%")

    # 전체 계좌 합산 포트폴리오
    if len(accounts) > 1:
        print("\n" + "-" * 50)
        print("🌟 [전체 계좌 통합 합산 포트폴리오]")
        print("-" * 50)
        comb = client.get_combined_balance()
        for it in comb:
            print(f"   • {it['ticker']} ({it['name']}): 총 {it['qty']}주 | 가중평균평단 ${it['avg_price']:,.2f} | 손익률 {it['profit_rate']:+.2f}% | 평가금액 ${it['eval_amount']:,.2f}")

    print("\n" + "=" * 60)
    print("🎉 다중 계좌 KIS API 연결 테스트 완료!")
    print("=" * 60)

if __name__ == "__main__":
    main()
