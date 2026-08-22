import json
import streamlit.components.v1 as components


def get_tradingview_symbol(ticker: str) -> str:
    """티커를 TradingView 형식의 심볼(거래소:티커)로 변환"""
    ticker_clean = ticker.strip().upper()

    # 한국 주식 (6자리 숫자)
    if ticker_clean.isdigit() and len(ticker_clean) == 6:
        return f"KRX:{ticker_clean}"

    # 미국 주식 주요 거래소 매핑
    nyse_tickers = {"ORCL", "TSM", "BABA", "NIO", "PLTR", "SPOT", "UBER", "RBLX", "SNOW", "NET", "DIS", "KO", "PFE", "RTX", "VST", "EME"}
    if ticker_clean in nyse_tickers:
        return f"NYSE:{ticker_clean}"

    # 기본 나스닥
    return f"NASDAQ:{ticker_clean}"


def render_tradingview_chart(ticker: str, timeframe: str = "일봉", settings: dict = None, height: int = 750):
    """
    트레이딩뷰(TradingView) 공식 Advanced Real-Time Chart Widget 렌더링
    - 사이드바에서 선택한 이동평균선(5 EMA, 10, 20, 30, 50, 150, 200 MA) 및 보조지표(RSI, MACD, Stoch) 자동 탑재
    """
    if settings is None:
        settings = {}

    tv_symbol = get_tradingview_symbol(ticker)

    # 타임프레임 매핑 (D: 일, W: 주, M: 월)
    interval_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    interval = interval_map.get(timeframe, "D")

    # 기본 활성화할 studies 구성
    studies_list = []

    # 1. 이동평균선 (설정에 맞춰 추가)
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

    # 2. 보조지표
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
                "hide_side_toolbar": false, /* 좌측 정품 드로잉 툴바 활성화 */
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
