import json
import streamlit.components.v1 as components


def get_tradingview_symbol(ticker: str) -> str:
    """티커를 TradingView 형식 심볼로 변환 (거래소 불일치 에러 완전 방지)"""
    ticker_clean = ticker.strip().upper()

    # 한국 주식 (6자리 숫자)
    if ticker_clean.isdigit() and len(ticker_clean) == 6:
        return f"KRX:{ticker_clean}"

    # 이미 거래소 접두사가 붙어있는 경우
    if ":" in ticker_clean:
        return ticker_clean

    # 미국 주식은 순수 티커만 넘겨주면 TradingView 위젯이 NASDAQ, NYSE, AMEX를 전자동 매칭!
    return ticker_clean


def render_tradingview_mini_chart(ticker: str, timeframe: str = "일봉", height: int = 320):
    """
    멀티 차트 그리드(3열)용 TradingView 실시간 컴팩트 캔들 차트
    - 트레이딩뷰 공식 글로벌 실시간 데이터피드로 100% 정확한 캔들/종가 표시
    - 5 EMA, 20 MA, 50 MA, 200 MA 및 거래량 기본 탑재
    """
    tv_symbol = get_tradingview_symbol(ticker)

    interval_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    interval = interval_map.get(timeframe, "D")

    studies = [
        {"id": "MAExp@tv-basicstudies", "inputs": {"length": 5}},
        {"id": "MASimple@tv-basicstudies", "inputs": {"length": 20}},
        {"id": "MASimple@tv-basicstudies", "inputs": {"length": 50}},
        {"id": "MASimple@tv-basicstudies", "inputs": {"length": 200}},
    ]
    studies_json = json.dumps(studies)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                background-color: #0f172a;
                overflow: hidden;
                border-radius: 8px;
            }}
            #tv_mini_container_{ticker} {{
                width: 100%;
                height: 100%;
            }}
        </style>
    </head>
    <body>
        <div id="tv_mini_container_{ticker}"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
            new TradingView.widget({{
                "autosize": true,
                "symbol": "{tv_symbol}",
                "interval": "{interval}",
                "timezone": "Asia/Seoul",
                "theme": "dark",
                "style": "1",
                "locale": "kr",
                "toolbar_bg": "#0f172a",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "hide_side_toolbar": true,
                "allow_symbol_change": false,
                "save_image": false,
                "studies": {studies_json},
                "container_id": "tv_mini_container_{ticker}"
            }});
        </script>
    </body>
    </html>
    """

    components.html(html_code, height=height)


def render_tradingview_chart(ticker: str, timeframe: str = "일봉", settings: dict = None, height: int = 750):
    """
    상세 분석용 TradingView 풀버전 프로 차트 (추세선, 피보나치, 수평선, 플로팅 도구 풀탑재)
    """
    if settings is None:
        settings = {}

    tv_symbol = get_tradingview_symbol(ticker)

    interval_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    interval = interval_map.get(timeframe, "D")

    studies_list = []
    if settings.get("show_ema5", True):
        studies_list.append({"id": "MAExp@tv-basicstudies", "inputs": {"length": 5}})
    if settings.get("show_ma20", True):
        studies_list.append({"id": "MASimple@tv-basicstudies", "inputs": {"length": 20}})
    if settings.get("show_ma50", True):
        studies_list.append({"id": "MASimple@tv-basicstudies", "inputs": {"length": 50}})
    if settings.get("show_ma200", True):
        studies_list.append({"id": "MASimple@tv-basicstudies", "inputs": {"length": 200}})
    if settings.get("show_ma10", False):
        studies_list.append({"id": "MASimple@tv-basicstudies", "inputs": {"length": 10}})
    if settings.get("show_ma30", False):
        studies_list.append({"id": "MASimple@tv-basicstudies", "inputs": {"length": 30}})
    if settings.get("show_ma150", False):
        studies_list.append({"id": "MASimple@tv-basicstudies", "inputs": {"length": 150}})

    sub_inds = settings.get("selected_sub_indicators", ["Stochastic", "RSI"])
    if "RSI" in sub_inds:
        studies_list.append("RSI@tv-basicstudies")
    if "Stochastic" in sub_inds:
        studies_list.append("StochasticRSI@tv-basicstudies")
    if "MACD" in sub_inds:
        studies_list.append("MACD@tv-basicstudies")

    studies_json = json.dumps(studies_list)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                background-color: #131722;
                overflow: hidden;
            }}
            #tv_chart_container {{
                width: 100%;
                height: 100%;
            }}
        </style>
    </head>
    <body>
        <div id="tv_chart_container"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
            new TradingView.widget({{
                "autosize": true,
                "symbol": "{tv_symbol}",
                "interval": "{interval}",
                "timezone": "Asia/Seoul",
                "theme": "dark",
                "style": "1",
                "locale": "kr",
                "toolbar_bg": "#1e222d",
                "enable_publishing": false,
                "allow_symbol_change": true,
                "hide_side_toolbar": false,
                "withdateranges": true,
                "save_image": true,
                "studies": {studies_json},
                "container_id": "tv_chart_container",
                "show_popup_button": true,
                "popup_width": "1000",
                "popup_height": "650"
            }});
        </script>
    </body>
    </html>
    """

    components.html(html_code, height=height)
