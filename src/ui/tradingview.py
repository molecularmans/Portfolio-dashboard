import json
import streamlit.components.v1 as components


def get_tradingview_symbol(ticker: str) -> str:
    """티커를 TradingView 형식의 심볼(거래소:티커)로 변환"""
    ticker_clean = ticker.strip().upper()

    # 한국 주식 (6자리 숫자)
    if ticker_clean.isdigit() and len(ticker_clean) == 6:
        return f"KRX:{ticker_clean}"

    # 뉴욕증권거래소(NYSE) 상장 주요 종목
    nyse_tickers = {
        "EME", "ORCL", "RTX", "STRL", "TSM", "PLTR", "BABA", "NIO", "SPOT",
        "UBER", "RBLX", "SNOW", "NET", "DIS", "KO", "PFE", "VST", "DE", "CAT",
        "IBM", "JPM", "V", "MA", "WMT", "UNH", "HD", "PG", "CVX", "XOM", "LLY"
    }
    if ticker_clean in nyse_tickers:
        return f"NYSE:{ticker_clean}"

    # 아멕스(AMEX) ETF
    amex_tickers = {"SPY", "IVV", "VOO", "DIA", "IWM", "QQQ"}
    if ticker_clean in amex_tickers:
        return f"AMEX:{ticker_clean}"

    # 기본 나스닥
    return f"NASDAQ:{ticker_clean}"


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
                "hide_side_toolbar": true, /* 미니 그리드에서는 측면 툴바 숨김 */
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
                "hide_side_toolbar": false, /* 추세선, 피보나치 등 좌측 풀 툴바 활성화 */
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
