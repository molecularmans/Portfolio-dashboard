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


def build_tradingview_studies_and_overrides(timeframe: str = "일봉", sub_indicators: list = None):
    """
    트레이딩뷰 엔진에서 4대 이평선이 각각 독립된 고유 색상(빨강, 보라, 연청, 초록)으로 100% 렌더링되도록
    서로 다른 Study ID와 1:1 studies_overrides 매핑 적용
    """
    if timeframe == "주봉":
        # 주봉 4대 이평선: 4주(빨강 두껍게), 13주(보라), 26주(연청), 52주(초록)
        studies_list = [
            {"id": "MAExp@tv-basicstudies", "inputs": {"length": 4}},       # 4주 (EMA 기반)
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 13}},    # 13주 (SMA)
            {"id": "MAWeighted@tv-basicstudies", "inputs": {"length": 26}},  # 26주 (WMA)
            {"id": "MASmoothed@tv-basicstudies", "inputs": {"length": 52}},  # 52주 (SMMA)
        ]
        overrides = {
            "volume.volume.color.0": "#ef5350",
            "volume.volume.color.1": "#26a69a",
            "volume.volume.transparency": 40,
            # 4주선: 빨간색 (약간 두껍게)
            "moving average exponential.plot.color": "#F44336",
            "moving average exponential.plot.linewidth": 3,
            # 13주선: 보라색
            "moving average.plot.color": "#AB47BC",
            "moving average.plot.linewidth": 2,
            # 26주선: 연청색 (Sky Blue)
            "moving average weighted.plot.color": "#00E5FF",
            "moving average weighted.plot.linewidth": 2,
            # 52주선: 초록색
            "moving average smoothed.plot.color": "#00E676",
            "moving average smoothed.plot.linewidth": 2,
        }
        ma_legend = [
            {"title": "4주 MA (빨강)", "color": "#F44336"},
            {"title": "13주 MA (보라)", "color": "#AB47BC"},
            {"title": "26주 MA (연청)", "color": "#00E5FF"},
            {"title": "52주 MA (초록)", "color": "#00E676"},
        ]
    elif timeframe == "월봉":
        studies_list = [
            {"id": "MAExp@tv-basicstudies", "inputs": {"length": 6}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 12}},
            {"id": "MAWeighted@tv-basicstudies", "inputs": {"length": 24}},
            {"id": "MASmoothed@tv-basicstudies", "inputs": {"length": 60}},
        ]
        overrides = {
            "volume.volume.color.0": "#ef5350",
            "volume.volume.color.1": "#26a69a",
            "moving average exponential.plot.color": "#FF9800",
            "moving average.plot.color": "#2196F3",
            "moving average weighted.plot.color": "#AB47BC",
            "moving average smoothed.plot.color": "#F44336",
        }
        ma_legend = [
            {"title": "6월 MA (주황)", "color": "#FF9800"},
            {"title": "12월 MA (파랑)", "color": "#2196F3"},
            {"title": "24월 MA (보라)", "color": "#AB47BC"},
            {"title": "60월 MA (빨강)", "color": "#F44336"},
        ]
    else:
        # 일봉: 5 EMA(주황), 20 MA(파랑), 50 MA(보라), 200 MA(빨강)
        studies_list = [
            {"id": "MAExp@tv-basicstudies", "inputs": {"length": 5}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 20}},
            {"id": "MAWeighted@tv-basicstudies", "inputs": {"length": 50}},
            {"id": "MASmoothed@tv-basicstudies", "inputs": {"length": 200}},
        ]
        overrides = {
            "volume.volume.color.0": "#ef5350",
            "volume.volume.color.1": "#26a69a",
            "volume.volume.transparency": 40,
            "moving average exponential.plot.color": "#FF9800",
            "moving average exponential.plot.linewidth": 2,
            "moving average.plot.color": "#2196F3",
            "moving average.plot.linewidth": 2,
            "moving average weighted.plot.color": "#AB47BC",
            "moving average weighted.plot.linewidth": 2,
            "moving average smoothed.plot.color": "#F44336",
            "moving average smoothed.plot.linewidth": 3,
        }
        ma_legend = [
            {"title": "5 EMA (주황)", "color": "#FF9800"},
            {"title": "20 MA (파랑)", "color": "#2196F3"},
            {"title": "50 MA (보라)", "color": "#AB47BC"},
            {"title": "200 MA (빨강)", "color": "#F44336"},
        ]

    if sub_indicators:
        if "RSI" in sub_indicators:
            studies_list.append("RSI@tv-basicstudies")
        if "Stochastic" in sub_indicators:
            studies_list.append("StochasticRSI@tv-basicstudies")
        if "MACD" in sub_indicators:
            studies_list.append("MACD@tv-basicstudies")

    return studies_list, overrides, ma_legend


def render_tradingview_mini_chart(ticker: str, timeframe: str = "일봉", timeframe_ma: dict = None, height: int = 320):
    """
    멀티 차트 그리드용 TradingView 컴팩트 캔들 차트 (주기별 4대 고유 색상 100% 개별 렌더링)
    """
    tv_symbol = get_tradingview_symbol(ticker)

    interval_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    interval = interval_map.get(timeframe, "D")

    studies_list, overrides, ma_legend = build_tradingview_studies_and_overrides(timeframe=timeframe)
    studies_json = json.dumps(studies_list)
    overrides_json = json.dumps(overrides)

    legend_html = "".join([
        f"<span style='display:inline-block;margin-right:10px;font-size:11px;font-weight:600;color:{item['color']};'>"
        f"● {item['title']}</span>"
        for item in ma_legend
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
    상세 분석용 TradingView 풀버전 프로 차트 (주기별 4대 고유 색상 100% 개별 렌더링)
    """
    if settings is None:
        settings = {}

    tv_symbol = get_tradingview_symbol(ticker)

    interval_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    interval = interval_map.get(timeframe, "D")

    sub_inds = settings.get("selected_sub_indicators", ["Stochastic", "RSI"])
    studies_list, overrides, ma_legend = build_tradingview_studies_and_overrides(timeframe=timeframe, sub_indicators=sub_inds)
    studies_json = json.dumps(studies_list)
    overrides_json = json.dumps(overrides)

    legend_html = "".join([
        f"<span style='display:inline-block;margin-right:14px;font-size:12px;font-weight:600;color:{item['color']};'>"
        f"● {item['title']}</span>"
        for item in ma_legend
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
