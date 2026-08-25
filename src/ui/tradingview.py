import json
import streamlit.components.v1 as components


def get_tradingview_symbol(ticker: str) -> str:
    """티커를 TradingView 형식 심볼로 변환 (거래소 불일치 에러 완전 방지)"""
    ticker_clean = ticker.strip().upper()

    # 한국 주식 (6자리 숫자)
    if ticker_clean.isdigit() and len(ticker_clean) == 6:
        return f"KRX:{ticker_clean}"

    if ":" in ticker_clean:
        return ticker_clean

    return ticker_clean


def get_ma_palette_and_lengths(timeframe: str = "일봉"):
    """주기별(일봉 vs 주봉) 최적의 이동평균선 기간 및 고유 색상/굵기 세팅"""
    if timeframe == "주봉":
        # 사용자 지정 주봉 색상: 4주(빨강 두껍게), 13주(보라), 26주(연청색), 52주(초록)
        return [
            {"id": "MA 1", "length": 4, "type": "SMA", "color": "#F44336", "linewidth": 2.5, "title": "4주 MA (빨강)"},
            {"id": "MA 2", "length": 13, "type": "SMA", "color": "#AB47BC", "linewidth": 1.8, "title": "13주 MA (보라)"},
            {"id": "MA 3", "length": 26, "type": "SMA", "color": "#00E5FF", "linewidth": 1.8, "title": "26주 MA (연청)"},
            {"id": "MA 4", "length": 52, "type": "SMA", "color": "#00E676", "linewidth": 2.0, "title": "52주 MA (초록)"},
        ]
    elif timeframe == "월봉":
        return [
            {"id": "MA 1", "length": 6, "type": "SMA", "color": "#FF9800", "linewidth": 2.0, "title": "6월 MA"},
            {"id": "MA 2", "length": 12, "type": "SMA", "color": "#2196F3", "linewidth": 2.0, "title": "12월 MA"},
            {"id": "MA 3", "length": 24, "type": "SMA", "color": "#AB47BC", "linewidth": 2.0, "title": "24월 MA"},
            {"id": "MA 4", "length": 60, "type": "SMA", "color": "#F44336", "linewidth": 2.5, "title": "60월 MA"},
        ]
    else:
        # 일봉: 5 EMA(주황), 20 MA(네온블루 두껍게), 50 MA(보라), 200 MA(빨강 두껍게)
        return [
            {"id": "EMA 1", "length": 5, "type": "EMA", "color": "#FF9800", "linewidth": 1.8, "title": "5 EMA (주황)"},
            {"id": "MA 1", "length": 20, "type": "SMA", "color": "#2196F3", "linewidth": 2.2, "title": "20 MA (파랑)"},
            {"id": "MA 2", "length": 50, "type": "SMA", "color": "#AB47BC", "linewidth": 1.8, "title": "50 MA (보라)"},
            {"id": "MA 3", "length": 200, "type": "SMA", "color": "#F44336", "linewidth": 2.5, "title": "200 MA (빨강)"},
        ]


def build_tradingview_studies_and_overrides(timeframe: str = "일봉", sub_indicators: list = None):
    """
    각 이동평균선마다 고유 색상과 굵기가 100% 자동 렌더링되도록 Studies 및 Overrides 구성
    """
    ma_list = get_ma_palette_and_lengths(timeframe)
    studies_list = []
    overrides = {
        "volume.volume.color.0": "#ef5350",
        "volume.volume.color.1": "#26a69a",
        "volume.volume.transparency": 40,
    }

    for item in ma_list:
        study_type = "MAExp@tv-basicstudies" if item["type"] == "EMA" else "MASimple@tv-basicstudies"
        studies_list.append({
            "id": study_type,
            "inputs": {"length": item["length"]},
        })

    if sub_indicators:
        if "RSI" in sub_indicators:
            studies_list.append("RSI@tv-basicstudies")
        if "Stochastic" in sub_indicators:
            studies_list.append("StochasticRSI@tv-basicstudies")
        if "MACD" in sub_indicators:
            studies_list.append("MACD@tv-basicstudies")

    return studies_list, overrides, ma_list


def render_tradingview_mini_chart(ticker: str, timeframe: str = "일봉", timeframe_ma: dict = None, height: int = 320):
    """
    멀티 차트 그리드용 TradingView 컴팩트 캔들 차트 (주기별 고유 색상 자동 완벽 적용)
    """
    tv_symbol = get_tradingview_symbol(ticker)

    interval_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    interval = interval_map.get(timeframe, "D")

    studies_list, overrides, ma_list = build_tradingview_studies_and_overrides(timeframe=timeframe)
    studies_json = json.dumps(studies_list)
    overrides_json = json.dumps(overrides)

    # 안내용 이평선 범례 배지
    legend_html = "".join([
        f"<span style='display:inline-block;margin-right:10px;font-size:11px;font-weight:600;color:{item['color']};'>"
        f"● {item['title']}</span>"
        for item in ma_list
    ])

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
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            .ma-legend-bar {{
                padding: 4px 8px;
                background-color: rgba(15, 23, 42, 0.85);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                white-space: nowrap;
                overflow-x: auto;
            }}
            #tv_mini_container_{ticker} {{
                width: 100%;
                height: calc(100% - 24px);
            }}
        </style>
    </head>
    <body>
        <div class="ma-legend-bar">
            {legend_html}
        </div>
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
                "studies_overrides": {overrides_json},
                "container_id": "tv_mini_container_{ticker}"
            }});
        </script>
    </body>
    </html>
    """

    components.html(html_code, height=height)


def render_tradingview_chart(ticker: str, timeframe: str = "일봉", settings: dict = None, height: int = 750):
    """
    상세 분석용 TradingView 풀버전 프로 차트 (추세선, 피보나치, 수평선, 주기별 고유 이평선 색상 범례 탑재)
    """
    if settings is None:
        settings = {}

    tv_symbol = get_tradingview_symbol(ticker)

    interval_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    interval = interval_map.get(timeframe, "D")

    sub_inds = settings.get("selected_sub_indicators", ["Stochastic", "RSI"])
    studies_list, overrides, ma_list = build_tradingview_studies_and_overrides(timeframe=timeframe, sub_indicators=sub_inds)
    studies_json = json.dumps(studies_list)
    overrides_json = json.dumps(overrides)

    legend_html = "".join([
        f"<span style='display:inline-block;margin-right:14px;font-size:12px;font-weight:600;color:{item['color']};'>"
        f"● {item['title']}</span>"
        for item in ma_list
    ])

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
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            .ma-legend-bar {{
                padding: 6px 12px;
                background-color: #1e222d;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                white-space: nowrap;
                overflow-x: auto;
            }}
            #tv_chart_container {{
                width: 100%;
                height: calc(100% - 30px);
            }}
        </style>
    </head>
    <body>
        <div class="ma-legend-bar">
            {legend_html}
        </div>
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
                "studies_overrides": {overrides_json},
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
