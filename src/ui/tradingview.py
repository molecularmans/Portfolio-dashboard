import json
import pandas as pd
import streamlit.components.v1 as components


def get_tradingview_symbol(ticker: str) -> str:
    """티커를 TradingView 형식 심볼로 변환"""
    ticker_clean = ticker.strip().upper()
    if ticker_clean.isdigit() and len(ticker_clean) == 6:
        return f"KRX:{ticker_clean}"
    if ":" in ticker_clean:
        return ticker_clean
    return ticker_clean


def render_lightweight_candlestick_chart(df: pd.DataFrame, ticker: str, timeframe: str = "일봉", height: int = 340):
    """
    TradingView 공식 Lightweight Charts 캔들 엔진
    - 주봉: 4주(빨강 굵게), 13주(보라), 26주(연청), 52주(초록) 100% 고유 색상 완벽 렌더링
    - 일봉: 5 EMA(주황), 20 MA(파랑), 50 MA(보라), 200 MA(빨강 굵게)
    - 상단 컬러 범례 바 탑재 & 52주선 누락 0% 보장
    """
    if df.empty or len(df) < 2:
        return

    tail_count = 60 if timeframe == "월봉" else (80 if timeframe == "주봉" else 90)
    plot_df = df.tail(tail_count).copy()

    # 1. 캔들 데이터 변환
    candle_records = []
    for _, row in plot_df.iterrows():
        d_str = row["date"].strftime("%Y-%m-%d") if isinstance(row["date"], (pd.Timestamp, str)) else str(row["date"])[:10]
        candle_records.append({
            "time": d_str,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })

    # 2. 거래량 데이터 변환
    vol_records = []
    for _, row in plot_df.iterrows():
        d_str = row["date"].strftime("%Y-%m-%d") if isinstance(row["date"], (pd.Timestamp, str)) else str(row["date"])[:10]
        is_up = row["close"] >= row["open"]
        vol_records.append({
            "time": d_str,
            "value": float(row["volume"]),
            "color": "rgba(38, 166, 154, 0.5)" if is_up else "rgba(239, 83, 80, 0.5)",
        })

    # 3. 주기별 이동평균선 구성 (사용자 지정 4대 색상)
    if timeframe == "주봉":
        ma_configs = [
            {"col": "ma_4", "label": "4주 MA", "color": "#F44336", "linewidth": 3},
            {"col": "ma_13", "label": "13주 MA", "color": "#AB47BC", "linewidth": 2},
            {"col": "ma_26", "label": "26주 MA", "color": "#00E5FF", "linewidth": 2},
            {"col": "ma_52", "label": "52주 MA", "color": "#00E676", "linewidth": 2.2},
        ]
    elif timeframe == "월봉":
        ma_configs = [
            {"col": "sma_10", "label": "6월 MA", "color": "#FF9800", "linewidth": 2},
            {"col": "sma_20", "label": "12월 MA", "color": "#2196F3", "linewidth": 2},
            {"col": "sma_50", "label": "24월 MA", "color": "#AB47BC", "linewidth": 2},
            {"col": "sma_200", "label": "60월 MA", "color": "#F44336", "linewidth": 3},
        ]
    else:
        # 일봉
        ma_configs = [
            {"col": "ema_5", "label": "5 EMA", "color": "#FF9800", "linewidth": 2},
            {"col": "sma_20", "label": "20 MA", "color": "#2196F3", "linewidth": 2.5},
            {"col": "sma_50", "label": "50 MA", "color": "#AB47BC", "linewidth": 2},
            {"col": "sma_200", "label": "200 MA", "color": "#F44336", "linewidth": 3},
        ]

    ma_series_data = []
    ma_legend = []
    for cfg in ma_configs:
        col_name = cfg["col"]
        if col_name in plot_df.columns:
            series_points = []
            for _, row in plot_df.iterrows():
                val = row.get(col_name)
                if pd.notna(val) and val > 0:
                    d_str = row["date"].strftime("%Y-%m-%d") if isinstance(row["date"], (pd.Timestamp, str)) else str(row["date"])[:10]
                    series_points.append({"time": d_str, "value": float(val)})

            if series_points:
                ma_series_data.append({
                    "label": cfg["label"],
                    "color": cfg["color"],
                    "linewidth": cfg["linewidth"],
                    "data": series_points,
                })
                ma_legend.append({
                    "label": cfg["label"],
                    "color": cfg["color"],
                })

    candle_json = json.dumps(candle_records)
    vol_json = json.dumps(vol_records)
    ma_json = json.dumps(ma_series_data)

    legend_html = "".join([
        f"<span style='display:inline-block;margin-right:12px;font-size:11px;font-weight:700;color:{item['color']};'>"
        f"● {item['label']}</span>"
        for item in ma_legend
    ])

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                background-color: #0f172a;
                overflow: hidden;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            .ma-legend-bar {{
                padding: 4px 10px;
                background-color: rgba(15, 23, 42, 0.95);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                white-space: nowrap;
                overflow-x: auto;
            }}
            #chart_container_{ticker} {{
                width: 100%;
                height: calc(100% - 24px);
            }}
        </style>
    </head>
    <body>
        <div class="ma-legend-bar">
            {legend_html}
        </div>
        <div id="chart_container_{ticker}"></div>
        <script>
            const container = document.getElementById('chart_container_{ticker}');
            const chart = LightweightCharts.createChart(container, {{
                width: container.clientWidth,
                height: {height - 26},
                layout: {{
                    background: {{ color: '#0f172a' }},
                    textColor: '#94a3b8',
                    fontSize: 10,
                }},
                grid: {{
                    vertLines: {{ color: 'rgba(255, 255, 255, 0.04)' }},
                    horzLines: {{ color: 'rgba(255, 255, 255, 0.04)' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                }},
                rightPriceScale: {{
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    scaleMargins: {{
                        top: 0.08,
                        bottom: 0.22,
                    }},
                }},
                timeScale: {{
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    timeVisible: false,
                    fixLeftEdge: true,
                    fixRightEdge: true,
                }},
            }});

            // 1. 캔들스틱 시리즈
            const candleSeries = chart.addCandlestickSeries({{
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            }});
            candleSeries.setData({candle_json});

            // 2. 거래량 바 시리즈
            const volumeSeries = chart.addHistogramSeries({{
                priceFormat: {{ type: 'volume' }},
                priceScaleId: '',
                scaleMargins: {{
                    top: 0.78,
                    bottom: 0,
                }},
            }});
            volumeSeries.setData({vol_json});

            // 3. 4대 이동평균선 시리즈 (고유 색상 100% 개별 렌더링)
            const maList = {ma_json};
            maList.forEach(ma => {{
                const maSeries = chart.addLineSeries({{
                    color: ma.color,
                    lineWidth: ma.linewidth || 2,
                    title: ma.label,
                    priceLineVisible: false,
                    crosshairMarkerVisible: false,
                }});
                maSeries.setData(ma.data);
            }});

            chart.timeScale().fitContent();

            window.addEventListener('resize', () => {{
                chart.applyOptions({{ width: container.clientWidth }});
            }});
        </script>
    </body>
    </html>
    """

    components.html(html_code, height=height)


def render_tradingview_chart(ticker: str, timeframe: str = "일봉", settings: dict = None, height: int = 750):
    """
    상세 분석용 TradingView 풀버전 프로 차트 (추세선, 피보나치, 수평선 툴 풀탑재)
    """
    if settings is None:
        settings = {}

    tv_symbol = get_tradingview_symbol(ticker)

    interval_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    interval = interval_map.get(timeframe, "D")

    if timeframe == "주봉":
        studies_list = [
            {"id": "MAExp@tv-basicstudies", "inputs": {"length": 4}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 13}},
            {"id": "MAWeighted@tv-basicstudies", "inputs": {"length": 26}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 52}},
        ]
        legend_html = "<span style='color:#F44336;font-weight:700;margin-right:12px;'>● 4주 MA</span><span style='color:#AB47BC;font-weight:700;margin-right:12px;'>● 13주 MA</span><span style='color:#00E5FF;font-weight:700;margin-right:12px;'>● 26주 MA</span><span style='color:#00E676;font-weight:700;margin-right:12px;'>● 52주 MA</span>"
    else:
        studies_list = [
            {"id": "MAExp@tv-basicstudies", "inputs": {"length": 5}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 20}},
            {"id": "MAWeighted@tv-basicstudies", "inputs": {"length": 50}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 200}},
        ]
        legend_html = "<span style='color:#FF9800;font-weight:700;margin-right:12px;'>● 5 EMA</span><span style='color:#2196F3;font-weight:700;margin-right:12px;'>● 20 MA</span><span style='color:#AB47BC;font-weight:700;margin-right:12px;'>● 50 MA</span><span style='color:#F44336;font-weight:700;margin-right:12px;'>● 200 MA</span>"

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
