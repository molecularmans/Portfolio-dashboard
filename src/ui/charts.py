import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


# Plotly 모드바 설정
CHART_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
    ],
    "modeBarButtonsToAdd": [
        "zoom2d",
        "pan2d",
        "zoomIn2d",
        "zoomOut2d",
        "resetScale2d",
        "autoScale2d",
    ],
}

# 이동평균선 색상 맵
MA_COLOR_MAP = {
    "ema_5": ("5 EMA", "#FF9800", 1.2),
    "sma_10": ("10 MA", "#FFEB3B", 1.2),
    "sma_20": ("20 MA", "#2196F3", 1.5),
    "sma_30": ("30 MA", "#00E676", 1.4),
    "sma_50": ("50 MA", "#9C27B0", 1.5),
    "sma_150": ("150 MA", "#E91E63", 1.7),
    "sma_200": ("200 MA", "#F44336", 1.8),
}


def add_moving_averages_to_fig(fig, df: pd.DataFrame, settings: dict, row: int = 1, col: int = 1, show_legend: bool = True):
    """설정에 따라 활성화된 이동평균선들을 차트에 추가"""
    ma_keys = [
        ("show_ema5", "ema_5"),
        ("show_ma10", "sma_10"),
        ("show_ma20", "sma_20"),
        ("show_ma30", "sma_30"),
        ("show_ma50", "sma_50"),
        ("show_ma150", "sma_150"),
        ("show_ma200", "sma_200"),
    ]

    for setting_key, col_name in ma_keys:
        if settings.get(setting_key, True) and col_name in df.columns:
            name, color, width = MA_COLOR_MAP[col_name]
            fig.add_trace(
                go.Scatter(
                    x=df["date"],
                    y=df[col_name],
                    mode="lines",
                    name=name,
                    line=dict(color=color, width=width),
                    showlegend=show_legend,
                ),
                row=row,
                col=col,
            )


def create_mini_chart(df: pd.DataFrame, ticker: str, settings: dict = None) -> go.Figure:
    """멀티 차트 그리드용 컴팩트 캔들스틱 + 이평선 + 거래량 서브플롯 차트"""
    if settings is None:
        settings = {}

    tf = settings.get("timeframe", "일봉")
    tail_count = 50 if tf == "월봉" else (65 if tf == "주봉" else 75)
    plot_df = df.tail(tail_count).copy()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )

    # 1. 캔들스틱
    fig.add_trace(
        go.Candlestick(
            x=plot_df["date"],
            open=plot_df["open"],
            high=plot_df["high"],
            low=plot_df["low"],
            close=plot_df["close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    # 2. 이동평균선 추가
    add_moving_averages_to_fig(fig, plot_df, settings, row=1, col=1, show_legend=False)

    # 3. 거래량 바
    colors = ["#26a69a" if c >= o else "#ef5350" for c, o in zip(plot_df["close"], plot_df["open"])]
    fig.add_trace(
        go.Bar(
            x=plot_df["date"],
            y=plot_df["volume"],
            marker_color=colors,
            opacity=0.65,
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        height=260,
        margin=dict(l=5, r=5, t=5, b=5),
        xaxis=dict(type="category", rangeslider=dict(visible=False), showgrid=False, showticklabels=False),
        xaxis2=dict(type="category", showgrid=False, tickfont=dict(size=8, color="#888888"), nticks=4),
        yaxis=dict(side="right", showgrid=True, gridcolor="rgba(128,128,128,0.15)", tickfont=dict(size=8, color="#888888")),
        yaxis2=dict(side="right", showgrid=False, showticklabels=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        dragmode="pan",
    )

    return fig


def create_detail_chart(df: pd.DataFrame, ticker: str, settings: dict = None, trendlines: list = None, selected_line_id: str = None) -> go.Figure:
    """
    대형 인터랙티브 차트 (대각선 추세선 및 수평선 100% 확실한 렌더링 & 하이라이트)
    """
    if settings is None:
        settings = {}

    tf = settings.get("timeframe", "일봉")
    tail_count = 100 if tf == "월봉" else (160 if tf == "주봉" else 200)
    plot_df = df.tail(tail_count).copy()
    sub_indicators = settings.get("selected_sub_indicators", ["Stochastic", "RSI"])
    mouse_mode = settings.get("mouse_mode", "pan")  # 'pan' or 'drawline'

    num_subs = len(sub_indicators)
    total_rows = 2 + num_subs

    if num_subs == 0:
        row_heights = [0.75, 0.25]
        subplot_titles = [f"{ticker} ({tf}) OHLCV & Trendlines", "Volume & RVOL"]
    else:
        sub_ratio = 0.40 / num_subs
        row_heights = [0.45, 0.15] + [sub_ratio] * num_subs
        subplot_titles = [f"{ticker} ({tf}) OHLCV & Trendlines", "Volume & RVOL"] + [f"{ind} Indicator" for ind in sub_indicators]

    total_height = max(720, 500 + (num_subs * 140))

    fig = make_subplots(
        rows=total_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )

    # 1. 캔들스틱 (Row 1)
    fig.add_trace(
        go.Candlestick(
            x=plot_df["date"],
            open=plot_df["open"],
            high=plot_df["high"],
            low=plot_df["low"],
            close=plot_df["close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1,
        col=1,
    )

    # 이동평균선 추가 (Row 1)
    add_moving_averages_to_fig(fig, plot_df, settings, row=1, col=1, show_legend=True)

    # 2. 영구 저장된 추세선 및 지지/저항선 오버레이 (Row 1)
    if trendlines:
        for tl in trendlines:
            line_id = tl.get("id")
            is_selected = (line_id == selected_line_id)
            
            base_color = tl.get("color", "#FFD700")
            line_color = "#00E5FF" if is_selected else base_color
            line_width = 3.5 if is_selected else 2.0
            label_text = tl.get("label", "추세선")
            badge = " [선택됨 🎯]" if is_selected else ""

            # 1) 수평 지지/저항선
            if tl.get("line_type") == "horizontal":
                p = tl.get("price1")
                if p is not None:
                    fig.add_hline(
                        y=p,
                        line_dash="solid" if is_selected else "dash",
                        line_color=line_color,
                        line_width=line_width,
                        annotation_text=f" {label_text}: ${p:,.2f}{badge}",
                        annotation_position="top right",
                        annotation_font_color=line_color,
                        annotation_font_size=12 if is_selected else 10,
                        row=1,
                        col=1,
                    )

            # 2) 대각선 추세선 (Scatter Line Trace로 확실하고 선명하게 렌더링)
            elif tl.get("line_type") == "trendline":
                d1, p1 = tl.get("date1"), tl.get("price1")
                d2, p2 = tl.get("date2"), tl.get("price2")
                if d1 and p1 is not None and d2 and p2 is not None:
                    fig.add_trace(
                        go.Scatter(
                            x=[d1, d2],
                            y=[p1, p2],
                            mode="lines+markers",
                            name=f"{label_text}{badge}",
                            line=dict(color=line_color, width=line_width, dash="solid" if is_selected else "dash"),
                            marker=dict(size=6, color=line_color),
                            hoverinfo="name+y",
                            showlegend=False,
                        ),
                        row=1,
                        col=1,
                    )

    # 3. 거래량 & 20일 거래량선 (Row 2)
    colors = ["#26a69a" if c >= o else "#ef5350" for c, o in zip(plot_df["close"], plot_df["open"])]
    fig.add_trace(
        go.Bar(
            x=plot_df["date"],
            y=plot_df["volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.75,
        ),
        row=2,
        col=1,
    )
    if "vol_ma20" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df["date"], y=plot_df["vol_ma20"], mode="lines", name="Vol MA20", line=dict(color="#FFC107", width=1.3)),
            row=2,
            col=1,
        )

    # 4. 보조지표들 동시 렌더링 (Row 3 ~ Row N)
    current_row = 3
    for ind in sub_indicators:
        if ind == "Stochastic" and "stoch_k" in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df["date"], y=plot_df["stoch_k"], mode="lines", name="Stoch %K", line=dict(color="#00BCD4", width=1.5)), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=plot_df["date"], y=plot_df["stoch_d"], mode="lines", name="Stoch %D", line=dict(color="#FF4081", width=1.5)), row=current_row, col=1)
            fig.add_hline(y=80, line_dash="dot", line_color="rgba(255,255,255,0.3)", row=current_row, col=1)
            fig.add_hline(y=20, line_dash="dot", line_color="rgba(255,255,255,0.3)", row=current_row, col=1)

        elif ind == "Williams %R" and "williams_r" in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df["date"], y=plot_df["williams_r"], mode="lines", name="Williams %R", line=dict(color="#AB47BC", width=1.5)), row=current_row, col=1)
            fig.add_hline(y=-20, line_dash="dot", line_color="rgba(255,255,255,0.3)", row=current_row, col=1)
            fig.add_hline(y=-80, line_dash="dot", line_color="rgba(255,255,255,0.3)", row=current_row, col=1)

        elif ind == "RSI" and "rsi_14" in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df["date"], y=plot_df["rsi_14"], mode="lines", name="RSI (14)", line=dict(color="#4CAF50", width=1.5)), row=current_row, col=1)
            fig.add_hline(y=70, line_dash="dot", line_color="rgba(255,255,255,0.3)", row=current_row, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="rgba(255,255,255,0.3)", row=current_row, col=1)

        elif ind == "MACD" and "macd_line" in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df["date"], y=plot_df["macd_line"], mode="lines", name="MACD", line=dict(color="#29B6F6", width=1.5)), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=plot_df["date"], y=plot_df["macd_signal"], mode="lines", name="Signal", line=dict(color="#FFA726", width=1.5)), row=current_row, col=1)
            hist_colors = ["#26a69a" if h >= 0 else "#ef5350" for h in plot_df["macd_hist"]]
            fig.add_trace(go.Bar(x=plot_df["date"], y=plot_df["macd_hist"], name="Histogram", marker_color=hist_colors, opacity=0.6), row=current_row, col=1)

        current_row += 1

    fig.update_layout(
        height=total_height,
        margin=dict(l=20, r=20, t=40, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        dragmode=mouse_mode,  # 사용자가 선택한 모드 (pan 또는 drawline)
    )

    for i in range(1, total_rows + 1):
        axis_name = "xaxis" if i == 1 else f"xaxis{i}"
        fig.update_layout({axis_name: dict(type="category", rangeslider=dict(visible=False))})

    fig.update_yaxes(side="right", gridcolor="rgba(128,128,128,0.15)")

    return fig
